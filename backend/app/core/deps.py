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
from app.core.users import User, UserStatus
from app.domain.roles import Role, has_rank

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
    # условие невыполнимым при любых данных, и отзыв сессий перестал бы
    # работать, продолжая выглядеть сделанным. Отключение учётной записи
    # при этом уцелеет — оно проверяется веткой выше и от множителя не
    # зависит; ошибка молчалива именно потому, что видимая часть защиты
    # продолжает действовать. Проверено мутацией в обе стороны: лишний
    # множитель здесь не выгоняет никого, лишний множитель на стороне
    # отметки выгоняет всех — второе заметили бы за минуту, первое нет.
    if user.sessions_valid_from is not None:
        valid_from_ms = user.sessions_valid_from.timestamp() * 1000
        if issued_at_ms < valid_from_ms:
            # Тот же текст, что и у прочих отказов входа. Отдельная
            # формулировка сообщала бы владельцу украденной куки, что
            # подпись верна, учётная запись существует и активна, а отказ —
            # из-за отзыва. Клиент всё равно ведёт на форму входа во всех
            # случаях, так что различать их незачем.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")

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
