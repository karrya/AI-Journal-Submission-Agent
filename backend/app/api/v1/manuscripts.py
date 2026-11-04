from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.manuscripts import (
    ManuscriptAuthorList,
    ManuscriptAuthorsUpdate,
    ManuscriptCreate,
    ManuscriptPage,
    ManuscriptResponse,
    ManuscriptUpdate,
    ManuscriptVersionCreate,
    ManuscriptVersionPage,
    ManuscriptVersionResponse,
)
from app.services.manuscripts import ManuscriptService

router = APIRouter(prefix="/api/v1", tags=["manuscripts"])
Order = Literal["asc", "desc"]


def _service(request: Request, db: Session, principal: Principal) -> ManuscriptService:
    return ManuscriptService(db, principal.user, request.state.request_id)


@router.get(
    "/manuscripts", response_model=ManuscriptPage, response_model_exclude_none=True
)
def list_manuscripts(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Literal["draft", "active", "archived"] | None = None,
    sort: str = "created_at",
    order: Order = "desc",
) -> ManuscriptPage:
    return _service(request, db, principal).list_page(
        page=page,
        page_size=page_size,
        status=status,
        sort=sort,
        order=order,
    )


@router.post(
    "/manuscripts",
    response_model=ManuscriptResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_manuscript(
    request: Request,
    payload: ManuscriptCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManuscriptResponse:
    return _service(request, db, principal).create(payload)


@router.get(
    "/manuscripts/{manuscript_id}",
    response_model=ManuscriptResponse,
    response_model_exclude_none=True,
)
def get_manuscript(
    request: Request,
    manuscript_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ManuscriptResponse:
    return _service(request, db, principal).get(str(manuscript_id))


@router.patch(
    "/manuscripts/{manuscript_id}",
    response_model=ManuscriptResponse,
    response_model_exclude_none=True,
)
def update_manuscript(
    request: Request,
    manuscript_id: UUID,
    payload: ManuscriptUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManuscriptResponse:
    return _service(request, db, principal).update(str(manuscript_id), payload)


@router.delete("/manuscripts/{manuscript_id}", status_code=204, response_model=None)
def delete_manuscript(
    request: Request,
    manuscript_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    _service(request, db, principal).delete(str(manuscript_id))
    return Response(status_code=204)


@router.get(
    "/manuscripts/{manuscript_id}/authors",
    response_model=ManuscriptAuthorList,
)
def list_manuscript_authors(
    request: Request,
    manuscript_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
):
    return _service(request, db, principal).list_authors(str(manuscript_id))


@router.put(
    "/manuscripts/{manuscript_id}/authors",
    response_model=ManuscriptAuthorList,
)
def replace_manuscript_authors(
    request: Request,
    manuscript_id: UUID,
    payload: ManuscriptAuthorsUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
):
    return _service(request, db, principal).replace_authors(
        str(manuscript_id), payload
    )


@router.get(
    "/manuscripts/{manuscript_id}/versions",
    response_model=ManuscriptVersionPage,
    response_model_exclude_none=True,
)
def list_manuscript_versions(
    request: Request,
    manuscript_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ManuscriptVersionPage:
    return _service(request, db, principal).list_versions(
        manuscript_id=str(manuscript_id), page=page, page_size=page_size
    )


@router.post(
    "/manuscripts/{manuscript_id}/versions",
    response_model=ManuscriptVersionResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_manuscript_version(
    request: Request,
    manuscript_id: UUID,
    payload: ManuscriptVersionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManuscriptVersionResponse:
    return _service(request, db, principal).create_version(str(manuscript_id), payload)


@router.get(
    "/manuscripts/{manuscript_id}/versions/{version_id}",
    response_model=ManuscriptVersionResponse,
    response_model_exclude_none=True,
)
def get_manuscript_version(
    request: Request,
    manuscript_id: UUID,
    version_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ManuscriptVersionResponse:
    return _service(request, db, principal).get_version(
        str(manuscript_id), str(version_id)
    )
