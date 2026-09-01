"""Фикстуры API-тестов.

Каждый тест идёт в своей транзакции и откатывается: база остаётся чистой,
и порядок тестов ни на что не влияет.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.db import Base, get_session
from app.core.security import hash_password
from app.core.users import User, UserStatus
from app.domain.roles import Role
from app.main import app

# Отдельный движок под отдельную базу. Движок приложения здесь не годится:
# фикстура ниже создаёт и удаляет схему целиком, а рабочая база после этого
# осталась бы без таблиц при alembic_version на head — то есть приложение
# перестало бы стартовать, а миграции считали бы, что накатывать нечего.
# Проверено: именно это и произошло при первом прогоне.
#
# Отказ громкий и намеренный. Молчаливый откат на рабочую базу означал бы,
# что забытая переменная окружения стоит человеку схемы.
if not settings.async_database_url_e2e:
    raise RuntimeError(
        "DATABASE_URL_E2E не задан. Тесты создают и удаляют схему целиком и "
        "поэтому идут только в отдельную базу — смотри .env.example."
    )

test_engine = create_async_engine(settings.async_database_url_e2e, pool_pre_ping=True)


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Сессия внутри внешней транзакции, которая всегда откатывается.

    join_transaction_mode="create_savepoint" позволяет сервисам делать
    commit() по-настоящему: коммитится вложенная точка сохранения, а внешняя
    транзакция остаётся открытой и откатывается в конце теста.
    """
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield db
        await db.close()
        await transaction.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    # Про проверку конверта пятисотки: Starlette после обработчика Exception
    # перебрасывает исключение наружу, поэтому тест, который хочет увидеть
    # именно 500 с конвертом, обязан создавать клиент с
    # raise_server_exceptions=False — иначе он упадёт с исходным
    # исключением, а не увидит ответ.
    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def make_user(session: AsyncSession):
    async def _make(
        login: str = "tester",
        role: Role = Role.admin,
        password: str = "секрет",
        status: UserStatus = UserStatus.active,
    ) -> User:
        user = User(
            login=login,
            name=login.capitalize(),
            role=role,
            password_hash=hash_password(password),
            status=status,
            created_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
        return user

    return _make


@pytest.fixture
async def login_as(client: AsyncClient, make_user):
    """Заводит пользователя и кладёт куку сессии в клиент."""

    async def _login(role: Role = Role.admin, login: str = "tester") -> User:
        user = await make_user(login=login, role=role)
        response = await client.post(
            "/api/auth/login", json={"login": login, "password": "секрет"}
        )
        assert response.status_code == 200, response.text
        return user

    return _login
