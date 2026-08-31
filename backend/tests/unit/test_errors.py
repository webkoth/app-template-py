import json

import pytest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from app.core.errors import (
    FALLBACK_MESSAGE,
    RuleViolation,
    _first_issue,
    validation_error_to_envelope,
)


class Sample(BaseModel):
    amount: str = Field(min_length=1)
    title: str


def test_rule_violation_carries_field():
    e = RuleViolation("Сумма должна быть больше нуля", field="amount")
    assert e.message == "Сумма должна быть больше нуля"
    assert e.field == "amount"


def test_rule_violation_without_field():
    assert RuleViolation("Так нельзя").field is None


def test_validation_error_maps_to_single_message():
    # Наружу уходит одна ошибка, а не список: форма показывает одно
    # сообщение, и выбирать из пяти пришлось бы клиенту.
    try:
        Sample(amount="", title="x")
    except ValidationError as exc:
        envelope = validation_error_to_envelope(exc)
    assert envelope["field"] == "amount"
    assert envelope["error"]


def test_missing_field_reports_its_name():
    try:
        Sample(amount="10")
    except ValidationError as exc:
        envelope = validation_error_to_envelope(exc)
    assert envelope["field"] == "title"


def test_empty_error_list_does_not_raise():
    # RequestValidationError с пустым списком прекрасно конструируется, а
    # обработчик на нём падал IndexError — то есть ошибка ввода
    # превращалась в пятисотку. Проверено воспроизведением.
    assert _first_issue([], strip_marker=True) == {
        "error": FALLBACK_MESSAGE,
        "field": None,
    }


def test_location_marker_stripped_only_from_head():
    # Отсев по значению, а не по позиции, съедал бы поле формы, которое
    # само называется "query" или "body": в loc такого поля маркер и имя
    # совпадают, и фильтр по значению вычищал оба.
    assert (
        _first_issue(
            [{"loc": ("body", "query"), "msg": "x", "type": "missing"}],
            strip_marker=True,
        )["field"]
        == "query"
    )
    # А маркер, стоящий в одиночку, означает само место, а не поле, и
    # именем поля стать не должен.
    assert (
        _first_issue(
            [{"loc": ("body",), "msg": "x", "type": "model_type"}],
            strip_marker=True,
        )["field"]
        is None
    )


def test_plain_validation_error_keeps_field_name():
    # У голого ValidationError маркера места нет, и снятие головы съело бы
    # настоящее имя поля.
    class Search(BaseModel):
        query: str = Field(min_length=1)

    try:
        Search(query="")
    except ValidationError as error:
        envelope = validation_error_to_envelope(error)
    else:
        pytest.fail("модель обязана была отвергнуть значение")
    assert envelope["field"] == "query"


def test_lone_surrogate_does_not_break_response():
    # Одинокий суррогат приходит из тела запроса, а Starlette сериализует
    # ответ без экранирования — построение ответа падало UnicodeEncodeError
    # внутри самого обработчика, превращая отказ 400 в 500.
    bad = json.loads('"\\ud800"')
    envelope = _first_issue(
        [{"loc": ("body", "title"), "msg": f"Плохо: {bad}", "type": "value_error"}],
        strip_marker=True,
    )
    JSONResponse(content=envelope)  # не должно бросать


def test_pydantic_message_translated():
    # Человек читает именно это сообщение, а pydantic пишет по-английски.
    assert (
        _first_issue(
            [{"loc": ("body", "login"), "msg": "Field required", "type": "missing"}],
            strip_marker=True,
        )["error"]
        == "Обязательное поле"
    )


def test_unknown_type_message_passed_through():
    # Незнакомый тип отдаётся как есть: неудобный английский лучше, чем
    # потерянная причина.
    assert (
        _first_issue(
            [{"loc": ("body", "x"), "msg": "Something odd", "type": "чужой_тип"}],
            strip_marker=True,
        )["error"]
        == "Something odd"
    )
