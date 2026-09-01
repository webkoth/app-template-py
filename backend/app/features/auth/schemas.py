from pydantic import BaseModel, Field

from app.domain.roles import Role


class LoginRequest(BaseModel):
    # Логин без пробельных символов: перевод строки внутри сломал бы разбор
    # токена, и такой пользователь молча не смог бы войти.
    login: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")
    password: str = Field(min_length=1, max_length=1024)


class CurrentUserResponse(BaseModel):
    id: str
    login: str
    name: str
    role: Role


class OkResponse(BaseModel):
    ok: bool = True
