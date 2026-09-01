"""Единый конверт ошибки: {"error": "текст", "field": "имя_поля"}.

Ожидаемые ошибки возвращаются, а не бросаются наружу как сбой. Клиент
разбирает одну форму ответа независимо от того, кто отказал — валидатор
схемы или правило в сервисе; иначе на клиенте появятся две ветки разбора, и
вторая будет написана хуже.
"""

import logging
from typing import Any, TypedDict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    # ge/le дают СВОИ типы, не greater_than/less_than. Разница видна только
    # на первом же применении: `?limit=0` отвечал «Input should be greater
    # than or equal to 1» — по-английски, в приложении с русским
    # интерфейсом. Ровно то, ради чего эта таблица существует.
    "greater_than_equal": "Значение слишком мало",
    "less_than_equal": "Значение слишком велико",
    # На HTTP-пути pydantic отдаёт именно model_attributes_type, а не
    # model_type: последний бывает только при прямой проверке модели, где
    # формулировка «тело запроса» неверна по смыслу.
    "model_attributes_type": "Тело запроса должно быть объектом",
    "json_invalid": "Тело запроса не разобрать как JSON",
    "string_unicode": "Значение содержит недопустимые символы",
}

# Префикс, которым pydantic оборачивает текст нашего собственного ValueError.
_VALUE_ERROR_PREFIX = "Value error, "


class Envelope(TypedDict):
    error: str
    field: str | None


class ErrorBody(BaseModel):
    """Тот же конверт, но для описания схемы.

    TypedDict выше — форма, которую собирают обработчики; эта модель нужна
    только затем, чтобы конверт попал в OpenAPI и оттуда в типы клиента.
    Без неё схема описывает лишь успешные ответы, и обещание «расхождение
    контракта становится ошибкой компиляции» на ошибки не распространяется:
    разбор отказа на клиенте пишется вслепую и компилятором не проверяется.
    """

    error: str
    field: str | None = None


# Один и тот же конверт на всех отказах — и объявляется он один раз, на все
# маршруты сразу. Точный набор кодов по каждому маршруту здесь намеренно не
# перечисляется: клиенту важна форма ответа, а она везде одна, и попытка
# держать перечень в согласии с кодом руками разошлась бы с ним на первой же
# новой проверке прав.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorBody, "description": text}
    for code, text in [
        (400, "Правило не пустило или схема не сошлась"),
        (401, "Нужно войти"),
        (403, "Недостаточно прав"),
        (404, "Запись не найдена"),
    ]
}


class RuleViolation(Exception):
    """Нарушение правила предметной области. Ожидаемое, отвечает 400."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class RecordNotFound(Exception):
    """Записи нет. Ожидаемое, отвечает 404.

    Свой класс, а не `LookupError`. Роутеры ловили `LookupError` и выносили
    наружу `str(exc)` — и то и другое оказалось дорого. `LookupError` —
    предок `KeyError` и `IndexError`, поэтому ЛЮБОЙ такой сбой внутри
    сервиса объявлялся «не найдено»: воспроизведено на строке с ролью,
    которой ещё нет в коде (обычный порядок выката миграции), — запрос
    вернул 404 с текстом «'owner' is not among the defined enum values.
    Enum name: role. Possible values: viewer, editor, admin». Настоящий сбой
    выдан за отсутствие записи, внутренности уехали клиенту вопреки правилу
    этого же модуля, и в лог не попало ничего: до обработчика пятисотки дело
    не дошло.

    Текст ответа задаёт тот, кто бросает, — но это НАШ текст, а не
    сообщение чужого исключения.
    """

    def __init__(self, message: str = "Запись не найдена") -> None:
        super().__init__(message)
        self.message = message


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

    # Имя поля берётся, только если хвост пути — строка. У ошибки разбора
    # JSON там лежит смещение в байтах (loc = ("body", 13)), и форма стала
    # бы подсвечивать поле с именем «13».
    tail = location[-1] if location else None
    field = _printable(tail) if isinstance(tail, str) else None
    return Envelope(error=_printable(message) or FALLBACK_MESSAGE, field=field)


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
            content=Envelope(
                error=_printable(exc.message) or FALLBACK_MESSAGE,
                # field тоже через _printable: он приходит из того же
                # пользовательского ввода, что и текст, и незащищённый
                # суррогат в нём роняет построение ответа ровно так же.
                field=_printable(exc.field) if exc.field else None,
            ),
        )

    @app.exception_handler(RecordNotFound)
    async def _missing(_: Request, exc: RecordNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=Envelope(
                error=_printable(exc.message) or FALLBACK_MESSAGE, field=None
            ),
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

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Без этого обработчика отказы FastAPI уходят в своей форме
        # {"detail": ...}, и обещание «одна форма ответа» не выполняется:
        # так отвечают непарсимое тело, 404, 405 и — начиная с зависимостей
        # доступа — все отказы по правам, то есть самая частая ошибка в
        # работающем приложении.
        return JSONResponse(
            status_code=exc.status_code,
            content=Envelope(
                error=_printable(str(exc.detail)) or FALLBACK_MESSAGE, field=None
            ),
            headers=getattr(exc, "headers", None),
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
