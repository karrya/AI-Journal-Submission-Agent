from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.identification import (
    ConfirmIdentityRequest,
    IdentifyRequest,
    IdentifyResponse,
    JournalCandidate,
    TaskResponse,
)
from app.services.identification import JournalIdentificationService

router = APIRouter(prefix="/api/v1", tags=["identification"])


def identification_service(
    db: Session, principal: Principal, request: Request
) -> JournalIdentificationService:
    return JournalIdentificationService(db, principal.user, request.state.request_id)


@router.post("/journals/identify", response_model=IdentifyResponse)
def identify_journal(
    request: Request,
    payload: IdentifyRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> IdentifyResponse:
    return identification_service(db, principal, request).identify(payload)


@router.post("/journals/{journal_id}/confirm-identity", response_model=JournalCandidate)
def confirm_identity(
    journal_id: UUID,
    request: Request,
    payload: ConfirmIdentityRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> JournalCandidate:
    return identification_service(db, principal, request).confirm_identity(
        str(journal_id), payload
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> TaskResponse:
    return identification_service(db, principal, request).get_task(str(task_id))
