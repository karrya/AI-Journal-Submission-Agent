from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal
from app.core.database import get_db
from app.schemas.audit import AuditLogPage, AuditLogResponse
from app.services.audit import AuditQueryService
from app.services.permissions import require_roles

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])
Order = Literal["asc", "desc"]
AuditReader = Annotated[Principal, Depends(require_roles("auditor"))]


@router.get("", response_model=AuditLogPage, response_model_exclude_none=True)
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    principal: AuditReader,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    actor_user_id: UUID | None = None,
    author_id: UUID | None = None,
    category: Literal[
        "authentication", "authorization", "business", "sensitive_access"
    ]
    | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: UUID | None = None,
    result: Literal["success", "failure"] | None = None,
    request_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "created_at",
    order: Order = "desc",
) -> AuditLogPage:
    return AuditQueryService(db).list_page(
        page=page,
        page_size=page_size,
        actor_user_id=str(actor_user_id) if actor_user_id else None,
        author_id=str(author_id) if author_id else None,
        category=category,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        result=result,
        request_id=str(request_id) if request_id else None,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
        order=order,
    )


@router.get(
    "/{log_id}", response_model=AuditLogResponse, response_model_exclude_none=True
)
def get_audit_log(
    log_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: AuditReader,
) -> AuditLogResponse:
    return AuditQueryService(db).get(str(log_id))
