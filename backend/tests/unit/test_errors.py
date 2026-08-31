import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError

from app.core.errors import (
    FALLBACK_MESSAGE,
    RuleViolation,
    _first_issue,
    register_error_handlers,
    validation_error_to_envelope,
)

SURROGATE_JSON = '"\\ud800"'


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


class TestRegisteredHandlers:
    """Проверки на настоящем приложении.

    Половина модуля — обработчики, и раньше она не была покрыта ничем: все
    четыре дефекта, найденных ревью, жили именно в ней.
    """

    @staticmethod
    def build() -> TestClient:
        app = FastAPI()
        register_error_handlers(app)

        class Body(BaseModel):
            title: str = Field(min_length=1)

        @app.post("/rule")
        async def rule(payload: dict) -> None:
            raise RuleViolation(payload.get("text", ""), field=payload.get("field"))

        @app.get("/surrogate")
        async def surrogate() -> None:
            # Суррогат подаётся со стороны сервера: через тело запроса его
            # не отправить, клиент сам не может его закодировать. В жизни
            # он попадает сюда из уже разобранных данных.
            bad = json.loads(SURROGATE_JSON)
            raise RuleViolation(f"Плохо: {bad}", field=f"поле{bad}")

        @app.post("/schema")
        async def schema(body: Body) -> dict:
            return {"ok": True}

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError(
                "postgresql://user:пароль@10.0.0.5/prod /var/www/app/secret.py"
            )

        # raise_server_exceptions=False обязателен: иначе Starlette
        # перебрасывает исходное исключение, и ответ 500 не увидеть.
        return TestClient(app, raise_server_exceptions=False)

    def test_rule_violation_answers_envelope(self):
        response = self.build().post("/rule", json={"text": "Так нельзя", "field": "x"})
        assert response.status_code == 400
        assert response.json() == {"error": "Так нельзя", "field": "x"}

    def test_surrogate_in_field_does_not_break_response(self):
        # Текст был защищён, а соседний аргумент в той же строке — нет, и
        # незащищённый суррогат в имени поля ронял построение ответа: отказ
        # 400 превращался в 500 внутри самого обработчика ошибок.
        response = self.build().get("/surrogate")
        assert response.status_code == 400
        assert response.json()["field"] is not None

    def test_empty_message_falls_back(self):
        response = self.build().post("/rule", json={"text": ""})
        assert response.json()["error"] == FALLBACK_MESSAGE

    def test_schema_error_answers_400_not_422(self):
        response = self.build().post("/schema", json={"title": ""})
        assert response.status_code == 400
        assert response.json()["field"] == "title"

    def test_unparseable_body_answers_envelope(self):
        # Непарсимое тело идёт не через HTTPException, а через ошибку
        # разбора схемы с типом json_invalid — и получает переведённый
        # текст. Проверяется здесь другое: что смещение в байтах, которое
        # лежит в loc вместо имени поля, не становится этим именем.
        response = self.build().post(
            "/schema",
            content=b"{not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert set(response.json()) == {"error", "field"}
        # Смещение в байтах не должно становиться именем поля.
        assert response.json()["field"] is None

    def test_not_found_answers_envelope(self):
        response = self.build().get("/нет-такого")
        assert response.status_code == 404
        assert set(response.json()) == {"error", "field"}

    def test_unexpected_failure_leaks_nothing(self):
        response = self.build().get("/boom")
        assert response.status_code == 500
        body = response.text
        for secret in ("пароль", "10.0.0.5", "/var/www", "postgresql"):
            assert secret not in body
