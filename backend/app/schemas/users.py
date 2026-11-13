from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.common import InputModel, OutputModel, Page, require_update_fields

RoleCode = Literal[
    "system_admin", "submission_operator", "reviewer", "author", "auditor"
]
UserStatus = Literal["active", "disabled"]


def validate_roles(value: list[RoleCode]) -> list[RoleCode]:
    if len(value) != len(set(value)):
        raise ValueError("角色不得重复")
    return value


class UserCreate(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    password_confirmation: str = Field(min_length=6, max_length=128)
    roles: list[RoleCode] = Field(min_length=1)

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value):
        return validate_roles(value)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致")
        return self


class UserUpdate(InputModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    roles: list[RoleCode] | None = Field(default=None, min_length=1)
    status: UserStatus | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_display_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value):
        return validate_roles(value) if value is not None else value

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class UserPasswordReset(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    new_password: str = Field(min_length=6, max_length=128)
    password_confirmation: str = Field(min_length=6, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致")
        return self


class ManagedUserResponse(OutputModel):
    id: UUID
    username: str
    display_name: str
    roles: list[RoleCode]
    status: UserStatus
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


UserPage = Page[ManagedUserResponse]
