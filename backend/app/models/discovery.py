from datetime import datetime

from sqlalchemy import JSON, CHAR, TEXT, VARCHAR, CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedUpdatedByMixin,
    UUIDPrimaryKeyMixin,
)


class DiscoveryTask(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "discovery_tasks"
    __table_args__ = (
        UniqueConstraint("task_type", "idempotency_key", name="uq_discovery_task_idempotency"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_discovery_progress"),
        Index("ix_discovery_status_updated", "status", "updated_at"),
        Index("ix_discovery_owner", "owner_author_id", "created_at"),
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
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
