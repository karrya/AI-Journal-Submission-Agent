"""Persistence queries for authors and their related resources."""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    AuthorAuthorization,
    AuthorEmail,
    AuthorInstitution,
    Institution,
    User,
)


class AuthorRepository:
    SORT_FIELDS = frozenset({"display_name", "created_at", "updated_at"})

    def __init__(self, db: Session):
        self.db = db

    def get(self, author_id: str) -> Author | None:
        return self.db.scalar(
            select(Author).where(
                Author.id == author_id,
                Author.deleted_at.is_(None),
            )
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        orcid: str | None,
        status: str | None,
        sort: str,
        order: str,
        user_id: str | None,
        permission: str | None,
        now_utc: datetime,
    ) -> tuple[list[Author], int]:
        predicates = [Author.deleted_at.is_(None)]
        if name:
            predicates.append(Author.display_name.contains(name))
        if orcid:
            predicates.append(Author.orcid == orcid)
        if status:
            predicates.append(Author.status == status)
        if user_id is not None and permission is not None:
            predicates.extend(
                (
                    Author.status == "active",
                    self._active_grant(
                        user_id=user_id, permission=permission, now_utc=now_utc
                    ),
                )
            )

        statement = select(Author).where(*predicates)
        count_statement = select(Author.id).where(*predicates)
        sort_column = getattr(Author, sort)
        statement = (
            statement.order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                Author.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total = self.db.scalar(
            select(func.count()).select_from(count_statement.subquery())
        )
        return list(self.db.scalars(statement).unique()), total or 0

    @staticmethod
    def _active_grant(*, user_id: str, permission: str, now_utc: datetime):
        return (
            select(AuthorAuthorization.id)
            .join(User, User.id == AuthorAuthorization.user_id)
            .where(
                AuthorAuthorization.author_id == Author.id,
                AuthorAuthorization.user_id == user_id,
                AuthorAuthorization.valid_from <= now_utc,
                AuthorAuthorization.valid_to > now_utc,
                AuthorAuthorization.revoked_at.is_(None),
                User.status == "active",
                User.deleted_at.is_(None),
                func.json_contains(
                    AuthorAuthorization.permissions, json.dumps(permission)
                )
                == 1,
            )
            .exists()
        )

    def add(self, author: Author) -> Author:
        self.db.add(author)
        return author


class EmailRepository:
    SORT_FIELDS = frozenset({"created_at", "updated_at", "normalized_email"})

    def __init__(self, db: Session):
        self.db = db

    def get(self, *, author_id: str, email_id: str) -> AuthorEmail | None:
        return self.db.scalar(
            select(AuthorEmail).where(
                AuthorEmail.id == email_id,
                AuthorEmail.author_id == author_id,
                AuthorEmail.deleted_at.is_(None),
            )
        )

    def list_page(
        self, *, author_id: str, page: int, page_size: int, sort: str, order: str
    ) -> tuple[list[AuthorEmail], int]:
        predicates = (
            AuthorEmail.author_id == author_id,
            AuthorEmail.deleted_at.is_(None),
        )
        count_statement = select(AuthorEmail.id).where(*predicates)
        total = self.db.scalar(
            select(func.count()).select_from(count_statement.subquery())
        )
        sort_column = getattr(AuthorEmail, sort)
        statement = (
            select(AuthorEmail)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                AuthorEmail.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0

    def add(self, email: AuthorEmail) -> AuthorEmail:
        self.db.add(email)
        return email


class InstitutionRepository:
    SORT_FIELDS = frozenset({"name", "created_at", "updated_at"})

    def __init__(self, db: Session):
        self.db = db

    def get(self, institution_id: str) -> Institution | None:
        return self.db.scalar(
            select(Institution).where(
                Institution.id == institution_id,
                Institution.deleted_at.is_(None),
            )
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        country_code: str | None,
        city: str | None,
        sort: str,
        order: str,
    ) -> tuple[list[Institution], int]:
        predicates = [Institution.deleted_at.is_(None)]
        if name:
            predicates.append(Institution.normalized_name.contains(name))
        if country_code:
            predicates.append(Institution.country_code == country_code)
        if city:
            predicates.append(Institution.city.contains(city))
        count_statement = select(Institution.id).where(*predicates)
        total = self.db.scalar(
            select(func.count()).select_from(count_statement.subquery())
        )
        sort_column = getattr(Institution, sort)
        statement = (
            select(Institution)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                Institution.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0

    def add(self, institution: Institution) -> Institution:
        self.db.add(institution)
        return institution


class AuthorInstitutionRepository:
    SORT_FIELDS = frozenset({"display_order", "created_at", "updated_at"})

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _predicates(author_id: str):
        return (
            AuthorInstitution.author_id == author_id,
            AuthorInstitution.deleted_at.is_(None),
            Institution.deleted_at.is_(None),
        )

    def get(
        self, *, author_id: str, link_id: str
    ) -> tuple[AuthorInstitution, Institution] | None:
        return self.db.execute(
            select(AuthorInstitution, Institution)
            .join(Institution, Institution.id == AuthorInstitution.institution_id)
            .where(
                AuthorInstitution.id == link_id,
                *self._predicates(author_id),
            )
        ).one_or_none()

    def list_page(
        self, *, author_id: str, page: int, page_size: int, sort: str, order: str
    ) -> tuple[list[tuple[AuthorInstitution, Institution]], int]:
        predicates = self._predicates(author_id)
        count_statement = (
            select(AuthorInstitution.id)
            .join(Institution, Institution.id == AuthorInstitution.institution_id)
            .where(*predicates)
        )
        total = self.db.scalar(
            select(func.count()).select_from(count_statement.subquery())
        )
        sort_column = getattr(AuthorInstitution, sort)
        statement = (
            select(AuthorInstitution, Institution)
            .join(Institution, Institution.id == AuthorInstitution.institution_id)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                AuthorInstitution.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.execute(statement).tuples()), total or 0

    def add(self, link: AuthorInstitution) -> AuthorInstitution:
        self.db.add(link)
        return link
