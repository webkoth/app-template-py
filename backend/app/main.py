"""Сборка приложения.

Маршруты добавляются по мере появления фич: каждая задача фазы дописывает
свой роутер в список ниже. Так тесты фичи работают сразу, а не ждут конца
фазы.
"""

import logging

from fastapi import FastAPI

from app.core.errors import register_error_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="apptemplate",
    # Схема нужна для генерации типов клиента; интерактивные страницы
    # FastAPI выключены — на контуре они висели бы открытым описанием API.
    docs_url=None,
    redoc_url=None,
)

register_error_handlers(app)
