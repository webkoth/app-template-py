from pydantic import BaseModel, Field

from app.core.users import Login
from app.domain.roles import Role


class LoginRequest(BaseModel):
    login: Login
    password: str = Field(min_length=1, max_length=1024)


class CurrentUserResponse(BaseModel):
    id: str
    login: str
    name: str
    role: Role
    # Считает сервер, а не клиент. Клиент не знает ни APP_BOOTSTRAP_LOGIN, ни
    # того, убраны ли переменные с контура, — а сравнение с литералом
    # «admin» промахивается в обе стороны разом: при своём имени учётной
    # записи предупреждение не покажется никогда, а владелец, назвавший
    # собственную запись admin, будет видеть его вечно и перестанет читать
    # предупреждения вообще.
    using_bootstrap_account: bool


class OkResponse(BaseModel):
    ok: bool = True
