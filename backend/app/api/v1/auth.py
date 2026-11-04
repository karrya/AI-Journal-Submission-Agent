from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    SESSION_COOKIE,
    Principal,
    get_principal,
    require_csrf,
    require_trusted_origin,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    UserResponse,
)
from app.security.csrf import csrf_token
from app.services.auth import AuthService, LoginRateLimiter

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _cookie_is_secure(request: Request, settings: Settings) -> bool:
    if settings.session_cookie_secure is not None:
        return settings.session_cookie_secure
    return request.url.scheme == "https" or settings.environment.lower() not in {
        "development",
        "test",
    }


def _set_session_cookie(
    response: Response, request: Request, settings: Settings, token: str, max_age: int
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max_age,
        path="/",
        secure=_cookie_is_secure(request, settings),
        httponly=True,
        samesite="lax",
    )


def _clear_session_cookie(
    response: Response, request: Request, settings: Settings
) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=_cookie_is_secure(request, settings),
        httponly=True,
        samesite="lax",
    )


def _user_response(service: AuthService, user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        roles=service.role_codes(user.id),
        status=user.status,
        must_change_password=user.must_change_password,
        last_login_at=_utc(user.last_login_at),
    )


@router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
    _origin_check: Annotated[None, Depends(require_trusted_origin)],
) -> LoginResponse:
    settings = get_settings()
    if not hasattr(request.app.state, "login_rate_limiter"):
        request.app.state.login_rate_limiter = LoginRateLimiter()
    service = AuthService(
        db,
        rate_limiter=request.app.state.login_rate_limiter,
        settings=settings,
    )
    source_ip = request.client.host if request.client else "unknown"
    result = service.login(
        payload.username,
        payload.password,
        source_ip,
        request.state.request_id,
    )
    max_age = max(
        0,
        int(
            (
                result.session.absolute_expires_at - result.session.created_at
            ).total_seconds()
        ),
    )
    _set_session_cookie(response, request, settings, result.raw_token, max_age)
    return LoginResponse(
        user=_user_response(service, result.user),
        csrf_token=result.csrf_token,
        idle_expires_at=_utc(result.session.idle_expires_at),
        absolute_expires_at=_utc(result.session.absolute_expires_at),
    )


@router.post("/logout", status_code=204, response_model=None)
def logout(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    settings = get_settings()
    AuthService(db, settings=settings).logout(
        principal.user, principal.session, request.state.request_id
    )
    response = Response(status_code=204)
    _clear_session_cookie(response, request, settings)
    return response


@router.get("/me", response_model=UserResponse)
def me(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> UserResponse:
    return _user_response(AuthService(db), principal.user)


@router.get("/csrf", response_model=CsrfResponse)
def get_csrf(
    principal: Annotated[Principal, Depends(get_principal)],
) -> CsrfResponse:
    token = csrf_token(principal.session.token_hash, get_settings().csrf_secret_key)
    return CsrfResponse(csrf_token=token)


@router.post("/change-password", status_code=204, response_model=None)
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    settings = get_settings()
    AuthService(db, settings=settings).change_password(
        principal.user,
        principal.session,
        payload.current_password,
        payload.new_password,
        request.state.request_id,
    )
    response = Response(status_code=204)
    _clear_session_cookie(response, request, settings)
    return response
