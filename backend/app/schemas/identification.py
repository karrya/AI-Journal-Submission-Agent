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


class EvidenceSummary(OutputModel):
    source_type: str
    url: str
    title: str | None = None
    http_status: int | None = None
    content_sha256: str | None = None


class DiscoveryCandidate(OutputModel):
    candidate_key: str | None = None
    id: UUID | None = None
    publisher_id: UUID | None = None
    name: str
    publisher_name: str | None = None
    issn: str | None = None
    eissn: str | None = None
    website_url: str | None = None
    author_guidelines_url: str | None = None
    submission_url: str | None = None
    platform_code: str | None = None
    platform_confidence: float = 0
    portal_original_url: str | None = None
    portal_verification_status: str = "UNVERIFIED"
    portal_access_status: str = "UNKNOWN"
    redirect_chain: list[str] = Field(default_factory=list)
    identity_status: str
    match_reasons: list[str] = Field(default_factory=list)
    conflict_reason: str | None = None
    updated_at: datetime | None = None
    verified_at: datetime | None = None
    sources: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSummary] = Field(default_factory=list)


class ConfirmCandidateRequest(InputModel):
    candidate_key: str = Field(min_length=1, max_length=128)
    confirmation_note: str | None = Field(default=None, max_length=2000)


class SubmissionPortalResponse(OutputModel):
    id: UUID
    journal_id: UUID
    original_url: str
    final_url: str
    redirect_chain: list[str]
    verification_status: str
    access_status: str
    platform_code: str
    platform_adapter_id: UUID | None
    support_status: str
    confidence: float
    evidence_summary: list[EvidenceSummary]


class SubmissionPortalListResponse(OutputModel):
    items: list[SubmissionPortalResponse]


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
    journal_id: UUID | None = None
    candidates: list[DiscoveryCandidate]


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
    stage: str | None = None
    warnings: list[str] = Field(default_factory=list)
    retryable: bool = False
    journal_id: UUID | None = None
    candidates: list[DiscoveryCandidate] = Field(default_factory=list)


class PublisherOption(OutputModel):
    id: UUID
    name: str


class PublisherOptionsResponse(OutputModel):
    items: list[PublisherOption]


class JournalOption(OutputModel):
    id: UUID
    publisher_id: UUID
    name: str
    issn: str | None
    eissn: str | None
    website_url: str | None


class JournalOptionsResponse(OutputModel):
    items: list[JournalOption]


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(validate_secure_url(value))
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("官网必须包含有效域名")
    return host.removeprefix("www.")
