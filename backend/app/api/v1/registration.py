"""Credential-free registration catalog, task, and admin APIs."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.core.errors import AppError
from app.models import (
    Journal,
    JournalSubmissionPortal,
    Publisher,
    Role,
    UserRole,
)
from app.repositories.registration import RegistrationRepository
from app.schemas.common import ErrorResponse, InputModel
from app.schemas.identification import JournalOption, JournalOptionsResponse, SubmissionPortalResponse
from app.schemas.registration import (
    PublisherSupportListResponse,
    PublisherSupportResponse,
    RegistrationTaskCreate,
    RegistrationTaskPage,
    RegistrationTaskResponse,
)
from app.services.audit import AuditService
from app.services.registration import RegistrationService

router = APIRouter(prefix="/api/v1", tags=["registration"])
VALIDATION_RESPONSE: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse}}
_CONFIG_AUDIT_FIELDS = frozenset(
    {
        "publisher_code",
        "support_status",
        "support_level",
        "adapter_code",
        "adapter_name",
        "adapter_version",
        "adapter_support_status",
        "adapter_allowed_domains",
        "adapter_last_verified_at",
        "disabled_reason",
    }
)
SupportStatus = Literal["SUPPORTED", "TESTING", "DISABLED"]
PublisherCode = Literal[
    "SPRINGER_NATURE", "ELSEVIER", "WILEY", "TAYLOR_FRANCIS", "SAGE"
]


class PublisherSupportConfig(InputModel):
    publisher_code: PublisherCode
    display_name: str = Field(min_length=1, max_length=255)
    support_status: SupportStatus
    support_level: Literal["V0_1", "V0_2"]
    official_domains: list[str] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class RegistrationPortalUpdate(InputModel):
    adapter_code: str | None = Field(default=None, min_length=1, max_length=100)
    adapter_name: str | None = Field(default=None, min_length=1, max_length=255)
    adapter_version: str | None = Field(default=None, min_length=1, max_length=64)
    adapter_support_status: SupportStatus | None = None
    adapter_allowed_domains: list[str] | None = Field(default=None, max_length=100)
    adapter_last_verified_at: datetime | None = None
    adapter_verification_notes: str | None = Field(default=None, max_length=2000)
    support_status: SupportStatus | None = None
    disabled_reason: str | None = Field(default=None, max_length=1000)

    @field_validator("adapter_last_verified_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("adapter_last_verified_at 必须包含时区信息")
        return value

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个可修改字段")
        return self


def registration_service(
    db: Session, principal: Principal, request: Request
) -> RegistrationService:
    return RegistrationService(db, principal.user, request.state.request_id)


def _config_audit(
    db: Session,
    principal: Principal,
    request: Request,
    *,
    action: str,
    target_type: str,
    target_id: str,
    result: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    error: AppError | None = None,
) -> None:
    AuditService(db).record(
        actor_user_id=principal.user.id,
        actor_type="user",
        category="business",
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request.state.request_id,
        result=result,
        before=before,
        after=after,
        allowed_fields=_CONFIG_AUDIT_FIELDS,
        error_code=error.code if error else None,
        error_message=error.message if error else None,
    )


def _failed_config(
    db: Session,
    principal: Principal,
    request: Request,
    *,
    action: str,
    target_type: str,
    target_id: str,
    error: AppError,
) -> None:
    db.rollback()
    _config_audit(
        db,
        principal,
        request,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result="failure",
        error=error,
    )
    db.commit()


def require_admin_csrf(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Principal:
    is_admin = (
        db.scalar(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == principal.user.id,
                Role.code == "system_admin",
            )
        )
        is not None
    )
    if not is_admin:
        raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")
    return principal


def _not_found() -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")


def _utc_filter(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(422, "VALIDATION_ERROR", "时间筛选条件必须包含时区信息")
    return value.astimezone(UTC).replace(tzinfo=None)


def _normalized_domains(domains: list[str]) -> list[str]:
    normalized = []
    for value in domains:
        domain = value.strip().lower().rstrip(".")
        try:
            parsed = urlsplit(f"https://{domain}")
            valid = (
                bool(domain)
                and parsed.hostname == domain
                and parsed.port is None
                and parsed.path == ""
                and parsed.query == ""
                and parsed.fragment == ""
            )
        except ValueError:
            valid = False
        if not valid:
            raise AppError(422, "VALIDATION_ERROR", "适配器域名必须是精确主机名")
        normalized.append(domain)
    return list(dict.fromkeys(normalized))


@router.get(
    "/registration/publishers",
    response_model=PublisherSupportListResponse,
    responses=VALIDATION_RESPONSE,
)
def list_registration_publishers(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> PublisherSupportListResponse:
    records = db.scalars(
        select(Publisher)
        .where(
            Publisher.deleted_at.is_(None),
            Publisher.registration_code.is_not(None),
        )
        .order_by(Publisher.name.asc(), Publisher.id.asc())
    )
    return PublisherSupportListResponse(
        items=[PublisherSupportResponse.from_publisher(record) for record in records]
    )


@router.get(
    "/registration/publishers/{publisher_id}/journals",
    response_model=JournalOptionsResponse,
    responses=VALIDATION_RESPONSE,
)
def list_registration_journals(
    publisher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> JournalOptionsResponse:
    support = RegistrationRepository(db).publisher_support(str(publisher_id))
    if support is None:
        raise _not_found()
    records = db.scalars(
        select(Journal)
        .where(
            Journal.publisher_id == str(publisher_id),
            Journal.deleted_at.is_(None),
        )
        .order_by(Journal.name.asc(), Journal.id.asc())
    )
    return JournalOptionsResponse(
        items=[JournalOption.model_validate(record) for record in records]
    )


@router.put(
    "/registration/publishers/{publisher_id}/support",
    response_model=PublisherSupportResponse,
    responses=VALIDATION_RESPONSE,
)
def configure_registration_publisher(
    publisher_id: UUID,
    payload: PublisherSupportConfig,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_csrf)],
) -> PublisherSupportResponse:
    action = "registration.publisher.configure"
    target_id = str(publisher_id)
    try:
        publisher = db.get(Publisher, target_id)
        if publisher is None or publisher.deleted_at is not None:
            raise _not_found()
        if payload.display_name != publisher.name:
            raise AppError(
                422, "VALIDATION_ERROR", "display_name 必须与出版社名称一致"
            )
        before = (
            {
                "publisher_code": publisher.registration_code,
                "support_status": publisher.registration_support_status,
                "support_level": publisher.registration_support_level,
            }
            if publisher.registration_code is not None
            else None
        )
        conflicting = db.scalar(
            select(Publisher).where(
                Publisher.registration_code == payload.publisher_code,
                Publisher.id != target_id,
            )
        )
        if conflicting is not None:
            raise AppError(409, "CONFLICT", "出版社代码已用于其他出版社")
        publisher.registration_code = payload.publisher_code
        publisher.registration_support_status = payload.support_status
        publisher.registration_support_level = payload.support_level
        publisher.registration_official_domains = payload.official_domains
        publisher.registration_notes = payload.notes
        publisher.registration_updated_by = principal.user.id
        after = {
            "publisher_code": payload.publisher_code,
            "support_status": payload.support_status,
            "support_level": payload.support_level,
        }
        _config_audit(
            db,
            principal,
            request,
            action=action,
            target_type="publisher",
            target_id=target_id,
            result="success",
            before=before,
            after=after,
        )
        db.commit()
        return PublisherSupportResponse.from_publisher(publisher)
    except AppError as exc:
        _failed_config(
            db,
            principal,
            request,
            action=action,
            target_type="publisher",
            target_id=target_id,
            error=exc,
        )
        raise
    except IntegrityError:
        error = AppError(409, "CONFLICT", "出版社支持配置唯一性冲突")
        _failed_config(
            db,
            principal,
            request,
            action=action,
            target_type="publisher",
            target_id=target_id,
            error=error,
        )
        raise error from None


@router.patch(
    "/registration/submission-portals/{portal_id}",
    response_model=SubmissionPortalResponse,
    responses=VALIDATION_RESPONSE,
)
def update_registration_portal(
    portal_id: UUID,
    payload: RegistrationPortalUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_admin_csrf)],
) -> JournalSubmissionPortal:
    action = "registration.portal.configure"
    target_id = str(portal_id)
    try:
        portal = RegistrationRepository(db).supported_portal(target_id)
        if portal is None:
            raise _not_found()
        values = payload.model_dump(exclude_unset=True)
        before = {
            field: getattr(portal, field)
            for field in _CONFIG_AUDIT_FIELDS
            if field in values and hasattr(portal, field)
        }
        if values.get("adapter_allowed_domains") is not None:
            values["adapter_allowed_domains"] = _normalized_domains(
                values["adapter_allowed_domains"]
            )
        verified_at = values.get("adapter_last_verified_at")
        if verified_at is not None:
            values["adapter_last_verified_at"] = verified_at.astimezone(UTC).replace(
                tzinfo=None
            )
        for field, value in values.items():
            setattr(portal, field, value)
        after = {
            field: values[field]
            for field in _CONFIG_AUDIT_FIELDS
            if field in values
        }
        _config_audit(
            db,
            principal,
            request,
            action=action,
            target_type="journal_submission_portal",
            target_id=target_id,
            result="success",
            before=before,
            after=after,
        )
        db.commit()
        return portal
    except AppError as exc:
        _failed_config(
            db,
            principal,
            request,
            action=action,
            target_type="journal_submission_portal",
            target_id=target_id,
            error=exc,
        )
        raise


@router.post(
    "/registration/tasks",
    response_model=RegistrationTaskResponse,
    status_code=202,
    responses=VALIDATION_RESPONSE,
)
def create_registration_task(
    request: Request,
    payload: RegistrationTaskCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> RegistrationTaskResponse:
    task = registration_service(db, principal, request).create_task(payload)
    return RegistrationTaskResponse.model_validate(task)


@router.get(
    "/registration/tasks",
    response_model=RegistrationTaskPage,
    responses=VALIDATION_RESPONSE,
)
def list_registration_tasks(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    author_id: UUID | None = None,
    publisher_id: UUID | None = None,
    journal_id: UUID | None = None,
    task_status: str | None = Query(None, max_length=40),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> RegistrationTaskPage:
    start = _utc_filter(created_from)
    end = _utc_filter(created_to)
    if start is not None and end is not None and end < start:
        raise AppError(422, "VALIDATION_ERROR", "created_to 不得早于 created_from")
    records, total = registration_service(db, principal, request).list_tasks(
        {
            "author_id": str(author_id) if author_id else None,
            "publisher_id": str(publisher_id) if publisher_id else None,
            "journal_id": str(journal_id) if journal_id else None,
            "task_status": task_status,
            "created_from": start,
            "created_to": end,
        },
        page=page,
        page_size=page_size,
    )
    return RegistrationTaskPage(
        items=[RegistrationTaskResponse.model_validate(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/registration/tasks/{task_id}",
    response_model=RegistrationTaskResponse,
    responses=VALIDATION_RESPONSE,
)
def get_registration_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> RegistrationTaskResponse:
    task = registration_service(db, principal, request).get_task(str(task_id))
    return RegistrationTaskResponse.model_validate(task)


@router.post(
    "/registration/tasks/{task_id}/cancel",
    response_model=RegistrationTaskResponse,
    responses=VALIDATION_RESPONSE,
)
def cancel_registration_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> RegistrationTaskResponse:
    task = registration_service(db, principal, request).cancel_task(str(task_id))
    return RegistrationTaskResponse.model_validate(task)


@router.post(
    "/registration/tasks/{task_id}/retry",
    response_model=RegistrationTaskResponse,
    responses=VALIDATION_RESPONSE,
)
def retry_registration_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> RegistrationTaskResponse:
    task = registration_service(db, principal, request).retry_task(str(task_id))
    return RegistrationTaskResponse.model_validate(task)
