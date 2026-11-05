"""Append-only operation log persistence and read-only query filters."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OperationLog


class AuditRepository:
    SORT_FIELDS = frozenset({"created_at"})

    def __init__(self, db: Session):
        self.db = db

    def append(self, **fields) -> OperationLog:
        log = OperationLog(**fields)
        self.db.add(log)
        return log

    def get(self, log_id: str) -> OperationLog | None:
        return self.db.get(OperationLog, log_id)

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        actor_user_id: str | None,
        author_id: str | None,
        category: str | None,
        action: str | None,
        target_type: str | None,
        target_id: str | None,
        result: str | None,
        request_id: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        sort: str,
        order: str,
    ) -> tuple[list[OperationLog], int]:
        predicates = []
        for column, value in (
            (OperationLog.actor_user_id, actor_user_id),
            (OperationLog.author_id, author_id),
            (OperationLog.category, category),
            (OperationLog.action, action),
            (OperationLog.target_type, target_type),
            (OperationLog.target_id, target_id),
            (OperationLog.result, result),
            (OperationLog.request_id, request_id),
        ):
            if value is not None:
                predicates.append(column == value)
        if created_from is not None:
            predicates.append(OperationLog.created_at >= created_from)
        if created_to is not None:
            predicates.append(OperationLog.created_at <= created_to)
        total = self.db.scalar(
            select(func.count()).select_from(OperationLog).where(*predicates)
        )
        sort_column = getattr(OperationLog, sort)
        statement = (
            select(OperationLog)
            .where(*predicates)
            .order_by(
                sort_column.asc() if order == "asc" else sort_column.desc(),
                OperationLog.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total or 0
