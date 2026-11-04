from typing import Annotated, Generic, TypeVar
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")


def validate_secure_url(value: str) -> str:
    parsed = urlsplit(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "localhost",
    }
    if parsed.scheme != "https" and not local_http:
        raise ValueError("URL must use HTTPS or approved local HTTP")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must have a host and must not contain user information")
    return value


SecureUrl = Annotated[str, AfterValidator(validate_secure_url)]


def require_update_fields(model: BaseModel, ignored: set[str] | None = None) -> None:
    ignored_fields = ignored or set()
    if not model.model_fields_set.difference(ignored_fields):
        raise ValueError("At least one modifiable field is required")


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorResponse(OutputModel):
    code: str
    message: str
    request_id: str
    details: list[dict] | dict | None


class HealthResponse(OutputModel):
    status: str


class Page(OutputModel, Generic[T]):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
