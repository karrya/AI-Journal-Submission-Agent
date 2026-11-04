import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.files import FilePage, FileResponse
from app.services.file_validation import CHUNK_SIZE, content_disposition
from app.services.files import FileService

router = APIRouter(prefix="/api/v1", tags=["files"])


def _service(request: Request, db: Session, principal: Principal) -> FileService:
    return FileService(db, principal.user, request.state.request_id)


def _descriptor_chunks(descriptor: int):
    try:
        while chunk := os.read(descriptor, CHUNK_SIZE):
            yield chunk
    finally:
        os.close(descriptor)


@router.get(
    "/manuscripts/{manuscript_id}/versions/{version_id}/files",
    response_model=FilePage,
    response_model_exclude_none=True,
)
def list_files(
    request: Request,
    manuscript_id: UUID,
    version_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FilePage:
    return _service(request, db, principal).list_page(
        manuscript_id=str(manuscript_id),
        version_id=str(version_id),
        page=page,
        page_size=page_size,
    )


@router.post(
    "/manuscripts/{manuscript_id}/versions/{version_id}/files",
    response_model=FileResponse,
    response_model_exclude_none=True,
    status_code=201,
)
def upload_file(
    request: Request,
    manuscript_id: UUID,
    version_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
    upload: Annotated[UploadFile, File(alias="file")],
    file_type: Annotated[str | None, Form()] = None,
    display_name: Annotated[str | None, Form()] = None,
    file_family_id: Annotated[UUID | None, Form()] = None,
) -> FileResponse:
    return _service(request, db, principal).upload(
        manuscript_id=str(manuscript_id),
        version_id=str(version_id),
        stream=upload.file,
        filename=upload.filename or "",
        declared_mime=upload.content_type or "",
        file_type=file_type,
        display_name=display_name,
        file_family_id=str(file_family_id) if file_family_id else None,
    )


@router.get(
    "/files/{file_id}", response_model=FileResponse, response_model_exclude_none=True
)
def get_file(
    request: Request,
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> FileResponse:
    return _service(request, db, principal).get(str(file_id))


@router.get("/files/{file_id}/download", response_class=StreamingResponse)
def download_file(
    request: Request,
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> StreamingResponse:
    downloaded = _service(request, db, principal).download(str(file_id))
    return StreamingResponse(
        _descriptor_chunks(downloaded.descriptor),
        media_type=downloaded.mime_type,
        headers={
            "Content-Disposition": content_disposition(downloaded.original_filename),
            "X-Content-Type-Options": "nosniff",
            "Content-Length": str(downloaded.size_bytes),
        },
    )


@router.delete("/files/{file_id}", status_code=204, response_model=None)
def delete_file(
    request: Request,
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    _service(request, db, principal).delete(str(file_id))
    return Response(status_code=204)
