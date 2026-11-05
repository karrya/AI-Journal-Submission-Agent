"""提供文件族和不可变文件版本的持久化及行锁查询。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FileFamily, ManuscriptFile, ManuscriptVersion


class FileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_family(
        self, family_id: str, manuscript_id: str, *, lock: bool = False
    ) -> FileFamily | None:
        statement = select(FileFamily).where(
            FileFamily.id == family_id,
            FileFamily.manuscript_id == manuscript_id,
            FileFamily.deleted_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def add_family(self, family: FileFamily) -> FileFamily:
        self.db.add(family)
        return family

    def next_file_version(self, family_id: str) -> int:
        latest = self.db.scalar(
            select(ManuscriptFile.file_version)
            .where(ManuscriptFile.file_family_id == family_id)
            .order_by(ManuscriptFile.file_version.desc())
            .limit(1)
            .with_for_update()
        )
        return (latest or 0) + 1

    def add(self, record: ManuscriptFile) -> ManuscriptFile:
        self.db.add(record)
        return record

    def get(self, file_id: str) -> ManuscriptFile | None:
        return self.db.scalar(
            select(ManuscriptFile).where(
                ManuscriptFile.id == file_id,
                ManuscriptFile.deleted_at.is_(None),
                ManuscriptFile.status == "active",
            )
        )

    def version_belongs_to_manuscript(
        self, *, manuscript_id: str, version_id: str
    ) -> bool:
        return self.db.scalar(
            select(ManuscriptVersion.id).where(
                ManuscriptVersion.id == version_id,
                ManuscriptVersion.manuscript_id == manuscript_id,
            )
        ) is not None

    def list_page(
        self, *, manuscript_id: str, version_id: str, page: int, page_size: int
    ) -> tuple[list[tuple[ManuscriptFile, FileFamily]], int]:
        predicates = (
            ManuscriptFile.manuscript_id == manuscript_id,
            ManuscriptFile.manuscript_version_id == version_id,
            ManuscriptFile.deleted_at.is_(None),
            ManuscriptFile.status == "active",
        )
        total = self.db.scalar(
            select(func.count()).select_from(ManuscriptFile).where(*predicates)
        )
        statement = (
            select(ManuscriptFile, FileFamily)
            .join(FileFamily, FileFamily.id == ManuscriptFile.file_family_id)
            .where(*predicates)
            .order_by(ManuscriptFile.created_at.desc(), ManuscriptFile.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.execute(statement).tuples()), total or 0
