"""Окружение Alembic.

Настройки берутся из `app.core.config` — того же места, откуда их берёт
приложение. Своего чтения окружения здесь нет намеренно: два разбора одного
`.env` разъезжаются молча, и миграция уходит в базу, отличную от той, с
которой работает приложение.

Единственная обвязка проекта, читающая окружение сама, — конфигурация
Playwright: она поднимает сервер как чужой процесс и до `app.core.config`
дотянуться не может.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import Base

# Состав схемы — в app/models.py, единственным списком. Без импорта таблица
# не попадает в Base.metadata, и autogenerate выдаёт ПУСТУЮ миграцию: файл
# ревизии создан, прогон зелёный, таблицы в базе нет. Ровно это и случилось
# с очередью, когда список вёлся здесь отдельно от обвязки тестов.
from app import models  # noqa: F401  # isort: skip

config = context.config
# %% вместо %: set_main_option кладёт значение в ConfigParser, а тот считает
# одиночный % началом подстановки. Пароль с процентом даёт не «не удалось
# подключиться», а ValueError с текстом «invalid interpolation syntax»,
# внутри которого — вся строка подключения целиком, вместе с паролем. То
# есть падает не только миграция: секрет уезжает в лог деплоя, обходя
# санитизацию, ради которой в app/core/config.py построен load_settings.
#
# Провижинер генерирует пароль через `openssl rand -hex`, где процента не
# бывает, поэтому сегодня это недостижимо. Но шаблон подключают и к
# управляемым базам стороннего провайдера, а там пароль какой дали.
config.set_main_option("sqlalchemy.url", settings.async_database_url.replace("%", "%%"))

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
