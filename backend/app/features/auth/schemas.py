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


class OkResponse(BaseModel):
    ok: bool = True
