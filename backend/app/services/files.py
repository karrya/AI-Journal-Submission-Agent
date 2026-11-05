"""提供文件族事务上传、授权下载和失败补偿。"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core import database
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import FileFamily, ManuscriptFile, User, utc_now
from app.repositories.files import FileRepository
from app.schemas.files import FilePage, FileResponse, FileType
from app.services.authors import DomainService
from app.services.file_validation import FileValidator
from app.services.manuscripts import ManuscriptService
from app.services.permissions import Permission
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

_FILE_TYPES = frozenset(get_args(FileType))
_AUDIT_FIELDS = frozenset(
    {
        "file_family_id",
        "file_type",
        "display_name",
        "file_version",
        "original_filename",
        "mime_type",
        "extension",
        "size_bytes",
        "sha256",
        "status",
        "deleted",
    }
)


def _not_found() -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")


def _validation(message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message)


def _integrity_error() -> AppError:
    return AppError(409, "FILE_INTEGRITY_ERROR", "文件缺失或完整性校验失败")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class DownloadedFile:
    descriptor: int
    size_bytes: int
    original_filename: str
    mime_type: str


class FileService(DomainService):
    def __init__(
        self,
        db: Session,
        user: User,
        request_id: str,
        *,
        storage: StorageService | None = None,
        validator: FileValidator | None = None,
        session_factory: sessionmaker | None = None,
    ):
        super().__init__(db, user, request_id)
        self.repository = FileRepository(db)
        self.manuscripts = ManuscriptService(db, user, request_id)
        self.storage = storage or StorageService()
        self.validator = validator or FileValidator(max_bytes=get_settings().max_upload_bytes)
        self.session_factory = session_factory or sessionmaker(
            bind=database.engine, expire_on_commit=False
        )

    @staticmethod
    def _original_filename(filename: str) -> str:
        normalized = unicodedata.normalize("NFC", filename)
        if not normalized or len(normalized) > 255:
            raise _validation("原始文件名必须包含 1 至 255 个字符")
        return normalized

    @staticmethod
    def _display_name(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = unicodedata.normalize("NFC", value.strip())
        if not normalized or len(normalized) > 255:
            raise _validation("显示名称必须包含 1 至 255 个字符")
        return normalized

    def _response(self, record: ManuscriptFile, family: FileFamily) -> FileResponse:
        values = {
            field: getattr(record, field)
            for field in (
                "id",
                "file_family_id",
                "manuscript_id",
                "manuscript_version_id",
                "file_version",
                "original_filename",
                "mime_type",
                "extension",
                "size_bytes",
                "sha256",
                "scan_status",
                "integrity_status",
                "status",
                "created_at",
                "uploaded_by",
            )
        }
        values.update(file_type=family.file_type, display_name=family.display_name)
        values["created_at"] = _utc(record.created_at)
        return FileResponse.model_validate(values)

    def _audit(
        self,
        *,
        action: str,
        record: ManuscriptFile,
        author_id: str,
        after: dict,
        before: dict | None = None,
    ) -> None:
        self.audit.record(
            actor_user_id=self.user.id,
            actor_type="user",
            category="business",
            action=action,
            target_type="manuscript_file",
            target_id=record.id,
            author_id=author_id,
            request_id=self.request_id,
            result="success",
            before=before,
            after=after,
            allowed_fields=_AUDIT_FIELDS,
        )

    def _family_for_upload(
        self,
        *,
        manuscript_id: str,
        author_id: str,
        family_id: str | None,
        file_type: str | None,
        display_name: str | None,
    ) -> FileFamily:
        normalized_display = self._display_name(display_name)
        if file_type is not None and file_type not in _FILE_TYPES:
            raise _validation("不支持的文件类型")
        if family_id is None:
            if file_type is None or normalized_display is None:
                raise _validation("新文件族必须提供 file_type 和 display_name")
            new_family = self.repository.add_family(
                FileFamily(
                    author_id=author_id,
                    manuscript_id=manuscript_id,
                    file_type=file_type,
                    display_name=normalized_display,
                    created_by=self.user.id,
                )
            )
            self.db.flush()
            return new_family
        family = self.repository.get_family(family_id, manuscript_id, lock=True)
        if family is None:
            raise _not_found()
        if file_type is not None and file_type != family.file_type:
            raise _validation("file_type 必须与现有文件族一致")
        if normalized_display is not None and normalized_display != family.display_name:
            raise _validation("display_name 必须与现有文件族一致")
        return family

    def _record_unknown(self, *, file_id: str, relative: Path, sha256: str, event: str) -> None:
        try:
            self.storage.append_reconciliation(
                file_id=file_id, relative_path=relative, sha256=sha256, event=event
            )
        except Exception as exc:
            logger.error(
                "追加核对清单失败，已保留正式文件；"
                "file_id=%s; event=%s; error_type=%s",
                file_id,
                event,
                type(exc).__name__,
            )

    def _record_absent_on_new_connection(self, file_id: str) -> bool:
        session = self.session_factory()
        try:
            return session.get(ManuscriptFile, file_id) is None
        finally:
            session.close()

    def _compensate_certain_rollback(
        self, *, file_id: str, relative: Path, final: Path, sha256: str
    ) -> None:
        try:
            absent = self._record_absent_on_new_connection(file_id)
        except Exception:
            self._record_unknown(
                file_id=file_id, relative=relative, sha256=sha256, event="unknown_connection"
            )
            return
        if not absent:
            self._record_unknown(
                file_id=file_id, relative=relative, sha256=sha256, event="reconciliation_required"
            )
            return
        try:
            self.storage.remove(final)
        except Exception:
            self._record_unknown(
                file_id=file_id, relative=relative, sha256=sha256, event="cleanup_failed"
            )

    def upload(
        self,
        *,
        manuscript_id: str,
        version_id: str,
        stream,
        filename: str,
        declared_mime: str,
        file_type: str | None = None,
        display_name: str | None = None,
        file_family_id: str | None = None,
    ) -> FileResponse:
        file_id = str(uuid4())
        temporary = self.storage.temporary_path(file_id)
        relative = None
        final = None
        moved = False
        commit_started = False
        final_preexisting = False
        sha256 = ""
        try:
            self.manuscripts.get_owned_manuscript(
                manuscript_id,
                Permission.MANUSCRIPT_READ,
                Permission.MANUSCRIPT_FILE_MANAGE,
            )
            original_filename = self._original_filename(filename)
            self.validator.store(stream, temporary)
            inspected = self.validator.inspect(temporary, original_filename, declared_mime)
            sha256 = inspected.sha256
            manuscript, _ = self.manuscripts.lock_current_version(
                manuscript_id,
                version_id,
                Permission.MANUSCRIPT_READ,
                Permission.MANUSCRIPT_FILE_MANAGE,
            )
            family = self._family_for_upload(
                manuscript_id=manuscript.id,
                author_id=manuscript.owner_author_id,
                family_id=file_family_id,
                file_type=file_type,
                display_name=display_name,
            )
            relative = self.storage.relative_path(
                manuscript.owner_author_id,
                manuscript.id,
                version_id,
                file_id,
                inspected.extension,
            )
            record = self.repository.add(
                ManuscriptFile(
                    id=file_id,
                    file_family_id=family.id,
                    manuscript_id=manuscript.id,
                    manuscript_version_id=version_id,
                    file_version=self.repository.next_file_version(family.id),
                    original_filename=original_filename,
                    stored_filename=f"{file_id}{inspected.extension}",
                    storage_path=relative.as_posix(),
                    mime_type=inspected.mime_type,
                    extension=inspected.extension,
                    size_bytes=inspected.size_bytes,
                    sha256=inspected.sha256,
                    scan_status="not_scanned",
                    integrity_status="normal",
                    status="active",
                    uploaded_by=self.user.id,
                )
            )
            self._audit(
                action="file.upload",
                record=record,
                author_id=manuscript.owner_author_id,
                after={
                    "file_family_id": family.id,
                    "file_type": family.file_type,
                    "display_name": family.display_name,
                    "file_version": record.file_version,
                    "original_filename": original_filename,
                    "mime_type": inspected.mime_type,
                    "extension": inspected.extension,
                    "size_bytes": inspected.size_bytes,
                    "sha256": inspected.sha256,
                    "status": "active",
                },
            )
            self.db.flush()
            response = self._response(record, family)
            final = self.storage.resolve(relative)
            final_preexisting = final.exists()
            self.storage.move_into_place(temporary, relative)
            moved = True
            commit_started = True
            self.db.commit()
            return response
        except Exception as exc:
            if commit_started and moved and relative is not None:
                self._record_unknown(
                    file_id=file_id,
                    relative=relative,
                    sha256=sha256,
                    event="unknown_commit",
                )
                raise
            rollback_certain = False
            try:
                self.db.rollback()
                rollback_certain = True
            except Exception:
                if relative is not None and final is not None and final.exists():
                    self._record_unknown(
                        file_id=file_id,
                        relative=relative,
                        sha256=sha256,
                        event="unknown_rollback",
                    )
                raise exc
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    logger.warning(
                        "临时上传文件清理失败；file_id=%s；error_type=%s",
                        file_id,
                        type(cleanup_error).__name__,
                    )
            if (
                rollback_certain
                and relative is not None
                and final is not None
                and not final_preexisting
                and not isinstance(exc, FileExistsError)
                and final.exists()
            ):
                self._compensate_certain_rollback(
                    file_id=file_id, relative=relative, final=final, sha256=sha256
                )
            if isinstance(exc, IntegrityError):
                raise AppError(409, "CONFLICT", "资源唯一性冲突") from None
            raise

    def get(self, file_id: str) -> FileResponse:
        record = self.repository.get(file_id)
        if record is None:
            raise _not_found()
        manuscript = self.manuscripts.get_owned_manuscript(
            record.manuscript_id, Permission.MANUSCRIPT_READ
        )
        family = self.repository.get_family(record.file_family_id, manuscript.id)
        if family is None:
            raise _not_found()
        return self._response(record, family)

    def list_page(
        self,
        *,
        manuscript_id: str,
        version_id: str,
        page: int,
        page_size: int,
    ) -> FilePage:
        self.manuscripts.get_owned_manuscript(manuscript_id, Permission.MANUSCRIPT_READ)
        if not self.repository.version_belongs_to_manuscript(
            manuscript_id=manuscript_id, version_id=version_id
        ):
            raise _not_found()
        rows, total = self.repository.list_page(
            manuscript_id=manuscript_id,
            version_id=version_id,
            page=page,
            page_size=page_size,
        )
        return FilePage(
            items=[self._response(record, family) for record, family in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    def download(self, file_id: str) -> DownloadedFile:
        record = self.repository.get(file_id)
        if record is None:
            raise _not_found()
        self.manuscripts.get_owned_manuscript(
            record.manuscript_id, Permission.MANUSCRIPT_FILE_MANAGE
        )
        if record.integrity_status != "normal":
            raise _integrity_error()
        try:
            integrity, descriptor = self.storage.open_verified(
                record.storage_path, record.size_bytes, record.sha256
            )
        except (ValueError, OSError):
            raise _integrity_error() from None
        if integrity != "normal":
            record.integrity_status = integrity
            self.db.commit()
            raise _integrity_error()
        if descriptor is None:
            raise _integrity_error()
        return DownloadedFile(
            descriptor, record.size_bytes, record.original_filename, record.mime_type
        )

    def delete(self, file_id: str) -> None:
        try:
            record = self.repository.get(file_id)
            if record is None:
                raise _not_found()
            manuscript = self.manuscripts.get_owned_manuscript(
                record.manuscript_id, Permission.MANUSCRIPT_FILE_MANAGE, lock=True
            )
            family = self.repository.get_family(
                record.file_family_id, manuscript.id, lock=True
            )
            if family is None:
                raise _not_found()
            record.status = "deleted"
            record.deleted_at = utc_now()
            self.db.flush()
            self._audit(
                action="file.delete",
                record=record,
                author_id=manuscript.owner_author_id,
                before={"status": "active", "deleted": False},
                after={"status": "deleted", "deleted": True},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
