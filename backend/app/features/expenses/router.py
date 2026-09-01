import uuid

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.expenses import service
from app.features.expenses.schemas import (
    CategoryTotalOut,
    CreateExpenseRequest,
    ExpenseOut,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])

ViewerDep = Depends(require_role(Role.viewer))
EditorDep = Depends(require_role(Role.editor))


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> list[ExpenseOut]:
    return [ExpenseOut.model_validate(e) for e in await service.list_expenses(session)]


@router.get("/summary", response_model=list[CategoryTotalOut])
async def summary(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> list[CategoryTotalOut]:
    return [
        CategoryTotalOut(category=t.category, total_minor=t.total_minor, share=t.share)
        for t in await service.summary(session)
    ]


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: CreateExpenseRequest, session: SessionDep, actor: CurrentUser = EditorDep
) -> ExpenseOut:
    return ExpenseOut.model_validate(
        await service.create_expense(session, payload, actor.login)
    )


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: uuid.UUID, session: SessionDep, actor: CurrentUser = EditorDep
) -> dict[str, bool]:
    # Без try: «расхода нет» — своё исключение с обработчиком в
    # core/errors.py. `except LookupError` ловил бы заодно KeyError и
    # IndexError изнутри сервиса и объявлял их отсутствием записи.
    await service.delete_expense(session, expense_id, actor.login)
    return {"ok": True}
