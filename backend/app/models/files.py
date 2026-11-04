from sqlalchemy import (
    CHAR,
    VARCHAR,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    CreatedUpdatedMixin,
    SoftDeleteMixin,
    UUIDPrimaryKeyMixin,
)


class FileFamily(UUIDPrimaryKeyMixin, CreatedAtMixin, SoftDeleteMixin, Base):
    __tablename__ = "file_families"
    __table_args__ = (
        UniqueConstraint("id", "manuscript_id", name="uq_file_families_id_manuscript"),
        ForeignKeyConstraint(
            ["manuscript_id", "author_id"],
            ["manuscripts.id", "manuscripts.owner_author_id"],
            name="fk_file_families_manuscript_owner",
            ondelete="RESTRICT",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    author_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    manuscript_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    file_type: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    display_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class ManuscriptFile(UUIDPrimaryKeyMixin, CreatedUpdatedMixin, SoftDeleteMixin, Base):
    __tablename__ = "manuscript_files"
    __table_args__ = (
        UniqueConstraint(
            "file_family_id",
            "file_version",
            name="uq_manuscript_files_family_version",
        ),
        UniqueConstraint("storage_path", name="uq_manuscript_files_storage_path"),
        ForeignKeyConstraint(
            ["file_family_id", "manuscript_id"],
            ["file_families.id", "file_families.manuscript_id"],
            name="fk_manuscript_files_family_manuscript",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["manuscript_id", "manuscript_version_id"],
            ["manuscript_versions.manuscript_id", "manuscript_versions.id"],
            name="fk_manuscript_files_manuscript_version",
            ondelete="RESTRICT",
        ),
        Index("ix_manuscript_files_sha256", "sha256"),
        MYSQL_TABLE_OPTIONS,
    )

    file_family_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    manuscript_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    manuscript_version_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    file_version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(
        VARCHAR(1024, collation="ascii_bin"), nullable=False
    )
    mime_type: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    extension: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="not_scanned", nullable=False
    )
    integrity_status: Mapped[str] = mapped_column(
        VARCHAR(32), default="normal", nullable=False
    )
    status: Mapped[str] = mapped_column(VARCHAR(32), default="active", nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
