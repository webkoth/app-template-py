"""Учётные записи приложения. Вход только собственный.

Модель лежит в `core`, а не в `features/users/`, по той же причине, что и
журнал аудита: её читает `core/deps.py` на каждом запросе, чтобы узнать
роль и статус. Оставь она в фиче — и `core` начал бы зависеть от
`features`, то есть слой основы от слоя фич. Заодно это ломало бы контракт
независимости: путь от любой фичи к `require_role` шёл бы через
`features.users`, и import-linter справедливо считал бы это связью между
фичами. Воспроизведено.

Фиче остаётся то, что и должно, — экран и правила: router, service,
schemas.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints
from sqlalchemy import DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.roles import Role
from app.domain.text import no_control_characters


class UserStatus(StrEnum):
    active = "active"
    disabled = "disabled"


LOGIN_MAX_LENGTH = 255


def _fits_the_column(login: str) -> str:
    """Проверяет длину ПОСЛЕ приведения регистра.

    max_length у StringConstraints считается до приведения, а приведение
    длину меняет: 200 турецких «İ» (U+0130) проверку проходят и превращаются
    в 400 символов — lower() раскладывает каждую букву на две.
    Воспроизведено.

    Сегодня такой логин только не нашёлся бы в базе (вход делает SELECT), но
    тот же тип берёт создание учётной записи, и там это
    StringDataRightTruncation: пятисотка вместо отказа формы, а SQL с
    параметрами уезжает в лог. Без этой проверки обещание ниже — «правило
    описывает ровно ту колонку, рядом с которой лежит» — попросту неверно.
    """
    if len(login) > LOGIN_MAX_LENGTH:
        # Текст по-русски и без значения: обработчик ошибок отдаёт его
        # человеку как есть (см. _VALUE_ERROR_PREFIX в core/errors.py).
        raise ValueError("Слишком длинное значение")
    return login


# Один вид логина на всё приложение.
#
# Тип лежит в `core`, а не в фиче входа, потому что его берут обе фичи —
# и вход, и учётные записи, — а импорт одной фичи из другой import-linter
# считает нарушением границы между ними. Место выбрано не наугад: правило
# описывает ровно ту колонку, рядом с которой лежит.
#
# Приведение к нижнему регистру. Без него `Иван` и `иван` — две разные
# учётные записи с общим бюджетом попыток: счётчик в `core/rate_limit.py`
# ключи casefold-ит, а поиск пользователя в базе регистр различает. Одно из
# двух обязано уступить, и уступает логин — у casefold в счётчике своё
# обоснование, без него пятибуквенный логин даёт 32 корзины вместо одной.
# Заодно логин, набранный не в том регистре, перестаёт молча не подходить.
#
# `^\S+$` — без пробельных символов: перевод строки внутри сломал бы разбор
# токена, и такой пользователь молча не смог бы войти. Управляющие символы
# этим шаблоном НЕ отсеиваются: NUL — не пробельный символ, и `\S` его
# пропускает. Отсюда отдельный no_control_characters — тот же, что и у
# обычного текста; без него логин с NUL доходит до вставки, PostgreSQL его
# не принимает, и отказ формы превращается в пятисотку с хешем пароля в
# трейсбеке.
#
# Длина проверяется отдельным валидатором — после приведения, а не до; см.
# _fits_the_column.
Login = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        pattern=r"^\S+$",
    ),
    AfterValidator(_fits_the_column),
    AfterValidator(no_control_characters),
    # Предел объявляется в схеме отдельно, потому что проверяет его валидатор
    # выше, а не StringConstraints. Описание схемы уходит в типы клиента, и
    # без этой строки форма не знает, на чём обрывать ввод.
    Field(json_schema_extra={"maxLength": LOGIN_MAX_LENGTH}),
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    # Длина колонки и предел в типе — один литерал. Разъедься они, и
    # значение, прошедшее проверку, база отказалась бы принимать.
    login: Mapped[str] = mapped_column(
        String(LOGIN_MAX_LENGTH), unique=True, index=True
    )
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
