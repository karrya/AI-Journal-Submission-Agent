from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Journal, Publisher
from app.services.authors import normalize_comparison


def _alias_contains(column, normalized: str):
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.json_search(
        column, "one", escaped, None, "$[*].normalized_alias"
    ).is_not(None)


class IdentificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def search_publishers(
        self, name: str | None, domain: str | None, page: int, page_size: int
    ) -> tuple[list[Publisher], int]:
        conditions = []
        if name:
            normalized = normalize_comparison(name)
            conditions.append(
                or_(
                    Publisher.normalized_name == normalized,
                    _alias_contains(Publisher.aliases, normalized),
                )
            )
        if domain:
            conditions.append(Publisher.primary_domain == domain)
        statement = select(Publisher).where(Publisher.deleted_at.is_(None), *conditions)
        total = self.db.scalar(
            select(func.count()).select_from(statement.subquery())
        ) or 0
        records = self.db.scalars(
            statement.order_by(Publisher.name, Publisher.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(records), total

    def search_journals(
        self,
        *,
        name: str | None,
        issn: str | None,
        eissn: str | None,
        publisher_id: str | None,
        domain: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[Journal, str]], int]:
        identifier_conditions: list[ColumnElement[bool]] = []
        if issn:
            identifier_conditions.append(Journal.issn == issn)
        if eissn:
            identifier_conditions.append(Journal.eissn == eissn)
        conditions: list[ColumnElement[bool]] = [Journal.deleted_at.is_(None)]
        if publisher_id:
            conditions.append(Journal.publisher_id == publisher_id)
        if identifier_conditions:
            conditions.extend(identifier_conditions)
        elif name:
            normalized = normalize_comparison(name)
            conditions.append(
                or_(
                    Journal.name == name,
                    _alias_contains(Journal.aliases, normalized),
                )
            )
        statement = (
            select(Journal, Publisher.name)
            .join(Publisher, Publisher.id == Journal.publisher_id)
            .where(*conditions)
        )
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        records = self.db.execute(
            statement.order_by(Journal.name, Journal.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(journal, publisher_name) for journal, publisher_name in records], total

    def publisher_options(self, name: str | None, limit: int) -> list[tuple[str, str]]:
        statement = select(Publisher.id, Publisher.name).where(Publisher.deleted_at.is_(None))
        if name:
            statement = statement.where(
                Publisher.normalized_name.startswith(normalize_comparison(name))
            )
        rows = self.db.execute(
            statement.order_by(Publisher.name, Publisher.id).limit(limit)
        ).all()
        return [(row.id, row.name) for row in rows]

    def journal_options(
        self, publisher_id: str, name: str | None, limit: int
    ) -> list[tuple[str, str, str, str | None, str | None, str | None]]:
        statement = select(
            Journal.id,
            Journal.publisher_id,
            Journal.name,
            Journal.issn,
            Journal.eissn,
            Journal.website_url,
        ).where(
            Journal.publisher_id == publisher_id,
            Journal.deleted_at.is_(None),
        )
        if name:
            statement = statement.where(Journal.name.startswith(name))
        rows = self.db.execute(
            statement.order_by(Journal.name, Journal.id).limit(limit)
        ).all()
        return [
            (row.id, row.publisher_id, row.name, row.issn, row.eissn, row.website_url)
            for row in rows
        ]

    def publisher_by_normalized_name(self, name: str) -> Publisher | None:
        normalized = normalize_comparison(name)
        return self.db.scalar(
            select(Publisher).where(
                Publisher.normalized_name == normalized,
                Publisher.deleted_at.is_(None),
            )
        )
