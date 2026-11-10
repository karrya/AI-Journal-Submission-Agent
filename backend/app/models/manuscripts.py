from sqlalchemy import (
    JSON,
    CHAR,
    TEXT,
    VARCHAR,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    CreatedUpdatedByMixin,
    SoftDeleteMixin,
    UUIDPrimaryKeyMixin,
)


class Manuscript(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, SoftDeleteMixin, Base):
    __tablename__ = "manuscripts"
    __table_args__ = (
        UniqueConstraint("internal_number", name="uq_manuscripts_internal_number"),
        UniqueConstraint("id", "owner_author_id", name="uq_manuscripts_id_owner"),
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["manuscript_versions.manuscript_id", "manuscript_versions.id"],
            name="fk_manuscripts_current_version",
            ondelete="RESTRICT",
        ),
        Index("ix_manuscripts_owner", "owner_author_id"),
        Index("ix_manuscripts_status", "status"),
        MYSQL_TABLE_OPTIONS,
    )

    internal_number: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    owner_author_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(VARCHAR(1000), nullable=False)
    abstract: Mapped[str] = mapped_column(TEXT, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    article_type: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    subject_field: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    language: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    funding_statement: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    funding_number: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    funding_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    publication_statement: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    acknowledgements: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    author_contributions: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    clinical_trial_number: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    conflict_of_interest_statement: Mapped[str | None] = mapped_column(
        TEXT, nullable=True
    )
    ethics_statement: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    data_availability_statement: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    status: Mapped[str] = mapped_column(VARCHAR(32), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)


class ManuscriptAuthor(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "manuscript_authors"
    __table_args__ = (
        UniqueConstraint(
            "manuscript_id",
            "author_id",
            name="uq_manuscript_authors_manuscript_author",
        ),
        UniqueConstraint(
            "manuscript_id",
            "position",
            name="uq_manuscript_authors_manuscript_position",
        ),
        CheckConstraint("position > 0", name="positive_position"),
        MYSQL_TABLE_OPTIONS,
    )

    manuscript_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("manuscripts.id", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_corresponding: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class ManuscriptVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "manuscript_versions"
    __table_args__ = (
        UniqueConstraint(
            "manuscript_id",
            "version_number",
            name="uq_manuscript_versions_manuscript_number",
        ),
        UniqueConstraint(
            "manuscript_id", "id", name="uq_manuscript_versions_manuscript_id"
        ),
        MYSQL_TABLE_OPTIONS,
    )

    manuscript_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("manuscripts.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(VARCHAR(100), nullable=True)
    change_note: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
