from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CHAR, ForeignKey, MetaData
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MYSQL_TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    """返回不带时区信息的 UTC 时间；MySQL DATETIME 值不包含时区偏移。"""
    return datetime.now(UTC).replace(tzinfo=None)


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=new_uuid)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), default=utc_now, nullable=False
    )


class CreatedUpdatedMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), default=utc_now, onupdate=utc_now, nullable=False
    )


class CreatedUpdatedByMixin(CreatedUpdatedMixin):
    created_by: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
