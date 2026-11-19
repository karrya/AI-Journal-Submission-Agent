"""Authorized registration task creation, queries, cancellation, and retry."""

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Author,
    AuthorAuthorization,
    Journal,
    JournalSubmissionPortal,
    Publisher,
    RegistrationTask,
    User,
    utc_now,
)
from app.repositories.authorizations import AuthorizationRepository
from app.repositories.registration import RegistrationRepository
from app.schemas.registration import RegistrationTaskCreate
from app.services.audit import AuditService
from app.services.permissions import Permission, has_author_permission
from app.services.registration_admission import (
    AdmissionResult,
    require_supported_registration_target,
)
from app.services.registration_authorization import require_registration_consent
from app.services.registration_workflow import RegistrationWorkflowService

_AUDIT_FIELDS = frozenset(
    {
        "task_status",
        "current_step",
        "retryable",
        "retry_count",
        "reused",
    }
)


class RegistrationService:
    def __init__(self, db: Session, user: User, request_id: str | None = None):
        self.db = db
        self.user = user
        self.request_id = request_id or str(uuid4())
        self.repository = RegistrationRepository(db)
        self.workflow = RegistrationWorkflowService()
        self.audit = AuditService(db)

    def _require_consent(self, author_id: str, authorization_id: str) -> None:
        require_registration_consent(
            self.db,
            self.user,
            author_id,
            authorization_id,
            {"account:register"},
            self.request_id,
        )

    def _audit(
        self,
        *,
        action: str,
        target_id: str,
        result: str,
        author_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        error: AppError | None = None,
    ) -> None:
        self.audit.record(
            actor_user_id=self.user.id,
            actor_type="user",
            category="business",
            action=action,
            target_type="registration_task",
            target_id=target_id,
            author_id=author_id,
            request_id=self.request_id,
            result=result,
            before=before,
            after=after,
            allowed_fields=_AUDIT_FIELDS,
            error_code=error.code if error else None,
            error_message=error.message if error else None,
        )

    @staticmethod
    def _matches_input(
        task: RegistrationTask, payload: RegistrationTaskCreate
    ) -> bool:
        expected = {
            "author_id": str(payload.author_id),
            "publisher_id": str(payload.publisher_id),
            "journal_id": str(payload.journal_id),
            "authorization_id": str(payload.authorization_id),
            "platform_code": payload.platform_code,
        }
        return all(getattr(task, field) == value for field, value in expected.items())

    def _reuse_existing(
        self, task: RegistrationTask, payload: RegistrationTaskCreate
    ) -> RegistrationTask:
        if not self._matches_input(task, payload):
            raise AppError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "相同幂等键已用于其他注册任务",
            )
        journal_id = task.journal_id
        portal_id = task.portal_id
        if journal_id is None or portal_id is None:
            raise AppError(409, "INVALID_TASK_STATE", "注册任务缺少期刊或投稿入口")
        require_supported_registration_target(
            self.db,
            task.publisher_id,
            journal_id,
            portal_id,
            task.platform_code,
        )
        return task

    def _admit_new_target(
        self, payload: RegistrationTaskCreate
    ) -> AdmissionResult:
        portal_ids = list(
            self.db.scalars(
                select(JournalSubmissionPortal.id)
                .where(
                    JournalSubmissionPortal.journal_id == str(payload.journal_id),
                    JournalSubmissionPortal.platform_code == payload.platform_code,
                )
                .order_by(
                    JournalSubmissionPortal.created_at.desc(),
                    JournalSubmissionPortal.id.asc(),
                )
                .with_for_update()
            )
        )
        first_error: AppError | None = None
        for portal_id in portal_ids:
            try:
                return require_supported_registration_target(
                    self.db,
                    str(payload.publisher_id),
                    str(payload.journal_id),
                    portal_id,
                    payload.platform_code,
                )
            except AppError as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error
        raise AppError(404, "JOURNAL_ENDPOINT_NOT_FOUND", "期刊入口不存在")

    def _reject_conflicting_task(self, payload: RegistrationTaskCreate, portal_id: str) -> None:
        conflict = self.db.scalar(
            select(RegistrationTask.id).where(
                RegistrationTask.author_id == str(payload.author_id),
                RegistrationTask.portal_id == portal_id,
                RegistrationTask.blocking_scope == "BLOCKED",
            )
        )
        if conflict is not None:
            raise AppError(
                409,
                "REGISTRATION_TASK_CONFLICT",
                "同一作者和投稿入口已有需完成或人工核查的注册任务",
            )

    def _reject_replacement_task(self, task: RegistrationTask) -> None:
        self.db.scalar(
            select(JournalSubmissionPortal.id)
            .where(JournalSubmissionPortal.id == task.portal_id)
            .with_for_update()
        )
        conflict = self.db.scalar(
            select(RegistrationTask.id).where(
                RegistrationTask.author_id == task.author_id,
                RegistrationTask.portal_id == task.portal_id,
                RegistrationTask.blocking_scope == "BLOCKED",
                RegistrationTask.id != task.id,
            )
        )
        if conflict is not None:
            raise AppError(
                409,
                "REGISTRATION_TASK_CONFLICT",
                "同一作者和投稿入口已有替代任务，不能重试旧任务",
            )

    def _create_task(
        self, payload: RegistrationTaskCreate, target_id: str
    ) -> tuple[RegistrationTask, bool]:
        self._require_consent(str(payload.author_id), str(payload.authorization_id))
        existing = self.repository.task_by_idempotency(payload.idempotency_key)
        if existing is not None:
            return self._reuse_existing(existing, payload), True

        admission = self._admit_new_target(payload)
        # The portal lock serializes scope checks; recheck idempotency after waiting.
        existing = self.repository.task_by_idempotency(payload.idempotency_key)
        if existing is not None:
            return self._reuse_existing(existing, payload), True
        self._reject_conflicting_task(payload, admission.portal.id)
        task = RegistrationTask(
            id=target_id,
            author_id=str(payload.author_id),
            publisher_id=str(payload.publisher_id),
            journal_id=str(payload.journal_id),
            portal_id=admission.portal.id,
            authorization_id=str(payload.authorization_id),
            platform_code=payload.platform_code,
            adapter_code=admission.adapter.adapter_code,
            adapter_version=admission.adapter.adapter_version,
            task_status="PENDING",
            idempotency_key=payload.idempotency_key,
            created_by=self.user.id,
            available_at=utc_now(),
        )
        self.db.add(task)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing = self.repository.task_by_idempotency(payload.idempotency_key)
            if existing is not None:
                return self._reuse_existing(existing, payload), True
            self._reject_conflicting_task(payload, admission.portal.id)
            raise
        return task, False

    def create_task(self, payload: RegistrationTaskCreate) -> RegistrationTask:
        target_id = str(uuid4())
        try:
            task, reused = self._create_task(payload, target_id)
            self._audit(
                action="registration.task.create",
                target_id=task.id,
                author_id=task.author_id,
                result="success",
                after={"task_status": task.task_status, "reused": reused},
            )
            self.db.commit()
            return task
        except AppError as exc:
            self.db.rollback()
            self._audit(
                action="registration.task.create",
                target_id=target_id,
                result="failure",
                error=exc,
            )
            self.db.commit()
            raise

    def get_task(self, task_id: str) -> RegistrationTask:
        task = self.db.get(RegistrationTask, str(task_id))
        if task is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        self._require_consent(task.author_id, task.authorization_id)
        return task

    def _authorized_grant_ids(self) -> list[str]:
        active_grants = AuthorizationRepository.active_grant_query(
            user_id=self.user.id,
            author_id=AuthorAuthorization.author_id,
            permission="account:register",
            now_utc=utc_now(),
        )
        grants = self.db.execute(
            select(AuthorAuthorization.id, AuthorAuthorization.author_id).where(
                AuthorAuthorization.id.in_(active_grants)
            )
        ).all()
        return [
            grant_id
            for grant_id, author_id in grants
            if has_author_permission(
                self.db,
                self.user,
                author_id,
                Permission.ACCOUNT_REGISTER,
            )
        ]

    def list_tasks(
        self,
        filters: Mapping[str, object] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[RegistrationTask], int]:
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        filters = filters or {}
        authorized_grants = self._authorized_grant_ids()
        if not authorized_grants:
            return [], 0

        predicates: list[ColumnElement[bool]] = [
            RegistrationTask.authorization_id.in_(authorized_grants),
            Author.deleted_at.is_(None),
            Publisher.deleted_at.is_(None),
            RegistrationTask.journal_id.is_(None) | Journal.deleted_at.is_(None),
        ]
        for field in ("author_id", "publisher_id", "journal_id", "task_status"):
            value = filters.get(field)
            if value is not None:
                predicates.append(getattr(RegistrationTask, field) == value)
        created_from = filters.get("created_from")
        if created_from is not None:
            predicates.append(RegistrationTask.created_at >= created_from)
        created_to = filters.get("created_to")
        if created_to is not None:
            predicates.append(RegistrationTask.created_at <= created_to)

        statement = (
            select(RegistrationTask)
            .join(Author, Author.id == RegistrationTask.author_id)
            .join(Publisher, Publisher.id == RegistrationTask.publisher_id)
            .outerjoin(Journal, Journal.id == RegistrationTask.journal_id)
            .where(*predicates)
        )
        total = (
            self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        records = self.db.scalars(
            statement.order_by(
                RegistrationTask.created_at.desc(), RegistrationTask.id.asc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(records), total

    def _task_for_update(self, task_id: str) -> RegistrationTask:
        task = self.db.scalar(
            select(RegistrationTask)
            .where(RegistrationTask.id == str(task_id))
            .with_for_update()
        )
        if task is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        self._require_consent(task.author_id, task.authorization_id)
        return task

    def cancel_task(
        self, task_id: str, *, reason: str = "用户取消"
    ) -> RegistrationTask:
        try:
            task = self._task_for_update(task_id)
            before = {"task_status": task.task_status, "retryable": task.retryable}
            self.workflow.cancel(task, actor_id=self.user.id, reason=reason)
            self._audit(
                action="registration.task.cancel",
                target_id=task.id,
                author_id=task.author_id,
                result="success",
                before=before,
                after={
                    "task_status": task.task_status,
                    "current_step": task.current_step,
                    "retryable": task.retryable,
                },
            )
            self.db.commit()
            return task
        except AppError as exc:
            self.db.rollback()
            failed_task = self.db.get(RegistrationTask, str(task_id))
            self._audit(
                action="registration.task.cancel",
                target_id=str(task_id),
                author_id=failed_task.author_id if failed_task else None,
                result="failure",
                error=exc,
            )
            self.db.commit()
            raise

    def retry_task(
        self, task_id: str, *, reason: str = "重新执行"
    ) -> RegistrationTask:
        try:
            task = self._task_for_update(task_id)
            self._reject_replacement_task(task)
            before = {"task_status": task.task_status, "retryable": task.retryable}
            self.workflow.restart(task, actor_id=self.user.id, reason=reason)
            self._audit(
                action="registration.task.retry",
                target_id=task.id,
                author_id=task.author_id,
                result="success",
                before=before,
                after={
                    "task_status": task.task_status,
                    "current_step": task.current_step,
                    "retryable": task.retryable,
                },
            )
            self.db.commit()
            return task
        except AppError as exc:
            self.db.rollback()
            failed_task = self.db.get(RegistrationTask, str(task_id))
            self._audit(
                action="registration.task.retry",
                target_id=str(task_id),
                author_id=failed_task.author_id if failed_task else None,
                result="failure",
                error=exc,
            )
            self.db.commit()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            if "uk_registration_blocking_scope" not in str(exc):
                raise
            failed_task = self.db.get(RegistrationTask, str(task_id))
            conflict = AppError(
                409,
                "REGISTRATION_TASK_CONFLICT",
                "同一作者和投稿入口已有替代任务，不能重试旧任务",
            )
            self._audit(
                action="registration.task.retry",
                target_id=str(task_id),
                author_id=failed_task.author_id if failed_task else None,
                result="failure",
                error=conflict,
            )
            self.db.commit()
            raise conflict from exc
