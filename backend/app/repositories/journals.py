"""提供出版商和期刊的持久化查询。"""

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.models import Journal, Publisher


class PublisherRepository:
    SORT_FIELDS = frozenset({"name", "created_at", "updated_at"})

    def __init__(self, db: Session):
        self.db = db

    def get(self, publisher_id: str) -> Publisher | None:
        return self.db.scalar(
            select(Publisher).where(
                Publisher.id == publisher_id,
                Publisher.deleted_at.is_(None),
            )
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        sort: str,
        order: str,
    ) -> tuple[list[Publisher], int]:
        predicates: list[ColumnElement[bool]] = [Publisher.deleted_at.is_(None)]
        if name:
            predicates.append(Publisher.normalized_name.contains(name))
        total = self.db.scalar(select(func.count()).select_from(Publisher).where(*predicates))
        sort_column = getattr(Publisher, sort)
        statement = (
            select(Publisher)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                Publisher.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0

    def add(self, publisher: Publisher) -> Publisher:
        self.db.add(publisher)
        return publisher


class JournalRepository:
    SORT_FIELDS = frozenset({"name", "created_at", "updated_at"})

    def __init__(self, db: Session):
        self.db = db

    def get(self, journal_id: str) -> Journal | None:
        return self.db.scalar(
            select(Journal).where(
                Journal.id == journal_id,
                Journal.deleted_at.is_(None),
            )
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        publisher_id: str | None,
        platform_code: str | None,
        issn: str | None,
        status: str | None,
        sort: str,
        order: str,
    ) -> tuple[list[Journal], int]:
        predicates: list[ColumnElement[bool]] = [Journal.deleted_at.is_(None)]
        if name:
            predicates.append(Journal.name.contains(name))
        if publisher_id:
            predicates.append(Journal.publisher_id == publisher_id)
        if platform_code:
            predicates.append(Journal.platform_code == platform_code)
        if issn:
            predicates.append((Journal.issn == issn) | (Journal.eissn == issn))
        if status:
            predicates.append(Journal.status == status)
        total = self.db.scalar(select(func.count()).select_from(Journal).where(*predicates))
        sort_column = getattr(Journal, sort)
        statement = (
            select(Journal)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                Journal.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0

    def add(self, journal: Journal) -> Journal:
        self.db.add(journal)
        return journal
