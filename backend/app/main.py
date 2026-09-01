"""Сборка приложения."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import SessionFactory
from app.core.errors import register_error_handlers
from app.core.static import mount_frontend
from app.features.audit.router import router as audit_router
from app.features.auth.router import router as auth_router
from app.features.auth.service import ensure_bootstrap_user
from app.features.expenses.router import router as expenses_router
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
    lifespan=lifespan,
    # Схема нужна для генерации типов клиента; интерактивные страницы
    # FastAPI выключены — на контуре они висели бы открытым описанием API.
    docs_url=None,
    redoc_url=None,
)

register_error_handlers(app)

for router in (
    meta_router,
    auth_router,
    users_router,
    expenses_router,
    audit_router,
):
    app.include_router(router, prefix="/api")

# Монтируется последним: перехватчик /{path:path} обязан стоять после всех
# маршрутов API, иначе он поглотит их.
mount_frontend(app)
