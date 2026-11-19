"""Hash-bound, single-use confirmations for registration actions."""

import hashlib
import json
import secrets
from datetime import timedelta
from typing import NoReturn

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import RegistrationConfirmation, RegistrationTask, User, utc_now
from app.schemas.confirmation import ConfirmationChallenge


class ConfirmationService:
    def __init__(self, db: Session):
        self.db = db

    def create_challenge(
        self,
        *,
        task: RegistrationTask,
        action_type: str,
        summary: dict,
        user: User,
        ttl_seconds: int = 600,
    ) -> ConfirmationChallenge:
        token = secrets.token_urlsafe(32)
        canonical = json.dumps(
            summary,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        summary_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        record = RegistrationConfirmation(
            task_id=task.id,
            action_type=action_type,
            summary_hash=summary_hash,
            token_hash=token_hash,
            requested_by=user.id,
            expires_at=utc_now() + timedelta(seconds=ttl_seconds),
        )
        self.db.add(record)
        self.db.flush()
        return ConfirmationChallenge(
            id=record.id,
            token=token,
            summary_hash=summary_hash,
        )

    def consume(
        self,
        task: RegistrationTask,
        confirmation_id: str,
        token: str,
        summary_hash: str,
        user: User,
    ) -> RegistrationConfirmation:
        now = utc_now()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        result = self.db.execute(
            update(RegistrationConfirmation)
            .where(
                RegistrationConfirmation.id == confirmation_id,
                RegistrationConfirmation.task_id == task.id,
                RegistrationConfirmation.requested_by == user.id,
                RegistrationConfirmation.consumed_at.is_(None),
                RegistrationConfirmation.expires_at > now,
                RegistrationConfirmation.token_hash == token_hash,
                RegistrationConfirmation.summary_hash == summary_hash,
            )
            .values(consumed_at=text("CURRENT_TIMESTAMP(6)"))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self._reject_consume(
                task,
                confirmation_id,
                token_hash,
                summary_hash,
                user,
                now,
            )

        record = self.db.execute(
            select(RegistrationConfirmation)
            .where(RegistrationConfirmation.id == confirmation_id)
            .execution_options(populate_existing=True)
        ).scalar_one()
        self.db.commit()
        return record

    def _reject_consume(
        self,
        task: RegistrationTask,
        confirmation_id: str,
        token_hash: str,
        summary_hash: str,
        user: User,
        now,
    ) -> None:
        record = self.db.scalar(
            select(RegistrationConfirmation)
            .where(RegistrationConfirmation.id == confirmation_id)
            .execution_options(populate_existing=True)
        )
        if record is None or not (
            record.task_id == task.id
            and record.requested_by == user.id
            and secrets.compare_digest(record.token_hash, token_hash)
            and secrets.compare_digest(record.summary_hash, summary_hash)
        ):
            self._invalid()
        if record.consumed_at is not None:
            raise AppError(409, "CONFIRMATION_CONSUMED", "确认已使用")
        if record.expires_at <= now:
            raise AppError(409, "CONFIRMATION_EXPIRED", "确认已过期")
        self._invalid()

    @staticmethod
    def _invalid() -> NoReturn:
        raise AppError(409, "CONFIRMATION_INVALID", "确认请求无效")
