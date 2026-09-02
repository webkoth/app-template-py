import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.users import Login, UserStatus
from app.domain.roles import Role
from app.domain.text import PlainText

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
    # Лишнее поле — ошибка, а не мусор, который молча выбрасывают. Без этого
    # `{"login": ..., "status": "disabled"}` отвечает 201 и заводит запись
    # АКТИВНОЙ: отправитель уверен, что завёл отключённую. Воспроизведено.
    model_config = ConfigDict(extra="forbid")

    # Тот же тип, что и у формы входа: логин хранится в нижнем регистре,
    # иначе `Иван` и `иван` стали бы двумя записями с общим бюджетом попыток.
    login: Login
    name: PlainText
    role: Role
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)

    @field_validator("password")
    @classmethod
    def _not_only_digits(cls, value: str) -> str:
        # Восьми символов мало, если все они цифры: дата рождения, телефон и
        # «12345678» проходят по длине и подбираются первыми. Запрет ровно
        # тот же, что в app-template-ts, и по той же причине.
        #
        # Проверяется обрезанное значение, а хранится исходное. Обрезка
        # только ради проверки: пароль «20260831 » — та же дата, и запрет
        # обходился одним пробелом в конце. Менять сам пароль нельзя, пробел
        # в нём — законный символ, и человек набрал именно его.
        stripped = value.strip()
        if not stripped:
            raise ValueError("Пароль из одних пробелов не годится")
        if stripped.isdigit():
            raise ValueError("Пароль из одних цифр не годится")
        return value


class UpdateUserRequest(BaseModel):
    """Частичное обновление: приходит только то, что меняют."""

    # Без запрета лишнего `{"role": "editor", "name": "Новое"}` отвечает 200,
    # имя при этом не меняется, и признака того, что половину просьбы
    # выбросили, нет никакого.
    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    status: UserStatus | None = None
