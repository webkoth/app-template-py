from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import static


def build(tmp_path: Path, monkeypatch) -> TestClient:
    # Сборки фронтенда во время прогона бэкенда нет, поэтому раздача
    # монтируется на подставной каталог. Иначе mount_frontend выходит по
    # первой же строке, и всё, что ниже, не проверяется вовсе.
    # exist_ok: проверка отдачи файла из assets кладёт его туда до вызова
    # build, и каталог к этому моменту уже есть.
    (tmp_path / "assets").mkdir(exist_ok=True)
    (tmp_path / "index.html").write_text("<!doctype html>окно", encoding="utf-8")
    monkeypatch.setattr(static, "DIST", tmp_path)

    app = FastAPI()

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    static.mount_frontend(app)
    return TestClient(app)


def test_unknown_path_gets_the_spa(tmp_path, monkeypatch):
    response = build(tmp_path, monkeypatch).get("/expenses/42")
    assert response.status_code == 200
    assert "окно" in response.text


def test_unknown_api_route_is_not_html(tmp_path, monkeypatch):
    # Перехватчик стоит последним и ловит всё, что не разобрали роутеры.
    # Отдать на несуществующий маршрут API страницу нельзя: клиент ждёт
    # JSON и покажет «неожиданный ответ» вместо честного 404, а искать
    # причину будут в клиенте.
    response = build(tmp_path, monkeypatch).get("/api/нет-такого")
    assert response.status_code == 404
    assert "<!doctype" not in response.text.lower()


def test_real_api_route_still_answers(tmp_path, monkeypatch):
    # Обратная сторона: перехватчик не должен съедать живые маршруты.
    response = build(tmp_path, monkeypatch).get("/api/health")
    assert response.json() == {"status": "ok"}


def test_file_from_the_build_is_served_as_itself(tmp_path, monkeypatch):
    # Vite кладёт в dist не только assets, но и всё содержимое public —
    # favicon, robots.txt, картинки — прямо в корень сборки. Без отдельной
    # ветки они попадали бы в перехватчик и получали index.html с кодом 200:
    # HTML вместо картинки, вкладка без значка и ни одной ошибки в консоли.
    (tmp_path / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    response = build(tmp_path, monkeypatch).get("/robots.txt")
    assert response.status_code == 200
    assert "User-agent" in response.text


def test_assets_are_served_by_the_mount(tmp_path, monkeypatch):
    # Монтирование /assets отдельным Mount снимает удаление: без него файл
    # подобрал бы перехватчик и вернул index.html с кодом 200 — то есть
    # страница грузилась бы, а скрипты молча не работали.
    (tmp_path / "assets").mkdir(exist_ok=True)
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    client = build(tmp_path, monkeypatch)
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text

    # Существующий файл отдаёт и перехватчик — ветка отдачи файла подобрала
    # бы его сама, и одной проверки выше мало: удаление монтирования её не
    # роняет. Различает реализации ОТСУТСТВУЮЩИЙ файл. StaticFiles отвечает
    # на него 404, перехватчик — index.html с кодом 200, и тогда тег script
    # получает HTML вместо кода: страница «грузится», приложение молчит, а в
    # консоли ошибка про MIME, по которой причину не найти.
    assert client.get("/assets/нет-такого.js").status_code == 404


def test_the_catch_all_stays_out_of_the_schema(tmp_path, monkeypatch):
    # Перехватчик в схеме означает маршрут `/{path:path}` в типах клиента:
    # он уедет туда молча и будет выглядеть частью API.
    # Ключ в схеме — `/{path}`, а не `/{path:path}`: FastAPI берёт
    # `route.path_format`, а тот преобразователь `:path` уже снял. Проверка
    # на исходную запись охраняла бы пустое место — такой строки в схеме не
    # бывает никогда, и снятие include_in_schema проходило бы молча.
    client = build(tmp_path, monkeypatch)
    assert "/{path}" not in client.app.openapi()["paths"]


def test_the_catch_all_is_registered_after_the_api(tmp_path, monkeypatch):
    # Порядок монтирования в main.py несущий: перехватчик обязан стоять
    # после всех роутеров. Пока сборки фронтенда нет, перестановка ничего не
    # меняет — mount_frontend выходит первой строкой, — и мутация проходит
    # молча. На контуре, где сборка есть, та же перестановка отвечает 404 на
    # КАЖДЫЙ маршрут API: проверено, падают 36 тестов.
    #
    # Поэтому приложение собирается здесь заново, с подложенным каталогом
    # сборки, — и проверяется само расположение маршрута.
    (tmp_path / "assets").mkdir(exist_ok=True)
    (tmp_path / "index.html").write_text("<!doctype html>окно", encoding="utf-8")
    monkeypatch.setattr(static, "DIST", tmp_path)

    from app.main import create_app

    paths = [getattr(route, "path", "") for route in create_app().routes]
    assert paths[-1] == "/{path:path}", paths[-3:]


async def _ask(app: FastAPI, path: str) -> bytes:
    """Запрос прямо в ASGI, минуя нормализацию клиента.

    Через TestClient такую проверку не сделать: httpx схлопывает `../` ещё
    до отправки, и проверялся бы клиент, а не приложение. uvicorn путь не
    схлопывает — только раскодирует %2F в разделитель. Сверено с живым
    сервером: `GET /../../.env` доходит до обработчика как есть.
    """
    chunks: list[bytes] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message) -> None:
        if message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"test")],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    return b"".join(chunks)


async def test_the_build_is_not_a_way_out_of_the_directory(tmp_path, monkeypatch):
    # Ветка отдачи файла склеивает путь из запроса — то есть открывает диск.
    # Держит её только проверка на принадлежность DIST, и без этой проверки
    # `GET /../../.env` отдаёт наружу секрет подписи сессий целиком: на
    # контуре .env лежит в корне репозитория, ровно двумя уровнями выше
    # dist. Воспроизведено на живом uvicorn — утекает, код 200.
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>окно", encoding="utf-8")
    (tmp_path / ".env").write_text("APP_AUTH_SECRET=секрет-подписи", encoding="utf-8")
    monkeypatch.setattr(static, "DIST", dist)

    app = FastAPI()
    static.mount_frontend(app)

    # Пути уже раскодированы — ровно в таком виде их отдаёт uvicorn, %2F он
    # разворачивает в разделитель сам.
    for target in [
        "/../.env",
        "/../../.env",
        "/./../../.env",
        "/assets/../../.env",
        "/index.html/../../.env",
    ]:
        body = await _ask(app, target)
        assert b"APP_AUTH_SECRET" not in body, target
