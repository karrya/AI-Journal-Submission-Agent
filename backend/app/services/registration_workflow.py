"""Controlled, reason-bearing state changes for registration tasks."""

from typing import NoReturn

from app.core.errors import AppError
from app.models import RegistrationConfirmation, RegistrationTask, utc_now

TERMINAL_STATUSES = frozenset({"REGISTERED", "FAILED", "CANCELLED", "EXPIRED"})
SUBMISSION_ACTIONS = frozenset({"SUBMIT", "SUBMITTING", "SUBMISSION_UNKNOWN"})

_TASK_STATUSES = frozenset(
    {
        "PENDING",
        "PROCESSING",
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
_ALLOWED_TRANSITIONS = {
    "PENDING": frozenset({"PROCESSING", "CHECKING_AUTHORIZATION", "CANCELLED"}),
    "PROCESSING": frozenset(
        {"PENDING", "NEEDS_MANUAL_REVIEW", "FAILED", "CANCELLED", "SUBMISSION_UNKNOWN", "REGISTERED"}
    ),
    "CHECKING_AUTHORIZATION": frozenset(
        {"OPENING_PAGE", "NEEDS_MANUAL_REVIEW", "FAILED", "CANCELLED"}
    ),
    "OPENING_PAGE": frozenset(
        {"DETECTING_FORM", "NEEDS_MANUAL_REVIEW", "FAILED", "CANCELLED"}
    ),
    "DETECTING_FORM": frozenset(
        {"FILLING_FORM", "NEEDS_MANUAL_REVIEW", "FAILED", "CANCELLED"}
    ),
    "FILLING_FORM": frozenset(
        {"READY_TO_SUBMIT", "WAITING_CAPTCHA", "NEEDS_MANUAL_REVIEW", "FAILED", "CANCELLED"}
    ),
    "WAITING_CAPTCHA": frozenset({"FILLING_FORM", "NEEDS_MANUAL_REVIEW", "CANCELLED"}),
    "READY_TO_SUBMIT": frozenset({"SUBMITTING", "CANCELLED", "EXPIRED"}),
    "SUBMITTING": frozenset({"SUBMITTED", "SUBMISSION_UNKNOWN"}),
    "SUBMITTED": frozenset({"WAITING_EMAIL", "REGISTERED", "CANCELLED"}),
    "SUBMISSION_UNKNOWN": frozenset({"NEEDS_MANUAL_REVIEW", "CANCELLED"}),
    "WAITING_EMAIL": frozenset(
        {"WAITING_EMAIL_CONFIRM", "REGISTERED", "FAILED", "CANCELLED", "EXPIRED"}
    ),
    "WAITING_EMAIL_CONFIRM": frozenset({"VERIFYING_EMAIL", "CANCELLED", "EXPIRED"}),
    "VERIFYING_EMAIL": frozenset(
        {"REGISTERED", "WAITING_EMAIL_CONFIRM", "FAILED", "CANCELLED"}
    ),
    "REGISTERED": frozenset(),
    "NEEDS_MANUAL_REVIEW": frozenset({"PENDING", "CANCELLED"}),
    "FAILED": frozenset({"PENDING"}),
    "CANCELLED": frozenset({"PENDING"}),
    "EXPIRED": frozenset(),
}
_DEDICATED_TARGETS = frozenset(
    {
        "READY_TO_SUBMIT",
        "SUBMITTING",
        "SUBMITTED",
        "SUBMISSION_UNKNOWN",
        "VERIFYING_EMAIL",
        "REGISTERED",
    }
)
_WORKER_RESULTS = frozenset({"NEEDS_MANUAL_REVIEW", "REGISTERED", "SUBMITTED"})


def _invalid_state() -> NoReturn:
    raise AppError(409, "INVALID_TASK_STATE", "当前任务状态不允许迁移")


def _evidence_required() -> NoReturn:
    raise AppError(
        409,
        "REGISTRATION_EVIDENCE_REQUIRED",
        "状态迁移缺少受控平台证据",
    )


class RegistrationWorkflowService:
    def validate_transition(
        self, task: RegistrationTask, target: str
    ) -> None:
        if target not in _TASK_STATUSES or task.task_status not in _TASK_STATUSES:
            _invalid_state()
        if task.task_status == target:
            return
        if target not in _ALLOWED_TRANSITIONS[task.task_status]:
            _invalid_state()

    def transition(
        self,
        task: RegistrationTask,
        target: str,
        *,
        actor_id: str,
        reason: str,
    ) -> RegistrationTask:
        if target in _DEDICATED_TARGETS or task.task_status == "WAITING_CAPTCHA":
            _invalid_state()
        return self._transition(task, target, reason=reason)

    def _transition(
        self, task: RegistrationTask, target: str, *, reason: str
    ) -> RegistrationTask:
        self.validate_transition(task, target)
        if task.task_status == target:
            return task
        task.task_status = target
        task.current_step = reason
        task.last_activity_at = utc_now()
        return task

    @staticmethod
    def _require_evidence(task: RegistrationTask, evidence_ref: str | None) -> str:
        evidence = evidence_ref or task.external_evidence_ref
        if not evidence:
            _evidence_required()
        return evidence

    @staticmethod
    def _require_confirmation(
        task: RegistrationTask,
        confirmation: RegistrationConfirmation | None,
        action_type: str,
    ) -> None:
        if confirmation is None:
            raise AppError(409, "CONFIRMATION_REQUIRED", "状态迁移需要有效人工确认")
        if (
            confirmation.task_id != task.id
            or confirmation.action_type != action_type
            or confirmation.consumed_at is None
        ):
            raise AppError(409, "CONFIRMATION_INVALID", "人工确认与任务动作不匹配")

    def mark_ready_to_submit(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        evidence_ref: str | None = None,
        reason: str = "表单已填写，等待提交确认",
    ) -> RegistrationTask:
        evidence = self._require_evidence(task, evidence_ref)
        task.external_evidence_ref = evidence
        return self._transition(task, "READY_TO_SUBMIT", reason=reason)

    def start_submission(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        confirmation: RegistrationConfirmation | None,
        reason: str = "人工确认提交",
    ) -> RegistrationTask:
        self.validate_transition(task, "SUBMITTING")
        self._require_confirmation(task, confirmation, "SUBMIT_REGISTRATION")
        return self._transition(task, "SUBMITTING", reason=reason)

    def mark_submitted(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        evidence_ref: str | None,
        reason: str = "平台已接受注册提交",
    ) -> RegistrationTask:
        evidence = self._require_evidence(task, evidence_ref)
        task.external_evidence_ref = evidence
        return self._transition(task, "SUBMITTED", reason=reason)

    def mark_registered(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        evidence_ref: str | None,
        reason: str = "平台注册与验证已完成",
    ) -> RegistrationTask:
        evidence = self._require_evidence(task, evidence_ref)
        task.external_evidence_ref = evidence
        return self._transition(task, "REGISTERED", reason=reason)

    def start_email_verification(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        confirmation: RegistrationConfirmation | None,
        reason: str = "人工确认访问验证链接",
    ) -> RegistrationTask:
        self._require_confirmation(task, confirmation, "VERIFY_EMAIL")
        return self._transition(task, "VERIFYING_EMAIL", reason=reason)

    def mark_submission_unknown(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "提交结果未知",
    ) -> RegistrationTask:
        if task.task_status == "PROCESSING" and task.last_external_action not in SUBMISSION_ACTIONS:
            _invalid_state()
        return self._transition(task, "SUBMISSION_UNKNOWN", reason=reason)

    def recover_submission_unknown(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "提交标记存在但 Worker 租约过期，等待人工核查",
    ) -> RegistrationTask:
        result = self.mark_submission_unknown(task, actor_id=actor_id, reason=reason)
        result.worker_id = None
        result.lease_expires_at = None
        result.available_at = None
        result.retryable = False
        result.last_heartbeat_at = utc_now()
        result.completed_at = result.last_activity_at
        return result

    def validate_worker_result(
        self,
        task: RegistrationTask,
        target: str,
        *,
        evidence_ref: str | None,
    ) -> None:
        if target not in _WORKER_RESULTS:
            _invalid_state()
        if target in {"REGISTERED", "SUBMITTED"}:
            self._require_evidence(task, evidence_ref)
        self.validate_transition(task, target)

    def cancel(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "用户取消",
    ) -> RegistrationTask:
        if task.task_status == "CANCELLED":
            return task
        self._transition(task, "CANCELLED", reason=reason)
        task.cancel_requested = True
        return task

    def restart(
        self,
        task: RegistrationTask,
        *,
        actor_id: str,
        reason: str = "重新执行",
    ) -> RegistrationTask:
        retryable_failure = task.task_status == "FAILED" and task.retryable
        if task.task_status != "CANCELLED" and not retryable_failure:
            _invalid_state()
        if task.last_external_action is not None:
            raise AppError(
                409,
                "PLATFORM_RECONCILIATION_REQUIRED",
                "涉及外部动作的重试必须先核查平台实际状态",
            )
        self._transition(task, "PENDING", reason=reason)
        now = utc_now()
        task.cancel_requested = False
        task.retryable = False
        task.worker_id = None
        task.lease_expires_at = None
        task.available_at = now
        task.last_activity_at = now
        return task

    def resume_handoff(self, task: RegistrationTask, *, actor_id: str) -> RegistrationTask:
        if (
            task.task_status != "NEEDS_MANUAL_REVIEW"
            or not (task.current_step or "").startswith("HANDOFF_")
            or task.last_external_action is not None
        ):
            raise AppError(
                409,
                "INVALID_TASK_STATE",
                "只有未产生外部最终动作的人工接管任务可以恢复",
            )
        self._transition(task, "PENDING", reason="HANDOFF_RESUMED")
        now = utc_now()
        task.cancel_requested = False
        task.retryable = False
        task.worker_id = None
        task.lease_expires_at = None
        task.available_at = now
        task.last_activity_at = now
        task.completed_at = None
        task.error_code = None
        task.error_message = None
        return task
