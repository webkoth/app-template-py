import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.errors import RuleViolation
from app.core.security import AUTH_COOKIE
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


async def test_login_records_last_login(client, session, make_user):
    await make_user(login="ivan")
    await client.post("/api/auth/login", json={"login": "ivan", "password": "секрет"})
    user = (
        await session.execute(select(User).where(User.login == "ivan"))
    ).scalar_one()
    assert user.last_login_at is not None


async def test_revoked_session_stops_working(client, session, login_as):
    user = await login_as(login="ivan")
    assert (await client.get("/api/auth/me")).status_code == 200
    # Отзыв: подпись куки остаётся верной, поэтому проверка обязана быть на
    # стороне сервера, а не в разборе токена.
    user.sessions_valid_from = datetime.now(UTC)
    await session.commit()
    assert (await client.get("/api/auth/me")).status_code == 401
