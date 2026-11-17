from datetime import UTC, datetime
from uuid import UUID
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.schemas.common import InputModel, OutputModel, SecureUrl, validate_secure_url


class PublisherCandidate(OutputModel):
    id: UUID
    name: str
    website_url: str | None
    primary_domain: str | None
    status: str
    match_reasons: list[str]


class PublisherSearchResponse(OutputModel):
    items: list[PublisherCandidate]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class JournalCandidate(OutputModel):
    id: UUID
    name: str
    publisher_id: UUID
    publisher_name: str
    issn: str | None
    eissn: str | None
    website_url: str | None
    identity_status: str
    match_reasons: list[str]
    conflict_reason: str | None
    updated_at: datetime
    verified_at: datetime | None


class IdentifyRequest(InputModel):
    publisher_name: str | None = Field(default=None, max_length=255)
    journal_name: str = Field(min_length=1, max_length=500)
    issn: str | None = Field(default=None, max_length=9)
    eissn: str | None = Field(default=None, max_length=9)
    website_url: SecureUrl | None = Field(default=None, max_length=2048)
    article_type: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class ConfirmIdentityRequest(InputModel):
    expected_updated_at: datetime
    confirmation_note: str | None = Field(default=None, max_length=2000)

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expected_updated_at 必须包含时区")
        return value.astimezone(UTC)


class IdentifyResponse(OutputModel):
    task_id: UUID
    status: str
    candidates: list[JournalCandidate]


class JournalSearchResponse(OutputModel):
    items: list[JournalCandidate]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class TaskResponse(OutputModel):
    task_id: UUID
    task_type: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str | None
    candidates: list[JournalCandidate]


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(validate_secure_url(value))
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("官网必须包含有效域名")
    return host.removeprefix("www.")
