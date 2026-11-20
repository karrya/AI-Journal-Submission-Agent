from datetime import datetime

from sqlalchemy import JSON, CHAR, TEXT, VARCHAR, Boolean, CheckConstraint, Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    CreatedUpdatedByMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class DiscoveryTask(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "discovery_tasks"
    __table_args__ = (
        UniqueConstraint("task_type", "idempotency_key", name="uq_discovery_task_idempotency"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_discovery_progress"),
        Index("ix_discovery_status_updated", "status", "updated_at"),
        Index("ix_discovery_owner", "owner_author_id", "created_at"),
        Index("ix_discovery_available", "status", "available_at", "lease_expires_at"),
        MYSQL_TABLE_OPTIONS,
    )

    task_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    journal_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=True
    )
    owner_author_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(30), default="PENDING", nullable=False)
    progress: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=3, nullable=False)
    checkpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    stage: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), default=utc_now)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class JournalSubmissionPortal(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "journal_submission_portals"
    __table_args__ = (
        Index("ix_submission_portal_journal", "journal_id", "created_at"),
        Index("idx_portal_status", "support_status", "verification_status"),
        Index("idx_portal_host", "normalized_host"),
        MYSQL_TABLE_OPTIONS,
    )

    journal_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("discovery_tasks.id", ondelete="RESTRICT"), nullable=True
    )
    original_url: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    redirect_chain: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    verification_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    access_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    platform_code: Mapped[str] = mapped_column(VARCHAR(50), default="UNKNOWN", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    evidence_summary: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    normalized_host: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    adapter_code: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    adapter_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    adapter_support_status: Mapped[str | None] = mapped_column(
        VARCHAR(32), nullable=True
    )
    adapter_allowed_domains: Mapped[list | None] = mapped_column(JSON, nullable=True)
    adapter_capability_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    adapter_last_verified_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    adapter_verification_notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    support_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="TESTING", nullable=False
    )
    verified_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    verification_evidence_ref: Mapped[str | None] = mapped_column(
        VARCHAR(255), nullable=True
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    disabled_reason: Mapped[str | None] = mapped_column(VARCHAR(1000), nullable=True)


class JournalSourceSnapshot(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "journal_source_snapshots"
    __table_args__ = (
        Index("ix_source_snapshot_task", "task_id", "created_at"),
        Index("ix_source_snapshot_journal", "journal_id", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    task_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("discovery_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    journal_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    original_url: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    final_url: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    http_status: Mapped[int | None] = mapped_column(INTEGER(unsigned=True), nullable=True)
    title: Mapped[str] = mapped_column(VARCHAR(500), default="", nullable=False)
    text_excerpt: Mapped[str] = mapped_column(TEXT, nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    parser_version: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class JournalDiscoveryLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "journal_discovery_logs"
    __table_args__ = (
        Index("ix_discovery_logs_task", "task_id", "created_at"),
        Index("ix_discovery_logs_journal", "journal_id", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    task_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("discovery_tasks.id", ondelete="RESTRICT"), nullable=True
    )
    journal_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    message: Mapped[str] = mapped_column(TEXT, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
