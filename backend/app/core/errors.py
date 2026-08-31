"""Единый конверт ошибки: {"error": "текст", "field": "имя_поля"}.

Ожидаемые ошибки возвращаются, а не бросаются наружу как сбой. Клиент
разбирает одну форму ответа независимо от того, кто отказал — валидатор
схемы или правило в сервисе; иначе на клиенте появятся две ветки разбора,
и вторая будет написана хуже.
"""

import logging
from typing import TypedDict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Что показывают, когда валидатор не сказал ничего внятного или не сказал
# ничего вовсе. Текст обязан быть годным для формы: его увидит человек.
FALLBACK_MESSAGE = "Значение не подходит"


class Envelope(TypedDict):
    error: str
    field: str | None


class RuleViolation(Exception):
    """Нарушение правила предметной области. Ожидаемое, отвечает 400."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _first_issue(errors: list[dict[str, object]]) -> Envelope:
    # Пустой список — не выдумка: RequestValidationError принимает любой
    # список, и errors()[0] на пустом бросает IndexError. Функция, обязанная
    # вернуть ответ, бросать не имеет права: это обработчик ошибок, и его
    # падение превращает промах в форме в пятисотку без объяснений.
    if not errors:
        return Envelope(error=FALLBACK_MESSAGE, field=None)

    issue = errors[0]
    location = [p for p in issue.get("loc") or () if p not in ("body", "query")]  # type: ignore[attr-defined]
    return Envelope(
        error=str(issue.get("msg", FALLBACK_MESSAGE)),
        # Пустой location — это ошибка не про поле, а про тело целиком
        # (например, вместо объекта пришёл список). Указывать на "body"
        # нечего: поля с таким именем в форме нет, подсветить его нельзя.
        field=str(location[-1]) if location else None,
    )


def validation_error_to_envelope(exc: ValidationError) -> Envelope:
    return _first_issue(exc.errors())  # type: ignore[arg-type]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RuleViolation)
    async def _rule(_: Request, exc: RuleViolation) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=Envelope(error=exc.message, field=exc.field),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_first_issue(exc.errors()),  # type: ignore[arg-type]
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Наружу — ничего о причине: текст исключения регулярно содержит
        # кусок запроса, путь на диске или адрес базы. Подробности идут в
        # лог, который читают через /logs.
        logger.exception("необработанный сбой на %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=Envelope(error="Что-то пошло не так", field=None),
        )
