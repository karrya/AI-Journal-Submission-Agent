import math
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models import AuthSession, OperationLog, Role, User, UserRole
from app.security.csrf import validate_csrf_secret
from app.security.passwords import (
    hash_password,
    normalize_username,
    password_needs_rehash,
    validate_new_password,
    verify_password,
)
from app.security.sessions import SessionService

_LOGIN_FAILURE_MESSAGE = "用户名或密码错误"


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: AuthSession
    raw_token: str
    csrf_token: str


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.clock = clock
        self._attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = now - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(key, None)
            return deque()
        return attempts

    def retry_after(self, normalized_username: str, source_ip: str) -> int | None:
        key = (normalized_username, source_ip)
        with self._lock:
            attempts = self._prune(key, self.clock())
            if len(attempts) < self.max_failures:
                return None
            return max(1, math.ceil(self.window_seconds - (self.clock() - attempts[0])))

    def record_failure(self, normalized_username: str, source_ip: str) -> None:
        key = (normalized_username, source_ip)
        with self._lock:
            now = self.clock()
            attempts = self._prune(key, now)
            if key not in self._attempts:
                self._attempts[key] = attempts
            attempts.append(now)

    def record_success(self, normalized_username: str, source_ip: str) -> None:
        with self._lock:
            self._attempts.pop((normalized_username, source_ip), None)


@lru_cache(maxsize=1)
def _timing_dummy_hash() -> str:
    return hash_password("timing-only-non-account-password")


class AuthService:
    def __init__(
        self,
        db: Session,
        *,
        rate_limiter: LoginRateLimiter | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.rate_limiter = rate_limiter or LoginRateLimiter()
        self.sessions = SessionService(db, self.settings)

    def _audit(
        self,
        *,
        action: str,
        result: str,
        request_id: str,
        user_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.db.add(
            OperationLog(
                actor_user_id=user_id,
                actor_type="user" if user_id else "anonymous",
                category="authentication",
                action=action,
                target_type="user" if user_id else None,
                target_id=user_id,
                request_id=request_id,
                result=result,
                before_summary=None,
                after_summary=None,
                error_code=error_code,
                error_message=error_message,
            )
        )

    def _validate_configuration(self) -> None:
        try:
            validate_csrf_secret(self.settings.csrf_secret_key)
        except ValueError:
            raise AppError(500, "INTERNAL_SERVER_ERROR", "认证服务配置不可用") from None

    def login(
        self, username: str, password: str, source_ip: str, request_id: str
    ) -> LoginResult:
        self._validate_configuration()
        normalized = normalize_username(username)
        if self.rate_limiter.retry_after(normalized, source_ip) is not None:
            self._audit(
                action="auth.login",
                result="failure",
                request_id=request_id,
                error_code="TOO_MANY_ATTEMPTS",
                error_message="Login rate limit exceeded",
            )
            self.db.commit()
            raise AppError(429, "TOO_MANY_ATTEMPTS", "登录尝试过多，请稍后重试")

        user = self.db.scalar(
            select(User).where(User.normalized_username == normalized)
        )
        password_hash = user.password_hash if user else _timing_dummy_hash()
        password_valid = verify_password(password_hash, password)
        if (
            not password_valid
            or user is None
            or user.status != "active"
            or user.deleted_at is not None
        ):
            self.rate_limiter.record_failure(normalized, source_ip)
            self._audit(
                action="auth.login",
                result="failure",
                request_id=request_id,
                error_code="UNAUTHORIZED",
                error_message=_LOGIN_FAILURE_MESSAGE,
            )
            self.db.commit()
            raise AppError(401, "UNAUTHORIZED", _LOGIN_FAILURE_MESSAGE)

        self.rate_limiter.record_success(normalized, source_ip)
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        session, raw_token, csrf = self.sessions.create_session(user)
        user.last_login_at = session.created_at
        self._audit(
            action="auth.login",
            result="success",
            request_id=request_id,
            user_id=user.id,
        )
        self.db.commit()
        return LoginResult(user, session, raw_token, csrf)

    def role_codes(self, user_id: str) -> list[str]:
        return list(
            self.db.scalars(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
                .order_by(Role.code)
            ).all()
        )

    def logout(self, user: User, session: AuthSession, request_id: str) -> None:
        self.sessions.revoke(session)
        self._audit(
            action="auth.logout",
            result="success",
            request_id=request_id,
            user_id=user.id,
        )
        self.db.commit()

    def change_password(
        self,
        user: User,
        session: AuthSession,
        current_password: str,
        new_password: str,
        request_id: str,
    ) -> None:
        if not verify_password(user.password_hash, current_password):
            self._audit(
                action="auth.change_password",
                result="failure",
                request_id=request_id,
                user_id=user.id,
                error_code="UNAUTHORIZED",
                error_message="Current password verification failed",
            )
            self.db.commit()
            raise AppError(401, "UNAUTHORIZED", "当前密码错误")
        try:
            validate_new_password(user.username, new_password)
        except ValueError as exc:
            self._audit(
                action="auth.change_password",
                result="failure",
                request_id=request_id,
                user_id=user.id,
                error_code="VALIDATION_ERROR",
                error_message="New password failed strength validation",
            )
            self.db.commit()
            raise AppError(422, "VALIDATION_ERROR", str(exc)) from None

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        self.sessions.revoke_all(user.id)
        self._audit(
            action="auth.change_password",
            result="success",
            request_id=request_id,
            user_id=user.id,
        )
        self.db.commit()
