"""Сборка приложения.

Маршруты добавляются по мере появления фич: каждая задача фазы дописывает
свой роутер в список ниже. Так тесты фичи работают сразу, а не ждут конца
фазы.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import SessionFactory
from app.core.errors import register_error_handlers
from app.features.auth.router import router as auth_router
from app.features.auth.service import ensure_bootstrap_user
from app.features.meta.router import router as meta_router
from app.features.users.router import router as users_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with SessionFactory() as session:
        await ensure_bootstrap_user(session)
    yield


app = FastAPI(
    title="apptemplate",
    # Схема нужна для генерации типов клиента; интерактивные страницы
    # FastAPI выключены — на контуре они висели бы открытым описанием API.
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

register_error_handlers(app)
app.include_router(meta_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
