"""Append-only operation log persistence."""

from sqlalchemy.orm import Session

from app.models import OperationLog


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def append(self, **fields) -> OperationLog:
        log = OperationLog(**fields)
        self.db.add(log)
        return log
