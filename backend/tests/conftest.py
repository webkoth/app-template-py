"""Фикстуры API-тестов.

Каждый тест идёт в своей транзакции и откатывается: база остаётся чистой,
и порядок тестов ни на что не влияет.
"""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.db import Base, get_session
from app.core.rate_limit import address_limiter, login_limiter
from app.core.security import hash_password
from app.core.users import User, UserStatus
from app.domain.roles import Role
from app.main import app

# Импорт ради регистрации таблиц в Base.metadata — по той же причине, что и
# в alembic/env.py. Схема тестовой базы создаётся из метаданных, а туда
# таблица попадает, только если её модуль кто-то импортировал. Без этих
# строк состав схемы зависит от того, какие роутеры уже подключены к
# приложению, то есть меняется от задачи к задаче: сейчас в метаданных одна
# таблица из трёх. Первый же тест фичи упал бы с «relation does not exist»,
# и причину искали бы в тесте, а не в цепочке импортов.
from app.core.audit import AuditLog  # noqa: F401  # isort: skip
from app.features.expenses.models import Expense  # noqa: F401  # isort: skip

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

# Отдельная проверка на совпадение адресов. Первая закрывает случай
# «переменную забыли», эта — «переменную скопировали»: опечатка в .env
# приводит ровно к тому же, от чего защищает первая, — схема рабочей базы
# уничтожается прогоном тестов. Воспроизведено.
if settings.database_url_e2e == settings.database_url:
    raise RuntimeError(
        "DATABASE_URL_E2E совпадает с DATABASE_URL. Тесты сбрасывают схему "
        "целиком, и рабочая база после прогона осталась бы пустой."
    )

test_engine = create_async_engine(settings.async_database_url_e2e, pool_pre_ping=True)


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with test_engine.begin() as conn:
        # Схема сбрасывается и ПЕРЕД прогоном, а не только после. Эту же базу
        # использует Playwright: он накатывает схему миграциями и оставляет
        # после себя строки, которые создали сценарии. create_all их не
        # трогает — таблицы уже есть, — и тесты, считающие записи или
        # заводящие учётную запись «admin», падают на чужих данных: после
        # прогона e2e `make check` давал 11 отказов в tests/api при
        # неизменном коде. Воспроизведено.
        #
        # IF EXISTS: на новой базе схемы public может не быть вовсе, и без
        # него первый же прогон падал бы на подготовке.
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        # Схема сбрасывается целиком, а не через drop_all. Две причины.
        #
        # Первая: drop_all удаляет только то, что попало в метаданные через
        # цепочку импортов обвязки. Таблица, чей модуль сюда не
        # импортируется, переживает прогон — и начинает удаляться позже,
        # когда её импорт где-нибудь появится. Поведение меняется молча.
        #
        # Вторая важнее: эту же базу использует Playwright, а он накатывает
        # схему миграциями. drop_all оставлял бы alembic_version с отметкой
        # «накатано», и следующий `alembic upgrade head` не делал бы
        # ничего — приложение стартовало бы на пустой базе, все сценарии
        # падали бы, а причина (чужой прогон pytest) была бы не видна.
        # Воспроизведено.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(autouse=True)
def _isolated_limiters() -> None:
    """Счётчики попыток — глобалы модуля, и состояние течёт между тестами.

    Подменить объект в фикстуре нельзя: сервис входа связывает имена при
    импорте (`from app.core.rate_limit import login_limiter`), и подмена
    атрибута модуля до него не дойдёт. Остаётся чистить содержимое.

    Без этого порядок тестов влияет на результат. Показано мутацией: удаление
    одной строки `login_limiter.reset(login)` в сервисе уронило посторонний
    тест про `/me` — тот всего лишь входил третьим по счёту. Пока успешный
    вход обнуляет оба счётчика, всё сходится само; первый же файл с длинной
    серией неудачных входов начнёт ронять соседей по порядку.
    """
    login_limiter.clear()
    address_limiter.clear()


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
def new_session() -> Callable[[], AsyncSession]:
    """Отдельная сессия на отдельном соединении, вне транзакции теста.

    Общая фикстура `session` для проверок одновременности не годится: десять
    параллельных запросов к одной AsyncSession дают ошибку SQLAlchemy вместо
    проверки поведения.

    Данные, заведённые `make_user`, такой сессии не видны: они лежат в
    транзакции, которая не коммитится. Это не изъян, а условие — проверка
    одновременности работает на несуществующем логине.
    """
    return lambda: AsyncSession(bind=test_engine)


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
