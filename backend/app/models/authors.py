from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CHAR,
    DATE,
    TEXT,
    VARCHAR,
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
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


class Author(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "authors"
    __table_args__ = (
        UniqueConstraint("orcid", name="uq_authors_orcid"),
        MYSQL_TABLE_OPTIONS,
    )

    given_name: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    family_name: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    display_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    alternate_names: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    orcid: Mapped[str | None] = mapped_column(CHAR(19), nullable=True)
    phone_country_code: Mapped[str | None] = mapped_column(VARCHAR(16), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    status: Mapped[str] = mapped_column(VARCHAR(32), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)


class AuthorEmail(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "author_emails"
    __table_args__ = (
        UniqueConstraint(
            "author_id", "normalized_email", name="uq_author_emails_author_normalized"
        ),
        UniqueConstraint(
            "active_primary_author_id", name="uq_author_emails_active_primary_author"
        ),
        Index("ix_author_emails_normalized", "normalized_email"),
        MYSQL_TABLE_OPTIONS,
    )

    author_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False
    )
    email: Mapped[str] = mapped_column(VARCHAR(254), nullable=False)
    normalized_email: Mapped[str] = mapped_column(VARCHAR(254), nullable=False)
    purpose: Mapped[str] = mapped_column(
        VARCHAR(32), default="communication", nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="unverified", nullable=False
    )
    authorization_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="unconfirmed", nullable=False
    )
    active_primary_author_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        Computed(
            "IF(is_primary = 1 AND deleted_at IS NULL, author_id, NULL)",
            persisted=True,
        ),
        nullable=True,
    )


class Institution(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (
        Index(
            "ix_institutions_normalized_location",
            "normalized_name",
            "country_code",
            "city",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    institution_type: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    website_url: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    city: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    region: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    country_code: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)


class AuthorInstitution(
    UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base
):
    __tablename__ = "author_institutions"
    __table_args__ = (
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="valid_date_order",
        ),
        Index("ix_author_institutions_author_order", "author_id", "display_order"),
        Index("ix_author_institutions_institution", "institution_id"),
        MYSQL_TABLE_OPTIONS,
    )

    author_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False
    )
    institution_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False
    )
    department: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    position_title: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(DATE, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(DATE, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AuthorAuthorization(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "author_authorizations"
    __table_args__ = (
        CheckConstraint("valid_to > valid_from", name="finite_validity_order"),
        Index("ix_author_authorizations_author_user", "author_id", "user_id"),
        Index("ix_author_authorizations_validity", "valid_from", "valid_to"),
        Index("ix_author_authorizations_revoked", "revoked_at"),
        MYSQL_TABLE_OPTIONS,
    )

    author_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    permissions: Mapped[list] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(VARCHAR(1024), nullable=True)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
