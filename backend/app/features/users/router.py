import uuid

from fastapi import APIRouter, Depends, status

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
    # Ни try, ни except: «записи нет» — своё исключение с обработчиком в
    # core/errors.py. Здесь стоял `except LookupError` с выносом `str(exc)`
    # наружу, и то и другое оказалось дорого: LookupError — предок KeyError
    # и IndexError, поэтому любой такой сбой внутри сервиса объявлялся «не
    # найдено», а текст чужого исключения уезжал клиенту. Воспроизведено на
    # строке с ролью, которой ещё нет в коде.
    user = await service.update_user(session, user_id, payload, actor.id, actor.login)
    return UserOut.model_validate(user)
