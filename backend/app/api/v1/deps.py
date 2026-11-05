import hmac
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import database
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models import AuthSession, User
from app.security.csrf import csrf_token, token_hash, validate_csrf_secret
from app.security.sessions import SessionService

SESSION_COOKIE = "asa_session"
FIRST_PASSWORD_ALLOWED_PATHS = frozenset(
    {
        "/api/v1/auth/me",
        "/api/v1/auth/csrf",
        "/api/v1/auth/change-password",
        "/api/v1/auth/logout",
    }
)
_PUBLIC_AUTH_PATHS = frozenset({"/api/v1/auth/login"})


@dataclass(frozen=True)
class Principal:
    user: User
    session: AuthSession


def _configuration_error() -> AppError:
    return AppError(500, "INTERNAL_SERVER_ERROR", "认证服务配置不可用")


def _validate_configuration(settings: Settings) -> None:
    try:
        validate_csrf_secret(settings.csrf_secret_key)
    except ValueError:
        raise _configuration_error() from None


def _origin_is_trusted(origin: str | None, settings: Settings) -> bool:
    return origin is not None and origin in settings.allowed_origins


def require_trusted_origin(
    origin: Annotated[str | None, Header(alias="Origin")] = None,
) -> None:
    if not _origin_is_trusted(origin, get_settings()):
        raise AppError(403, "SECURITY_CHECK_FAILED", "请求来源或安全令牌校验失败")


def _get_principal(request: Request, db: Session, *, touch: bool) -> Principal:
    settings = get_settings()
    _validate_configuration(settings)
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise AppError(401, "UNAUTHORIZED", "请先登录")
    resolved = SessionService(db, settings).resolve(raw_token, touch=touch)
    if resolved is None:
        raise AppError(401, "UNAUTHORIZED", "登录已失效，请重新登录")
    principal = Principal(*resolved)
    if (
        principal.user.must_change_password
        and request.url.path not in FIRST_PASSWORD_ALLOWED_PATHS
    ):
        raise AppError(403, "PASSWORD_CHANGE_REQUIRED", "首次登录后必须修改密码")
    request.state.principal = principal
    return principal


def get_principal(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> Principal:
    return _get_principal(request, db, touch=True)


def get_mutation_principal(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> Principal:
    return _get_principal(request, db, touch=False)


def require_csrf(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_mutation_principal)],
    origin: Annotated[str | None, Header(alias="Origin")] = None,
    supplied_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Principal:
    settings = get_settings()
    _validate_configuration(settings)
    sessions = SessionService(db, settings)
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        sessions.refresh_activity(principal.session)
        return principal
    expected = csrf_token(principal.session.token_hash, settings.csrf_secret_key)
    token_matches = supplied_token is not None and hmac.compare_digest(
        supplied_token, expected
    )
    stored_hash_matches = supplied_token is not None and hmac.compare_digest(
        token_hash(supplied_token), principal.session.csrf_token_hash
    )
    if not _origin_is_trusted(origin, settings) or not (
        token_matches and stored_hash_matches
    ):
        raise AppError(403, "SECURITY_CHECK_FAILED", "请求来源或安全令牌校验失败")
    sessions.refresh_activity(principal.session)
    return principal


def get_request_id(request: Request) -> str:
    candidate = getattr(request.state, "request_id", None)
    if isinstance(candidate, str):
        try:
            parsed = UUID(candidate)
        except ValueError:
            pass
        else:
            if str(parsed) == candidate:
                return candidate
    generated = str(uuid4())
    request.state.request_id = generated
    return generated


def _middleware_error(request: Request, status: int, code: str, message: str):
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "request_id": get_request_id(request),
            "details": None,
        },
    )


async def first_password_gate(request: Request, call_next):
    path = request.url.path
    if (
        not path.startswith("/api/v1/")
        or path.startswith("/api/v1/health")
        or path in _PUBLIC_AUTH_PATHS
        or path in FIRST_PASSWORD_ALLOWED_PATHS
    ):
        return await call_next(request)
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return await call_next(request)

    settings = get_settings()
    try:
        validate_csrf_secret(settings.csrf_secret_key)
    except ValueError:
        return _middleware_error(
            request, 500, "INTERNAL_SERVER_ERROR", "认证服务配置不可用"
        )

    db = database.SessionLocal()
    try:
        resolved = SessionService(db, settings).resolve(raw_token, touch=False)
        if (
            resolved is not None
            and resolved[0].must_change_password
            and path not in FIRST_PASSWORD_ALLOWED_PATHS
        ):
            return _middleware_error(
                request,
                403,
                "PASSWORD_CHANGE_REQUIRED",
                "首次登录后必须修改密码",
            )
    finally:
        db.close()
    return await call_next(request)
