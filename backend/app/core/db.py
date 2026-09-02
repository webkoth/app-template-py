"""Единственная точка доступа к базе в коде приложения.

Транзакцией управляет сервис фичи: он и знает, что должно уехать вместе.
Сессия здесь только выдаётся и закрывается.
"""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Имена ограничений задаются нами, а не базой. Без этого соглашения
# внешний ключ создаётся вообще без имени, и PostgreSQL придумывает своё.
# Пока связей нет, разница незаметна; как только они появятся — а в
# настоящем приложении они появятся, — `alembic --autogenerate` начнёт
# выдавать `op.drop_constraint(None, ...)`, и миграция упадёт на `None`
# вместо имени.
#
# Соглашение обязано стоять до первой миграции: она замораживает имена, и
# переименование потом — отдельная миграция ради того, что стоило одной
# строки. Проверено сравнением DDL: с соглашением ограничения получают
# читаемые pk_users, fk_expenses_author_id_users, ck_expenses_*.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Общий предок таблиц. От него же Alembic берёт метаданные."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_async_engine(
    settings.async_database_url,
    # Соединение, простоявшее ночь, PostgreSQL успевает закрыть со своей
    # стороны. Без pre_ping первый утренний запрос падал бы разрывом связи.
    pool_pre_ping=True,
    # Приложение внутреннее, пользователей десятки: большой пул только
    # занимал бы соединения на общем сервере, где живут и соседние базы.
    pool_size=5,
    max_overflow=5,
)

SessionFactory = async_sessionmaker(
    engine,
    # Иначе после commit() у объектов сбрасываются атрибуты, и первое же
    # обращение к ним вне транзакции уходит в базу за уже известным —
    # в async-коде это ещё и MissingGreenlet, который нечем читать.
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия на запрос."""
    async with SessionFactory() as session:
        yield session
