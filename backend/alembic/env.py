"""Окружение Alembic.

Обвязка запускается до того, как приложение существует, и читает настройки
сама — так же, как это описано для скриптов в правилах проекта.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import Base

# Импорт ради регистрации таблиц в Base.metadata: без него autogenerate
# видит пустую схему и предлагает удалить всё, что есть в базе.
#
# Директива ниже не даёт ruff слить эти три строки с импортами выше и
# разложить всё по алфавиту: тогда комментарий остался бы над одним
# случайным импортом из трёх, а объяснять он должен все три.
# isort: split
from app.core.audit import AuditLog  # noqa: F401
from app.features.expenses.models import Expense  # noqa: F401
from app.features.users.models import User  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.async_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.async_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Без этого Alembic не замечает смену типа колонки: миграция
        # выглядит применённой, а тип в базе остаётся прежним.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Движок асинхронный, то есть Alembic ходит в базу тем же asyncpg, что
    # и приложение. Синхронный драйвер (psycopg) здесь не нужен и в
    # зависимостях его нет намеренно: вторая библиотека доступа к базе —
    # это второй набор различий в поведении, который однажды придётся
    # разбирать.
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
