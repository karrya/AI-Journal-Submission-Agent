from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import OutputModel, Page

FileType = Literal[
    "main_manuscript",
    "title_page",
    "abstract",
    "figure",
    "table",
    "supplement",
    "cover_letter",
    "reviewer_suggestion",
    "other",
]


class FileResponse(OutputModel):
    id: UUID
    file_family_id: UUID
    manuscript_id: UUID
    manuscript_version_id: UUID
    file_type: FileType = Field(max_length=32)
    display_name: str = Field(max_length=255)
    file_version: int = Field(ge=1)
    original_filename: str = Field(max_length=255)
    mime_type: str = Field(max_length=255)
    extension: str = Field(max_length=16)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scan_status: str = Field(max_length=32)
    integrity_status: Literal["normal", "missing", "hash_mismatch"]
    status: Literal["active", "deleted"]
    created_at: datetime
    uploaded_by: UUID


FilePage = Page[FileResponse]
