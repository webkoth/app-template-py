"""Единственная точка доступа к базе в коде приложения.

Транзакцией управляет сервис фичи: он и знает, что должно уехать вместе.
Сессия здесь только выдаётся и закрывается.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Общий предок таблиц. От него же Alembic берёт метаданные."""


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
