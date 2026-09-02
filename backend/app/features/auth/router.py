from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.deps import CurrentUserDep, SessionDep
from app.core.security import AUTH_COOKIE, SESSION_MAX_AGE_SECONDS
from app.features.auth import service
from app.features.auth.schemas import CurrentUserResponse, LoginRequest, OkResponse
from app.features.auth.service import bootstrap_login

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Адрес сокета из X-Real-IP, который ставит nginx.

    Не X-Forwarded-For: там цепочка, и первый сегмент прислал клиент —
    ограничение по такому адресу обходится одним заголовком.
    """
    return request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )


@router.post("/login", response_model=OkResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> OkResponse:
    token = await service.authenticate(
        session, payload.login, payload.password, _client_ip(request)
    )
    response.set_cookie(
        AUTH_COOKIE,
        token,
        # Срок куки и срок токена — одна политика и одна константа. Двумя
        # константами они разъезжаются молча, и обе стороны плохи: короче —
        # человека выкидывает раньше срока без причины; длиннее — SPA видит
        # куку, считает себя вошедшим и получает 401 на каждый запрос.
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        # Lax, а не Strict: при Strict кука не уезжает при переходе по
        # ссылке из письма или мессенджера, и человек видит форму входа,
        # хотя вошёл минуту назад.
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return OkResponse()


@router.post("/logout", response_model=OkResponse)
async def logout(response: Response) -> OkResponse:
    response.delete_cookie(AUTH_COOKIE, path="/")
    return OkResponse()


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUserDep) -> CurrentUserResponse:
    # Признак гаснет сам, когда владелец делает то, что предписано после
    # установки: заводит свою запись и убирает APP_BOOTSTRAP_* из .env
    # контура. Пустые переменные выключают bootstrap — см. bootstrap_enabled.
    using_bootstrap = settings.bootstrap_enabled and user.login == bootstrap_login()
    return CurrentUserResponse(
        id=user.id,
        login=user.login,
        name=user.name,
        role=user.role,
        using_bootstrap_account=using_bootstrap,
    )
