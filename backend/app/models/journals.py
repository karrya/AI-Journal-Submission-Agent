from datetime import datetime

from sqlalchemy import (
    JSON,
    CHAR,
    TEXT,
    VARCHAR,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedUpdatedByMixin,
    SoftDeleteMixin,
    UUIDPrimaryKeyMixin,
)


class Publisher(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "publishers"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_publishers_normalized_name"),
        MYSQL_TABLE_OPTIONS,
    )

    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)


class JournalPlatform(
    UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base
):
    __tablename__ = "journal_platforms"
    __table_args__ = (
        UniqueConstraint("code", name="uq_journal_platforms_code"),
        MYSQL_TABLE_OPTIONS,
    )

    code: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    description: Mapped[str] = mapped_column(TEXT, default="", nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(32), default="active", nullable=False)


class Journal(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "journals"
    __table_args__ = (
        UniqueConstraint("issn", name="uq_journals_issn"),
        UniqueConstraint("eissn", name="uq_journals_eissn"),
        Index("ix_journals_publisher_name", "publisher_id", "name"),
        Index("ix_journals_platform", "platform_id"),
        MYSQL_TABLE_OPTIONS,
    )

    publisher_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    platform_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("journal_platforms.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    issn: Mapped[str | None] = mapped_column(CHAR(8), nullable=True)
    eissn: Mapped[str | None] = mapped_column(CHAR(8), nullable=True)
    website_url: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    submission_url: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    author_guidelines_url: Mapped[str | None] = mapped_column(
        VARCHAR(1024), nullable=True
    )
    subject_categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    article_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    requirements: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    requirements_source_url: Mapped[str | None] = mapped_column(
        VARCHAR(1024), nullable=True
    )
    requirements_verified_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    status: Mapped[str] = mapped_column(VARCHAR(32), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
