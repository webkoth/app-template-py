"""Правила работы с учётными записями."""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import RuleViolation
from app.core.security import hash_password
from app.core.users import User, UserStatus
from app.domain.roles import Role
from app.features.users.schemas import CreateUserRequest, UpdateUserRequest


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


LOGIN_TAKEN = "Такой логин уже занят"


async def login_taken(session: AsyncSession, login: str) -> bool:
    """Занят ли логин. Отдельной функцией — чтобы её можно было обойти в тесте."""
    return (
        await session.execute(select(User.id).where(User.login == login))
    ).first() is not None


async def create_user(
    session: AsyncSession, payload: CreateUserRequest, actor: str
) -> User:
    if await login_taken(session, payload.login):
        # Проверка до вставки: до человека доходит понятное сообщение с именем
        # поля, а не текст драйвера. Но настоящий охранник тут не она.
        raise RuleViolation(LOGIN_TAKEN, field="login")

    user = User(
        login=payload.login,
        name=payload.name,
        role=payload.role,
        # В пул потоков: scrypt считается около 25 мс сплошного счёта и
        # прямым вызовом заморозил бы цикл событий вместе со всеми
        # остальными запросами.
        password_hash=await asyncio.to_thread(hash_password, payload.password),
        created_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        # flush, а не commit: нужен id для записи в журнал, но транзакция
        # обязана остаться одной на мутацию вместе с аудитом.
        await session.flush()
    except IntegrityError as clash:
        # Настоящий охранник — уникальный индекс, и проверка выше только
        # делает его сообщение человеческим. Между проверкой и вставкой стоит
        # await на scrypt: два одновременных запроса с одним логином проходят
        # проверку оба, и второй упирается уже в индекс. Без этой ветки
        # админ видит «Что-то пошло не так» вместо «логин занят», а в лог
        # уезжает трейсбек с текстом SQL — то есть охранник срабатывает и
        # выглядит поломкой.
        await session.rollback()
        raise RuleViolation(LOGIN_TAKEN, field="login") from clash
    write_audit(session, actor, "create", "User", str(user.id), payload.role.value)
    await session.commit()
    return user


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    actor_id: str,
    actor_login: str,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise LookupError("Учётная запись не найдена")

    changes: list[str] = []
    if payload.role is not None and payload.role is not user.role:
        if str(user.id) == actor_id and payload.role is not Role.admin:
            # Тот же запрет, что и на отключение себя, и по той же причине:
            # единственный администратор, понизивший себя до editor, запирает
            # контур — вернуть права будет некому. Отдельным правилом, а не
            # частью проверки статуса: понижение проходит мимо неё целиком, и
            # без этой ветки запрет выглядел бы поставленным, оставляя дверь
            # рядом открытой.
            raise RuleViolation(
                "Нельзя снять права администратора с самого себя", field="role"
            )
        user.role = payload.role
        changes.append(f"роль → {payload.role.value}")

    if payload.status is not None and payload.status is not user.status:
        if payload.status is UserStatus.disabled and str(user.id) == actor_id:
            # Отключив себя, администратор запирает контур: включить обратно
            # будет некому.
            raise RuleViolation("Нельзя отключить собственную запись", field="status")
        user.status = payload.status
        changes.append(f"статус → {payload.status.value}")
        if payload.status is UserStatus.disabled:
            # Отключение обязано отзывать уже выданные сессии: подпись куки
            # остаётся верной, и без отзыва человек работает дальше.
            user.sessions_valid_from = datetime.now(UTC)

    if not changes:
        raise RuleViolation("Менять нечего")

    write_audit(
        session, actor_login, "update", "User", str(user.id), ", ".join(changes)
    )
    await session.commit()
    return user
