import pytest
from sqlalchemy.exc import OperationalError

from app.features.meta import router as meta


async def test_health_is_open_and_touches_db(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_answers_503_when_database_is_down(client, session, monkeypatch):
    # Ради этой ветки проверка и ходит в базу. Без неё маршрут отвечает 200
    # при недоступной базе, доставка объявляет контур живым, и человек
    # узнаёт правду от первого пользователя.
    #
    # Мутация «убрать session.execute» оставляет тест на счастливый путь
    # зелёным: он подтверждает только то, что процесс жив.
    async def broken(*args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", None, Exception("база недоступна"))

    monkeypatch.setattr(session, "execute", broken)
    response = await client.get("/api/health")
    assert response.status_code == 503


def test_repo_root_points_at_the_repository():
    # parents[4] — счёт уровней вручную, и он ломается молча: при переезде
    # файла на уровень глубже все документы начинают отвечать «не найден», а
    # искать причину будут в списке разрешённых имён.
    assert (meta.REPO_ROOT / "backend" / "pyproject.toml").exists()


async def test_build_info_is_open(client):
    response = await client.get("/api/meta/build-info")
    assert response.status_code == 200
    assert "commit" in response.json()


async def test_docs_requires_login(client):
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 401


async def test_docs_returns_markdown(client, login_as, monkeypatch, tmp_path):
    # Файл подставляется временный. Настоящие AGENTS.md и docs/commands/*
    # появляются в задачах 38–39, а чтение документа проверяется здесь — и
    # проверка не должна зависеть от того, что лежит в репозитории сегодня:
    # тест на содержимое чужого файла ломается при первой же его правке и
    # при этом ничего не говорит об этом обработчике.
    document = tmp_path / "AGENTS.md"
    document.write_text("# Правила\n", encoding="utf-8")
    monkeypatch.setitem(meta.DOCUMENTS, "agents", document)
    await login_as()
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 200
    assert response.json()["content"] == "# Правила\n"


async def test_known_name_without_file_is_404(client, login_as, monkeypatch, tmp_path):
    # Имя из списка разрешённых есть, а файла на диске нет: так выглядит
    # документ, который ещё не написан или переименован. Ответ — 404, а не
    # пятисотка от чтения несуществующего пути.
    monkeypatch.setitem(meta.DOCUMENTS, "agents", tmp_path / "нет-такого.md")
    await login_as()
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        # Первым — единственное имя, которое различает реализации. Остальные
        # четыре отвергаются по посторонним причинам: `../` схлопывает сам
        # клиент ещё до запроса, имя со слэшем не подходит под сегмент пути,
        # а `secrets` и путь на два уровня вверх просто не существуют на
        # диске. Проверено мутацией: с именем, склеенным в путь, все четыре
        # оставались зелёными — то есть охраняли пустое место.
        #
        # `.env` лежит в корне репозитория и содержит секрет подписи сессий.
        # Со списком разрешённых имён он отвергается до входа в обработчик;
        # со склейкой — читается и уходит в ответ целиком.
        ".env",
        "../../.env",
        "..%2F..%2F.env",
        "secrets",
        "agents/../../.env",
    ],
)
async def test_unknown_document_rejected(client, login_as, name):
    # Имя документа не превращается в путь: список разрешённых задан явно.
    # Иначе первый же ../ отдал бы .env с секретом подписи наружу.
    await login_as()
    response = await client.get(f"/api/meta/docs/{name}")
    assert response.status_code in (404, 400)
