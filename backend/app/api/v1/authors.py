from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.authors import (
    AuthorCreate,
    AuthorInstitutionLinkCreate,
    AuthorInstitutionLinkUpdate,
    AuthorInstitutionPage,
    AuthorInstitutionResponse,
    AuthorPage,
    AuthorResponse,
    AuthorUpdate,
    EmailCreate,
    EmailPage,
    EmailResponse,
    EmailUpdate,
    InstitutionCreate,
    InstitutionPage,
    InstitutionResponse,
    InstitutionSummaryResponse,
    InstitutionUpdate,
)
from app.schemas.common import InputModel
from app.services.authors import (
    AuthorInstitutionService,
    AuthorService,
    EmailService,
    InstitutionService,
)

router = APIRouter(prefix="/api/v1", tags=["authors"])
Order = Literal["asc", "desc"]


class EmailBindingConfirmation(InputModel):
    confirm_email_binding: Literal[True]


@router.get("/authors", response_model=AuthorPage, response_model_exclude_none=True)
def list_authors(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    name: str | None = None,
    orcid: str | None = None,
    status: Literal["active", "inactive"] | None = None,
    sort: str = "display_name",
    order: Order = "asc",
) -> AuthorPage:
    return AuthorService(db, principal.user, request.state.request_id).list_page(
        page=page,
        page_size=page_size,
        name=name,
        orcid=orcid,
        status=status,
        sort=sort,
        order=order,
    )


@router.post(
    "/authors",
    response_model=AuthorResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_author(
    request: Request,
    payload: AuthorCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorResponse:
    return AuthorService(db, principal.user, request.state.request_id).create(payload)


@router.get(
    "/authors/{author_id}",
    response_model=AuthorResponse,
    response_model_exclude_none=True,
)
def get_author(
    request: Request,
    author_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> AuthorResponse:
    return AuthorService(db, principal.user, request.state.request_id).get(
        str(author_id)
    )


@router.patch(
    "/authors/{author_id}",
    response_model=AuthorResponse,
    response_model_exclude_none=True,
)
def update_author(
    request: Request,
    author_id: UUID,
    payload: AuthorUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorResponse:
    return AuthorService(db, principal.user, request.state.request_id).update(
        str(author_id), payload
    )


@router.delete("/authors/{author_id}", status_code=204, response_model=None)
def delete_author(
    request: Request,
    author_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    AuthorService(db, principal.user, request.state.request_id).delete(str(author_id))
    return Response(status_code=204)


@router.get(
    "/authors/{author_id}/emails",
    response_model=EmailPage,
    response_model_exclude_none=True,
)
def list_emails(
    request: Request,
    author_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: str = "created_at",
    order: Order = "asc",
) -> EmailPage:
    return EmailService(db, principal.user, request.state.request_id).list_page(
        author_id=str(author_id),
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )


@router.post(
    "/authors/{author_id}/emails",
    response_model=EmailResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_email(
    request: Request,
    author_id: UUID,
    payload: EmailCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> EmailResponse:
    return EmailService(db, principal.user, request.state.request_id).create(
        str(author_id), payload
    )


@router.patch(
    "/authors/{author_id}/emails/{email_id}",
    response_model=EmailResponse,
    response_model_exclude_none=True,
)
def update_email(
    request: Request,
    author_id: UUID,
    email_id: UUID,
    payload: EmailUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> EmailResponse:
    return EmailService(db, principal.user, request.state.request_id).update(
        str(author_id), str(email_id), payload
    )


@router.delete(
    "/authors/{author_id}/emails/{email_id}", status_code=204, response_model=None
)
def delete_email(
    request: Request,
    author_id: UUID,
    email_id: UUID,
    payload: EmailBindingConfirmation,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    EmailService(db, principal.user, request.state.request_id).delete(
        str(author_id),
        str(email_id),
        confirm_email_binding=payload.confirm_email_binding,
    )
    return Response(status_code=204)


@router.get("/institutions", response_model=InstitutionPage)
def list_institutions(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    name: str | None = None,
    country_code: str | None = None,
    city: str | None = None,
    sort: str = "name",
    order: Order = "asc",
) -> InstitutionPage:
    return InstitutionService(db, principal.user, request.state.request_id).list_page(
        page=page,
        page_size=page_size,
        name=name,
        country_code=country_code,
        city=city,
        sort=sort,
        order=order,
    )


@router.post("/institutions", response_model=InstitutionResponse, status_code=201)
def create_institution(
    request: Request,
    payload: InstitutionCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> InstitutionResponse:
    return InstitutionService(db, principal.user, request.state.request_id).create(
        payload
    )


@router.get(
    "/institutions/{institution_id}",
    response_model=InstitutionResponse,
    response_model_exclude_none=True,
)
def get_institution(
    request: Request,
    institution_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
):
    result = InstitutionService(db, principal.user, request.state.request_id).get(
        str(institution_id)
    )
    if type(result) is InstitutionSummaryResponse:
        return JSONResponse(content=result.model_dump(mode="json", exclude_none=True))
    return result


@router.patch(
    "/institutions/{institution_id}",
    response_model=InstitutionResponse,
    response_model_exclude_none=True,
)
def update_institution(
    request: Request,
    institution_id: UUID,
    payload: InstitutionUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> InstitutionResponse:
    return InstitutionService(db, principal.user, request.state.request_id).update(
        str(institution_id), payload
    )


@router.delete("/institutions/{institution_id}", status_code=204, response_model=None)
def delete_institution(
    request: Request,
    institution_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    InstitutionService(db, principal.user, request.state.request_id).delete(
        str(institution_id)
    )
    return Response(status_code=204)


@router.get(
    "/authors/{author_id}/institutions",
    response_model=AuthorInstitutionPage,
    response_model_exclude_none=True,
)
def list_author_institutions(
    request: Request,
    author_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: str = "display_order",
    order: Order = "asc",
) -> AuthorInstitutionPage:
    return AuthorInstitutionService(
        db, principal.user, request.state.request_id
    ).list_page(
        author_id=str(author_id),
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )


@router.post(
    "/authors/{author_id}/institutions",
    response_model=AuthorInstitutionResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def create_author_institution(
    request: Request,
    author_id: UUID,
    payload: AuthorInstitutionLinkCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorInstitutionResponse:
    return AuthorInstitutionService(
        db, principal.user, request.state.request_id
    ).create(str(author_id), payload)


@router.patch(
    "/authors/{author_id}/institutions/{link_id}",
    response_model=AuthorInstitutionResponse,
    response_model_exclude_none=True,
)
def update_author_institution(
    request: Request,
    author_id: UUID,
    link_id: UUID,
    payload: AuthorInstitutionLinkUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> AuthorInstitutionResponse:
    return AuthorInstitutionService(
        db, principal.user, request.state.request_id
    ).update(str(author_id), str(link_id), payload)


@router.delete(
    "/authors/{author_id}/institutions/{link_id}",
    status_code=204,
    response_model=None,
)
def delete_author_institution(
    request: Request,
    author_id: UUID,
    link_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    AuthorInstitutionService(db, principal.user, request.state.request_id).delete(
        str(author_id), str(link_id)
    )
    return Response(status_code=204)
