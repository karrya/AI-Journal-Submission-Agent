from datetime import datetime

from sqlalchemy import CHAR, VARCHAR, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    CreatedUpdatedByMixin,
    SoftDeleteMixin,
    UUIDPrimaryKeyMixin,
)


class User(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("normalized_username", name="uq_users_normalized_username"),
        Index("ix_users_status", "status"),
        MYSQL_TABLE_OPTIONS,
    )

    username: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    normalized_username: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    display_name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(32), default="active", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )


class Role(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_roles_code"),
        MYSQL_TABLE_OPTIONS,
    )

    code: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    description: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)


class UserRole(CreatedAtMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (MYSQL_TABLE_OPTIONS,)

    user_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    assigned_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class AuthSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_auth_sessions_absolute_expires", "absolute_expires_at"),
        MYSQL_TABLE_OPTIONS,
    )

    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
