import logging
import random
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Event
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import RegistrationTask, User, utc_now
from app.services.audit import AuditService
from app.services.registration_admission import require_supported_registration_target
from app.services.registration_authorization import require_registration_consent
from app.services.registration_workflow import (
    SUBMISSION_ACTIONS,
    RegistrationWorkflowService,
)

logger = logging.getLogger(__name__)

_SUBMISSION_ACTIONS = SUBMISSION_ACTIONS
_CHECKPOINT_FIELDS = frozenset(
    {
        "current_step",
        "last_external_action",
        "external_evidence_ref",
        "browser_handoff_id",
    }
)
_AUDIT_FIELDS = frozenset(
    {
        "task_status",
        "current_step",
        "retryable",
        "retry_count",
        "error_code",
    }
)


@dataclass
class RegistrationExecutionResult:
    status: str
    checkpoint: dict = field(default_factory=dict)


class RegistrationExecutionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        code: str = "REGISTRATION_EXECUTION_ERROR",
    ):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class TaskCancelled(Exception):
    pass


class TaskLeaseLost(Exception):
    pass


class RegistrationWorker:
    def __init__(
        self,
        engine,
        *,
        worker_id: str,
        executor=None,
        lease_seconds: int = 300,
        retry_base_seconds: int = 5,
        max_retry_delay_seconds: int = 300,
        retry_jitter_ratio: float = 0.2,
        max_retries: int = 3,
    ):
        if retry_jitter_ratio < 0 or retry_jitter_ratio > 1:
            raise ValueError("retry_jitter_ratio must be between 0 and 1")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self.engine = engine
        self.worker_id = worker_id
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds
        self.max_retry_delay_seconds = max_retry_delay_seconds
        self.retry_jitter_ratio = retry_jitter_ratio
        self.max_retries = max_retries
        self.workflow = RegistrationWorkflowService()

    @staticmethod
    def _has_no_unknown_submission():
        return or_(
            RegistrationTask.last_external_action.is_(None),
            RegistrationTask.last_external_action.not_in(_SUBMISSION_ACTIONS),
        )

    def _claimable(self, task_id, now):
        return and_(
            RegistrationTask.id == task_id,
            RegistrationTask.cancel_requested.is_(False),
            self._has_no_unknown_submission(),
            or_(
                and_(
                    RegistrationTask.task_status == "PENDING",
                    or_(
                        RegistrationTask.available_at.is_(None),
                        RegistrationTask.available_at <= now,
                    ),
                ),
                and_(
                    RegistrationTask.task_status == "PROCESSING",
                    RegistrationTask.lease_expires_at.is_not(None),
                    RegistrationTask.lease_expires_at < now,
                ),
            ),
        )

    def _owned(self, task_id, *, allow_cancel: bool):
        conditions = [
            RegistrationTask.id == str(task_id),
            RegistrationTask.worker_id == self.worker_id,
            RegistrationTask.task_status == "PROCESSING",
        ]
        if not allow_cancel:
            conditions.append(RegistrationTask.cancel_requested.is_(False))
        return and_(*conditions)

    @staticmethod
    def _audit(
        session: Session,
        task: RegistrationTask,
        *,
        action: str,
        result: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        AuditService(session).record(
            actor_user_id=None,
            actor_type="system",
            category="business",
            action=action,
            target_type="registration_task",
            target_id=task.id,
            author_id=task.author_id,
            request_id=str(uuid4()),
            result=result,
            before=before,
            after=after,
            allowed_fields=_AUDIT_FIELDS,
            error_code=error_code,
            error_message=(
                "注册任务执行失败；未将执行器详细消息写入审计"
                if error_code
                else None
            ),
        )

    def _recover_expired_submissions(self, now) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            candidate_ids = list(
                session.scalars(
                    select(RegistrationTask.id).where(
                        RegistrationTask.task_status == "PROCESSING",
                        RegistrationTask.lease_expires_at.is_not(None),
                        RegistrationTask.lease_expires_at < now,
                        RegistrationTask.last_external_action.in_(
                            _SUBMISSION_ACTIONS
                        ),
                    )
                )
            )
            for task_id in candidate_ids:
                task = session.scalar(
                    select(RegistrationTask)
                    .where(RegistrationTask.id == task_id)
                    .with_for_update()
                )
                if (
                    task is None
                    or task.task_status != "PROCESSING"
                    or task.lease_expires_at is None
                    or task.lease_expires_at >= now
                    or task.last_external_action not in _SUBMISSION_ACTIONS
                ):
                    continue
                before = {
                    "task_status": task.task_status,
                    "retryable": task.retryable,
                }
                self.workflow.recover_submission_unknown(
                    task, actor_id=self.worker_id
                )
                self._audit(
                    session,
                    task,
                    action="registration.task.recover_submission_unknown",
                    result="success",
                    before=before,
                    after={
                        "task_status": task.task_status,
                        "current_step": task.current_step,
                        "retryable": task.retryable,
                    },
                )
            session.commit()

    def claim_next(self) -> str | None:
        now = utc_now()
        self._recover_expired_submissions(now)
        with Session(bind=self.engine, expire_on_commit=False) as session:
            candidate = session.scalar(
                select(RegistrationTask)
                .where(
                    RegistrationTask.cancel_requested.is_(False),
                    self._has_no_unknown_submission(),
                    or_(
                        and_(
                            RegistrationTask.task_status == "PENDING",
                            or_(
                                RegistrationTask.available_at.is_(None),
                                RegistrationTask.available_at <= now,
                            ),
                        ),
                        and_(
                            RegistrationTask.task_status == "PROCESSING",
                            RegistrationTask.lease_expires_at.is_not(None),
                            RegistrationTask.lease_expires_at < now,
                        ),
                    ),
                )
                .order_by(RegistrationTask.created_at, RegistrationTask.id)
                .limit(1)
            )
            if candidate is None:
                return None
            candidate_id = candidate.id
            self.workflow.validate_transition(candidate, "PROCESSING")
            before = {
                "task_status": candidate.task_status,
                "retry_count": candidate.retry_count,
            }
            result = session.execute(
                update(RegistrationTask)
                .where(self._claimable(candidate_id, now))
                .values(
                    task_status="PROCESSING",
                    current_step="CLAIMED",
                    worker_id=self.worker_id,
                    lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                    available_at=None,
                    last_heartbeat_at=now,
                    last_activity_at=now,
                    started_at=now,
                    completed_at=None,
                    retry_count=RegistrationTask.retry_count + 1,
                    retryable=False,
                    error_code=None,
                    error_message=None,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            self._audit(
                session,
                candidate,
                action="registration.task.claim",
                result="success",
                before=before,
                after={
                    "task_status": "PROCESSING",
                    "current_step": "CLAIMED",
                    "retry_count": candidate.retry_count + 1,
                    "retryable": False,
                },
            )
            session.commit()
            return candidate_id

    def run_once(self) -> bool:
        task_id = self.claim_next()
        if task_id is None:
            return False
        self.execute_claimed(task_id)
        return True

    @staticmethod
    def _checkpoint_values(checkpoint: dict) -> dict:
        return {
            key: value for key, value in checkpoint.items() if key in _CHECKPOINT_FIELDS
        }

    def _save_checkpoint(self, session: Session, task: RegistrationTask, checkpoint: dict):
        now = utc_now()
        updated = session.execute(
            update(RegistrationTask)
            .where(self._owned(task.id, allow_cancel=False))
            .values(
                **self._checkpoint_values(checkpoint),
                last_heartbeat_at=now,
                last_activity_at=now,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
            )
        )
        if updated.rowcount != 1:
            session.rollback()
            if self._cancel_requested(task.id):
                raise TaskCancelled()
            raise TaskLeaseLost()
        session.commit()

    def save_checkpoint(self, task_id: UUID | str, checkpoint: dict) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            task = session.get(RegistrationTask, str(task_id))
            if task is None:
                raise TaskLeaseLost()
            self._ensure_not_cancelled(task)
            self._ensure_owned(task)
            self._validate_prerequisites(task, session)
            self._save_checkpoint(session, task, checkpoint)

    def execute_claimed(self, task_id: UUID | str) -> None:
        try:
            with Session(bind=self.engine, expire_on_commit=False) as session:
                task = session.get(RegistrationTask, str(task_id))
                if task is None:
                    return
                self._ensure_not_cancelled(task)
                self._ensure_owned(task)
                if task.last_external_action in _SUBMISSION_ACTIONS:
                    logger.warning(
                        "注册任务存在未知提交动作，停止自动重放 task_id=%s", task_id
                    )
                    return
                self._validate_prerequisites(task, session)
                executor = self.executor or self._default_executor
                result = executor(task, session)

                self._revalidate_claimed(task_id)
                evidence_ref = result.checkpoint.get("external_evidence_ref")
                self.workflow.validate_worker_result(
                    task, result.status, evidence_ref=evidence_ref
                )
                now = utc_now()
                updated = session.execute(
                    update(RegistrationTask)
                    .where(self._owned(task.id, allow_cancel=False))
                    .values(
                        task_status=result.status,
                        **self._checkpoint_values(result.checkpoint),
                        last_heartbeat_at=now,
                        last_activity_at=now,
                        completed_at=now,
                        available_at=None,
                        worker_id=None,
                        lease_expires_at=None,
                        retryable=False,
                        error_code=None,
                        error_message=None,
                    )
                    .execution_options(synchronize_session=False)
                )
                if updated.rowcount != 1:
                    session.rollback()
                    if self._cancel_requested(task_id):
                        raise TaskCancelled()
                    raise TaskLeaseLost()
                self._audit(
                    session,
                    task,
                    action="registration.task.result",
                    result="success",
                    before={"task_status": "PROCESSING"},
                    after={
                        "task_status": result.status,
                        "current_step": result.checkpoint.get("current_step"),
                        "retryable": False,
                    },
                )
                session.commit()
        except TaskCancelled:
            self._save_cancelled(task_id)
        except TaskLeaseLost:
            logger.info("注册任务租约已失效，放弃提交 task_id=%s", task_id)
        except RegistrationExecutionError as exc:
            self._save_failure(
                task_id,
                code=exc.code,
                message=str(exc)[:1000],
                retryable=exc.retryable,
            )
        except AppError as exc:
            self._save_failure(
                task_id,
                code=exc.code,
                message=exc.message[:1000],
                retryable=False,
            )
        except Exception:
            logger.exception("注册任务执行失败 task_id=%s", task_id)
            self._save_failure(
                task_id,
                code="REGISTRATION_FAILED",
                message="注册任务执行失败，请查看脱敏日志",
                retryable=False,
            )

    @staticmethod
    def _ensure_not_cancelled(task: RegistrationTask) -> None:
        if task.cancel_requested or task.task_status == "CANCELLED":
            raise TaskCancelled()

    def _ensure_owned(self, task: RegistrationTask) -> None:
        if task.worker_id != self.worker_id or task.task_status != "PROCESSING":
            raise TaskLeaseLost()

    def _validate_prerequisites(self, task: RegistrationTask, session: Session) -> None:
        self._ensure_not_cancelled(task)
        user = session.get(User, task.created_by) if task.created_by else None
        if user is None:
            raise AppError(403, "AUTHORIZATION_INVALID", "作者注册授权无效")
        require_registration_consent(
            session,
            user,
            task.author_id,
            task.authorization_id,
            {"account:register"},
            f"registration-worker:{task.id}",
        )
        journal_id = task.journal_id
        portal_id = task.portal_id
        if journal_id is None or portal_id is None:
            raise AppError(409, "INVALID_TASK_STATE", "注册任务缺少期刊或投稿入口")
        require_supported_registration_target(
            session,
            task.publisher_id,
            journal_id,
            portal_id,
            task.platform_code,
        )

    @staticmethod
    def _default_executor(task, session) -> RegistrationExecutionResult:
        return RegistrationExecutionResult(
            "NEEDS_MANUAL_REVIEW",
            checkpoint={"current_step": "MANUAL_REVIEW_REQUIRED_NO_EXTERNAL_ACTION"},
        )

    def _revalidate_claimed(self, task_id: UUID | str) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            task = session.get(RegistrationTask, str(task_id))
            if task is None:
                raise TaskLeaseLost()
            self._ensure_not_cancelled(task)
            self._ensure_owned(task)
            self._validate_prerequisites(task, session)

    def _cancel_requested(self, task_id: UUID | str) -> bool:
        with Session(bind=self.engine) as session:
            row = session.execute(
                select(RegistrationTask.cancel_requested, RegistrationTask.task_status).where(
                    RegistrationTask.id == str(task_id),
                    RegistrationTask.worker_id == self.worker_id,
                )
            ).first()
            return bool(row and (row[0] or row[1] == "CANCELLED"))

    def _save_cancelled(self, task_id: UUID | str) -> None:
        now = utc_now()
        with Session(bind=self.engine, expire_on_commit=False) as session:
            task = session.get(RegistrationTask, str(task_id))
            if task is None or task.worker_id != self.worker_id:
                return
            before = {"task_status": task.task_status, "retryable": task.retryable}
            self.workflow.cancel(
                task, actor_id=self.worker_id, reason="Worker 在下一安全检查点停止"
            )
            updated = session.execute(
                update(RegistrationTask)
                .where(
                    RegistrationTask.id == str(task_id),
                    RegistrationTask.worker_id == self.worker_id,
                    RegistrationTask.task_status.in_(["PROCESSING", "CANCELLED"]),
                )
                .values(
                    task_status="CANCELLED",
                    retryable=False,
                    available_at=None,
                    last_heartbeat_at=now,
                    last_activity_at=now,
                    completed_at=now,
                    worker_id=None,
                    lease_expires_at=None,
                    error_code=None,
                    error_message=None,
                )
                .execution_options(synchronize_session=False)
            )
            if updated.rowcount != 1:
                session.rollback()
                return
            self._audit(
                session,
                task,
                action="registration.task.cancel",
                result="success",
                before=before,
                after={"task_status": "CANCELLED", "retryable": False},
            )
            session.commit()

    def _retry_delay(self, retry_count: int) -> int:
        exponent = min(max(retry_count - 1, 0), 31)
        base = min(
            self.retry_base_seconds * (2**exponent),
            self.max_retry_delay_seconds,
        )
        bound = base * self.retry_jitter_ratio
        jittered = base + random.uniform(-bound, bound)
        return max(0, min(self.max_retry_delay_seconds, round(jittered)))

    def _save_failure(
        self,
        task_id: UUID | str,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            task = session.get(RegistrationTask, str(task_id))
            if task is None:
                return
            now = utc_now()
            submission_unknown = task.last_external_action in _SUBMISSION_ACTIONS
            can_retry = (
                retryable
                and not submission_unknown
                and task.retry_count < self.max_retries
            )
            exhausted = retryable and not submission_unknown and not can_retry
            target = (
                "SUBMISSION_UNKNOWN"
                if submission_unknown
                else "PENDING"
                if can_retry
                else "NEEDS_MANUAL_REVIEW"
                if exhausted
                else "FAILED"
            )
            self.workflow.validate_transition(task, target)
            before = {"task_status": task.task_status, "retryable": task.retryable}
            values = {
                "task_status": target,
                "retryable": can_retry,
                "available_at": (
                    now + timedelta(seconds=self._retry_delay(task.retry_count))
                    if can_retry
                    else None
                ),
                "last_heartbeat_at": now,
                "last_activity_at": now,
                "completed_at": now if not can_retry else None,
                "worker_id": None,
                "lease_expires_at": None,
                "error_code": code,
                "error_message": message,
            }
            if submission_unknown:
                values["current_step"] = "SUBMISSION_UNKNOWN"
            elif can_retry:
                values["current_step"] = "RETRY_WAIT"
            elif exhausted:
                values["current_step"] = "RETRY_LIMIT_MANUAL_REVIEW"
            updated = session.execute(
                update(RegistrationTask)
                .where(self._owned(task.id, allow_cancel=False))
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            if updated.rowcount != 1:
                session.rollback()
                if self._cancel_requested(task_id):
                    self._save_cancelled(task_id)
                return
            self._audit(
                session,
                task,
                action="registration.task.failure",
                result="failure",
                before=before,
                after={
                    "task_status": target,
                    "current_step": values.get("current_step"),
                    "retryable": can_retry,
                    "retry_count": task.retry_count,
                    "error_code": code,
                },
                error_code=code,
            )
            session.commit()

    def run_forever(self, *, poll_interval: float = 1.0, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        while not stop.is_set():
            if not self.run_once():
                stop.wait(poll_interval)
