from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from uuid import uuid4

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


class RegistrationAdapter(Protocol):
    def execute(
        self,
        data: RegistrationData,
        browser: Any,
        checkpoint: CheckpointCallback,
    ) -> RegistrationReceipt: ...

    def resume(
        self,
        data: RegistrationData,
        browser: Any,
        checkpoint: CheckpointCallback,
    ) -> RegistrationReceipt: ...


def registration_handoff(
    step: str,
    manual_url: str,
    *,
    browser_handoff_id: str | None = None,
    last_external_action: str | None = None,
) -> RegistrationReceipt:
    checkpoint: dict[str, Any] = {
        "current_step": step,
        "manual_url": manual_url,
        "browser_handoff_id": browser_handoff_id or str(uuid4()),
    }
    if last_external_action is not None:
        checkpoint["last_external_action"] = last_external_action
    return RegistrationReceipt("NEEDS_MANUAL_REVIEW", checkpoint)
