import asyncio
import logging
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.errors import RuleViolation
from app.core.security import AUTH_COOKIE, SESSION_MAX_AGE_SECONDS
from app.core.users import User, UserStatus
from app.domain.roles import Role


async def test_login_sets_cookie(client, make_user):
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    assert response.status_code == 200
    assert AUTH_COOKIE in response.cookies


async def test_cookie_is_httponly_and_samesite(client, make_user):
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    # Сравнение без учёта регистра. Starlette пишет значение ровно так, как
    # его передали, а передать «Lax» нельзя: параметр объявлен как
    # Literal["lax", "strict", "none"], и проверка типов такое не пропустит.
    # На поведение регистр не влияет — по RFC 6265bis значение атрибута
    # разбирается без учёта регистра, и браузеры читают «lax».
    assert "samesite=lax" in header.lower()
    # Срок куки и срок токена — одна политика. Раньше это были две
    # несвязанные константы, и мутация «сделать срок куки минутой» проходила
    # молча: короче — человека выкидывает раньше срока без причины, длиннее
    # — SPA видит куку, считает себя вошедшим и получает 401 на каждый
    # запрос. Величина закреплена литералом, а не той же константой, которой
    # задаётся: тест, сверяющий константу с собой, зелен при любом её
    # значении.
    assert SESSION_MAX_AGE_SECONDS == 7 * 24 * 60 * 60
    assert "max-age=604800" in header.lower()


async def test_cookie_is_secure_only_when_the_contour_is_under_https(
    client, make_user, monkeypatch
):
    # Secure — единственный из трёх атрибутов, чья потеря невидима: кука
    # продолжает работать, просто уезжает и по http, то есть достаётся любому
    # на пути. Проверяется в обе стороны: жёстко вписанный False снимает
    # защиту на контуре, жёстко вписанный True ломает локальную разработку —
    # браузер такую куку по http не примет и человек не войдёт вовсе.
    await make_user(login="ivan")

    monkeypatch.setattr(settings, "cookie_secure", True)
    secured = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    assert "; secure" in secured.headers["set-cookie"].lower()

    monkeypatch.setattr(settings, "cookie_secure", False)
    plain = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    assert "; secure" not in plain.headers["set-cookie"].lower()


async def test_wrong_password_rejected(client, make_user):
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "мимо"}
    )
    assert response.status_code == 400
    assert AUTH_COOKIE not in response.cookies


async def test_unknown_login_gives_same_message_as_wrong_password(client, make_user):
    await make_user(login="ivan")
    wrong = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "мимо"}
    )
    missing = await client.post(
        "/api/auth/login", json={"login": "неттакого", "password": "мимо"}
    )
    # Разные тексты подсказали бы, какие логины существуют.
    assert wrong.json()["error"] == missing.json()["error"]


async def test_login_with_whitespace_inside_is_refused(client, make_user):
    # `^\S+$`. Без него форма принимает «ad\nmin», сервис находит такого
    # пользователя, подписывает токен и ставит куку — а разбор токена
    # спотыкается о перевод строки, verify_session_token возвращает None, и
    # человек получает 200 с Set-Cookie, а затем 401 на каждый запрос. Молча.
    # Воспроизведено.
    await make_user(login="ad\nmin")
    response = await client.post(
        "/api/auth/login", json={"login": "ad\nmin", "password": "секрет"}
    )
    assert response.status_code == 400
    assert AUTH_COOKIE not in response.cookies


async def test_login_is_trimmed(client, make_user):
    # Логин, скопированный из письма, приходит с пробелами по краям. Без
    # обрезки он не просто не находится: он не проходит `^\S+$`, и человек
    # получает «недопустимые символы» на верной паре.
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": " ivan ", "password": "секрет"}
    )
    assert response.status_code == 200


async def test_login_length_is_checked_after_case_folding(client):
    # 200 турецких «İ» (U+0130) проходят проверку длины и превращаются в 400
    # символов: lower() раскладывает каждую букву на две. Сегодня цена этому
    # — SELECT, который ничего не найдёт, но тот же тип берёт создание
    # учётной записи, и там это StringDataRightTruncation: пятисотка вместо
    # отказа формы, а SQL с параметрами уезжает в лог.
    #
    # Проверяется текст отказа, а не только код: при проверке длины ДО
    # приведения такой логин доходит до базы и получает обычное «неверный
    # логин или пароль», то есть по коду ответа мутация неотличима.
    response = await client.post(
        "/api/auth/login", json={"login": "İ" * 200, "password": "секрет"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Слишком длинное значение"


async def test_login_ignores_case(client, make_user):
    # Учётная запись заведена в нижнем регистре, человек набирает как
    # привык. Без приведения он получил бы «неверный логин или пароль» на
    # верном пароле и не понял бы, почему.
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "IVAN", "password": "секрет"}
    )
    assert response.status_code == 200


async def test_disabled_user_cannot_login(client, make_user):
    await make_user(login="ivan", status=UserStatus.disabled)
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    assert response.status_code == 400


async def test_me_returns_current_user(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["login"] == "ivan"
    assert body["role"] == "editor"


async def test_me_marks_the_bootstrap_account(client, login_as, monkeypatch):
    # Предупреждение на первом экране висит по этому признаку. Считать его на
    # клиенте нечем: он не знает ни настроенного логина, ни того, убраны ли
    # переменные с контура.
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_bootstrap_login", "шеф")
    await login_as(login="шеф")
    assert (await client.get("/api/auth/me")).json()["using_bootstrap_account"] is True


async def test_me_does_not_mark_an_ordinary_account(client, login_as, monkeypatch):
    # Обратная сторона: предупреждение, которое висит всегда, читать
    # перестают. Сравнение с литералом «admin» промахивалось бы здесь —
    # владелец, назвавший собственную запись admin, видел бы его вечно.
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_bootstrap_login", "шеф")
    await login_as(login="ivan")
    assert (await client.get("/api/auth/me")).json()["using_bootstrap_account"] is False


async def test_me_stops_marking_when_bootstrap_is_switched_off(
    client, login_as, monkeypatch
):
    # Признак гаснет сам, когда владелец убирает APP_BOOTSTRAP_* из .env
    # контура — последний шаг установки. Иначе предупреждение осталось бы
    # висеть на выполненной работе.
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_bootstrap_login", "шеф")
    await login_as(login="шеф")
    monkeypatch.setattr(settings, "app_bootstrap_password", "")
    assert (await client.get("/api/auth/me")).json()["using_bootstrap_account"] is False


async def test_me_without_cookie_is_401(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_logout_clears_cookie(client, login_as):
    await login_as()
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_budget_is_taken_before_password_check(new_session):
    # Порядок вызовов, а не их наличие. Между проверкой бюджета и записью
    # неудачи стоит await на scrypt, и при обратном порядке цикл событий
    # пропускает в ворота все ждущие запросы разом: десять одновременных
    # попыток дают десять проверок пароля при пределе пять.
    #
    # Отличить порядок можно ТОЛЬКО одновременностью. Одиночная неудачная
    # попытка записывается в счётчик при любом порядке, поэтому проверка
    # «после одной попытки счётчик не пуст» о порядке не говорит ничего и
    # проходит на заведомо дырявом коде.
    #
    # Каждому вызову — своя сессия: десять одновременных запросов к одной
    # AsyncSession дают ошибку SQLAlchemy вместо проверки входа. Логин взят
    # несуществующий намеренно: ворота стоят до обращения к базе, и вся
    # разница видна именно на нём.
    from app.core.rate_limit import address_limiter, login_limiter
    from app.features.auth.service import DENIED, authenticate

    login = "натиск"
    address = "10.0.0.1"
    login_limiter.reset(login)
    address_limiter.reset(address)

    async def attempt() -> str:
        async with new_session() as db:
            try:
                await authenticate(db, login, "мимо", address)
            except RuleViolation as denial:
                return denial.message
        raise AssertionError("несуществующий логин обязан был получить отказ")

    messages = await asyncio.gather(*(attempt() for _ in range(10)))
    # Пять попыток дошли до проверки, остальные упёрлись в бюджет. При
    # обратном порядке до проверки дошли бы все десять.
    assert messages.count(DENIED) == 5, messages
    assert all(
        m.startswith("Слишком много попыток") for m in messages if m != DENIED
    ), messages


async def test_denial_is_not_faster_than_the_floor(new_session):
    # Выравнивание времени ответа — единственная защита от перебора логинов
    # по времени, и без этой проверки её потеря молчалива: отказ продолжает
    # быть отказом, тесты остаются зелёными, а оракул возвращается.
    #
    # Отказ по несуществующему логину scrypt не считает и без выравнивания
    # возвращается за единицы миллисекунд; отказ по неверному паролю — за
    # десятки. Проверяется нижняя граница, а не разница между ветками:
    # граница не зависит от загрузки машины и потому не флапает.
    from app.core.rate_limit import address_limiter, login_limiter
    from app.features.auth.service import MIN_RESPONSE_SECONDS, authenticate

    # Величина закреплена литералом. Мерить той же константой, которую тест
    # и охраняет, бесполезно: при MIN_RESPONSE_SECONDS = 0 такая проверка
    # остаётся зелёной, то есть ловит «убрали вызов finish()» и не ловит
    # «выключили границу» — а защиты умирают именно так, под предлогом
    # «ускорим тесты».
    assert MIN_RESPONSE_SECONDS == 0.25

    login_limiter.reset("призрак")
    address_limiter.reset("10.0.0.2")
    started = time.monotonic()
    async with new_session() as db:
        with pytest.raises(RuleViolation):
            await authenticate(db, "призрак", "мимо", "10.0.0.2")
    assert time.monotonic() - started >= 0.25


async def test_denial_gives_the_connection_back_before_it_waits(monkeypatch):
    """Выравнивание времени не должно держать соединение пула.

    Замерено на прежнем варианте с пулом приложения (5 плюс 5 сверху): сорок
    одновременных отказов занимали все десять соединений на четверть секунды
    каждое, и посторонний `select 1` шёл 211 мс вместо 0,7 мс. То есть один
    дешёвый POST без единого верного пароля укладывал все прочие маршруты, а
    дальше начинался pool_timeout. После возврата соединения перед сном тот
    же замер даёт 1–15 мс.

    Проверяется событие пула, а не секундомер и не опрос. Первая редакция
    требовала «посторонний запрос ждал меньше 100 мс» — и падала на исправном
    коде: под нагрузкой одно только получение соединения занимает 380–460 мс.
    Воспроизведено на двадцати четырёх фоновых процессах. Разбор показал, что
    и без нагрузки замер мерил не то: соединение держал не сон, а установка
    первого соединения и сам SELECT — около 300 мс. Случайный красный в CI
    дороже отсутствующего теста: он приучает перезапускать прогон, не читая.

    Вторая редакция опрашивала `pool.checkedout()` шагом 10 мс и ждала
    сначала «занято», потом «свободно». Она тоже флапала, и хуже: один
    красный на десять полных прогонов, изолированно 15 из 15 зелёных. На
    пути «логина нет» соединение занято ровно на один короткий SELECT, и
    поллер в это окно попадал не всегда — отказ приходил не от защиты, а от
    промаха наблюдателя («соединение так и не занялось — проверять нечего»).
    Воспроизведено на первом же прогоне ревью.

    Здесь наблюдатель не опрашивает, а слушает: пул сам сообщает о возврате
    соединения событием `checkin`, и промахнуться мимо окна нечем. Сравнение
    без порогов на время работы: возврат обязан случиться заметно раньше
    конца отказа, а «заметно» задано растянутым окном выравнивания — 2
    секунды против миллисекунд, которые проходят между возвратом и концом
    задачи, если соединение отпускают только в конце.
    """
    from app.features.auth import service

    # Окно растянуто, чтобы разрыв «отпустил» — «закончил» был заведомо
    # больше любой случайной задержки на любой машине.
    window = 2.0
    monkeypatch.setattr(service, "MIN_RESPONSE_SECONDS", window)

    engine = create_async_engine(
        settings.async_database_url_e2e, pool_size=1, max_overflow=0
    )
    returned_at: list[float] = []
    try:
        # Соединение устанавливается заранее. Иначе первым делом отказ платит
        # за установку — сотни миллисекунд, в которые он законно держит
        # соединение, — и наблюдение спутало бы её с удержанием на время сна.
        async with AsyncSession(bind=engine) as warmup:
            await warmup.execute(text("select 1"))

        # Слушатель ставится ПОСЛЕ прогрева: возврат прогревочного соединения
        # — тоже checkin, и он оказался бы первым в списке.
        event.listen(
            engine.sync_engine,
            "checkin",
            lambda *_: returned_at.append(time.monotonic()),
        )

        async with AsyncSession(bind=engine) as db:
            with pytest.raises(RuleViolation):
                await service.authenticate(db, "призрак", "мимо", "10.0.0.3")
        finished_at = time.monotonic()
    finally:
        await engine.dispose()

    assert returned_at, (
        "соединение в пул не возвращалось вовсе — проверять нечего. Либо "
        "отказ его не занимал, либо возврат перестал быть виден пулу"
    )
    assert finished_at - returned_at[0] >= window / 2, (
        "соединение вернулось в пул вместе с завершением отказа, а не до "
        "него — значит выравнивание времени держало его всё ожидание"
    )


class _SlowDatabase:
    """Сессия, у которой база отвечает медленно. Больше ничего не меняет."""

    def __init__(self, inner, delay: float) -> None:
        self._inner = inner
        self._delay = delay

    async def execute(self, *args, **kwargs):
        await asyncio.sleep(self._delay)
        return await self._inner.execute(*args, **kwargs)

    async def commit(self):
        return await self._inner.commit()

    async def rollback(self):
        return await self._inner.rollback()


async def test_alarm_ignores_time_spent_outside_the_password_check(
    caplog, session, make_user
):
    # Сигнализация о потере выравнивания обязана мерить проверку пароля, а не
    # время ответа целиком. По полному времени она врёт под нагрузкой:
    # замерено — сорок одновременных отказов по несуществующему логину давали
    # 30 предупреждений, хотя scrypt в этих запросах не вызывался вовсе, а
    # после возврата соединения в пул сто одновременных отказов с проверкой
    # пароля давали ещё 38. Лишнее время уходило на ожидание соединения —
    # одинаковое для обеих веток и потому никакого различия не создающее.
    #
    # Здесь то же самое воспроизводится дёшево: база отвечает 300 мс, сама
    # проверка пароля остаётся быстрой. Молчания достаточно: единственная
    # сигнализация о молчаливой потере защиты не имеет права давать ложные
    # срабатывания — её перестанут читать ровно до того, как она понадобится.
    from app.features.auth import service

    await make_user(login="ivan")
    service._alarm_last_at = None
    with caplog.at_level(logging.WARNING, logger=service.__name__):
        with pytest.raises(RuleViolation):
            await service.authenticate(
                _SlowDatabase(session, 0.3), "ivan", "мимо", "10.0.0.4"
            )
    assert [r.getMessage() for r in caplog.records if r.name == service.__name__] == []


async def test_alarm_fires_once_when_the_password_check_outgrows_the_floor(
    caplog, session, make_user, monkeypatch
):
    # Обратная сторона: когда scrypt перестаёт укладываться в границу,
    # различие веток по времени возвращается, и сказать об этом некому — на
    # ответе это не видно. Строка в логе и есть единственный признак.
    #
    # Строка одна на две попытки. Если scrypt действительно замедлился, это
    # верно для каждого входа, и без задвижки один POST даёт одну строку
    # WARNING в единственный диагностический канал контура: настоящий сигнал
    # утонул бы в собственных повторах.
    from app.features.auth import service

    await make_user(login="ivan")
    service._alarm_last_at = None

    def slow_verify(password: str, stored: str) -> bool:
        time.sleep(service.MIN_RESPONSE_SECONDS + 0.05)
        return False

    monkeypatch.setattr(service, "verify_password", slow_verify)
    with caplog.at_level(logging.WARNING, logger=service.__name__):
        for _ in range(2):
            with pytest.raises(RuleViolation):
                await service.authenticate(session, "ivan", "мимо", "10.0.0.5")
    lines = [r.getMessage() for r in caplog.records if r.name == service.__name__]
    assert len(lines) == 1, lines


async def test_successful_login_clears_counter(client, make_user):
    # Обратная сторона: бюджет занимается до проверки, поэтому успешный
    # вход обязан счётчик обнулить — иначе честный пользователь копил бы
    # отметки на каждом входе и однажды заперся бы сам.
    #
    # Отметка сначала ставится неудачной попыткой, и проверяется её
    # исчезновение. Без этого шага счётчик пуст и до успешного входа, и
    # после — проверять нечего.
    from app.core.rate_limit import login_limiter

    await make_user(login="ivan")
    login_limiter.reset("ivan")
    await client.post("/api/auth/login", json={"login": "ivan", "password": "мимо"})
    marked = login_limiter.size()
    await client.post("/api/auth/login", json={"login": "ivan", "password": "секрет"})
    assert login_limiter.size() == marked - 1


async def test_successful_login_clears_the_address_counter(client, make_user):
    # Второй счётчик обнуляется по той же причине, что и первый, но цена
    # ошибки другая: адрес общий. Без этого офис за одним NAT запирается
    # после тридцати успешных входов за пятнадцать минут — ровно тот
    # сценарий, ради которого счётчиков два.
    from app.core.rate_limit import address_limiter

    await make_user(login="ivan")
    headers = {"X-Real-IP": "10.0.0.8"}
    await client.post(
        "/api/auth/login",
        json={"login": "ivan", "password": "мимо"},
        headers=headers,
    )
    assert address_limiter.size() == 1
    await client.post(
        "/api/auth/login",
        json={"login": "ivan", "password": "секрет"},
        headers=headers,
    )
    assert address_limiter.size() == 0


async def test_attempts_are_counted_by_x_real_ip(client, make_user):
    # Адрес берётся из X-Real-IP, который ставит nginx, а не из
    # X-Forwarded-For: там цепочка, и первый сегмент прислал клиент — то
    # есть ограничение по адресу обходится одним заголовком.
    #
    # Ключ проверяется вычитанием: сброс чужого ключа счётчик не меняет,
    # сброс своего — опустошает. Иначе о том, ПО ЧЕМУ считали, тест не
    # говорит ничего.
    from app.core.rate_limit import address_limiter

    await make_user(login="ivan")
    await client.post(
        "/api/auth/login",
        json={"login": "ivan", "password": "мимо"},
        headers={"X-Real-IP": "10.0.0.9", "X-Forwarded-For": "203.0.113.7"},
    )
    assert address_limiter.size() == 1
    address_limiter.reset("203.0.113.7")
    assert address_limiter.size() == 1, "отметка легла по X-Forwarded-For"
    address_limiter.reset("10.0.0.9")
    assert address_limiter.size() == 0


async def test_login_records_last_login(client, session, make_user):
    # Проверяется ЗАПИСЬ, а не присвоение. Тест, который просто читает
    # пользователя через ту же сессию, зелен и без commit(): объект берётся
    # из карты сессии вместе с атрибутом, присвоенным в памяти.
    #
    # В обвязке join_transaction_mode="create_savepoint": commit сервиса
    # отпускает точку сохранения, и откат ниже до неё уже не достаёт.
    # Присвоенное без commit откат отменяет. Что пережило откат — то
    # записано; expire_all заставляет прочитать это из базы, а не из карты.
    await make_user(login="ivan")
    await client.post("/api/auth/login", json={"login": "ivan", "password": "секрет"})
    await session.rollback()
    session.expire_all()
    user = (
        await session.execute(select(User).where(User.login == "ivan"))
    ).scalar_one()
    assert user.last_login_at is not None


async def test_bootstrap_login_follows_the_rule_of_the_form(session, monkeypatch):
    # Первая учётная запись обязана нормализоваться ровно тем же типом, что
    # и логин из формы: обрезка и приведение регистра — не рукописные.
    #
    # Отказ здесь самозапечатывающийся: запись создана, таблица непуста,
    # ensure_bootstrap_user второй раз не сработает, и починить это можно
    # только прямым доступом к базе.
    from app.features.auth.service import ensure_bootstrap_user

    monkeypatch.setattr(settings, "app_bootstrap_login", " Admin ")
    await ensure_bootstrap_user(session)

    created = (await session.execute(select(User))).scalars().all()
    assert [user.login for user in created] == ["admin"]
    assert created[0].role is Role.admin


async def test_bootstrap_refuses_a_login_the_form_would_never_accept(
    session, monkeypatch
):
    # `Админ Один` рукописная нормализация клала в базу как «админ один», а
    # форма такой ввод не пропускает вовсе (`^\S+$`) — войти под этой
    # записью было невозможно никогда.
    #
    # `\x1cAdmin` — то же расхождение с другой стороны, и раньше оно
    # заводило запись молча: питоновский str.strip() режет U+001C и клал в
    # базу «admin», а pydantic обрезает по Unicode White_Space, куда U+001C
    # не входит, — форма отдала бы «\x1cadmin». Теперь управляющие символы
    # в логине запрещены целиком (см. no_control_characters в core/users.py),
    # и значение отвергается вместе с остальными негодными. Оба случая
    # воспроизведены.
    #
    # Негодное значение обязано ронять старт: контур без входа хуже, чем
    # контур, который не поднялся.
    from app.features.auth.service import ensure_bootstrap_user

    for value in ["Админ Один", "\x1cAdmin"]:
        monkeypatch.setattr(settings, "app_bootstrap_login", value)
        with pytest.raises(RuntimeError, match="APP_BOOTSTRAP_LOGIN"):
            await ensure_bootstrap_user(session)
        assert (await session.execute(select(User))).first() is None, value


async def test_bootstrap_leaves_a_filled_table_alone(session, make_user, monkeypatch):
    # Значение проверяется перед созданием записи, а не в начале функции, и
    # это выбор: пока в таблице кто-то есть, APP_BOOTSTRAP_LOGIN ни на что не
    # влияет, и ронять из-за него работающий контур на каждом перезапуске
    # было бы отказом ради ничего. Заодно закреплена и вторая половина
    # правила: непустая таблица не трогается — иначе каждый перезапуск
    # возвращал бы отключённую запись admin с известной всем парой.
    from app.features.auth.service import ensure_bootstrap_user

    await make_user(login="ivan")
    monkeypatch.setattr(settings, "app_bootstrap_login", "Админ Один")
    await ensure_bootstrap_user(session)

    logins = (await session.execute(select(User.login))).scalars().all()
    assert logins == ["ivan"]


async def test_revoked_session_stops_working(client, session, login_as):
    user = await login_as(login="ivan")
    assert (await client.get("/api/auth/me")).status_code == 200
    # Отзыв: подпись куки остаётся верной, поэтому проверка обязана быть на
    # стороне сервера, а не в разборе токена.
    user.sessions_valid_from = datetime.now(UTC)
    await session.commit()
    assert (await client.get("/api/auth/me")).status_code == 401
