from sqlalchemy import JSON, CHAR, VARCHAR, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class OperationLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "operation_logs"
    __table_args__ = (
        Index("ix_operation_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_operation_logs_author_created", "author_id", "created_at"),
        Index("ix_operation_logs_target", "target_type", "target_id"),
        Index("ix_operation_logs_action_created", "action", "created_at"),
        Index("ix_operation_logs_request", "request_id"),
        MYSQL_TABLE_OPTIONS,
    )

    actor_user_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    category: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    action: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    author_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    result: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    before_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
