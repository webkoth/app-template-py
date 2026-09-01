"""Правила работы с учётными записями."""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import RecordNotFound, RuleViolation
from app.core.security import hash_password
from app.core.users import User, UserStatus
from app.domain.roles import Role
from app.features.users.schemas import CreateUserRequest, UpdateUserRequest


async def list_users(session: AsyncSession) -> list[User]:
    # Второй ключ сортировки не украшение: created_at ставится в коде, и две
    # записи, заведённые в одну миллисекунду, иначе меняются местами от
    # запроса к запросу. Предела выборки здесь нет намеренно — это экран
    # «все учётные записи», и показать его частично хуже, чем показать
    # целиком: в приложении на десятки человек список конечен по существу.
    result = await session.execute(select(User).order_by(User.created_at, User.id))
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
    # Логин в записи журнала обязателен. Без него строка выглядит как
    # «boss | create | User | 01a0…| admin»: кому именно выдали права,
    # читается только сверкой UUID с живой базой — а журнал обещает быть
    # читаемым сам по себе и переживать учётную запись.
    write_audit(
        session,
        actor,
        "create",
        "User",
        str(user.id),
        f"{user.login}, роль {payload.role.value}",
    )
    await session.commit()
    return user


async def active_admins_besides(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Сколько активных администраторов останется, кроме этого.

    Читает С БЛОКИРОВКОЙ и НЕ исключает самого проверяемого из выборки —
    оба решения существенны. Два администратора, два одновременных запроса:
    A снимает права с B, B — с A. Оба прошли require_role до чужого commit,
    строки разные, конфликта нет — и контур остаётся без единого активного
    администратора. Воспроизведено; вернуть права после этого можно только
    прямым доступом к базе.

    Блокировка по одному и тому же набору строк заставляет запросы встать в
    очередь, а PostgreSQL после снятия блокировки перепроверяет условие: тот,
    кто пришёл вторым, уже не увидит понижённого первым.
    """
    rows = await session.execute(
        select(User.id)
        .where(User.role == Role.admin, User.status == UserStatus.active)
        .with_for_update()
    )
    return len([row for row in rows.scalars().all() if row != user_id])


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    actor_id: str,
    actor_login: str,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise RecordNotFound("Учётная запись не найдена")

    # Пустое тело — не то же самое, что повтор уже применённого изменения.
    # Первое означает, что запрос собран неверно; второе — двойной клик или
    # повтор после обрыва связи, и красное на него человек видеть не должен.
    if not payload.model_fields_set:
        raise RuleViolation("Менять нечего")

    losing_admin = (
        user.role is Role.admin
        and user.status is UserStatus.active
        # Про себя ниже стоят два отдельных запрета, и они точнее: у них есть
        # имя поля и текст про «самого себя». Без этого условия инвариант
        # срабатывает первым и отвечает «Это последний администратор контура»
        # без поля — test_cannot_demote_self это и поймал. Заодно единственный
        # админ, понижающий себя, доходил бы до инварианта ОДНИМ запросом, а
        # тот существует ради одновременных: см. active_admins_besides.
        and str(user.id) != actor_id
        and (
            (payload.role is not None and payload.role is not Role.admin)
            or payload.status is UserStatus.disabled
        )
    )
    if losing_admin and await active_admins_besides(session, user.id) == 0:
        raise RuleViolation("Это последний администратор контура")

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
        # Прежнее значение записывается вместе с новым: «роль → admin» не
        # отвечает на вопрос, что именно поменялось, а журнал читают спустя
        # месяцы и без базы под рукой.
        changes.append(f"роль {user.role.value} → {payload.role.value}")
        user.role = payload.role

    if payload.status is not None and payload.status is not user.status:
        if payload.status is UserStatus.disabled and str(user.id) == actor_id:
            # Отключив себя, администратор запирает контур: включить обратно
            # будет некому.
            raise RuleViolation("Нельзя отключить собственную запись", field="status")
        changes.append(f"статус {user.status.value} → {payload.status.value}")
        user.status = payload.status
        if payload.status is UserStatus.disabled:
            # Отключение обязано отзывать уже выданные сессии: подпись куки
            # остаётся верной, и без отзыва человек работает дальше.
            user.sessions_valid_from = datetime.now(UTC)

    if not changes:
        # Просили то, что уже так. Это не ошибка: повтор запроса обязан быть
        # безвредным. Записи в журнале при этом нет — записывать нечего.
        return user

    write_audit(
        session,
        actor_login,
        "update",
        "User",
        str(user.id),
        f"{user.login}: " + ", ".join(changes),
    )
    await session.commit()
    return user
