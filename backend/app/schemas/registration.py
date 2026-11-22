"""Typed, credential-free contracts for registration resources."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import Field

from app.schemas.common import InputModel, OutputModel, Page

if TYPE_CHECKING:
    from app.models import Publisher


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


class RegistrationHandoffResponse(OutputModel):
    task_id: UUID
    reason: str
    manual_url: str
    browser_handoff_id: str
    current_step: str
    resumable: bool


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

    @classmethod
    def from_publisher(cls, publisher: "Publisher") -> "PublisherSupportResponse":
        code = publisher.registration_code
        status = publisher.registration_support_status
        level = publisher.registration_support_level
        if code is None or status is None or level is None:
            raise ValueError("注册支持配置不完整")
        return cls(
            id=UUID(publisher.id),
            publisher_id=UUID(publisher.id),
            publisher_code=code,
            display_name=publisher.name,
            support_status=status,
            support_level=level,
            official_domains=publisher.registration_official_domains,
            notes=publisher.registration_notes,
            created_at=publisher.created_at,
            updated_at=publisher.updated_at,
        )


class PublisherSupportListResponse(OutputModel):
    items: list[PublisherSupportResponse]
