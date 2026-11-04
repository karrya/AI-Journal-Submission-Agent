"""Transactional manuscript, ordered-authorship, and immutable-version services."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    Role,
    User,
    UserRole,
    utc_now,
)
from app.repositories.manuscripts import ManuscriptRepository
from app.schemas.manuscripts import (
    ManuscriptAuthorInput,
    ManuscriptAuthorsUpdate,
    ManuscriptCreate,
    ManuscriptPage,
    ManuscriptResponse,
    ManuscriptUpdate,
    ManuscriptVersionCreate,
    ManuscriptVersionPage,
    ManuscriptVersionResponse,
)
from app.services.audit import AuditService
from app.services.authors import AuthorService
from app.services.permissions import Permission, require_author_permission

_METADATA_FIELDS = (
    "title",
    "abstract",
    "keywords",
    "article_type",
    "subject_field",
    "language",
    "funding_statement",
    "conflict_of_interest_statement",
    "ethics_statement",
    "data_availability_statement",
    "notes",
)
_NON_NULLABLE_UPDATE_FIELDS = frozenset(
    {"title", "abstract", "keywords", "article_type", "language"}
)
_AUDIT_METADATA_FIELDS = frozenset(_METADATA_FIELDS) - {"notes"}
_AUDIT_FIELDS = frozenset(
    {
        *_METADATA_FIELDS,
        "owner_author_id",
        "authors",
        "author_id",
        "display_name",
        "position",
        "is_corresponding",
        "version_number",
        "label",
        "deleted",
    }
)


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _not_found() -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")


def _validation(message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message)


def _invalid_state() -> AppError:
    return AppError(409, "INVALID_MANUSCRIPT_STATE", "稿件状态不允许此操作")


class ManuscriptService:
    def __init__(self, db: Session, user: User, request_id: str):
        self.db = db
        self.user = user
        self.request_id = request_id
        self.repository = ManuscriptRepository(db)
        self.audit = AuditService(db)

    def _roles(self) -> set[str]:
        return set(
            self.db.scalars(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .join(User, User.id == UserRole.user_id)
                .where(
                    UserRole.user_id == self.user.id,
                    User.status == "active",
                    User.deleted_at.is_(None),
                )
            ).all()
        )

    def _is_admin(self) -> bool:
        return "system_admin" in self._roles()

    def _require_author(self, author_id: str, *permissions: Permission):
        author = None
        for permission in permissions:
            author = require_author_permission(
                self.db, self.user, author_id, permission
            )
        if author is None or author.deleted_at is not None:
            raise _not_found()
        return author

    def _flush(self) -> None:
        self.db.flush()

    def _commit(self) -> None:
        self.db.commit()

    def _rollback_exception(self, exc: Exception) -> None:
        self.db.rollback()
        if isinstance(exc, IntegrityError):
            raise AppError(409, "CONFLICT", "资源唯一性冲突") from None

    def _audit(
        self,
        *,
        action: str,
        target_type: str,
        target_id: str,
        author_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        self.audit.record(
            actor_user_id=self.user.id,
            actor_type="user",
            category="business",
            action=action,
            target_type=target_type,
            target_id=target_id,
            author_id=author_id,
            request_id=self.request_id,
            result="success",
            before=before,
            after=after,
            allowed_fields=_AUDIT_FIELDS,
        )

    def _role_allows(self, permission: Permission) -> bool:
        roles = self._roles()
        if "system_admin" in roles:
            return True
        if permission in {
            Permission.MANUSCRIPT_READ,
            Permission.AUTHOR_PROFILE_READ,
        }:
            return not roles.isdisjoint({"submission_operator", "reviewer", "author"})
        return "submission_operator" in roles

    def _require_manuscript_access(
        self, author_id: str, *permissions: Permission
    ) -> None:
        for permission in permissions:
            try:
                self._require_author(author_id, permission)
            except AppError as exc:
                has_manuscript_record = self.repository.has_grant_record(
                    user_id=self.user.id,
                    author_id=author_id,
                    permissions=[
                        code.value
                        for code in Permission
                        if code.value.startswith("manuscript:")
                    ],
                )
                if (
                    exc.status_code == 403
                    and self._role_allows(permission)
                    and not has_manuscript_record
                ):
                    raise _not_found() from None
                raise

    def get_owned_manuscript(
        self,
        manuscript_id: str,
        *permissions: Permission,
        lock: bool = False,
    ) -> Manuscript:
        manuscript = self.repository.get(manuscript_id, lock=lock)
        if manuscript is None:
            raise _not_found()
        self._require_manuscript_access(
            manuscript.owner_author_id,
            *(permissions or (Permission.MANUSCRIPT_READ,)),
        )
        return manuscript

    @staticmethod
    def _require_mutable(manuscript: Manuscript) -> None:
        if manuscript.status == "archived":
            raise _invalid_state()

    def lock_current_version(
        self,
        manuscript_id: str,
        version_id: str,
        *permissions: Permission,
    ) -> tuple[Manuscript, ManuscriptVersion]:
        manuscript = self.get_owned_manuscript(
            manuscript_id,
            *(
                permissions
                or (Permission.MANUSCRIPT_READ, Permission.MANUSCRIPT_FILE_MANAGE)
            ),
            lock=True,
        )
        self._require_mutable(manuscript)
        if manuscript.current_version_id != version_id:
            raise _invalid_state()
        version = self.repository.get_version(
            manuscript_id=manuscript.id, version_id=version_id
        )
        if version is None:
            raise _invalid_state()
        return manuscript, version

    @staticmethod
    def _minimal_authors(
        rows: list[tuple[ManuscriptAuthor, str]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "author_id": link.author_id,
                "display_name": display_name,
                "position": link.position,
                "is_corresponding": link.is_corresponding,
            }
            for link, display_name in rows
        ]

    def _current_minimal_authors(self, manuscript_id: str) -> list[dict[str, Any]]:
        return self._minimal_authors(self.repository.authors(manuscript_id))

    def _response(
        self,
        manuscript: Manuscript,
        *,
        authors: list[dict[str, Any]] | None = None,
    ) -> ManuscriptResponse:
        values = {
            field: getattr(manuscript, field)
            for field in (
                "id",
                "internal_number",
                "owner_author_id",
                *_METADATA_FIELDS,
                "status",
                "current_version_id",
                "created_at",
                "updated_at",
            )
        }
        values["created_at"] = _utc(manuscript.created_at)
        values["updated_at"] = _utc(manuscript.updated_at)
        values["authors"] = (
            authors
            if authors is not None
            else self._current_minimal_authors(manuscript.id)
        )
        return ManuscriptResponse.model_validate(values)

    @staticmethod
    def _version_response(version: ManuscriptVersion) -> ManuscriptVersionResponse:
        response = ManuscriptVersionResponse.model_validate(version)
        return response.model_copy(update={"created_at": _utc(version.created_at)})

    @staticmethod
    def _validate_authorship(
        *, owner_author_id: str, entries: list[ManuscriptAuthorInput] | None
    ) -> list[ManuscriptAuthorInput]:
        if entries is None:
            return [
                ManuscriptAuthorInput(
                    author_id=owner_author_id, position=1, is_corresponding=True
                )
            ]
        if not entries or len(entries) > 200:
            raise _validation("Authorship must contain between 1 and 200 authors")
        ordered = sorted(entries, key=lambda entry: entry.position)
        author_ids = [str(entry.author_id) for entry in ordered]
        positions = [entry.position for entry in ordered]
        if len(set(author_ids)) != len(author_ids):
            raise _validation("Authorship authors must be unique")
        if positions != list(range(1, len(ordered) + 1)):
            raise _validation("Authorship positions must be contiguous from 1")
        if owner_author_id not in author_ids:
            raise _validation("The manuscript owner must remain in authorship")
        if not any(entry.is_corresponding for entry in ordered):
            raise _validation("At least one corresponding author is required")
        return ordered

    def _require_new_coauthors(
        self,
        *,
        owner_author_id: str,
        entries: list[ManuscriptAuthorInput],
        existing_author_ids: set[str],
    ) -> None:
        readers = AuthorService(self.db, self.user, self.request_id)
        for author_id in {
            str(entry.author_id)
            for entry in entries
            if str(entry.author_id) != owner_author_id
            and str(entry.author_id) not in existing_author_ids
        }:
            readers.require_readable_author(author_id)

    def _database_authors(
        self, entries: list[ManuscriptAuthorInput]
    ) -> dict[str, str]:
        records = self.repository.authors_by_ids(
            {str(entry.author_id) for entry in entries}
        )
        if len(records) != len(entries):
            raise _not_found()
        return {author_id: author.display_name for author_id, author in records.items()}

    @staticmethod
    def _minimal_from_entries(
        entries: list[ManuscriptAuthorInput], display_names: dict[str, str]
    ) -> list[dict[str, Any]]:
        return [
            {
                "author_id": str(entry.author_id),
                "display_name": display_names[str(entry.author_id)],
                "position": entry.position,
                "is_corresponding": entry.is_corresponding,
            }
            for entry in entries
        ]

    @staticmethod
    def _new_links(
        *, manuscript_id: str, entries: list[ManuscriptAuthorInput], user_id: str
    ) -> list[ManuscriptAuthor]:
        return [
            ManuscriptAuthor(
                manuscript_id=manuscript_id,
                author_id=str(entry.author_id),
                position=entry.position,
                is_corresponding=entry.is_corresponding,
                created_by=user_id,
            )
            for entry in entries
        ]

    def _snapshot(self, manuscript: Manuscript) -> dict[str, Any]:
        return {
            "owner_author_id": manuscript.owner_author_id,
            **{field: getattr(manuscript, field) for field in _METADATA_FIELDS},
            "authors": self._current_minimal_authors(manuscript.id),
        }

    def _create_version_locked(
        self, manuscript: Manuscript, payload: ManuscriptVersionCreate
    ) -> ManuscriptVersion:
        version = self.repository.add_version(
            ManuscriptVersion(
                manuscript_id=manuscript.id,
                version_number=self.repository.next_version_number(manuscript.id),
                label=payload.label,
                change_note=payload.change_note,
                metadata_snapshot=self._snapshot(manuscript),
                created_by=self.user.id,
            )
        )
        self._flush()
        manuscript.current_version_id = version.id
        self._flush()
        self._audit(
            action="manuscript.version.create",
            target_type="manuscript_version",
            target_id=version.id,
            author_id=manuscript.owner_author_id,
            after={"version_number": version.version_number, "label": version.label},
        )
        return version

    def create(self, payload: ManuscriptCreate) -> ManuscriptResponse:
        try:
            owner_id = str(payload.owner_author_id)
            self._require_author(
                owner_id, Permission.MANUSCRIPT_CREATE, Permission.MANUSCRIPT_READ
            )
            if self.repository.lock_owner(owner_id) is None:
                raise _not_found()
            entries = self._validate_authorship(
                owner_author_id=owner_id, entries=payload.authors
            )
            self._require_new_coauthors(
                owner_author_id=owner_id, entries=entries, existing_author_ids=set()
            )
            display_names = self._database_authors(entries)
            values = payload.model_dump(exclude={"authors"})
            values["owner_author_id"] = owner_id
            manuscript = self.repository.add(
                Manuscript(
                    **values,
                    internal_number=f"MS-{uuid4().hex}",
                    created_by=self.user.id,
                )
            )
            self._flush()
            self.repository.add_authors(
                self._new_links(
                    manuscript_id=manuscript.id, entries=entries, user_id=self.user.id
                )
            )
            authors = self._minimal_from_entries(entries, display_names)
            self._audit(
                action="manuscript.create",
                target_type="manuscript",
                target_id=manuscript.id,
                author_id=owner_id,
                after={
                    "owner_author_id": owner_id,
                    "title": manuscript.title,
                    "authors": authors,
                },
            )
            self._create_version_locked(manuscript, ManuscriptVersionCreate())
            response = self._response(manuscript, authors=authors)
            self._commit()
            return response
        except Exception as exc:
            self._rollback_exception(exc)
            raise

    def get(self, manuscript_id: str) -> ManuscriptResponse:
        manuscript = self.get_owned_manuscript(
            manuscript_id, Permission.MANUSCRIPT_READ
        )
        return self._response(manuscript)

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        sort: str,
        order: str,
    ) -> ManuscriptPage:
        if sort not in self.repository.SORT_FIELDS:
            raise _validation("Unsupported sort field")
        roles = self._roles()
        is_admin = "system_admin" in roles
        if not is_admin and roles.isdisjoint(
            {"submission_operator", "reviewer", "author"}
        ):
            return ManuscriptPage(items=[], page=page, page_size=page_size, total=0)
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            status=status,
            sort=sort,
            order=order,
            user_id=None if is_admin else self.user.id,
            now_utc=None if is_admin else utc_now(),
        )
        grouped = self.repository.authors_for_manuscripts(
            [manuscript.id for manuscript in records]
        )
        return ManuscriptPage(
            items=[
                self._response(
                    manuscript, authors=self._minimal_authors(grouped[manuscript.id])
                )
                for manuscript in records
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    def update(self, manuscript_id: str, payload: ManuscriptUpdate) -> ManuscriptResponse:
        try:
            manuscript = self.get_owned_manuscript(
                manuscript_id,
                Permission.MANUSCRIPT_UPDATE,
                Permission.MANUSCRIPT_READ,
                lock=True,
            )
            self._require_mutable(manuscript)
            values = payload.model_dump(exclude_unset=True)
            if any(
                field in values and values[field] is None
                for field in _NON_NULLABLE_UPDATE_FIELDS
            ):
                raise _validation("A required manuscript field cannot be null")
            before = {
                field: getattr(manuscript, field)
                for field in values
                if field in _AUDIT_METADATA_FIELDS
            }
            for field, value in values.items():
                setattr(manuscript, field, value)
            self._flush()
            self._audit(
                action="manuscript.update",
                target_type="manuscript",
                target_id=manuscript.id,
                author_id=manuscript.owner_author_id,
                before=before,
                after={
                    field: value
                    for field, value in values.items()
                    if field in _AUDIT_METADATA_FIELDS
                },
            )
            response = self._response(manuscript)
            self._commit()
            return response
        except Exception as exc:
            self._rollback_exception(exc)
            raise

    def delete(self, manuscript_id: str) -> None:
        try:
            manuscript = self.get_owned_manuscript(
                manuscript_id, Permission.MANUSCRIPT_UPDATE, lock=True
            )
            manuscript.deleted_at = utc_now()
            self._flush()
            self._audit(
                action="manuscript.delete",
                target_type="manuscript",
                target_id=manuscript.id,
                author_id=manuscript.owner_author_id,
                before={"deleted": False},
                after={"deleted": True},
            )
            self._commit()
        except Exception as exc:
            self._rollback_exception(exc)
            raise

    def list_authors(self, manuscript_id: str) -> list[dict[str, Any]]:
        manuscript = self.get_owned_manuscript(
            manuscript_id, Permission.MANUSCRIPT_READ
        )
        return self._current_minimal_authors(manuscript.id)

    def replace_authors(
        self, manuscript_id: str, payload: ManuscriptAuthorsUpdate
    ) -> list[dict[str, Any]]:
        try:
            manuscript = self.get_owned_manuscript(
                manuscript_id,
                Permission.MANUSCRIPT_UPDATE,
                Permission.MANUSCRIPT_READ,
                lock=True,
            )
            self._require_mutable(manuscript)
            before = self._current_minimal_authors(manuscript.id)
            entries = self._validate_authorship(
                owner_author_id=manuscript.owner_author_id, entries=payload.authors
            )
            existing_ids = {item["author_id"] for item in before}
            self._require_new_coauthors(
                owner_author_id=manuscript.owner_author_id,
                entries=entries,
                existing_author_ids=existing_ids,
            )
            display_names = self._database_authors(entries)
            after = self._minimal_from_entries(entries, display_names)
            self.repository.replace_authors(
                manuscript_id=manuscript.id,
                links=self._new_links(
                    manuscript_id=manuscript.id, entries=entries, user_id=self.user.id
                ),
            )
            self._audit(
                action="manuscript.authors.replace",
                target_type="manuscript",
                target_id=manuscript.id,
                author_id=manuscript.owner_author_id,
                before={"authors": before},
                after={"authors": after},
            )
            self._commit()
            return after
        except Exception as exc:
            self._rollback_exception(exc)
            raise

    def create_version(
        self, manuscript_id: str, payload: ManuscriptVersionCreate
    ) -> ManuscriptVersionResponse:
        try:
            manuscript = self.get_owned_manuscript(
                manuscript_id,
                Permission.MANUSCRIPT_UPDATE,
                Permission.MANUSCRIPT_READ,
                lock=True,
            )
            self._require_mutable(manuscript)
            version = self._create_version_locked(manuscript, payload)
            response = self._version_response(version)
            self._commit()
            return response
        except Exception as exc:
            self._rollback_exception(exc)
            raise

    def get_version(self, manuscript_id: str, version_id: str) -> ManuscriptVersionResponse:
        manuscript = self.get_owned_manuscript(
            manuscript_id, Permission.MANUSCRIPT_READ
        )
        version = self.repository.get_version(
            manuscript_id=manuscript.id, version_id=version_id
        )
        if version is None:
            raise _not_found()
        return self._version_response(version)

    def list_versions(
        self, *, manuscript_id: str, page: int, page_size: int
    ) -> ManuscriptVersionPage:
        manuscript = self.get_owned_manuscript(
            manuscript_id, Permission.MANUSCRIPT_READ
        )
        records, total = self.repository.list_versions(
            manuscript_id=manuscript.id, page=page, page_size=page_size
        )
        return ManuscriptVersionPage(
            items=[self._version_response(version) for version in records],
            page=page,
            page_size=page_size,
            total=total,
        )
