"""Persistence queries for layered author authorization."""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Author, AuthorAuthorization, User


class AuthorizationRepository:
    def __init__(self, db: Session):
        self.db = db

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

    def any_current(
        self, *, user_id: str, author_id: str, now_utc: datetime
    ) -> bool:
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
