"""Раздача собранного фронтенда.

FastAPI отдаёт и API, и статику: так vhost остаётся чистым proxy_pass, и
общий app-provision, которым пользуется и TS-шаблон, не требует правок.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    if not DIST.exists():
        # В разработке фронтенд поднимает Vite на своём порту, сборки нет.
        return

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        # Маршруты SPA не существуют на диске: любой неизвестный путь отдаёт
        # index.html, и дальше решает роутер в браузере.
        #
        # /api сюда не попадает: роутеры примонтированы раньше, и FastAPI
        # выбирает первое совпадение. Но если запрос всё же дошёл — это
        # несуществующий маршрут API, и отдавать на него HTML нельзя:
        # клиент ждёт JSON и покажет «неожиданный ответ» вместо 404.
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Маршрут не найден")
        return FileResponse(DIST / "index.html")
