"""Administrator-only finite author authorization management."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Author, AuthorAuthorization, User, utc_now
from app.repositories.authorizations import AuthorizationRepository
from app.schemas.authors import (
    AuthorizationCreate,
    AuthorizationPage,
    AuthorizationResponse,
    AuthorizationUpdate,
)
from app.services.authors import DomainService


def _mysql_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class AuthorizationService(DomainService):
    VALIDITY_STATUSES = frozenset(
        {"not_yet_active", "active", "expired", "revoked", "inactive_subject"}
    )

    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = AuthorizationRepository(db)

    @staticmethod
    def _validate_interval(*, valid_from: datetime, valid_to: datetime, now: datetime):
        if valid_to <= now:
            raise AppError(422, "VALIDATION_ERROR", "valid_to must be in the future")
        if valid_to <= valid_from:
            raise AppError(
                422, "VALIDATION_ERROR", "valid_to must be later than valid_from"
            )

    def _active_subject(self, author_id: str, user_id: str) -> None:
        author = self.db.get(Author, author_id)
        user = self.db.get(User, user_id)
        if author is None or user is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        if (
            author.deleted_at is not None
            or author.status != "active"
            or user.deleted_at is not None
            or user.status != "active"
        ):
            raise AppError(
                422, "VALIDATION_ERROR", "Authorization subjects must be active"
            )

    def _get(self, authorization_id: str) -> AuthorAuthorization:
        authorization = self.repository.get(authorization_id)
        if authorization is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return authorization

    def _validity_status(
        self, authorization: AuthorAuthorization, now: datetime
    ) -> str:
        if authorization.revoked_at is not None:
            return "revoked"
        author = self.db.get(Author, authorization.author_id)
        user = self.db.get(User, authorization.user_id)
        if (
            author is None
            or user is None
            or author.deleted_at is not None
            or author.status != "active"
            or user.deleted_at is not None
            or user.status != "active"
        ):
            return "inactive_subject"
        if authorization.valid_to <= now:
            return "expired"
        if authorization.valid_from > now:
            return "not_yet_active"
        return "active"

    def _response(self, authorization: AuthorAuthorization) -> AuthorizationResponse:
        now = utc_now()
        response = AuthorizationResponse.model_validate(
            {
                "id": authorization.id,
                "author_id": authorization.author_id,
                "user_id": authorization.user_id,
                "permissions": authorization.permissions,
                "valid_from": _aware_utc(authorization.valid_from),
                "valid_to": _aware_utc(authorization.valid_to),
                "evidence_ref": authorization.evidence_ref,
                "notes": authorization.notes,
                "revoked_at": _aware_utc(authorization.revoked_at),
                "reviewed_by": authorization.reviewed_by,
                "reviewed_at": _aware_utc(authorization.reviewed_at),
                "created_at": _aware_utc(authorization.created_at),
                "updated_at": _aware_utc(authorization.updated_at),
                "validity_status": self._validity_status(authorization, now),
            }
        )
        return response

    def _audit(
        self,
        *,
        action: str,
        authorization: AuthorAuthorization,
        before: Sequence[str] | None,
        after: Sequence[str],
    ) -> None:
        self.audit.record(
            actor_user_id=self.user.id,
            actor_type="user",
            category="authorization",
            action=action,
            target_type="author_authorization",
            target_id=authorization.id,
            author_id=authorization.author_id,
            request_id=self.request_id,
            result="success",
            before={"permissions": before} if before is not None else None,
            after={"permissions": after},
            allowed_fields={"permissions"},
        )

    def create(self, payload: AuthorizationCreate) -> AuthorizationResponse:
        self._require_admin()
        self._active_subject(str(payload.author_id), str(payload.user_id))
        now = utc_now()
        valid_from = _mysql_utc(payload.valid_from)
        valid_to = _mysql_utc(payload.valid_to)
        self._validate_interval(valid_from=valid_from, valid_to=valid_to, now=now)
        permissions = sorted(set(payload.permissions))
        authorization = self.repository.add(
            AuthorAuthorization(
                author_id=str(payload.author_id),
                user_id=str(payload.user_id),
                permissions=permissions,
                valid_from=valid_from,
                valid_to=valid_to,
                evidence_ref=payload.evidence_ref,
                notes=payload.notes,
                reviewed_by=self.user.id,
                reviewed_at=now,
                created_by=self.user.id,
            )
        )
        self._flush()
        self._audit(
            action="authorization.create",
            authorization=authorization,
            before=None,
            after=permissions,
        )
        self._commit()
        return self._response(authorization)

    def get(self, authorization_id: str) -> AuthorizationResponse:
        self._require_admin()
        return self._response(self._get(authorization_id))

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        author_id: str | None,
        user_id: str | None,
        permission: str | None,
        validity_status: str | None,
        sort: str,
        order: str,
    ) -> AuthorizationPage:
        self._require_admin()
        self._validate_sort(self.repository, sort)
        if (
            validity_status is not None
            and validity_status not in self.VALIDITY_STATUSES
        ):
            raise AppError(422, "VALIDATION_ERROR", "Unsupported validity status")
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            author_id=author_id,
            user_id=user_id,
            permission=permission,
            validity_status=validity_status,
            sort=sort,
            order=order,
            now_utc=utc_now(),
        )
        return AuthorizationPage(
            items=[self._response(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def update(
        self, authorization_id: str, payload: AuthorizationUpdate
    ) -> AuthorizationResponse:
        self._require_admin()
        authorization = self._get(authorization_id)
        before = sorted(set(authorization.permissions))
        values = payload.model_dump(exclude_unset=True)
        valid_from = (
            _mysql_utc(values["valid_from"])
            if "valid_from" in values
            else authorization.valid_from
        )
        valid_to = (
            _mysql_utc(values["valid_to"])
            if "valid_to" in values
            else authorization.valid_to
        )
        self._validate_interval(valid_from=valid_from, valid_to=valid_to, now=utc_now())
        if "permissions" in values:
            values["permissions"] = sorted(set(values["permissions"]))
        for key, value in values.items():
            if key in {"valid_from", "valid_to"}:
                value = _mysql_utc(value)
            setattr(authorization, key, value)
        authorization.reviewed_by = self.user.id
        authorization.reviewed_at = utc_now()
        self._flush()
        after = sorted(set(authorization.permissions))
        self._audit(
            action="authorization.update",
            authorization=authorization,
            before=before,
            after=after,
        )
        self._commit()
        return self._response(authorization)

    def revoke(self, authorization_id: str) -> AuthorizationResponse:
        self._require_admin()
        authorization = self._get(authorization_id)
        before = sorted(set(authorization.permissions))
        if authorization.revoked_at is None:
            authorization.revoked_at = utc_now()
        authorization.reviewed_by = self.user.id
        authorization.reviewed_at = utc_now()
        self._flush()
        self._audit(
            action="authorization.revoke",
            authorization=authorization,
            before=before,
            after=sorted(set(authorization.permissions)),
        )
        self._commit()
        return self._response(authorization)
