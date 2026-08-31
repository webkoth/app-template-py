"""Единый конверт ошибки: {"error": "текст", "field": "имя_поля"}.

Ожидаемые ошибки возвращаются, а не бросаются наружу как сбой. Клиент
разбирает одну форму ответа независимо от того, кто отказал — валидатор
схемы или правило в сервисе; иначе на клиенте появятся две ветки разбора, и
вторая будет написана хуже.
"""

import logging
from typing import TypedDict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "Значение не подходит"

# Маркеры места, которые FastAPI ставит первым элементом loc. Снимается
# только голова, и только у ошибок разбора запроса: отсев по значению съел
# бы поле формы, которое само называется "query" или "body", — а поисковая
# строка с именем query вещь обычная.
_LOCATION_MARKERS = frozenset({"body", "query", "path", "header", "cookie"})

# Тексты pydantic — английские и техничные: «String should have at least 8
# characters». Интерфейс приложения русский, и человек читает именно это
# сообщение, поэтому частые случаи переводятся. Незнакомый тип отдаётся как
# есть: неудобный английский лучше, чем потерянная причина.
_MESSAGES = {
    "missing": "Обязательное поле",
    "string_too_short": "Слишком короткое значение",
    "string_too_long": "Слишком длинное значение",
    "string_pattern_mismatch": "Недопустимые символы",
    "string_type": "Нужна строка",
    "int_parsing": "Нужно целое число",
    "int_type": "Нужно целое число",
    "float_parsing": "Нужно число",
    "bool_parsing": "Нужно да или нет",
    "enum": "Недопустимое значение",
    "literal_error": "Недопустимое значение",
    "model_type": "Тело запроса должно быть объектом",
    "extra_forbidden": "Лишнее поле",
    "greater_than": "Значение слишком мало",
    "less_than": "Значение слишком велико",
}

# Префикс, которым pydantic оборачивает текст нашего собственного ValueError.
_VALUE_ERROR_PREFIX = "Value error, "


class Envelope(TypedDict):
    error: str
    field: str | None


class RuleViolation(Exception):
    """Нарушение правила предметной области. Ожидаемое, отвечает 400."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _printable(text: str) -> str:
    """Убирает из текста то, что невозможно отправить.

    Одинокий суррогат приходит из тела запроса — `json.loads('"\\ud800"')`
    его возвращает, — а Starlette сериализует ответ без экранирования, и
    построение ответа падает с UnicodeEncodeError. Падает при этом сам
    обработчик ошибок, то есть отказ 400 превращается в 500 ровно тогда,
    когда что-то уже пошло не так. Путь не теоретический: тексты вида
    «Дата «{значение}» не похожа на дату» собираются из пользовательского
    ввода. Проверено воспроизведением.
    """
    return text.encode("utf-8", "replace").decode("utf-8")


def _first_issue(errors: list[dict[str, object]], strip_marker: bool) -> Envelope:
    """Первая ошибка из списка в виде конверта.

    Наружу уходит одна, а не список: форма показывает одно сообщение, и
    выбирать из пяти пришлось бы клиенту.
    """
    if not errors:
        # Пустой список возможен: RequestValidationError с ним прекрасно
        # конструируется. Без этой ветки обработчик падает IndexError, и
        # ошибка ввода превращается в пятисотку. Проверено.
        return Envelope(error=FALLBACK_MESSAGE, field=None)

    issue = errors[0]
    # isinstance, а не приведение: значение приходит как object, и проверка
    # типа заодно закрывает случай, когда loc отсутствует или равен None.
    raw_location = issue.get("loc")
    location = list(raw_location) if isinstance(raw_location, (list, tuple)) else []
    if strip_marker and location and location[0] in _LOCATION_MARKERS:
        location = location[1:]

    raw = str(issue.get("msg", FALLBACK_MESSAGE))
    if raw.startswith(_VALUE_ERROR_PREFIX):
        # Текст нашего собственного валидатора, он уже по-русски.
        message = raw[len(_VALUE_ERROR_PREFIX) :]
    else:
        message = _MESSAGES.get(str(issue.get("type", "")), raw)

    return Envelope(
        error=_printable(message),
        field=str(location[-1]) if location else None,
    )


def validation_error_to_envelope(error: ValidationError) -> Envelope:
    """Конверт из ошибки прямой проверки модели.

    Маркер места здесь не снимается: у голого ValidationError его нет, и
    снятие головы съело бы настоящее имя поля.
    """
    return _first_issue(error.errors(), strip_marker=False)  # type: ignore[arg-type]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RuleViolation)
    async def _rule(_: Request, exc: RuleViolation) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=Envelope(error=_printable(exc.message), field=exc.field),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 400, а не привычный 422: клиенту незачем различать «схема не
        # сошлась» и «правило не пустило» — для человека это одна и та же
        # ошибка в форме.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_first_issue(exc.errors(), strip_marker=True),  # type: ignore[arg-type]
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
