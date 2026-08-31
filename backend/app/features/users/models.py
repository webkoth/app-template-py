"""Учётные записи приложения. Вход только собственный."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.roles import Role


class UserStatus(StrEnum):
    active = "active"
    disabled = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    login: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        # values_callable обязателен: без него SQLAlchemy пишет в базу ИМЕНА
        # членов enum, а не значения. Для StrEnum они совпадают, и ошибка
        # всплыла бы только после первого переименования члена.
        Enum(Role, name="role", values_callable=lambda e: [i.value for i in e])
    )
    # scrypt$<N>$<salt_hex>$<hash_hex>; NULL = вход невозможен.
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Отключение: вход закрыт, данные и журнал остаются. Удаления
    # пользователей нет намеренно — удалённый автор записи в журнале
    # превратил бы историю в набор осиротевших строк.
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=UserStatus.active,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Сессии, выданные раньше этой отметки, недействительны. NULL = не
    # отзывались.
    sessions_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
