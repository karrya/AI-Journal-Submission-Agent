"""提供分层作者授权的持久化查询。"""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Author, AuthorAuthorization, User


class AuthorizationRepository:
    SORT_FIELDS = frozenset({"created_at", "updated_at", "valid_from", "valid_to"})

    def __init__(self, db: Session):
        self.db = db

    def get(self, authorization_id: str) -> AuthorAuthorization | None:
        return self.db.get(AuthorAuthorization, authorization_id)

    def add(self, authorization: AuthorAuthorization) -> AuthorAuthorization:
        self.db.add(authorization)
        return authorization

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        author_id: str | None,
        user_id: str | None,
        permission: str | None,
        validity_status: str | None,
        sort: str,
        order: str,
        now_utc: datetime,
    ) -> tuple[list[AuthorAuthorization], int]:
        predicates = []
        if author_id:
            predicates.append(AuthorAuthorization.author_id == author_id)
        if user_id:
            predicates.append(AuthorAuthorization.user_id == user_id)
        if permission:
            predicates.append(
                func.json_contains(
                    AuthorAuthorization.permissions, json.dumps(permission)
                )
                == 1
            )
        active_subject = (
            User.status == "active",
            User.deleted_at.is_(None),
            Author.status == "active",
            Author.deleted_at.is_(None),
        )
        status_predicates = {
            "revoked": (AuthorAuthorization.revoked_at.is_not(None),),
            "inactive_subject": (
                AuthorAuthorization.revoked_at.is_(None),
                (User.status != "active")
                | (User.deleted_at.is_not(None))
                | (Author.status != "active")
                | (Author.deleted_at.is_not(None)),
            ),
            "expired": (
                AuthorAuthorization.revoked_at.is_(None),
                *active_subject,
                AuthorAuthorization.valid_to <= now_utc,
            ),
            "not_yet_active": (
                AuthorAuthorization.revoked_at.is_(None),
                *active_subject,
                AuthorAuthorization.valid_from > now_utc,
                AuthorAuthorization.valid_to > now_utc,
            ),
            "active": (
                AuthorAuthorization.revoked_at.is_(None),
                AuthorAuthorization.valid_from <= now_utc,
                AuthorAuthorization.valid_to > now_utc,
                *active_subject,
            ),
        }
        if validity_status:
            predicates.extend(status_predicates[validity_status])

        count_statement = (
            select(AuthorAuthorization.id)
            .join(User, User.id == AuthorAuthorization.user_id)
            .join(Author, Author.id == AuthorAuthorization.author_id)
            .where(*predicates)
        )
        total = self.db.scalar(
            select(func.count()).select_from(count_statement.subquery())
        )
        sort_column = getattr(AuthorAuthorization, sort)
        statement = (
            select(AuthorAuthorization)
            .join(User, User.id == AuthorAuthorization.user_id)
            .join(Author, Author.id == AuthorAuthorization.author_id)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                AuthorAuthorization.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0

    @staticmethod
    def _active_subject_predicates(user_id: str, author_id: str):
        return (
            AuthorAuthorization.user_id == user_id,
            AuthorAuthorization.author_id == author_id,
            User.status == "active",
            User.deleted_at.is_(None),
            Author.status == "active",
            Author.deleted_at.is_(None),
        )

    @staticmethod
    def _current_grant_predicates(now_utc: datetime):
        return (
            AuthorAuthorization.valid_from <= now_utc,
            AuthorAuthorization.valid_to > now_utc,
            AuthorAuthorization.revoked_at.is_(None),
        )

    def any_active(
        self, *, user_id: str, author_id: str, permission: str, now_utc: datetime
    ) -> bool:
        statement = (
            select(AuthorAuthorization.id)
            .join(User, User.id == AuthorAuthorization.user_id)
            .join(Author, Author.id == AuthorAuthorization.author_id)
            .where(
                *self._active_subject_predicates(user_id, author_id),
                *self._current_grant_predicates(now_utc),
                func.json_contains(
                    AuthorAuthorization.permissions, json.dumps(permission)
                )
                == 1,
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None

    def any_current(self, *, user_id: str, author_id: str, now_utc: datetime) -> bool:
        statement = (
            select(AuthorAuthorization.id)
            .join(User, User.id == AuthorAuthorization.user_id)
            .join(Author, Author.id == AuthorAuthorization.author_id)
            .where(
                *self._active_subject_predicates(user_id, author_id),
                *self._current_grant_predicates(now_utc),
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None

    def any_record(self, *, user_id: str, author_id: str) -> bool:
        statement = (
            select(AuthorAuthorization.id)
            .where(
                AuthorAuthorization.user_id == user_id,
                AuthorAuthorization.author_id == author_id,
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None
