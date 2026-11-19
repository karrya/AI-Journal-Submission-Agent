from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.common import ErrorResponse
from app.schemas.identification import (
    ConfirmCandidateRequest,
    ConfirmIdentityRequest,
    IdentifyRequest,
    IdentifyResponse,
    JournalCandidate,
    SubmissionPortalListResponse,
    TaskResponse,
)
from app.services.identification import JournalIdentificationService

router = APIRouter(prefix="/api/v1", tags=["identification"])
VALIDATION_RESPONSE: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse}}


def identification_service(
    db: Session, principal: Principal, request: Request
) -> JournalIdentificationService:
    return JournalIdentificationService(db, principal.user, request.state.request_id)


@router.post(
    "/journals/identify",
    response_model=IdentifyResponse,
    status_code=202,
    responses=VALIDATION_RESPONSE,
)
def identify_journal(
    request: Request,
    payload: IdentifyRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> IdentifyResponse:
    return identification_service(db, principal, request).create_network_task(payload)


@router.post(
    "/journals/{journal_id}/confirm-identity",
    response_model=JournalCandidate,
    responses=VALIDATION_RESPONSE,
)
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


@router.get("/tasks/{task_id}", response_model=TaskResponse, responses=VALIDATION_RESPONSE)
def get_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> TaskResponse:
    return identification_service(db, principal, request).get_task(str(task_id))


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse, responses=VALIDATION_RESPONSE)
def retry_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> TaskResponse:
    return identification_service(db, principal, request).retry_task(str(task_id))


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse, responses=VALIDATION_RESPONSE)
def cancel_task(
    task_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> TaskResponse:
    return identification_service(db, principal, request).cancel_task(str(task_id))


@router.post(
    "/tasks/{task_id}/confirm-candidate",
    response_model=TaskResponse,
    responses=VALIDATION_RESPONSE,
)
def confirm_task_candidate(
    task_id: UUID,
    request: Request,
    payload: ConfirmCandidateRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> TaskResponse:
    return identification_service(db, principal, request).confirm_task_candidate(
        str(task_id), payload
    )


@router.get(
    "/journals/{journal_id}/submission-portals",
    response_model=SubmissionPortalListResponse,
    responses=VALIDATION_RESPONSE,
)
def list_submission_portals(
    journal_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> SubmissionPortalListResponse:
    return identification_service(db, principal, request).list_submission_portals(
        str(journal_id)
    )
