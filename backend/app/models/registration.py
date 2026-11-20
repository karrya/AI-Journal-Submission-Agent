from datetime import datetime

from sqlalchemy import (
    CHAR,
    TEXT,
    VARCHAR,
    Boolean,
    Computed,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    CreatedUpdatedByMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class RegistrationTask(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "registration_tasks"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uk_registration_idempotency"),
        UniqueConstraint(
            "author_id",
            "portal_id",
            "blocking_scope",
            name="uk_registration_blocking_scope",
        ),
        Index("idx_registration_author_status", "author_id", "task_status"),
        Index("idx_registration_created", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    author_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False
    )
    publisher_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    journal_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=True
    )
    portal_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("journal_submission_portals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    authorization_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("author_authorizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    platform_code: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    adapter_code: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    task_status: Mapped[str] = mapped_column(
        VARCHAR(40), default="PENDING", nullable=False
    )
    current_step: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), default=0, nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    available_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), default=utc_now, nullable=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_external_action: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    external_evidence_ref: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    browser_handoff_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    blocking_scope: Mapped[str | None] = mapped_column(
        VARCHAR(7),
        Computed(
            "CASE WHEN task_status NOT IN ('CANCELLED', 'FAILED', 'EXPIRED') "
            "OR last_external_action IS NOT NULL THEN 'BLOCKED' ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class RegistrationConfirmation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "registration_confirmations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uk_confirmation_token"),
        Index("idx_confirmation_task", "task_id", "action_type", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    task_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("registration_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    summary_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
