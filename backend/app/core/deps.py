"""Проверка сессии и роли.

Каждый роутер проверяет роль сам — включая маршруты, куда интерфейс не
ведёт. Клиентский гейт в SPA только показывает форму входа вместо пустого
экрана; защита живёт здесь.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.security import AUTH_COOKIE, verify_session_token
from app.domain.roles import Role, has_rank
from app.features.users.models import User, UserStatus

logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: str
    login: str
    name: str
    role: Role


async def get_current_user(
    session: SessionDep,
    app_session: Annotated[str | None, Cookie(alias=AUTH_COOKIE)] = None,
) -> CurrentUser:
    claims = verify_session_token(app_session, settings.app_auth_secret)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")
    login, issued_at_ms = claims

    user = (
        await session.execute(select(User).where(User.login == login))
    ).scalar_one_or_none()
    if user is None or user.status is not UserStatus.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")

    # Отзыв сессий: подпись у отозванной куки остаётся верной, поэтому
    # проверка обязана быть здесь, а не в проверке подписи.
    #
    # issued_at_ms уже в миллисекундах. Лишнее умножение на 1000 сделало бы
    # условие невыполнимым при любых данных, и отключение учётной записи
    # перестало бы выгонять, продолжая выглядеть сделанным.
    if user.sessions_valid_from is not None:
        valid_from_ms = user.sessions_valid_from.timestamp() * 1000
        if issued_at_ms < valid_from_ms:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия отозвана")

    return CurrentUser(
        id=str(user.id), login=user.login, name=user.name, role=user.role
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(minimum: Role) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Фабрика зависимости: не ниже указанной роли.

    Тип возврата выписан полностью, а не подавлен `# noqa`. Подавление тут
    не работает дважды: `ANN` в наборе правил не включён, поэтому ruff
    ругается уже на само подавление (RUF100), а mypy на комментарии ruff и
    вовсе не смотрит и требует аннотацию. Проверено — красными были оба.
    """

    async def dependency(user: CurrentUserDep) -> CurrentUser:
        if not has_rank(user.role, minimum):
            # В журнал аудита не пишем — там мутации данных, а это отказ. Но
            # в серверный лог попасть обязано: иначе о попытках обойти права
            # не узнает никто, а посмотреть их можно только через /logs.
            logger.warning(
                "доступ отклонён: %s (%s) требовалось %s",
                user.login,
                user.role.value,
                minimum.value,
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return dependency
