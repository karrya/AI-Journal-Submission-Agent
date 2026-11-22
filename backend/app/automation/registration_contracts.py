from dataclasses import dataclass, field
from typing import Any, Callable

CheckpointCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class RegistrationData:
    task_id: str
    login_name: str
    secret: str
    profile: dict[str, Any]
    portal_url: str
    allowed_hosts: tuple[str, ...]
    adapter_code: str
    adapter_version: str
    checkpoint: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistrationReceipt:
    status: str
    checkpoint: dict[str, Any]
    retryable: bool = False


class RegistrationAutomationError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class RegistrationAdapter:
    execute: Callable[[RegistrationData, Any, CheckpointCallback], RegistrationReceipt]
