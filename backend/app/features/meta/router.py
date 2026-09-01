"""Служебные маршруты: живость, версия сборки, тексты правил для /docs."""

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.deps import CurrentUserDep, SessionDep

router = APIRouter(tags=["meta"])

# Корень репозитория: app/features/meta/router.py → четыре уровня вверх.
REPO_ROOT = Path(__file__).resolve().parents[4]

# Список разрешённых документов задан явно, а имя НЕ превращается в путь.
# Любая склейка вида REPO_ROOT / name отдала бы .env с секретом подписи по
# первому же ../ в запросе.
DOCUMENTS: dict[str, Path] = {
    "agents": REPO_ROOT / "AGENTS.md",
    "checklist": REPO_ROOT / "CHECKLIST.md",
    "onboarding": REPO_ROOT / "docs" / "commands" / "onboarding.md",
    "ship": REPO_ROOT / "docs" / "commands" / "ship.md",
    "status": REPO_ROOT / "docs" / "commands" / "status.md",
    "logs": REPO_ROOT / "docs" / "commands" / "logs.md",
    "rollback": REPO_ROOT / "docs" / "commands" / "rollback.md",
}

DocumentName = Literal[
    "agents", "checklist", "onboarding", "ship", "status", "logs", "rollback"
]


class Health(BaseModel):
    status: Literal["ok"]


class BuildInfo(BaseModel):
    commit: str
    built_at: str


class Document(BaseModel):
    name: str
    content: str


@router.get("/health", response_model=Health)
async def health(session: SessionDep) -> Health:
    """Единственный маршрут без авторизации.

    Ходит в базу намеренно: проверка, которая отвечает 200 при недоступной
    базе, подтверждает только то, что процесс жив, — а доставка на основании
    такой проверки объявляет успешной заведомо нерабочий контур.

    Сбой базы ловится и превращается в 503, а не летит наверх пятисоткой.
    Три причины, и ни одна не про красоту кода. 503 — это «сервис временно
    недоступен», ровно то, что произошло, и балансировщик с монитором
    понимают его без объяснений. Пятисотка же означает «в коде что-то
    сломалось» и тянет за собой трейсбек в лог на КАЖДУЮ проверку живости —
    а ходит она раз в несколько секунд, и настоящая ошибка утонет. И
    третье: ветку отказа можно проверить тестом только если она отвечает, а
    не выбрасывает.

    Доставка ждёт ровно 200, так что 503 её по-прежнему останавливает.
    """
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "База данных недоступна"
        ) from error
    return Health(status="ok")


@router.get("/meta/build-info", response_model=BuildInfo)
async def build_info() -> BuildInfo:
    """Версия доставленного кода. Пишется при сборке, читается с диска."""
    marker = REPO_ROOT / "build-info.json"
    if not marker.exists():
        return BuildInfo(commit="dev", built_at="")
    data = json.loads(marker.read_text(encoding="utf-8"))
    return BuildInfo(
        commit=data.get("commit", "dev"), built_at=data.get("built_at", "")
    )


@router.get("/meta/docs/{name}", response_model=Document)
async def document(name: DocumentName, user: CurrentUserDep) -> Document:
    """Отдаёт текст правил или команды. Читает файлы репозитория с диска."""
    path = DOCUMENTS[name]
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return Document(name=name, content=path.read_text(encoding="utf-8"))
