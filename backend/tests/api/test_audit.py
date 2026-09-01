from app.domain.roles import Role

EXPENSE = {
    "date": "2026-08-31",
    "title": "Подписка",
    "category": "Софт",
    "amount": "100",
}


async def test_audit_requires_admin(client, login_as):
    await login_as(role=Role.editor)
    assert (await client.get("/api/audit")).status_code == 403


async def test_admin_reads_journal(client, login_as):
    await login_as(role=Role.admin, login="boss")
    await client.post("/api/expenses", json=EXPENSE)
    response = await client.get("/api/audit")
    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["actor"] == "boss"
    assert rows[0]["action"] == "create"


async def test_limit_has_a_hard_ceiling(client, login_as):
    # Журнал растёт неограниченно, и запрос без предела однажды выгрузит в
    # память всю историю контура. Потолок стоит в объявлении параметра, и
    # без этой проверки его снятие проходит молча: на пустой базе разницы
    # не видно, а видно станет через год работы.
    await login_as(role=Role.admin, login="boss")
    assert (await client.get("/api/audit?limit=5000")).status_code == 400
    assert (await client.get("/api/audit?limit=0")).status_code == 400


async def test_newest_first(client, login_as):
    await login_as(role=Role.admin, login="boss")
    await client.post("/api/expenses", json={**EXPENSE, "title": "Первый"})
    await client.post("/api/expenses", json={**EXPENSE, "title": "Второй"})
    rows = (await client.get("/api/audit")).json()
    assert len(rows) == 2
    assert rows[0]["ts"] >= rows[1]["ts"]
