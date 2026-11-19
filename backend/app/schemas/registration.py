"""Typed, credential-free contracts for registration resources."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import InputModel, OutputModel, Page


class RegistrationTaskCreate(InputModel):
    author_id: UUID
    publisher_id: UUID
    journal_id: UUID
    authorization_id: UUID
    platform_code: str = Field(max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=128)


class RegistrationTaskResponse(OutputModel):
    id: UUID
    author_id: UUID
    publisher_id: UUID
    journal_id: UUID
    platform_code: str
    task_status: str
    current_step: str | None
    retryable: bool
    created_at: datetime


RegistrationTaskPage = Page[RegistrationTaskResponse]


class PublisherSupportResponse(OutputModel):
    id: UUID
    publisher_id: UUID
    publisher_code: str
    display_name: str
    support_status: str
    support_level: str
    official_domains: list[str] | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PublisherSupportListResponse(OutputModel):
    items: list[PublisherSupportResponse]


class PlatformAdapterResponse(OutputModel):
    id: UUID
    adapter_code: str
    adapter_name: str
    platform_type: str
    adapter_version: str
    support_status: str
    allowed_domains: list[str]
    capability_config: dict | None
    last_verified_at: datetime | None
    verification_notes: str | None
    created_at: datetime
    updated_at: datetime


class PlatformAdapterListResponse(OutputModel):
    items: list[PlatformAdapterResponse]


class PublisherAccountResponse(OutputModel):
    id: UUID
    author_id: UUID
    publisher_id: UUID
    journal_id: UUID | None
    platform_code: str
    account_namespace: str
    account_email: str
    platform_account_id: str | None
    username: str | None
    account_status: str
    email_verified_at: datetime | None
    registered_at: datetime | None
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublisherAccountPage(Page[PublisherAccountResponse]):
    pass
