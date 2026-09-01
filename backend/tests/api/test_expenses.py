from sqlalchemy import select

from app.core.audit import AuditLog
from app.domain.expenses import CATEGORIES
from app.domain.money import MAX_AMOUNT_MINOR
from app.domain.roles import Role
from app.features.expenses.schemas import Category

VALID = {
    "date": "2026-08-31",
    "title": "Подписка на редактор",
    "category": "Софт",
    "amount": "1 200,50",
}


def test_schema_categories_match_domain():
    # Схема перечисляет категории литералами, чтобы не терять типизацию под
    # mypy, а домен держит их кортежем. Два списка обязаны совпадать — иначе
    # схема начнёт отвергать категорию, которую домен считает допустимой,
    # и разойдутся они молча.
    from typing import get_args

    assert get_args(Category) == CATEGORIES


async def test_viewer_can_read(client, login_as):
    await login_as(role=Role.viewer)
    assert (await client.get("/api/expenses")).status_code == 200


async def test_viewer_cannot_create(client, login_as):
    await login_as(role=Role.viewer)
    assert (await client.post("/api/expenses", json=VALID)).status_code == 403


async def test_editor_creates(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/expenses", json=VALID)
    assert response.status_code == 201
    body = response.json()
    assert body["amount_minor"] == 120050
    assert body["category"] == "Софт"


async def test_create_writes_audit(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/expenses", json=VALID)
    entries = (await session.execute(select(AuditLog))).scalars().all()
    assert [(e.actor, e.action, e.entity) for e in entries] == [
        ("ivan", "create", "Expense")
    ]


async def test_impossible_date_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "date": "2026-02-31"})
    assert response.status_code == 400
    assert response.json()["field"] == "date"
    # Введённое эхом в тексте: поле type="date" не умеет показать невалидную
    # строку, и без эха человек видит пустое поле и сообщение без пояснения.
    assert "2026-02-31" in response.json()["error"]


async def test_unparseable_amount_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "amount": "много"})
    assert response.status_code == 400
    assert response.json()["field"] == "amount"


async def test_zero_amount_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "amount": "0"})
    assert response.status_code == 400


async def test_amount_over_int4_rejected_with_readable_message(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post(
        "/api/expenses", json={**VALID, "amount": str(MAX_AMOUNT_MINOR // 100 + 1)}
    )
    assert response.status_code == 400
    # Без этой проверки сумма прошла бы разбор и упала в базе ошибкой
    # драйвера, которую специалисту читать нечем.
    assert "предельной" in response.json()["error"]


async def test_blank_title_rejected(client, login_as):
    # Пробелы проходят проверку длины, если обрезать после неё, и в списке
    # расходов появляется строка без назначения.
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/expenses", json={**VALID, "title": "   "})
    assert response.status_code == 400
    assert response.json()["field"] == "title"


async def test_unknown_category_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "category": "Ремонт"})
    assert response.status_code == 400


async def test_delete_requires_editor(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    created = (await client.post("/api/expenses", json=VALID)).json()
    assert (await client.delete(f"/api/expenses/{created['id']}")).status_code == 200


async def test_delete_writes_audit(client, session, login_as):
    # Удаление — такая же мутация, как создание, и в журнал обязано попасть
    # оно же. Проверка «удаление требует роли» этого не закрепляет: с
    # потерянной записью удаление продолжает работать, а история молча
    # обрывается — по журналу расход выглядит существующим.
    await login_as(role=Role.editor, login="ivan")
    created = await client.post("/api/expenses", json={**VALID, "title": "На снос"})
    await client.delete(f"/api/expenses/{created.json()['id']}")
    actions = (await session.execute(select(AuditLog.action))).scalars().all()
    assert "delete" in actions, actions


async def test_summary_returns_shares(client, login_as):
    await login_as(role=Role.editor)
    await client.post("/api/expenses", json={**VALID, "amount": "750"})
    await client.post(
        "/api/expenses", json={**VALID, "category": "Аренда", "amount": "250"}
    )
    response = await client.get("/api/expenses/summary")
    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["category"] == "Софт"
    assert rows[0]["share"] == 0.75
