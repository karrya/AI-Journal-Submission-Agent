"""Persistence and row-locking queries for manuscripts and immutable versions."""

import json
from datetime import datetime

from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    AuthorAuthorization,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    User,
)


class ManuscriptRepository:
    SORT_FIELDS = frozenset({"created_at", "updated_at", "title"})

    def __init__(self, db: Session):
        self.db = db

    def add(self, manuscript: Manuscript) -> Manuscript:
        self.db.add(manuscript)
        return manuscript

    def get(self, manuscript_id: str, *, lock: bool = False) -> Manuscript | None:
        statement = select(Manuscript).where(
            Manuscript.id == manuscript_id,
            Manuscript.deleted_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def lock_owner(self, author_id: str) -> Author | None:
        return self.db.scalar(
            select(Author)
            .where(Author.id == author_id, Author.deleted_at.is_(None))
            .with_for_update()
        )

    def has_grant_record(
        self, *, user_id: str, author_id: str, permissions: list[str]
    ) -> bool:
        permission_predicates = [
            func.json_contains(AuthorAuthorization.permissions, json.dumps(permission))
            == 1
            for permission in permissions
        ]
        return self.db.scalar(
            select(AuthorAuthorization.id)
            .where(
                AuthorAuthorization.user_id == user_id,
                AuthorAuthorization.author_id == author_id,
                or_(*permission_predicates),
            )
            .limit(1)
        ) is not None

    @staticmethod
    def _active_grant(*, user_id: str, now_utc: datetime):
        return (
            select(AuthorAuthorization.id)
            .join(User, User.id == AuthorAuthorization.user_id)
            .join(Author, Author.id == AuthorAuthorization.author_id)
            .where(
                AuthorAuthorization.author_id == Manuscript.owner_author_id,
                AuthorAuthorization.user_id == user_id,
                AuthorAuthorization.valid_from <= now_utc,
                AuthorAuthorization.valid_to > now_utc,
                AuthorAuthorization.revoked_at.is_(None),
                User.status == "active",
                User.deleted_at.is_(None),
                Author.status == "active",
                Author.deleted_at.is_(None),
                func.json_contains(
                    AuthorAuthorization.permissions, json.dumps("manuscript:read")
                )
                == 1,
            )
            .exists()
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        sort: str,
        order: str,
        user_id: str | None,
        now_utc: datetime | None,
    ) -> tuple[list[Manuscript], int]:
        predicates: list[ColumnElement[bool]] = [Manuscript.deleted_at.is_(None)]
        if status is not None:
            predicates.append(Manuscript.status == status)
        if user_id is not None and now_utc is not None:
            predicates.append(self._active_grant(user_id=user_id, now_utc=now_utc))
        statement = select(Manuscript).where(*predicates)
        count_statement = select(Manuscript.id).where(*predicates)
        sort_column = getattr(Manuscript, sort)
        statement = (
            statement.order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                Manuscript.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total = self.db.scalar(
            select(func.count()).select_from(count_statement.subquery())
        )
        return list(self.db.scalars(statement)), total or 0

    def authors(self, manuscript_id: str) -> list[tuple[ManuscriptAuthor, str]]:
        statement = (
            select(ManuscriptAuthor, Author.display_name)
            .join(Author, Author.id == ManuscriptAuthor.author_id)
            .where(ManuscriptAuthor.manuscript_id == manuscript_id)
            .order_by(ManuscriptAuthor.position.asc())
        )
        return list(self.db.execute(statement).tuples())

    def authors_for_manuscripts(
        self, manuscript_ids: list[str]
    ) -> dict[str, list[tuple[ManuscriptAuthor, str]]]:
        if not manuscript_ids:
            return {}
        statement = (
            select(ManuscriptAuthor, Author.display_name)
            .join(Author, Author.id == ManuscriptAuthor.author_id)
            .where(ManuscriptAuthor.manuscript_id.in_(manuscript_ids))
            .order_by(
                ManuscriptAuthor.manuscript_id.asc(), ManuscriptAuthor.position.asc()
            )
        )
        grouped: dict[str, list[tuple[ManuscriptAuthor, str]]] = {
            manuscript_id: [] for manuscript_id in manuscript_ids
        }
        for link, display_name in self.db.execute(statement).tuples():
            grouped[link.manuscript_id].append((link, display_name))
        return grouped

    def authors_by_ids(self, author_ids: set[str]) -> dict[str, Author]:
        if not author_ids:
            return {}
        records = self.db.scalars(select(Author).where(Author.id.in_(author_ids)))
        return {author.id: author for author in records}

    def replace_authors(
        self, *, manuscript_id: str, links: list[ManuscriptAuthor]
    ) -> None:
        self.db.execute(
            delete(ManuscriptAuthor).where(
                ManuscriptAuthor.manuscript_id == manuscript_id
            )
        )
        self.db.flush()
        self.db.add_all(links)
        self.db.flush()

    def add_authors(self, links: list[ManuscriptAuthor]) -> None:
        self.db.add_all(links)
        self.db.flush()

    def next_version_number(self, manuscript_id: str) -> int:
        latest = self.db.scalar(
            select(ManuscriptVersion.version_number)
            .where(ManuscriptVersion.manuscript_id == manuscript_id)
            .order_by(ManuscriptVersion.version_number.desc())
            .limit(1)
            .with_for_update()
        )
        return (latest or 0) + 1

    def add_version(self, version: ManuscriptVersion) -> ManuscriptVersion:
        self.db.add(version)
        return version

    def get_version(
        self, *, manuscript_id: str, version_id: str
    ) -> ManuscriptVersion | None:
        return self.db.scalar(
            select(ManuscriptVersion).where(
                ManuscriptVersion.id == version_id,
                ManuscriptVersion.manuscript_id == manuscript_id,
            )
        )

    def list_versions(
        self, *, manuscript_id: str, page: int, page_size: int
    ) -> tuple[list[ManuscriptVersion], int]:
        predicates = (ManuscriptVersion.manuscript_id == manuscript_id,)
        total = self.db.scalar(
            select(func.count())
            .select_from(ManuscriptVersion)
            .where(*predicates)
        )
        statement = (
            select(ManuscriptVersion)
            .where(*predicates)
            .order_by(ManuscriptVersion.version_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0
