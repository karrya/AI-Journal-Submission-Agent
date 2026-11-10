from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.authors import (
    AuthorizationCreate,
    AuthorizationOptionsResponse,
    AuthorizationPage,
    AuthorizationResponse,
    AuthorizationRevokeRequest,
    AuthorizationUpdate,
    PermissionCode,
)
from app.services.authorizations import AuthorizationService

router = APIRouter(prefix="/api/v1/author-authorizations", tags=["authorizations"])
Order = Literal["asc", "desc"]


@router.get("/options", response_model=AuthorizationOptionsResponse)
def authorization_options(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> AuthorizationOptionsResponse:
    return AuthorizationService(db, principal.user, request.state.request_id).options()


@router.get("", response_model=AuthorizationPage)
def list_authorizations(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    author_id: UUID | None = None,
    user_id: UUID | None = None,
    permission: PermissionCode | None = None,
    validity_status: Literal[
        "not_yet_active", "active", "expired", "revoked", "inactive_subject"
    ]
    | None = None,
    sort: str = "created_at",
    order: Order = "desc",
) -> AuthorizationPage:
    return AuthorizationService(db, principal.user, request.state.request_id).list_page(
        page=page,
        page_size=page_size,
        author_id=str(author_id) if author_id else None,
        user_id=str(user_id) if user_id else None,
        permission=permission,
        validity_status=validity_status,
        sort=sort,
        order=order,
    )


@router.post("", response_model=AuthorizationResponse, status_code=201)
def create_authorization(
    request: Request,
    payload: AuthorizationCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorizationResponse:
    return AuthorizationService(db, principal.user, request.state.request_id).create(
        payload
    )


@router.get("/{authorization_id}", response_model=AuthorizationResponse)
def get_authorization(
    request: Request,
    authorization_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> AuthorizationResponse:
    return AuthorizationService(db, principal.user, request.state.request_id).get(
        str(authorization_id)
    )


@router.patch("/{authorization_id}", response_model=AuthorizationResponse)
def update_authorization(
    request: Request,
    authorization_id: UUID,
    payload: AuthorizationUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorizationResponse:
    return AuthorizationService(db, principal.user, request.state.request_id).update(
        str(authorization_id), payload
    )


@router.post("/{authorization_id}/revoke", response_model=AuthorizationResponse)
def revoke_authorization(
    request: Request,
    authorization_id: UUID,
    payload: AuthorizationRevokeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorizationResponse:
    return AuthorizationService(db, principal.user, request.state.request_id).revoke(
        str(authorization_id)
    )
