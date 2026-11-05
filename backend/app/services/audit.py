"""Sanitized, transaction-sharing audit records."""

from collections.abc import Collection, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import OperationLog
from app.repositories.audit import AuditRepository
from app.schemas.audit import AuditLogPage, AuditLogResponse

_SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "password",
        "token",
        "cookie",
        "secret",
        "email",
        "phone",
        "address",
        "storagepath",
        "session",
        "csrf",
    }
)


def _normalized_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def _sanitize_summary(
    value: Any, *, allowed_fields: frozenset[str], path: str = "summary"
) -> Any:
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Audit summary keys must be strings")
            normalized = _normalized_key(key)
            if any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS):
                raise ValueError("Audit summary contains a sensitive key")
            if key not in allowed_fields:
                raise ValueError("Audit summary field is outside the explicit allowlist")
            sanitized[key] = _sanitize_summary(
                item, allowed_fields=allowed_fields, path=f"{path}.{key}"
            )
        return sanitized
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_summary(item, allowed_fields=allowed_fields, path=path)
            for item in value
        ]
    return deepcopy(value)


class AuditService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AuditRepository(db)

    def record(
        self,
        *,
        actor_type: str,
        category: str,
        action: str,
        request_id: str,
        result: str,
        actor_user_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        author_id: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        allowed_fields: Collection[str] = frozenset(),
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> OperationLog:
        allowed = frozenset(allowed_fields)
        before_summary = (
            _sanitize_summary(before, allowed_fields=allowed)
            if before is not None
            else None
        )
        after_summary = (
            _sanitize_summary(after, allowed_fields=allowed)
            if after is not None
            else None
        )
        return self.repository.append(
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            category=category,
            action=action,
            target_type=target_type,
            target_id=target_id,
            author_id=author_id,
            request_id=request_id,
            result=result,
            before_summary=before_summary,
            after_summary=after_summary,
            error_code=error_code,
            error_message=error_message,
        )


class AuditQueryService:
    """Read-only audit queries; authorization is enforced at the API boundary."""

    def __init__(self, db: Session):
        self.repository = AuditRepository(db)

    @staticmethod
    def _response(record: OperationLog) -> AuditLogResponse:
        response = AuditLogResponse.model_validate(record)
        created_at = response.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return response.model_copy(update={"created_at": created_at})

    @staticmethod
    def _utc_filter(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise AppError(
                422, "VALIDATION_ERROR", "Audit time filters must be timezone-aware"
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        actor_user_id: str | None,
        author_id: str | None,
        category: str | None,
        action: str | None,
        target_type: str | None,
        target_id: str | None,
        result: str | None,
        request_id: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        sort: str,
        order: str,
    ) -> AuditLogPage:
        if sort not in self.repository.SORT_FIELDS:
            raise AppError(422, "VALIDATION_ERROR", "Unsupported sort field")
        start = self._utc_filter(created_from)
        end = self._utc_filter(created_to)
        if start is not None and end is not None and end < start:
            raise AppError(
                422, "VALIDATION_ERROR", "created_to must not precede created_from"
            )
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            actor_user_id=actor_user_id,
            author_id=author_id,
            category=category,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            request_id=request_id,
            created_from=start,
            created_to=end,
            sort=sort,
            order=order,
        )
        return AuditLogPage(
            items=[self._response(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, log_id: str) -> AuditLogResponse:
        record = self.repository.get(log_id)
        if record is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return self._response(record)
