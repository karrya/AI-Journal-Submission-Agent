"""Persistence queries for registration targets, tasks, and accounts."""

import json
from collections.abc import Mapping

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    AuthorAuthorization,
    Journal,
    JournalSubmissionPortal,
    PlatformAdapter,
    Publisher,
    PublisherAccount,
    PublisherRegistrationSupport,
    RegistrationTask,
    User,
    utc_now,
)


class RegistrationRepository:
    def __init__(self, db: Session):
        self.db = db

    def publisher_support(
        self, publisher_id: str
    ) -> PublisherRegistrationSupport | None:
        return self.db.scalar(
            select(PublisherRegistrationSupport)
            .join(Publisher, Publisher.id == PublisherRegistrationSupport.publisher_id)
            .where(
                PublisherRegistrationSupport.publisher_id == publisher_id,
                Publisher.deleted_at.is_(None),
            )
        )

    def supported_portal(self, portal_id: str) -> JournalSubmissionPortal | None:
        return self.db.scalar(
            select(JournalSubmissionPortal)
            .join(Journal, Journal.id == JournalSubmissionPortal.journal_id)
            .join(Publisher, Publisher.id == Journal.publisher_id)
            .where(
                JournalSubmissionPortal.id == portal_id,
                Journal.deleted_at.is_(None),
                Publisher.deleted_at.is_(None),
            )
        )

    def adapter(self, adapter_id: str) -> PlatformAdapter | None:
        return self.db.scalar(
            select(PlatformAdapter).where(PlatformAdapter.id == adapter_id)
        )

    def task_by_idempotency(self, key: str) -> RegistrationTask | None:
        return self.db.scalar(
            select(RegistrationTask).where(RegistrationTask.idempotency_key == key)
        )

    def task_page(
        self,
        filters: Mapping[str, object],
        page: int,
        page_size: int,
    ) -> tuple[list[RegistrationTask], int]:
        if page_size > 100:
            raise ValueError("page_size must be less than or equal to 100")
        predicates: list[ColumnElement[bool]] = [
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

    def account_page(
        self, user_id: str, page: int, page_size: int
    ) -> tuple[list[PublisherAccount], int]:
        if page_size > 100:
            raise ValueError("page_size must be less than or equal to 100")
        now = utc_now()
        authorized = (
            select(AuthorAuthorization.id)
            .join(User, User.id == AuthorAuthorization.user_id)
            .where(
                AuthorAuthorization.author_id == PublisherAccount.author_id,
                AuthorAuthorization.user_id == user_id,
                AuthorAuthorization.valid_from <= now,
                AuthorAuthorization.valid_to > now,
                AuthorAuthorization.revoked_at.is_(None),
                func.json_contains(
                    AuthorAuthorization.permissions, json.dumps("account:register")
                )
                == 1,
                User.status == "active",
                User.deleted_at.is_(None),
            )
            .correlate(PublisherAccount)
            .exists()
        )
        statement = (
            select(PublisherAccount)
            .join(Author, Author.id == PublisherAccount.author_id)
            .join(Publisher, Publisher.id == PublisherAccount.publisher_id)
            .outerjoin(Journal, Journal.id == PublisherAccount.journal_id)
            .where(
                PublisherAccount.deleted_at.is_(None),
                Author.deleted_at.is_(None),
                Author.status == "active",
                Publisher.deleted_at.is_(None),
                PublisherAccount.journal_id.is_(None) | Journal.deleted_at.is_(None),
                authorized,
            )
        )
        total = (
            self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        records = self.db.scalars(
            statement.order_by(
                PublisherAccount.created_at.desc(), PublisherAccount.id.asc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(records), total
