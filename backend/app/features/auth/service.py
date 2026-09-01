"""Правила входа."""

import asyncio
import logging
import math
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import RuleViolation
from app.core.rate_limit import address_limiter, login_limiter
from app.core.security import hash_password, sign_session_token, verify_password
from app.core.users import User, UserStatus
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
# вернётся молча, поэтому превышение пишется в лог.
MIN_RESPONSE_SECONDS = 0.25


async def authenticate(
    session: AsyncSession, login: str, password: str, client_ip: str
) -> str:
    """Проверяет пару и возвращает токен сессии. Отказ — RuleViolation."""
    started = time.monotonic()

    async def finish() -> None:
        remaining = MIN_RESPONSE_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)
        else:
            # Работа не уложилась в границу — значит ветки перестали быть
            # неразличимыми по времени. Молча это оставлять нельзя: оракул
            # вернётся, и заметить его будет нечем.
            logger.warning(
                "вход занял %.0f мс при границе %.0f мс: выравнивание времени "
                "ответа больше не работает",
                (time.monotonic() - started) * 1000,
                MIN_RESPONSE_SECONDS * 1000,
            )

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

    # verify_password уходит в пул потоков намеренно. Один вызов scrypt
    # занимает около 25 мс сплошного счёта, и вызванный напрямую он
    # блокирует цикл событий целиком: замеряно — восемь проверок подряд
    # держат цикл 195 мс, за которые он не проворачивается ни разу, то есть
    # встают и все прочие запросы, включая проверку живости. Через пул те
    # же восемь занимают 42 мс и цикл остаётся живым.
    ok = (
        user is not None
        and user.status is UserStatus.active
        and user.password_hash is not None
        and await asyncio.to_thread(verify_password, password, user.password_hash)
    )
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
            # Тот же вид, что и у логина из формы: без приведения запись,
            # заведённая как APP_BOOTSTRAP_LOGIN=Admin, оказалась бы
            # недостижимой — форма привела бы ввод к «admin», а в базе
            # лежало бы «Admin».
            login=settings.app_bootstrap_login.strip().lower(),
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
