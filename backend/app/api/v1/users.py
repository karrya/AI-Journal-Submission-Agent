from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.users import (
    ManagedUserResponse,
    UserCreate,
    UserPage,
    UserPasswordReset,
    UserUpdate,
)
from app.services.users import UserManagementService

router = APIRouter(prefix="/api/v1/users", tags=["users"])
Status = Literal["active", "disabled"]
Order = Literal["asc", "desc"]


def service(
    db: Session, principal: Principal, request: Request
) -> UserManagementService:
    return UserManagementService(db, principal.user, request.state.request_id)


@router.get("", response_model=UserPage)
def list_users(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None, max_length=128),
    status: Status | None = None,
    sort: str = "created_at",
    order: Order = "desc",
) -> UserPage:
    return service(db, principal, request).list_page(
        page=page,
        page_size=page_size,
        name=name,
        status=status,
        sort=sort,
        order=order,
    )


@router.post("", response_model=ManagedUserResponse, status_code=201)
def create_user(
    request: Request,
    payload: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManagedUserResponse:
    return service(db, principal, request).create(payload)


@router.get("/{user_id}", response_model=ManagedUserResponse)
def get_user(
    user_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ManagedUserResponse:
    return service(db, principal, request).get(user_id)


@router.patch("/{user_id}", response_model=ManagedUserResponse)
def update_user(
    user_id: str,
    request: Request,
    payload: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManagedUserResponse:
    return service(db, principal, request).update(user_id, payload)


@router.post("/{user_id}/reset-password", status_code=204, response_model=None)
def reset_user_password(
    user_id: str,
    request: Request,
    payload: UserPasswordReset,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    service(db, principal, request).reset_password(user_id, payload)
    return Response(status_code=204)
