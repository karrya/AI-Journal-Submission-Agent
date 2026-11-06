from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from app.schemas.common import InputModel, OutputModel


class LoginRequest(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class UserResponse(OutputModel):
    id: UUID
    username: str = Field(max_length=64)
    display_name: str = Field(max_length=128)
    roles: list[str]
    status: Literal["active", "disabled"]
    must_change_password: bool
    last_login_at: datetime | None


class LoginResponse(OutputModel):
    user: UserResponse
    csrf_token: str = Field(min_length=1)
    idle_expires_at: datetime
    absolute_expires_at: datetime


class CsrfResponse(OutputModel):
    csrf_token: str = Field(min_length=1)


class ChangePasswordRequest(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
