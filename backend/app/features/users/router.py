import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.users import service
from app.features.users.schemas import CreateUserRequest, UpdateUserRequest, UserOut

router = APIRouter(prefix="/users", tags=["users"])

AdminDep = Depends(require_role(Role.admin))


@router.get("", response_model=list[UserOut])
async def list_users(session: SessionDep, _: CurrentUser = AdminDep) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await service.list_users(session)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest, session: SessionDep, actor: CurrentUser = AdminDep
) -> UserOut:
    return UserOut.model_validate(
        await service.create_user(session, payload, actor.login)
    )


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    session: SessionDep,
    actor: CurrentUser = AdminDep,
) -> UserOut:
    try:
        user = await service.update_user(
            session, user_id, payload, actor.id, actor.login
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return UserOut.model_validate(user)
