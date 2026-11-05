import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, field_validator, model_validator

from app.schemas.common import (
    InputModel,
    OutputModel,
    Page,
    SecureUrl,
    require_update_fields,
)


def normalize_issn(value: str) -> str:
    compact = value.replace("-", "").upper()
    if re.fullmatch(r"\d{7}[\dX]", compact) is None:
        raise ValueError("ISSN（国际标准连续出版物号）格式无效")
    weighted_sum = sum(int(digit) * weight for digit, weight in zip(compact[:7], range(8, 1, -1)))
    check_value = (11 - weighted_sum % 11) % 11
    check_character = "X" if check_value == 10 else str(check_value)
    if compact[-1] != check_character:
        raise ValueError("ISSN（国际标准连续出版物号）校验位无效")
    return compact


Issn = Annotated[str, AfterValidator(normalize_issn)]


class PublisherCreate(InputModel):
    name: str = Field(min_length=1, max_length=255)
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    notes: str | None = None


class PublisherUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    notes: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class PublisherResponse(OutputModel):
    id: UUID
    name: str = Field(max_length=255)
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


PublisherPage = Page[PublisherResponse]


class JournalPlatformCreate(InputModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    status: Literal["active", "needs_review", "disabled"] = "active"


class JournalPlatformUpdate(InputModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: Literal["active", "needs_review", "disabled"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class JournalPlatformResponse(OutputModel):
    id: UUID
    code: str = Field(max_length=64)
    name: str = Field(max_length=255)
    description: str
    status: Literal["active", "needs_review", "disabled"]
    created_at: datetime
    updated_at: datetime


JournalPlatformPage = Page[JournalPlatformResponse]


class JournalRequirement(InputModel):
    key: str = Field(min_length=1)
    value: str | int | float | bool = Field(allow_inf_nan=False)
    scope: str = Field(min_length=1)
    source_url: SecureUrl = Field(max_length=1024)
    verified_at: datetime

    @field_validator("verified_at")
    @classmethod
    def normalize_verified_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("投稿要求的 verified_at 必须包含时区信息")
        return value.astimezone(UTC)

    @field_validator("value")
    @classmethod
    def require_nonempty_string(cls, value):
        if isinstance(value, str) and not value:
            raise ValueError("投稿要求的值不能为空")
        return value


class JournalCreate(InputModel):
    publisher_id: UUID
    platform_id: UUID | None = None
    name: str = Field(min_length=1, max_length=500)
    issn: Issn | None = None
    eissn: Issn | None = None
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    submission_url: SecureUrl | None = Field(default=None, max_length=1024)
    author_guidelines_url: SecureUrl | None = Field(default=None, max_length=1024)
    subject_categories: list[str] = Field(default_factory=list)
    article_types: list[str] = Field(default_factory=list)
    requirements: list[JournalRequirement] = Field(default_factory=list, max_length=200)
    requirements_source_url: SecureUrl | None = Field(default=None, max_length=1024)
    requirements_verified_at: datetime | None = None
    status: str = Field(default="active", min_length=1, max_length=32)
    notes: str | None = None


class JournalUpdate(InputModel):
    publisher_id: UUID | None = None
    platform_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=500)
    issn: Issn | None = None
    eissn: Issn | None = None
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    submission_url: SecureUrl | None = Field(default=None, max_length=1024)
    author_guidelines_url: SecureUrl | None = Field(default=None, max_length=1024)
    subject_categories: list[str] | None = None
    article_types: list[str] | None = None
    requirements: list[JournalRequirement] | None = Field(default=None, max_length=200)
    requirements_source_url: SecureUrl | None = Field(default=None, max_length=1024)
    requirements_verified_at: datetime | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)
    notes: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class JournalResponse(OutputModel):
    id: UUID
    publisher_id: UUID
    platform_id: UUID | None
    name: str = Field(max_length=500)
    issn: Issn | None
    eissn: Issn | None
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    submission_url: SecureUrl | None = Field(default=None, max_length=1024)
    author_guidelines_url: SecureUrl | None = Field(default=None, max_length=1024)
    subject_categories: list[str]
    article_types: list[str]
    requirements: list[JournalRequirement] = Field(max_length=200)
    requirements_source_url: SecureUrl | None = Field(default=None, max_length=1024)
    requirements_verified_at: datetime | None
    status: str = Field(max_length=32)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


JournalPage = Page[JournalResponse]
