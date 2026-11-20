from datetime import datetime

from sqlalchemy import (
    JSON,
    CHAR,
    TEXT,
    VARCHAR,
    Computed,
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
        UniqueConstraint("active_normalized_name", name="uq_publishers_active_normalized_name"),
        UniqueConstraint("registration_code", name="uq_publishers_registration_code"),
        Index("ix_publishers_domain", "primary_domain"),
        Index("ix_publishers_registration_status", "registration_support_status"),
        MYSQL_TABLE_OPTIONS,
    )

    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    publisher_name_en: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    primary_domain: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    country: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    publisher_type: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    parent_organization_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(VARCHAR(30), default="ACTIVE", nullable=False)
    source_url: Mapped[str | None] = mapped_column(VARCHAR(2048), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    registration_code: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    registration_support_status: Mapped[str | None] = mapped_column(
        VARCHAR(32), nullable=True
    )
    registration_support_level: Mapped[str | None] = mapped_column(
        VARCHAR(32), nullable=True
    )
    registration_official_domains: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    registration_notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    registration_updated_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    active_normalized_name: Mapped[str | None] = mapped_column(
        VARCHAR(255),
        Computed("IF(deleted_at IS NULL, normalized_name, NULL)", persisted=True),
        nullable=True,
    )


class Journal(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "journals"
    __table_args__ = (
        UniqueConstraint("active_issn", name="uq_journals_active_issn"),
        UniqueConstraint("active_eissn", name="uq_journals_active_eissn"),
        Index("ix_journals_publisher_name", "publisher_id", "name"),
        Index("ix_journals_platform", "platform_code"),
        MYSQL_TABLE_OPTIONS,
    )

    publisher_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    platform_code: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
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
    journal_name_en: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    aims_scope: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    open_access_status: Mapped[str | None] = mapped_column(VARCHAR(50), nullable=True)
    identity_status: Mapped[str] = mapped_column(
        VARCHAR(30), default="UNVERIFIED", index=True, nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(VARCHAR(2048), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    active_issn: Mapped[str | None] = mapped_column(
        CHAR(8),
        Computed("CASE WHEN deleted_at IS NULL THEN issn ELSE NULL END", persisted=True),
        nullable=True,
    )
    active_eissn: Mapped[str | None] = mapped_column(
        CHAR(8),
        Computed("CASE WHEN deleted_at IS NULL THEN eissn ELSE NULL END", persisted=True),
        nullable=True,
    )
