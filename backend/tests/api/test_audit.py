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


async def test_limit_actually_limits(client, login_as):
    # Потолок был доказан только объявлением параметра: что запрос его
    # ПРИМЕНЯЕТ, не проверяло ничто — удаление `.limit(limit)` из сервиса
    # проходило молча. А смысл потолка именно в применении: без него запрос
    # однажды выгрузит в память всю историю контура.
    await login_as(role=Role.admin, login="boss")
    for title in ["Первый", "Второй", "Третий"]:
        await client.post("/api/expenses", json={**EXPENSE, "title": title})
    assert len((await client.get("/api/audit?limit=1")).json()) == 1


async def test_entry_carries_what_the_screen_shows(client, login_as):
    # Состав записи не проверял ничто: удаление detail из схемы оставляло
    # прогон зелёным. Экран журнала показывает именно эти колонки, а detail
    # — единственное, по чему через год поймут, что произошло.
    await login_as(role=Role.admin, login="boss")
    await client.post("/api/expenses", json=EXPENSE)
    row = (await client.get("/api/audit")).json()[0]
    assert row["entity"] == "Expense"
    assert row["entity_id"]
    assert "Софт" in row["detail"]


async def test_limit_refusal_speaks_russian(client, login_as):
    # Отказ по границе уходил клиенту по-английски: «Input should be greater
    # than or equal to 1». ge/le дают СВОИ типы ошибки, которых не было в
    # таблице переводов, и разница вылезла на первом же их применении.
    # Проверка кода ответа этого не видит — человек видит.
    await login_as(role=Role.admin, login="boss")
    body = (await client.get("/api/audit?limit=0")).json()
    assert body["field"] == "limit"
    assert body["error"] == "Значение слишком мало"
    assert (await client.get("/api/audit?limit=5000")).json()["error"] == (
        "Значение слишком велико"
    )


async def test_interactive_docs_are_off(client, login_as):
    # Страницы FastAPI выключены намеренно: на контуре они висели бы
    # открытым описанием API. Решение принято в задаче 17 и не проверялось
    # ничем — во всём наборе тестов не было ни одного упоминания /docs.
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/redoc")).status_code == 404


async def test_schema_describes_the_api(client):
    # Из этой схемы генерируются типы клиента. Пустая или неполная схема
    # означает молча пропавшие маршруты на фронтенде — а `make check-openapi`
    # ловит только расхождение с уже сгенерированным файлом.
    from app.main import app

    paths = app.openapi()["paths"]
    for path in ["/api/health", "/api/auth/login", "/api/users", "/api/expenses"]:
        assert path in paths, sorted(paths)
