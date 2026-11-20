from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.common import ErrorResponse
from app.schemas.identification import (
    JournalOptionsResponse,
    JournalSearchResponse,
    PublisherOptionsResponse,
    PublisherSearchResponse,
)
from app.schemas.journals import (
    JournalCreate,
    JournalPage,
    JournalResponse,
    JournalUpdate,
    PublisherCreate,
    PublisherPage,
    PublisherResponse,
    PublisherUpdate,
)
from app.services.identification import (
    JournalIdentificationService,
    PublisherIdentificationService,
)
from app.services.journals import JournalService, PublisherService

router = APIRouter(prefix="/api/v1", tags=["journals"])
Order = Literal["asc", "desc"]


@router.get("/publishers", response_model=PublisherPage, response_model_exclude_none=True)
def list_publishers(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    name: str | None = None,
    sort: str = "name",
    order: Order = "asc",
) -> PublisherPage:
    return PublisherService(db, principal.user, request.state.request_id).list_page(
        page=page,
        page_size=page_size,
        name=name,
        sort=sort,
        order=order,
    )


@router.post(
    "/publishers",
    response_model=PublisherResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_publisher(
    request: Request,
    payload: PublisherCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> PublisherResponse:
    return PublisherService(db, principal.user, request.state.request_id).create(payload)


@router.get(
    "/publishers/options",
    response_model=PublisherOptionsResponse,
    responses={422: {"model": ErrorResponse}},
)
def publisher_options(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    name: str | None = Query(None, max_length=255),
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
) -> PublisherOptionsResponse:
    return PublisherIdentificationService(
        db, principal.user, request.state.request_id
    ).options(name, limit)


@router.get("/publishers/search", response_model=PublisherSearchResponse)
def search_publishers(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    name: str | None = None,
    website_url: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PublisherSearchResponse:
    return PublisherIdentificationService(
        db, principal.user, request.state.request_id
    ).search(name=name, website_url=website_url, page=page, page_size=page_size)


@router.get(
    "/publishers/{publisher_id}",
    response_model=PublisherResponse,
    response_model_exclude_none=True,
)
def get_publisher(
    request: Request,
    publisher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> PublisherResponse:
    return PublisherService(db, principal.user, request.state.request_id).get(
        str(publisher_id)
    )


@router.patch(
    "/publishers/{publisher_id}",
    response_model=PublisherResponse,
    response_model_exclude_none=True,
)
def update_publisher(
    request: Request,
    publisher_id: UUID,
    payload: PublisherUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> PublisherResponse:
    return PublisherService(db, principal.user, request.state.request_id).update(
        str(publisher_id), payload
    )


@router.delete("/publishers/{publisher_id}", status_code=204, response_model=None)
def delete_publisher(
    request: Request,
    publisher_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    PublisherService(db, principal.user, request.state.request_id).delete(
        str(publisher_id)
    )
    return Response(status_code=204)


@router.get("/journals", response_model=JournalPage, response_model_exclude_none=True)
def list_journals(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    name: str | None = None,
    publisher_id: UUID | None = None,
    platform_code: str | None = Query(None, max_length=64),
    issn: str | None = None,
    status: str | None = None,
    sort: str = "name",
    order: Order = "asc",
) -> JournalPage:
    return JournalService(db, principal.user, request.state.request_id).list_page(
        page=page,
        page_size=page_size,
        name=name,
        publisher_id=str(publisher_id) if publisher_id else None,
        platform_code=str(platform_code) if platform_code else None,
        issn=issn,
        status=status,
        sort=sort,
        order=order,
    )


@router.post(
    "/journals",
    response_model=JournalResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_journal(
    request: Request,
    payload: JournalCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> JournalResponse:
    return JournalService(db, principal.user, request.state.request_id).create(payload)


@router.get(
    "/journals/options",
    response_model=JournalOptionsResponse,
    responses={422: {"model": ErrorResponse}},
)
def journal_options(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    publisher_id: UUID,
    name: str | None = Query(None, max_length=500),
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
) -> JournalOptionsResponse:
    return JournalIdentificationService(
        db, principal.user, request.state.request_id
    ).options(str(publisher_id), name, limit)


@router.get("/journals/search", response_model=JournalSearchResponse)
def search_journals(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    name: str | None = None,
    issn: str | None = None,
    eissn: str | None = None,
    publisher_id: UUID | None = None,
    website_url: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JournalSearchResponse:
    return JournalIdentificationService(
        db, principal.user, request.state.request_id
    ).search(
        name=name,
        issn=issn,
        eissn=eissn,
        publisher_id=str(publisher_id) if publisher_id else None,
        website_url=website_url,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/journals/{journal_id}",
    response_model=JournalResponse,
    response_model_exclude_none=True,
)
def get_journal(
    request: Request,
    journal_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> JournalResponse:
    return JournalService(db, principal.user, request.state.request_id).get(
        str(journal_id)
    )


@router.patch(
    "/journals/{journal_id}",
    response_model=JournalResponse,
    response_model_exclude_none=True,
)
def update_journal(
    request: Request,
    journal_id: UUID,
    payload: JournalUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> JournalResponse:
    return JournalService(db, principal.user, request.state.request_id).update(
        str(journal_id), payload
    )


@router.delete("/journals/{journal_id}", status_code=204, response_model=None)
def delete_journal(
    request: Request,
    journal_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    JournalService(db, principal.user, request.state.request_id).delete(str(journal_id))
    return Response(status_code=204)
