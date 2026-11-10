from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.schemas.common import InputModel, OutputModel, Page, require_update_fields

Keyword = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class ManuscriptAuthorInput(InputModel):
    author_id: UUID
    position: int = Field(ge=1)
    is_corresponding: bool


class ManuscriptAuthorResponse(OutputModel):
    author_id: UUID
    display_name: str
    position: int
    is_corresponding: bool


ManuscriptAuthorList = list[ManuscriptAuthorResponse]


class ManuscriptCreate(InputModel):
    owner_author_id: UUID
    title: str = Field(min_length=1, max_length=1000)
    abstract: str = Field(min_length=1)
    keywords: list[Keyword] = Field(default_factory=list, max_length=50)
    article_type: str = Field(min_length=1, max_length=100)
    subject_field: str | None = Field(default=None, max_length=255)
    language: str = Field(min_length=1, max_length=32)
    funding_statement: str | None = None
    funding_number: str | None = Field(default=None, max_length=255)
    funding_name: str | None = Field(default=None, max_length=255)
    publication_statement: str | None = None
    acknowledgements: str | None = None
    author_contributions: str | None = None
    clinical_trial_number: str | None = Field(default=None, max_length=255)
    conflict_of_interest_statement: str | None = None
    ethics_statement: str | None = None
    data_availability_statement: str | None = None
    notes: str | None = None
    authors: list[ManuscriptAuthorInput] | None = Field(default=None, max_length=200)


class ManuscriptUpdate(InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    abstract: str | None = Field(default=None, min_length=1)
    keywords: list[Keyword] | None = Field(default=None, max_length=50)
    article_type: str | None = Field(default=None, min_length=1, max_length=100)
    subject_field: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, min_length=1, max_length=32)
    funding_statement: str | None = None
    funding_number: str | None = Field(default=None, max_length=255)
    funding_name: str | None = Field(default=None, max_length=255)
    publication_statement: str | None = None
    acknowledgements: str | None = None
    author_contributions: str | None = None
    clinical_trial_number: str | None = Field(default=None, max_length=255)
    conflict_of_interest_statement: str | None = None
    ethics_statement: str | None = None
    data_availability_statement: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class ManuscriptResponse(OutputModel):
    id: UUID
    internal_number: str = Field(max_length=64)
    owner_author_id: UUID
    title: str = Field(max_length=1000)
    abstract: str
    keywords: list[Keyword] = Field(max_length=50)
    article_type: str = Field(max_length=100)
    subject_field: str | None = Field(default=None, max_length=255)
    language: str = Field(max_length=32)
    funding_statement: str | None = None
    funding_number: str | None = Field(default=None, max_length=255)
    funding_name: str | None = Field(default=None, max_length=255)
    publication_statement: str | None = None
    acknowledgements: str | None = None
    author_contributions: str | None = None
    clinical_trial_number: str | None = Field(default=None, max_length=255)
    conflict_of_interest_statement: str | None = None
    ethics_statement: str | None = None
    data_availability_statement: str | None = None
    notes: str | None = None
    status: Literal["draft", "active", "archived"]
    current_version_id: UUID | None
    authors: list[ManuscriptAuthorResponse] = Field(max_length=200)
    created_at: datetime
    updated_at: datetime


ManuscriptPage = Page[ManuscriptResponse]


class ManuscriptAuthorsUpdate(InputModel):
    authors: list[ManuscriptAuthorInput] = Field(min_length=1, max_length=200)
    confirm_authorship_change: Literal[True]


class ManuscriptSnapshot(OutputModel):
    owner_author_id: UUID
    title: str = Field(max_length=1000)
    abstract: str
    keywords: list[Keyword] = Field(max_length=50)
    article_type: str = Field(max_length=100)
    subject_field: str | None = Field(default=None, max_length=255)
    language: str = Field(max_length=32)
    funding_statement: str | None = None
    funding_number: str | None = Field(default=None, max_length=255)
    funding_name: str | None = Field(default=None, max_length=255)
    publication_statement: str | None = None
    acknowledgements: str | None = None
    author_contributions: str | None = None
    clinical_trial_number: str | None = Field(default=None, max_length=255)
    conflict_of_interest_statement: str | None = None
    ethics_statement: str | None = None
    data_availability_statement: str | None = None
    notes: str | None = None
    authors: list[ManuscriptAuthorResponse] = Field(max_length=200)


class ManuscriptVersionCreate(InputModel):
    label: str | None = Field(default=None, max_length=100)
    change_note: str | None = None


class ManuscriptVersionResponse(OutputModel):
    id: UUID
    manuscript_id: UUID
    version_number: int = Field(ge=1)
    label: str | None = Field(default=None, max_length=100)
    change_note: str | None = None
    metadata_snapshot: ManuscriptSnapshot
    created_at: datetime
    created_by: UUID


ManuscriptVersionPage = Page[ManuscriptVersionResponse]
