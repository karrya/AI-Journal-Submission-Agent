import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, EmailStr, Field, field_validator, model_validator

from app.schemas.common import (
    InputModel,
    OutputModel,
    Page,
    SecureUrl,
    require_update_fields,
)

PermissionCode = Literal[
    "manuscript:read",
    "manuscript:create",
    "manuscript:update",
    "manuscript:file:manage",
    "author:profile:read",
    "author:email:read",
    "author:phone:read",
    "author:address:read",
    "author:profile:update",
]


def normalize_orcid(value: str) -> str:
    match = re.fullmatch(
        r"(?:https://orcid\.org/)?(\d{4}-\d{4}-\d{4}-[\dX]{4})",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError("Invalid ORCID format")
    orcid = match.group(1).upper()
    digits = orcid.replace("-", "")
    total = 0
    for digit in digits[:15]:
        total = (total + int(digit)) * 2
    check_value = (12 - total % 11) % 11
    check_character = "X" if check_value == 10 else str(check_value)
    if digits[-1] != check_character:
        raise ValueError("Invalid ORCID checksum")
    return orcid


Orcid = Annotated[str, AfterValidator(normalize_orcid)]


class AlternateName(InputModel):
    language: str | None = Field(default=None, max_length=32)
    given_name: str | None = Field(default=None, max_length=128)
    middle_name: str | None = Field(default=None, max_length=128)
    family_name: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, max_length=255)


class AuthorCreate(InputModel):
    given_name: str | None = Field(default=None, max_length=128)
    middle_name: str | None = Field(default=None, max_length=128)
    family_name: str | None = Field(default=None, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    alternate_names: list[AlternateName] = Field(default_factory=list, max_length=20)
    orcid: Orcid | None = None
    phone_country_code: str | None = Field(default=None, max_length=16)
    phone_number: str | None = Field(default=None, max_length=32)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = None
    confirm_identity_change: Literal[True]


class AuthorUpdate(InputModel):
    given_name: str | None = Field(default=None, max_length=128)
    middle_name: str | None = Field(default=None, max_length=128)
    family_name: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    alternate_names: list[AlternateName] | None = Field(default=None, max_length=20)
    orcid: Orcid | None = None
    phone_country_code: str | None = Field(default=None, max_length=16)
    phone_number: str | None = Field(default=None, max_length=32)
    status: Literal["active", "inactive"] | None = None
    notes: str | None = None
    confirm_identity_change: Literal[True]

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self, {"confirm_identity_change"})
        return self


class AuthorResponse(OutputModel):
    id: UUID
    given_name: str | None = Field(default=None, max_length=128)
    middle_name: str | None = Field(default=None, max_length=128)
    family_name: str | None = Field(default=None, max_length=128)
    display_name: str = Field(max_length=255)
    alternate_names: list[AlternateName] = Field(default_factory=list, max_length=20)
    orcid: Orcid | None = None
    phone_country_code: str | None = Field(default=None, max_length=16)
    phone_number: str | None = Field(default=None, max_length=32)
    status: Literal["active", "inactive"]
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


AuthorPage = Page[AuthorResponse]


class EmailCreate(InputModel):
    email: EmailStr = Field(max_length=254)
    purpose: Literal["communication", "registration", "backup"] = "communication"
    is_primary: bool = False
    confirm_email_binding: Literal[True]


class EmailUpdate(InputModel):
    email: EmailStr | None = Field(default=None, max_length=254)
    purpose: Literal["communication", "registration", "backup"] | None = None
    is_primary: bool | None = None
    confirm_email_binding: Literal[True] | None = None
    verification_status: Literal["unverified", "verified"] | None = None
    authorization_status: Literal["unconfirmed", "authorized", "revoked"] | None = None

    @model_validator(mode="after")
    def validate_change(self):
        require_update_fields(self, {"confirm_email_binding"})
        if "email" in self.model_fields_set and self.confirm_email_binding is not True:
            raise ValueError("Email changes require explicit binding confirmation")
        return self


class EmailResponse(OutputModel):
    id: UUID
    author_id: UUID
    email: EmailStr = Field(max_length=254)
    normalized_email: EmailStr = Field(max_length=254)
    purpose: Literal["communication", "registration", "backup"]
    is_primary: bool
    verification_status: Literal["unverified", "verified"]
    authorization_status: Literal["unconfirmed", "authorized", "revoked"]
    created_at: datetime
    updated_at: datetime


EmailPage = Page[EmailResponse]


class InstitutionCreate(InputModel):
    name: str = Field(min_length=1, max_length=255)
    institution_type: str | None = Field(default=None, max_length=32)
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class InstitutionUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    institution_type: str | None = Field(default=None, max_length=32)
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class InstitutionSummaryResponse(OutputModel):
    id: UUID
    name: str = Field(max_length=255)
    institution_type: str | None = Field(default=None, max_length=32)
    website_url: SecureUrl | None = Field(default=None, max_length=1024)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    city: str | None = Field(default=None, max_length=128)


class InstitutionResponse(InstitutionSummaryResponse):
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    created_at: datetime
    updated_at: datetime


InstitutionPage = Page[InstitutionSummaryResponse]


class AuthorInstitutionLinkCreate(InputModel):
    institution_id: UUID
    department: str | None = Field(default=None, max_length=255)
    position_title: str | None = Field(default=None, max_length=255)
    valid_from: date | None = None
    valid_to: date | None = None
    is_current: bool = False
    display_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must not be earlier than valid_from")
        return self


class AuthorInstitutionLinkUpdate(InputModel):
    institution_id: UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    position_title: str | None = Field(default=None, max_length=255)
    valid_from: date | None = None
    valid_to: date | None = None
    is_current: bool | None = None
    display_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_change(self):
        require_update_fields(self)
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must not be earlier than valid_from")
        return self


class AuthorInstitutionLinkResponse(OutputModel):
    id: UUID
    author_id: UUID
    institution_id: UUID
    institution_name: str = Field(max_length=255)
    department: str | None = Field(default=None, max_length=255)
    position_title: str | None = Field(default=None, max_length=255)
    valid_from: date | None = None
    valid_to: date | None = None
    is_current: bool
    display_order: int = Field(ge=0)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    created_at: datetime
    updated_at: datetime


AuthorInstitutionResponse = AuthorInstitutionLinkResponse
AuthorInstitutionPage = Page[AuthorInstitutionLinkResponse]


class AuthorizationCreate(InputModel):
    author_id: UUID
    user_id: UUID
    permissions: list[PermissionCode] = Field(min_length=1, max_length=9)
    valid_from: datetime
    valid_to: datetime
    evidence_ref: str | None = Field(default=None, max_length=1024)
    notes: str | None = None

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[PermissionCode]):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate permissions are not allowed")
        return sorted(value)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class AuthorizationUpdate(InputModel):
    permissions: list[PermissionCode] | None = Field(
        default=None, min_length=1, max_length=9
    )
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_ref: str | None = Field(default=None, max_length=1024)
    notes: str | None = None

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[PermissionCode] | None):
        if value is None:
            raise ValueError("permissions cannot be null")
        if len(value) != len(set(value)):
            raise ValueError("Duplicate permissions are not allowed")
        return sorted(value)

    @model_validator(mode="after")
    def validate_change(self):
        require_update_fields(self)
        for field_name in ("valid_from", "valid_to"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be later than valid_from")
        return self


class AuthorizationRevokeRequest(InputModel):
    reason: str | None = Field(default=None, max_length=2000)


class AuthorizationResponse(OutputModel):
    id: UUID
    author_id: UUID
    user_id: UUID
    permissions: list[PermissionCode] = Field(min_length=1, max_length=9)
    valid_from: datetime
    valid_to: datetime
    evidence_ref: str | None = Field(default=None, max_length=1024)
    notes: str | None = None
    revoked_at: datetime | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    validity_status: Literal[
        "not_yet_active", "active", "expired", "revoked", "inactive_subject"
    ]

    @field_validator("permissions")
    @classmethod
    def normalize_permissions(cls, value: list[PermissionCode]):
        return sorted(set(value))

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


AuthorizationPage = Page[AuthorizationResponse]
