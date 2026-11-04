from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import OutputModel, Page


class AuditLogResponse(OutputModel):
    id: UUID
    actor_user_id: UUID | None
    actor_type: Literal["user", "system", "anonymous"]
    category: Literal["authentication", "authorization", "business", "sensitive_access"]
    action: str = Field(max_length=100)
    target_type: str | None = Field(default=None, max_length=64)
    target_id: UUID | None
    author_id: UUID | None
    request_id: UUID
    result: Literal["success", "failure"]
    before_summary: dict[str, Any] | None
    after_summary: dict[str, Any] | None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=1024)
    created_at: datetime


AuditLogPage = Page[AuditLogResponse]


class RecentOperation(OutputModel):
    action: str = Field(max_length=100)
    target_id: UUID | None
    result: Literal["success", "failure"]
    created_at: datetime


class DashboardSummary(OutputModel):
    author_count: int = Field(ge=0)
    manuscript_count: int = Field(ge=0)
    current_version_file_count: int = Field(ge=0)
    expiring_authorization_count: int = Field(ge=0)
    recent_operations: list[RecentOperation]
