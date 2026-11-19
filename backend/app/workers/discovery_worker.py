import logging
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Event
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models import DiscoveryTask, utc_now
from app.services.discovery_providers import ProviderError

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    status: str = "SUCCEEDED"
    checkpoint: dict = field(default_factory=dict)
    journal_id: str | None = None
    stage: str | None = None


class TaskCancelled(Exception):
    pass


class TaskLeaseLost(Exception):
    pass


class DiscoveryWorker:
    def __init__(
        self,
        engine,
        *,
        worker_id: str,
        executor=None,
        lease_seconds: int = 300,
        retry_base_seconds: int = 5,
    ):
        self.engine = engine
        self.worker_id = worker_id
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds

    def _claimable(self, task_id, now):
        return and_(
            DiscoveryTask.id == task_id,
            DiscoveryTask.cancel_requested.is_(False),
            or_(
                and_(
                    DiscoveryTask.status == "PENDING",
                    or_(
                        DiscoveryTask.available_at.is_(None),
                        DiscoveryTask.available_at <= now,
                    ),
                ),
                and_(
                    DiscoveryTask.status == "PROCESSING",
                    DiscoveryTask.lease_expires_at.is_not(None),
                    DiscoveryTask.lease_expires_at < now,
                ),
            ),
        )

    def _owned(self, task_id, *, allow_cancel: bool):
        conditions = [
            DiscoveryTask.id == task_id,
            DiscoveryTask.worker_id == self.worker_id,
            DiscoveryTask.status == "PROCESSING",
        ]
        if not allow_cancel:
            conditions.append(DiscoveryTask.cancel_requested.is_(False))
        return and_(*conditions)

    def claim_next(self) -> UUID | None:
        now = utc_now()
        with Session(bind=self.engine, expire_on_commit=False) as session:
            candidate_id = session.scalar(
                select(DiscoveryTask.id)
                .where(
                    DiscoveryTask.cancel_requested.is_(False),
                    or_(
                        and_(
                            DiscoveryTask.status == "PENDING",
                            or_(
                                DiscoveryTask.available_at.is_(None),
                                DiscoveryTask.available_at <= now,
                            ),
                        ),
                        and_(
                            DiscoveryTask.status == "PROCESSING",
                            DiscoveryTask.lease_expires_at.is_not(None),
                            DiscoveryTask.lease_expires_at < now,
                        ),
                    ),
                )
                .order_by(DiscoveryTask.created_at, DiscoveryTask.id)
                .limit(1)
            )
            if candidate_id is None:
                return None
            result = session.execute(
                update(DiscoveryTask)
                .where(self._claimable(candidate_id, now))
                .values(
                    status="PROCESSING",
                    stage="CLAIMED",
                    progress=0,
                    worker_id=self.worker_id,
                    lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                    started_at=now,
                    completed_at=None,
                    attempt_count=DiscoveryTask.attempt_count + 1,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            return UUID(candidate_id)

    def run_once(self) -> bool:
        task_id = self.claim_next()
        if task_id is None:
            return False
        self.execute_claimed(task_id)
        return True

    def execute_claimed(self, task_id: UUID) -> None:
        try:
            with Session(bind=self.engine, expire_on_commit=False) as session:
                task = session.get(DiscoveryTask, str(task_id))
                if task is None:
                    return
                if task.cancel_requested:
                    raise TaskCancelled()
                executor = self.executor or self._default_executor
                result = executor(task, session)
                checkpoint = result.checkpoint or {
                    "response": {
                        "task_id": task.id,
                        "status": result.status,
                        "candidates": [],
                    },
                    "warnings": [],
                }
                updated = session.execute(
                    update(DiscoveryTask)
                    .where(self._owned(task.id, allow_cancel=False))
                    .values(
                        status=result.status,
                        progress=100 if result.status == "SUCCEEDED" else task.progress,
                        stage=result.stage or task.stage or "PERSIST",
                        journal_id=result.journal_id or task.journal_id,
                        checkpoint=checkpoint,
                        completed_at=utc_now(),
                        worker_id=None,
                        lease_expires_at=None,
                        retryable=False,
                    )
                )
                if updated.rowcount != 1:
                    session.rollback()
                    if self._cancel_requested(task_id):
                        raise TaskCancelled()
                    raise TaskLeaseLost()
                session.commit()
        except TaskCancelled:
            self._save_terminal_state(task_id, "CANCELLED", None, False)
        except TaskLeaseLost:
            logger.info("识别任务租约已失效，放弃提交 task_id=%s", task_id)
        except ProviderError as exc:
            self._save_provider_failure(task_id, exc)
        except Exception:
            logger.exception("识别任务执行失败 task_id=%s", task_id)
            self._save_terminal_state(task_id, "FAILED", "DISCOVERY_FAILED", False)

    def _default_executor(self, task, session) -> ExecutionResult:
        from app.services.network_identification import NetworkIdentificationService

        return NetworkIdentificationService(
            session, worker_id=self.worker_id, lease_seconds=self.lease_seconds
        ).execute(task)

    def _cancel_requested(self, task_id: UUID) -> bool:
        with Session(bind=self.engine) as session:
            return bool(
                session.scalar(
                    select(DiscoveryTask.cancel_requested).where(
                        DiscoveryTask.id == str(task_id),
                        DiscoveryTask.worker_id == self.worker_id,
                    )
                )
            )

    def _save_provider_failure(self, task_id: UUID, error: ProviderError) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            task = session.get(DiscoveryTask, str(task_id))
            if task is None:
                return
            can_retry = error.retryable and task.attempt_count < task.max_attempts
            updated = session.execute(
                update(DiscoveryTask)
                .where(self._owned(task.id, allow_cancel=False))
                .values(
                    status="PENDING" if can_retry else "FAILED",
                    retryable=error.retryable,
                    available_at=(
                        utc_now()
                        + timedelta(
                            seconds=self.retry_base_seconds * (2 ** max(task.attempt_count - 1, 0))
                        )
                        if can_retry
                        else None
                    ),
                    stage="RETRY_WAIT" if can_retry else task.stage,
                    completed_at=None if can_retry else utc_now(),
                    worker_id=None,
                    lease_expires_at=None,
                    last_error_code="PROVIDER_ERROR",
                    last_error_message=str(error)[:1000],
                )
            )
            if updated.rowcount != 1:
                session.rollback()
                if self._cancel_requested(task_id):
                    self._save_terminal_state(task_id, "CANCELLED", None, False)
                return
            session.commit()

    def _save_terminal_state(
        self,
        task_id: UUID,
        status: str,
        error_code: str | None,
        retryable: bool,
    ) -> None:
        with Session(bind=self.engine, expire_on_commit=False) as session:
            session.execute(
                update(DiscoveryTask)
                .where(self._owned(str(task_id), allow_cancel=True))
                .values(
                    status=status,
                    retryable=retryable,
                    completed_at=utc_now(),
                    worker_id=None,
                    lease_expires_at=None,
                    last_error_code=error_code,
                    last_error_message=(
                        "识别任务执行失败，请查看脱敏日志" if error_code else None
                    ),
                )
            )
            session.commit()

    def run_forever(self, *, poll_interval: float = 1.0, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        while not stop.is_set():
            if not self.run_once():
                stop.wait(poll_interval)
