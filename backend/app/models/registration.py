from datetime import datetime

from sqlalchemy import (
    JSON,
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
    CreatedUpdatedMixin,
    SoftDeleteMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class PublisherRegistrationSupport(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "publisher_registration_support"
    __table_args__ = (
        UniqueConstraint("publisher_id", name="uk_publisher_support_id"),
        UniqueConstraint("publisher_code", name="uk_publisher_code"),
        Index("idx_publisher_status", "support_status"),
        MYSQL_TABLE_OPTIONS,
    )

    publisher_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    publisher_code: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    display_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    support_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="SUPPORTED", nullable=False
    )
    support_level: Mapped[str] = mapped_column(
        VARCHAR(32), default="V0_1", nullable=False
    )
    official_domains: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class PlatformAdapter(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "platform_adapters"
    __table_args__ = (
        UniqueConstraint("adapter_code", "adapter_version", name="uk_adapter_version"),
        Index("idx_adapter_platform_status", "platform_type", "support_status"),
        MYSQL_TABLE_OPTIONS,
    )

    adapter_code: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    adapter_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    platform_type: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    adapter_version: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    support_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="TESTING", nullable=False
    )
    allowed_domains: Mapped[list] = mapped_column(JSON, nullable=False)
    capability_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    verification_notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)


class PublisherAccount(
    UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base
):
    __tablename__ = "publisher_accounts"
    __table_args__ = (
        UniqueConstraint(
            "platform_code",
            "account_namespace",
            "active_account_email",
            name="uk_platform_account",
        ),
        Index("idx_account_author", "author_id"),
        Index("idx_account_publisher", "publisher_id"),
        Index("idx_account_journal", "journal_id"),
        Index("idx_account_status", "account_status"),
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
    platform_code: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    account_namespace: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    account_email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    normalized_email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    platform_account_id: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    username: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    account_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="PENDING", nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    registered_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    active_account_email: Mapped[str | None] = mapped_column(
        VARCHAR(255),
        Computed("IF(deleted_at IS NULL, normalized_email, NULL)", persisted=True),
        nullable=True,
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
        Index("idx_registration_account", "account_id"),
        Index("idx_registration_created", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    account_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("publisher_accounts.id", ondelete="RESTRICT"), nullable=True
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


class EmailVerificationRecord(UUIDPrimaryKeyMixin, CreatedUpdatedMixin, Base):
    __tablename__ = "email_verification_records"
    __table_args__ = (
        UniqueConstraint("task_id", "email_message_id", name="uk_task_message"),
        Index("idx_verification_account", "account_id"),
        Index("idx_verification_status", "verification_status"),
        MYSQL_TABLE_OPTIONS,
    )

    account_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("publisher_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("registration_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    email_address: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    email_message_id: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    sender_address: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    link_domain: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="PENDING", nullable=False
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


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
