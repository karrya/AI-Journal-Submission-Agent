import logging
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Event
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import RegistrationTask, User, utc_now
from app.services.registration_admission import require_supported_registration_target
from app.services.registration_authorization import require_registration_consent

logger = logging.getLogger(__name__)

_SUBMISSION_ACTIONS = frozenset({"SUBMIT", "SUBMITTING", "SUBMISSION_UNKNOWN"})
_CHECKPOINT_FIELDS = frozenset(
    {
        "current_step",
        "last_external_action",
        "external_evidence_ref",
        "browser_handoff_id",
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
    ):
        self.engine = engine
        self.worker_id = worker_id
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds
        self.max_retry_delay_seconds = max_retry_delay_seconds

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

    def claim_next(self) -> str | None:
        now = utc_now()
        with Session(bind=self.engine, expire_on_commit=False) as session:
            candidate_id = session.scalar(
                select(RegistrationTask.id)
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
            if candidate_id is None:
                return None
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
            )
            if result.rowcount != 1:
                session.rollback()
                return None
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
                )
                if updated.rowcount != 1:
                    session.rollback()
                    if self._cancel_requested(task_id):
                        raise TaskCancelled()
                    raise TaskLeaseLost()
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
            checkpoint={"current_step": "MANUAL_REVIEW_REQUIRED"},
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
        with Session(bind=self.engine) as session:
            session.execute(
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
            )
            session.commit()

    def _retry_delay(self, retry_count: int) -> int:
        exponent = min(max(retry_count - 1, 0), 31)
        return min(
            self.retry_base_seconds * (2**exponent),
            self.max_retry_delay_seconds,
        )

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
            can_retry = retryable and not submission_unknown
            values = {
                "task_status": (
                    "SUBMISSION_UNKNOWN"
                    if submission_unknown
                    else "PENDING" if can_retry else "FAILED"
                ),
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
            updated = session.execute(
                update(RegistrationTask)
                .where(self._owned(task.id, allow_cancel=False))
                .values(**values)
            )
            if updated.rowcount != 1:
                session.rollback()
                if self._cancel_requested(task_id):
                    self._save_cancelled(task_id)
                return
            session.commit()

    def run_forever(self, *, poll_interval: float = 1.0, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        while not stop.is_set():
            if not self.run_once():
                stop.wait(poll_interval)
