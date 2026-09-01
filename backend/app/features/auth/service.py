"""Правила входа."""

import asyncio
import logging
import math
import time
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ENV_FILE, settings
from app.core.errors import RuleViolation
from app.core.rate_limit import address_limiter, login_limiter
from app.core.security import hash_password, sign_session_token, verify_password
from app.core.users import Login, User, UserStatus
from app.domain.roles import Role

logger = logging.getLogger(__name__)

# Один и тот же текст на любой отказ: разные сообщения подсказывают, какие
# логины существуют.
DENIED = "Неверный логин или пароль"
TOO_MANY = "Слишком много попыток. Попробуй через {minutes} мин"
# Нижняя граница времени ответа. Без неё отказ по несуществующему логину
# возвращается заметно быстрее, чем по неверному паролю: scrypt считается
# только во втором случае, и по времени ответа логины перебираются.
#
# Граница выравнивает ветки, только пока настоящая работа в неё
# укладывается. scrypt занимает около 25 мс, под нагрузкой в пуле потоков
# — до 60 мс, запас четырёхкратный. Если он однажды исчерпается, различие
# вернётся молча, поэтому превышение пишется в лог — см.
# _check_verification_time.
MIN_RESPONSE_SECONDS = 0.25

# Не чаще одной строки в минуту. Если scrypt действительно перестал
# укладываться в границу, это верно для каждого входа, и без задвижки один
# POST даёт одну строку WARNING в `<слаг>-logs` — единственный
# диагностический канал контура. Сигнал должен быть заметен, а не утопить
# собой всё остальное.
ALARM_QUIET_SECONDS = 60.0
_alarm_last_at: float | None = None


def _check_verification_time(elapsed: float) -> None:
    """Сообщает, что граница перестала прикрывать разницу веток.

    Меряется ТОЛЬКО проверка пароля, а не время ответа целиком. Полное время
    для этого не годится: в него входит ожидание соединения в пуле и очередь
    в цикле событий — одинаковые для обеих веток и потому никакого различия
    по времени не создающие. Замерено дважды. По полному времени: сорок
    одновременных отказов по несуществующему логину давали 30 предупреждений,
    хотя scrypt в этих запросах не вызывался вовсе; после возврата соединения
    в пул (см. finish) этот случай исчез, но сто одновременных отказов с
    проверкой пароля дали 38 предупреждений — там время уходило на ожидание
    соединения. По времени самой проверки в тех же прогонах — ни одного.
    Ложные срабатывания хуже молчания: их перестанут читать ровно до того,
    как сигнал понадобится.

    scrypt — единственная работа, которая есть в одной ветке и которой нет в
    другой, то есть единственный источник различия по времени. Как только он
    один перестаёт умещаться в границу, оракул возвращается.
    """
    global _alarm_last_at
    if elapsed <= MIN_RESPONSE_SECONDS:
        return
    now = time.monotonic()
    if _alarm_last_at is not None and now - _alarm_last_at < ALARM_QUIET_SECONDS:
        return
    _alarm_last_at = now
    logger.warning(
        "проверка пароля заняла %.0f мс при границе %.0f мс: выравнивание "
        "времени ответа больше не скрывает разницу веток",
        elapsed * 1000,
        MIN_RESPONSE_SECONDS * 1000,
    )


async def authenticate(
    session: AsyncSession, login: str, password: str, client_ip: str
) -> str:
    """Проверяет пару и возвращает токен сессии. Отказ — RuleViolation."""
    started = time.monotonic()

    async def finish() -> None:
        # Соединение возвращается в пул ДО сна. Иначе один дешёвый
        # неаутентифицированный POST держит одно из десяти соединений
        # (pool_size=5 плюс overflow=5) целую четверть секунды. Замерено на
        # прежнем варианте: сорок одновременных отказов занимали весь пул
        # (10 из 10 занято), и посторонний `select 1` шёл 211 мс вместо 0,7
        # мс — то есть форма входа без единого верного пароля укладывала все
        # прочие маршруты, а дальше начинался pool_timeout.
        #
        # Именно rollback, а не close. close вдобавок отсоединяет объекты от
        # сессии (expunge), а сессия здесь общая с вызывающим: в обвязке
        # тестов она одна на весь тест, и отсоединённого пользователя уже не
        # сохранить. rollback объекты только гасит (expire) — они
        # перечитаются при следующем обращении.
        #
        # На успешном пути и на пути «слишком много попыток» вызов бесплатен:
        # транзакции там нет — её закрыл commit или она не начиналась.
        await session.rollback()
        remaining = MIN_RESPONSE_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)

    # Два ограничителя с разными порогами: по логину строго, по адресу
    # мягко. Общий порог на адрес оставлял бы без входа весь офис за одним
    # NAT из-за пяти чужих опечаток.
    wait = max(login_limiter.retry_after(login), address_limiter.retry_after(client_ip))
    if wait > 0:
        await finish()
        raise RuleViolation(TOO_MANY.format(minutes=math.ceil(wait / 60)))

    # Бюджет занимается ДО дорогой проверки, а не после неё. Между
    # retry_after и register_failure стоит await на scrypt, и за это время
    # цикл событий успевает пропустить в ворота все ждущие запросы: сорок
    # одновременных попыток дают сорок проверок пароля при пределе пять.
    # Замерено ревью. Успешный вход счётчик обнуляет, так что честного
    # пользователя это не задевает.
    login_limiter.register_failure(login)
    address_limiter.register_failure(client_ip)

    user = (
        await session.execute(select(User).where(User.login == login))
    ).scalar_one_or_none()

    ok = False
    if (
        user is not None
        and user.status is UserStatus.active
        and user.password_hash is not None
    ):
        # verify_password уходит в пул потоков намеренно. Один вызов scrypt
        # занимает около 25 мс сплошного счёта, и вызванный напрямую он
        # блокирует цикл событий целиком: замеряно — восемь проверок подряд
        # держат цикл 195 мс, за которые он не проворачивается ни разу, то
        # есть встают и все прочие запросы, включая проверку живости. Через
        # пул те же восемь занимают 42 мс и цикл остаётся живым.
        #
        # Соединение на время этой проверки остаётся занятым: SELECT уже
        # сделан, транзакция ещё открыта. Это настоящая работа (25–60 мс), а
        # не сон, и убрать её из-под соединения можно только сняв нужные поля
        # в локальные переменные и откатив сессию до scrypt — но тогда объект
        # пользователя гаснет, и отметку last_login_at пришлось бы писать
        # отдельным UPDATE. Замерено, во что обходится: сто одновременных
        # отказов с проверкой пароля задерживают посторонний `select 1` на
        # 314 мс. Столько одновременных попыток внутреннее приложение на
        # десятки человек не увидит — счётчики пускают 5 на логин и 30 на
        # адрес за 15 минут, — поэтому размен не сделан. Понадобится он на
        # нагруженном контуре, и тогда причина уже написана.
        verification_started = time.monotonic()
        ok = await asyncio.to_thread(verify_password, password, user.password_hash)
        _check_verification_time(time.monotonic() - verification_started)

    if not ok or user is None:
        await finish()
        raise RuleViolation(DENIED)

    login_limiter.reset(login)
    address_limiter.reset(client_ip)
    issued_at_ms = int(datetime.now(UTC).timestamp() * 1000)
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await finish()
    return sign_session_token(user.login, issued_at_ms, settings.app_auth_secret)


# Тот же тип, что проверяет логин из формы. Не копия правила: две записи
# одного инварианта однажды разъезжаются — см. bootstrap_login.
_LOGIN = TypeAdapter(Login)


def bootstrap_login() -> str:
    """APP_BOOTSTRAP_LOGIN, приведённый ровно тем же правилом, что и форма.

    Здесь стоял рукописный `strip().lower()`, и он расходился с типом
    дважды. `Админ Один` ложился в базу как «админ один», а форма такой ввод
    не пропускает вовсе (`^\\S+$`) — войти было невозможно никогда.
    `\\x1cadmin` ложился как «admin», а форма отдаёт «\\x1cadmin»: питоновский
    str.strip() режет U+001C, а strip у pydantic (по Unicode White_Space) —
    нет. Оба случая воспроизведены.

    Отказ при этом самозапечатывающийся: запись создана, таблица больше не
    пуста, ensure_bootstrap_user второй раз не сработает — и контур остаётся
    без единого входа, без пути назад без прямого доступа к базе. Поэтому
    негодное значение обязано ронять старт, а не создавать недостижимую
    запись.
    """
    try:
        return _LOGIN.validate_python(settings.app_bootstrap_login)
    except ValidationError:
        # Значение в текст не подставляется: сообщение уходит в лог старта, а
        # в эту переменную по ошибке попадает и то, чему в логе не место.
        # Правило описано словами — этого хватает, чтобы понять, что чинить.
        raise RuntimeError(
            "APP_BOOTSTRAP_LOGIN не годится в логин: нужны непустые символы "
            "без пробелов, не длиннее 255. С таким значением первая учётная "
            "запись завелась бы недостижимой: форма привела бы набранное к "
            f"другому виду. Проверь {ENV_FILE}."
        ) from None


async def ensure_bootstrap_user(session: AsyncSession) -> None:
    """Заводит первую учётную запись, если таблица пуста.

    Пара по умолчанию admin / admin известна всем, у кого есть шаблон,
    поэтому на боевом контуре под ней не работают: заводят свою запись и
    отключают эту. Условие выключения выражено свойством
    `settings.bootstrap_enabled`, а не проверкой по месту: инвариант должен
    жить в одном месте, иначе его однажды выразят по-своему.
    """
    if not settings.bootstrap_enabled:
        return
    existing = (await session.execute(select(User.id).limit(1))).first()
    if existing is not None:
        return
    session.add(
        User(
            # Проверка стоит здесь, а не выше по функции, намеренно: пока
            # таблица непуста, значение переменной ни на что не влияет, и
            # ронять из-за него работающий контур на каждом перезапуске было
            # бы отказом ради ничего.
            login=bootstrap_login(),
            name=settings.app_bootstrap_name,
            role=Role.admin,
            # Тоже в пул потоков: hash_password стоит столько же, сколько
            # проверка, а вызывается он при старте приложения.
            password_hash=await asyncio.to_thread(
                hash_password, settings.app_bootstrap_password
            ),
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
