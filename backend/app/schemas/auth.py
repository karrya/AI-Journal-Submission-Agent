from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import InputModel, OutputModel


class LoginRequest(InputModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


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
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
