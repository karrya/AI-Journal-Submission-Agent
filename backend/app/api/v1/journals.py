from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.journals import (
    JournalCreate,
    JournalPage,
    JournalPlatformCreate,
    JournalPlatformPage,
    JournalPlatformResponse,
    JournalPlatformUpdate,
    JournalResponse,
    JournalUpdate,
    PublisherCreate,
    PublisherPage,
    PublisherResponse,
    PublisherUpdate,
)
from app.services.journals import JournalPlatformService, JournalService, PublisherService

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


@router.get(
    "/journal-platforms",
    response_model=JournalPlatformPage,
    response_model_exclude_none=True,
)
def list_platforms(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    code: str | None = None,
    name: str | None = None,
    status: Literal["active", "needs_review", "disabled"] | None = None,
    sort: str = "code",
    order: Order = "asc",
) -> JournalPlatformPage:
    return JournalPlatformService(
        db, principal.user, request.state.request_id
    ).list_page(
        page=page,
        page_size=page_size,
        code=code,
        name=name,
        status=status,
        sort=sort,
        order=order,
    )


@router.post(
    "/journal-platforms",
    response_model=JournalPlatformResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_platform(
    request: Request,
    payload: JournalPlatformCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> JournalPlatformResponse:
    return JournalPlatformService(db, principal.user, request.state.request_id).create(
        payload
    )


@router.get(
    "/journal-platforms/{platform_id}",
    response_model=JournalPlatformResponse,
    response_model_exclude_none=True,
)
def get_platform(
    request: Request,
    platform_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> JournalPlatformResponse:
    return JournalPlatformService(db, principal.user, request.state.request_id).get(
        str(platform_id)
    )


@router.patch(
    "/journal-platforms/{platform_id}",
    response_model=JournalPlatformResponse,
    response_model_exclude_none=True,
)
def update_platform(
    request: Request,
    platform_id: UUID,
    payload: JournalPlatformUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> JournalPlatformResponse:
    return JournalPlatformService(db, principal.user, request.state.request_id).update(
        str(platform_id), payload
    )


@router.delete("/journal-platforms/{platform_id}", status_code=204, response_model=None)
def delete_platform(
    request: Request,
    platform_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    JournalPlatformService(db, principal.user, request.state.request_id).delete(
        str(platform_id)
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
    platform_id: UUID | None = None,
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
        platform_id=str(platform_id) if platform_id else None,
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
