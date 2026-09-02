"""Сборка приложения."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import SessionFactory
from app.core.errors import ERROR_RESPONSES, register_error_handlers
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


def create_app() -> FastAPI:
    """Собирает приложение.

    Фабрика, а не сборка по месту, ради одной проверки: порядок монтирования
    здесь несущий, а поймать его перестановку иначе нечем. Пока сборки
    фронтенда нет, `mount_frontend` выходит первой же строкой, перестановка
    ничего не меняет, и мутация проходит молча — а на контуре, где сборка
    есть, та же перестановка отвечает 404 на КАЖДЫЙ маршрут API. Проверено:
    с подложенной сборкой падают 36 тестов.

    С фабрикой проверка собирает приложение сама, подсунув каталог сборки, и
    смотрит, что перехватчик зарегистрирован последним.
    """
    app = FastAPI(
        # Имя шаблона одно на всё: слаг контура, базы, роль, заголовок
        # схемы. «apptemplate» занят соседним TS-шаблоном, а контур у них
        # общий — совпади имя, и совпали бы каталог /var/www, процесс pm2,
        # база и vhost. При установке это имя меняется на имя приложения,
        # и менять его надо в одном виде, а не в двух.
        title="apptemplatepy",
        lifespan=lifespan,
        # Интерактивные страницы FastAPI выключены: на контуре они висели бы
        # открытым описанием API. Вместе с ними выключен и openapi_url —
        # иначе обещание не выполняется: страницы закрыты, а сама схема
        # по-прежнему отдаётся любому, кто знает адрес. Замерено: 18 кБ
        # описания всех маршрутов без единой проверки прав.
        #
        # Генерации типов клиента это не мешает: схему печатает
        # `python -m app.openapi` в том же процессе, не по HTTP.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    register_error_handlers(app)

    for router in (
        meta_router,
        auth_router,
        users_router,
        expenses_router,
        audit_router,
    ):
        app.include_router(router, prefix="/api", responses=ERROR_RESPONSES)

    # Монтируется последним: перехватчик /{path:path} обязан стоять после
    # всех маршрутов API, иначе он поглотит их.
    mount_frontend(app)
    return app


# Имя `app` остаётся: `uvicorn app.main:app` и обвязка тестов ссылаются на него.
app = create_app()
