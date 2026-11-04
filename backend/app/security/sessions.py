import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AuthSession, User, utc_now
from app.security.csrf import csrf_token, token_hash, validate_csrf_secret


class SessionService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def create_session(self, user: User) -> tuple[AuthSession, str, str]:
        validate_csrf_secret(self.settings.csrf_secret_key)
        raw_token = secrets.token_urlsafe(32)
        session_hash = token_hash(raw_token)
        csrf = csrf_token(session_hash, self.settings.csrf_secret_key)
        now = utc_now()
        absolute_expiry = now + timedelta(hours=self.settings.session_absolute_hours)
        idle_expiry = min(
            now + timedelta(minutes=self.settings.session_idle_minutes),
            absolute_expiry,
        )
        session = AuthSession(
            token_hash=session_hash,
            csrf_token_hash=token_hash(csrf),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=idle_expiry,
            absolute_expires_at=absolute_expiry,
            revoked_at=None,
        )
        self.db.add(session)
        self.db.flush()
        return session, raw_token, csrf

    def refresh_activity(self, session: AuthSession) -> None:
        now = utc_now()
        session.last_seen_at = now
        session.idle_expires_at = min(
            now + timedelta(minutes=self.settings.session_idle_minutes),
            session.absolute_expires_at,
        )
        self.db.commit()

    def resolve(
        self, raw_token: str, *, touch: bool = True
    ) -> tuple[User, AuthSession] | None:
        session_hash = token_hash(raw_token)
        statement = (
            select(User, AuthSession)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(AuthSession.token_hash == session_hash)
        )
        if touch:
            statement = statement.with_for_update()
        result = self.db.execute(statement).first()
        if result is None:
            return None
        user, session = result
        now = utc_now()
        expired = now >= session.idle_expires_at or now >= session.absolute_expires_at
        if (
            user.status != "active"
            or user.deleted_at is not None
            or session.revoked_at is not None
            or expired
        ):
            if touch and expired and session.revoked_at is None:
                session.revoked_at = now
                self.db.commit()
            return None
        if touch:
            self.refresh_activity(session)
        return user, session

    def revoke(self, session: AuthSession) -> None:
        if session.revoked_at is None:
            session.revoked_at = utc_now()
            self.db.flush()

    def revoke_all(self, user_id: str) -> None:
        self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        self.db.flush()
