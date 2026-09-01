from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import static


def build(tmp_path: Path, monkeypatch) -> TestClient:
    # Сборки фронтенда во время прогона бэкенда нет, поэтому раздача
    # монтируется на подставной каталог. Иначе mount_frontend выходит по
    # первой же строке, и всё, что ниже, не проверяется вовсе.
    (tmp_path / "assets").mkdir()
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
