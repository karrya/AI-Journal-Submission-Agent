"""Permission-filtered dashboard aggregates and current-user operation summaries."""

from datetime import UTC, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    AuthorAuthorization,
    Manuscript,
    ManuscriptFile,
    OperationLog,
    User,
    utc_now,
)
from app.repositories.authors import AuthorRepository
from app.repositories.manuscripts import ManuscriptRepository
from app.schemas.audit import DashboardSummary, RecentOperation
from app.services.authors import DomainService
from app.services.permissions import Permission


EXPIRING_WINDOW = timedelta(days=7)
RECENT_OPERATION_LIMIT = 10


class DashboardService(DomainService):
    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.authors = AuthorRepository(db)
        self.manuscripts = ManuscriptRepository(db)

    def _author_count(self, *, is_admin: bool, now) -> int:
        _, total = self.authors.list_page(
            page=1,
            page_size=1,
            name=None,
            orcid=None,
            status=None,
            sort="display_name",
            order="asc",
            user_id=None if is_admin else self.user.id,
            permission=None if is_admin else Permission.AUTHOR_PROFILE_READ.value,
            now_utc=now,
        )
        return total

    def _manuscript_count(self, *, is_admin: bool, now) -> int:
        _, total = self.manuscripts.list_page(
            page=1,
            page_size=1,
            status=None,
            sort="created_at",
            order="desc",
            user_id=None if is_admin else self.user.id,
            now_utc=None if is_admin else now,
        )
        return total

    def _current_version_file_count(self, *, is_admin: bool, now) -> int:
        predicates = [
            Manuscript.deleted_at.is_(None),
            ManuscriptFile.deleted_at.is_(None),
            ManuscriptFile.status == "active",
        ]
        if not is_admin:
            predicates.append(
                self.manuscripts._active_grant(user_id=self.user.id, now_utc=now)
            )
        statement = (
            select(func.count(ManuscriptFile.id))
            .select_from(ManuscriptFile)
            .join(
                Manuscript,
                (Manuscript.id == ManuscriptFile.manuscript_id)
                & (
                    Manuscript.current_version_id
                    == ManuscriptFile.manuscript_version_id
                ),
            )
            .where(*predicates)
        )
        return self.db.scalar(statement) or 0

    def _expiring_authorization_count(self, *, is_admin: bool, now) -> int:
        predicates = [
            AuthorAuthorization.valid_from <= now,
            AuthorAuthorization.valid_to > now,
            AuthorAuthorization.valid_to <= now + EXPIRING_WINDOW,
            AuthorAuthorization.revoked_at.is_(None),
            User.status == "active",
            User.deleted_at.is_(None),
            Author.status == "active",
            Author.deleted_at.is_(None),
        ]
        if not is_admin:
            predicates.append(AuthorAuthorization.user_id == self.user.id)
        statement = (
            select(func.count(AuthorAuthorization.id))
            .select_from(AuthorAuthorization)
            .join(User, User.id == AuthorAuthorization.user_id)
            .join(Author, Author.id == AuthorAuthorization.author_id)
            .where(*predicates)
        )
        return self.db.scalar(statement) or 0

    def _recent_operations(self) -> list[RecentOperation]:
        records = self.db.scalars(
            select(OperationLog)
            .where(OperationLog.actor_user_id == self.user.id)
            .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
            .limit(RECENT_OPERATION_LIMIT)
        ).all()
        operations = []
        for record in records:
            operation = RecentOperation.model_validate(record)
            created_at = operation.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            operations.append(operation.model_copy(update={"created_at": created_at}))
        return operations

    def summary(self) -> DashboardSummary:
        is_admin = self._is_admin()
        now = utc_now()
        return DashboardSummary(
            author_count=self._author_count(is_admin=is_admin, now=now),
            manuscript_count=self._manuscript_count(is_admin=is_admin, now=now),
            current_version_file_count=self._current_version_file_count(
                is_admin=is_admin, now=now
            ),
            expiring_authorization_count=self._expiring_authorization_count(
                is_admin=is_admin, now=now
            ),
            recent_operations=self._recent_operations(),
        )
