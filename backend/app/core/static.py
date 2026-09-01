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

        # Файл с таким именем в сборке — отдаём его. Монтирования /assets
        # мало: Vite кладёт в dist ещё и всё содержимое public — favicon,
        # robots.txt, картинки, — а они лежат в корне сборки, а не в assets.
        # Без этой ветки запрос на /favicon.ico получал бы index.html с
        # кодом 200, то есть HTML вместо картинки, и вкладка оставалась бы
        # без значка без единой ошибки в консоли.
        #
        # Путь склеивается из запроса, то есть эта ветка открывает диск, и
        # держит её ровно одна проверка — принадлежность DIST после resolve.
        # Без неё `GET /../../.env` отдаёт наружу секрет подписи сессий: на
        # контуре .env лежит в корне репозитория, ровно двумя уровнями выше
        # dist. Воспроизведено на живом uvicorn — утекает, код 200; uvicorn
        # путь не схлопывает и %2F раскодирует сам. Обращение к каталогу
        # уходит в index.html как обычный маршрут SPA.
        candidate = (DIST / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)

        return FileResponse(DIST / "index.html")
