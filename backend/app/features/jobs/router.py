import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.jobs import service

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Зависимость модульной переменной, как в остальных роутерах: вызов Depends
# прямо в значении по умолчанию — это B008 у ruff, и `make check` на нём
# красный.
ViewerDep = Depends(require_role(Role.viewer))


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    progress: int
    # Что задача просила сделать. В плане этого поля не было, и без него
    # десять строк «datasets.parse» на экране неразличимы: понять, КАКАЯ
    # таблица не разобралась, нельзя ни по чему. Кладёт сюда значения сама
    # фича, ставящая задачу, — и потому условие: в payload не кладут ничего,
    # что нельзя показать тому, кто задачу поставил.
    payload: dict[str, Any]
    result: dict[str, Any] | None
    # Причина отказа. Единственное место, кроме серверного лога, где она
    # вообще есть: упавший разбор оставляет таблицу со сводкой NULL, и на
    # экране таблиц это неотличимо от «считаем».
    error: str
    attempts: int
    actor: str
    created_at: datetime
    finished_at: datetime | None


@router.get("", response_model=list[JobOut])
async def list_jobs(
    session: SessionDep,
    limit: int = Query(default=service.DEFAULT_LIMIT, ge=1, le=service.MAX_LIMIT),
    user: CurrentUser = ViewerDep,
) -> list[JobOut]:
    # Свои задачи каждому, все — администратору. Это показ, а не защита:
    # фильтр стоит в запросе, а не в разметке, потому что «спрятать чужое»
    # на клиенте означает всё-таки его отдать.
    actor = None if user.role is Role.admin else user.login
    return [
        JobOut.model_validate(j) for j in await service.list_jobs(session, limit, actor)
    ]


@router.get("/health")
async def worker_health(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> dict[str, bool]:
    # Отдельный маршрут, а не поле в списке. Список отфильтрован по человеку
    # и обрезан пределом, а признак живости от того, чьи задачи смотрят, не
    # зависит вовсе — и нужен он как раз тогда, когда список пуст.
    return {"воркер_жив": await service.worker_is_alive(session)}
