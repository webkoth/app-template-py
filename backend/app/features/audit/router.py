import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.audit import service

router = APIRouter(prefix="/audit", tags=["audit"])

# Зависимость вынесена в модульную переменную, как в остальных роутерах:
# вызов Depends прямо в значении по умолчанию — это B008 у ruff, и
# `make check` на нём красный.
AdminDep = Depends(require_role(Role.admin))


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # uuid.UUID, а не str. Pydantic строку из UUID сам не делает — проверено:
    # model_validate падает с «Input should be a valid string». В JSON поле
    # всё равно уезжает строкой, а в схеме OpenAPI получает format: uuid, то
    # есть клиент видит тот же string.
    id: uuid.UUID
    ts: datetime
    actor: str
    action: str
    entity: str
    entity_id: str
    detail: str


@router.get("", response_model=list[AuditEntryOut])
async def list_entries(
    session: SessionDep,
    limit: int = Query(default=service.DEFAULT_LIMIT, ge=1, le=service.MAX_LIMIT),
    _: CurrentUser = AdminDep,
) -> list[AuditEntryOut]:
    return [
        AuditEntryOut.model_validate(e)
        for e in await service.list_entries(session, limit)
    ]
