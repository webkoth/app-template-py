import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.users import Login, UserStatus
from app.domain.roles import Role

# Восемь символов — не про стойкость, а про то, чтобы не заводили «123».
# Настоящую защиту даёт ограничение попыток входа.
MIN_PASSWORD_LENGTH = 8


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # uuid.UUID, а не str. Pydantic строку из UUID сам не делает — проверено:
    # model_validate падает с «Input should be a valid string». В JSON поле
    # всё равно уезжает строкой, а в схеме OpenAPI получает format: uuid, то
    # есть клиент видит тот же string.
    id: uuid.UUID
    login: str
    name: str
    role: Role
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime


class CreateUserRequest(BaseModel):
    # Тот же тип, что и у формы входа: логин хранится в нижнем регистре,
    # иначе `Иван` и `иван` стали бы двумя записями с общим бюджетом попыток.
    login: Login
    # Обрезка ДО проверки длины. При `Field(min_length=1)` имя из одних
    # пробелов проходит проверку и ложится в базу пустым — в списке
    # пользователей такая строка выглядит как сбой отрисовки.
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    role: Role
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)

    @field_validator("password")
    @classmethod
    def _not_only_digits(cls, value: str) -> str:
        # Восьми символов мало, если все они цифры: дата рождения, телефон и
        # «12345678» проходят по длине и подбираются первыми. Запрет ровно
        # тот же, что в app-template-ts, и по той же причине.
        if value.isdigit():
            raise ValueError("Пароль из одних цифр не годится")
        return value


class UpdateUserRequest(BaseModel):
    """Частичное обновление: приходит только то, что меняют."""

    role: Role | None = None
    status: UserStatus | None = None
