"""Controlled, reason-bearing state changes for registration tasks."""

from app.core.errors import AppError
from app.models import RegistrationTask, utc_now

TERMINAL_STATUSES = frozenset({"REGISTERED", "FAILED", "CANCELLED", "EXPIRED"})

_TASK_STATUSES = frozenset(
    {
        "PENDING",
        "CHECKING_AUTHORIZATION",
        "OPENING_PAGE",
        "DETECTING_FORM",
        "FILLING_FORM",
        "WAITING_CAPTCHA",
        "READY_TO_SUBMIT",
        "SUBMITTING",
        "SUBMITTED",
        "SUBMISSION_UNKNOWN",
        "WAITING_EMAIL",
        "WAITING_EMAIL_CONFIRM",
        "VERIFYING_EMAIL",
        "REGISTERED",
        "NEEDS_MANUAL_REVIEW",
        "FAILED",
        "CANCELLED",
        "EXPIRED",
    }
)
_DEDICATED_TARGETS = frozenset(
    {"READY_TO_SUBMIT", "SUBMITTING", "SUBMISSION_UNKNOWN"}
)


def _invalid_state() -> None:
    raise AppError(409, "INVALID_TASK_STATE", "当前任务状态不允许迁移")


class RegistrationWorkflowService:
    def transition(
        self,
        task: RegistrationTask,
        target: str,
        *,
        actor_id: str,
        reason: str,
    ) -> RegistrationTask:
        if target in _DEDICATED_TARGETS:
            _invalid_state()
        return self._transition(task, target, reason=reason)

    def _transition(
        self, task: RegistrationTask, target: str, *, reason: str
    ) -> RegistrationTask:
        if target not in _TASK_STATUSES:
            _invalid_state()
        if task.task_status == target:
            return task
        if task.task_status in TERMINAL_STATUSES:
            _invalid_state()
        task.task_status = target
        task.current_step = reason
        task.last_activity_at = utc_now()
        return task

    def mark_ready_to_submit(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "表单已填写，等待提交确认",
    ) -> RegistrationTask:
        if task.task_status != "FILLING_FORM":
            _invalid_state()
        return self._transition(task, "READY_TO_SUBMIT", reason=reason)

    def start_submission(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "人工确认提交",
    ) -> RegistrationTask:
        if task.task_status != "READY_TO_SUBMIT":
            _invalid_state()
        return self._transition(task, "SUBMITTING", reason=reason)

    def mark_submission_unknown(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "提交结果未知",
    ) -> RegistrationTask:
        if task.task_status != "SUBMITTING":
            _invalid_state()
        return self._transition(task, "SUBMISSION_UNKNOWN", reason=reason)

    def cancel(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "用户取消",
    ) -> RegistrationTask:
        if task.task_status == "CANCELLED":
            return task
        if task.task_status in TERMINAL_STATUSES:
            _invalid_state()
        task.task_status = "CANCELLED"
        task.cancel_requested = True
        task.current_step = reason
        task.last_activity_at = utc_now()
        return task

    def restart(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "重新执行",
    ) -> RegistrationTask:
        now = utc_now()
        task.task_status = "PENDING"
        task.cancel_requested = False
        task.retryable = False
        task.worker_id = None
        task.lease_expires_at = None
        task.available_at = now
        task.current_step = reason
        task.last_activity_at = now
        return task
