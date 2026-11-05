"""提供具备事务和授权校验的作者领域服务。"""

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Author,
    AuthorEmail,
    AuthorInstitution,
    Institution,
    Role,
    User,
    UserRole,
    utc_now,
)
from app.models.base import Base
from app.repositories.authors import (
    AuthorInstitutionRepository,
    AuthorRepository,
    EmailRepository,
    InstitutionRepository,
)
from app.schemas.authors import (
    AuthorCreate,
    AuthorInstitutionLinkCreate,
    AuthorInstitutionLinkResponse,
    AuthorInstitutionLinkUpdate,
    AuthorInstitutionPage,
    AuthorPage,
    AuthorResponse,
    AuthorUpdate,
    EmailCreate,
    EmailPage,
    EmailResponse,
    EmailUpdate,
    InstitutionCreate,
    InstitutionPage,
    InstitutionResponse,
    InstitutionSummaryResponse,
    InstitutionUpdate,
    normalize_orcid,
)
from app.services.audit import AuditService
from app.services.permissions import (
    Permission,
    has_author_permission,
    require_author_permission,
)


def normalize_display_name(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def normalize_comparison(value: str) -> str:
    return value.strip().lower()


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _not_found() -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")


def _validation(message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message)


def _is_known_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    if original is None or not original.args or original.args[0] != 1062:
        return False
    match = re.search(r"for key '([^']+)'", str(original))
    if match is None:
        return False
    key = match.group(1).rsplit(".", maxsplit=1)[-1]
    if key == "PRIMARY":
        return True
    for table in Base.metadata.tables.values():
        if any(
            constraint.name == key
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ) or any(index.unique and index.name == key for index in table.indexes):
            return True
    return False


class DomainService:
    def __init__(self, db: Session, user: User, request_id: str):
        self.db = db
        self.user = user
        self.request_id = request_id
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

    def _require_admin(self) -> None:
        if not self._is_admin():
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")

    def _require_institution_reader(self) -> None:
        if self._roles().isdisjoint(
            {"system_admin", "submission_operator", "reviewer"}
        ):
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")

    def _can(self, author_id: str, permission: Permission) -> bool:
        return has_author_permission(self.db, self.user, author_id, permission)

    def _require_author(self, author_id: str, *permissions: Permission) -> Author:
        author = None
        for permission in permissions:
            author = require_author_permission(
                self.db, self.user, author_id, permission, request_id=self.request_id
            )
        if author is None or author.deleted_at is not None:
            raise _not_found()
        return author

    def _flush(self) -> None:
        try:
            self.db.flush()
        except IntegrityError as error:
            self.db.rollback()
            if not _is_known_unique_violation(error):
                raise
            raise AppError(409, "CONFLICT", "资源唯一性冲突") from None

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            if not _is_known_unique_violation(error):
                raise
            raise AppError(409, "CONFLICT", "资源唯一性冲突") from None
        except Exception:
            self.db.rollback()
            raise

    def _business_audit(
        self,
        *,
        action: str,
        target_type: str,
        target_id: str,
        author_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        allowed_fields = set((before or {}).keys() | (after or {}).keys()) | {
            "language",
            "given_name",
            "middle_name",
            "family_name",
            "display_name",
        }
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
            allowed_fields=allowed_fields,
        )

    def _sensitive_audit(self, *, author_id: str, category: str) -> None:
        self.audit.record(
            actor_user_id=self.user.id,
            actor_type="user",
            category="sensitive_access",
            action=f"author.{category}.read",
            target_type="author",
            target_id=author_id,
            author_id=author_id,
            request_id=self.request_id,
            result="success",
        )

    @staticmethod
    def _validate_sort(repository, sort: str) -> None:
        if sort not in repository.SORT_FIELDS:
            raise _validation("不支持的排序字段")


class AuthorService(DomainService):
    SAFE_FIELDS = frozenset(
        {
            "given_name",
            "middle_name",
            "family_name",
            "display_name",
            "alternate_names",
            "orcid",
            "status",
        }
    )

    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = AuthorRepository(db)

    def require_readable_author(self, author_id: str) -> Author:
        return self._require_author(author_id, Permission.AUTHOR_PROFILE_READ)

    @staticmethod
    def _normalized_values(values: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        for field in ("given_name", "middle_name", "family_name", "display_name"):
            if isinstance(normalized.get(field), str):
                normalized[field] = normalize_display_name(normalized[field])
        if normalized.get("display_name") is None and "display_name" in normalized:
            raise _validation("display_name 不能为空")
        if normalized.get("status") is None and "status" in normalized:
            raise _validation("status 不能为空")
        if (
            "alternate_names" in normalized
            and normalized["alternate_names"] is not None
        ):
            variants = []
            for variant in normalized["alternate_names"]:
                variants.append(
                    {
                        key: normalize_display_name(value)
                        if isinstance(value, str)
                        else value
                        for key, value in variant.items()
                    }
                )
            normalized["alternate_names"] = variants
        return normalized

    def _response(self, author: Author, *, include_phone: bool) -> AuthorResponse:
        response = AuthorResponse.model_validate(author)
        updates: dict[str, Any] = {
            "created_at": _utc(author.created_at),
            "updated_at": _utc(author.updated_at),
        }
        if not include_phone:
            updates.update(phone_country_code=None, phone_number=None)
        return response.model_copy(update=updates)

    def _phone_response(
        self, author: Author, *, known_permission: bool | None = None
    ) -> AuthorResponse:
        include_phone = (
            self._can(author.id, Permission.AUTHOR_PHONE_READ)
            if known_permission is None
            else known_permission
        )
        if include_phone and (
            author.phone_country_code is not None or author.phone_number is not None
        ):
            self._sensitive_audit(author_id=author.id, category="phone")
        return self._response(author, include_phone=include_phone)

    @classmethod
    def _safe_summary(cls, values: dict[str, Any]) -> dict[str, Any]:
        return {key: values[key] for key in values if key in cls.SAFE_FIELDS}

    def create(self, payload: AuthorCreate) -> AuthorResponse:
        self._require_admin()
        if payload.confirm_identity_change is not True:
            raise _validation("必须明确确认作者身份信息")
        values = self._normalized_values(
            payload.model_dump(exclude={"confirm_identity_change"})
        )
        author = self.repository.add(Author(**values, created_by=self.user.id))
        self._flush()
        self._business_audit(
            action="author.create",
            target_type="author",
            target_id=author.id,
            author_id=author.id,
            after=self._safe_summary(values),
        )
        response = self._phone_response(author, known_permission=True)
        self._commit()
        return response

    def get(self, author_id: str) -> AuthorResponse:
        author = self.require_readable_author(author_id)
        response = self._phone_response(author)
        if self.db.new:
            self._commit()
        return response

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
    ) -> AuthorPage:
        self._validate_sort(self.repository, sort)
        normalized_orcid = None
        if orcid:
            try:
                normalized_orcid = normalize_orcid(orcid)
            except ValueError:
                raise _validation("ORCID（开放研究者与贡献者标识）筛选条件无效") from None
        is_admin = self._is_admin()
        role_can_read = not self._roles().isdisjoint(
            {"system_admin", "submission_operator", "reviewer", "author"}
        )
        if not role_can_read:
            return AuthorPage(items=[], page=page, page_size=page_size, total=0)
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            name=normalize_display_name(name) if name else None,
            orcid=normalized_orcid,
            status=status,
            sort=sort,
            order=order,
            user_id=None if is_admin else self.user.id,
            permission=None if is_admin else Permission.AUTHOR_PROFILE_READ.value,
            now_utc=utc_now(),
        )
        items = [self._phone_response(record) for record in records]
        if self.db.new:
            self._commit()
        return AuthorPage(items=items, page=page, page_size=page_size, total=total)

    def update(self, author_id: str, payload: AuthorUpdate) -> AuthorResponse:
        author = self._require_author(
            author_id,
            Permission.AUTHOR_PROFILE_UPDATE,
            Permission.AUTHOR_PROFILE_READ,
        )
        if payload.confirm_identity_change is not True:
            raise _validation("必须明确确认作者身份信息")
        values = self._normalized_values(
            payload.model_dump(exclude_unset=True, exclude={"confirm_identity_change"})
        )
        before = {
            key: getattr(author, key) for key in values if key in self.SAFE_FIELDS
        }
        for key, value in values.items():
            setattr(author, key, value)
        self._flush()
        self._business_audit(
            action="author.update",
            target_type="author",
            target_id=author.id,
            author_id=author.id,
            before=self._safe_summary(before),
            after=self._safe_summary(values),
        )
        response = self._phone_response(author)
        self._commit()
        return response

    def delete(self, author_id: str) -> None:
        self._require_admin()
        author = self.repository.get(author_id)
        if author is None:
            raise _not_found()
        author.deleted_at = utc_now()
        self._business_audit(
            action="author.delete",
            target_type="author",
            target_id=author.id,
            author_id=author.id,
            before={"deleted": False},
            after={"deleted": True},
        )
        self._commit()


class EmailService(DomainService):
    SAFE_FIELDS = frozenset(
        {"purpose", "is_primary", "verification_status", "authorization_status"}
    )

    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = EmailRepository(db)

    @staticmethod
    def _response(email: AuthorEmail) -> EmailResponse:
        response = EmailResponse.model_validate(email)
        return response.model_copy(
            update={
                "created_at": _utc(email.created_at),
                "updated_at": _utc(email.updated_at),
            }
        )

    def _require_email_author(self, author_id: str) -> Author:
        return self._require_author(
            author_id,
            Permission.AUTHOR_PROFILE_UPDATE,
            Permission.AUTHOR_EMAIL_READ,
        )

    def _get(self, author_id: str, email_id: str) -> AuthorEmail:
        email = self.repository.get(author_id=author_id, email_id=email_id)
        if email is None:
            raise _not_found()
        return email

    def list_page(
        self, *, author_id: str, page: int, page_size: int, sort: str, order: str
    ) -> EmailPage:
        self._require_author(author_id, Permission.AUTHOR_EMAIL_READ)
        self._validate_sort(self.repository, sort)
        records, total = self.repository.list_page(
            author_id=author_id,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
        )
        if records:
            self._sensitive_audit(author_id=author_id, category="email")
            self._commit()
        return EmailPage(
            items=[self._response(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def create(self, author_id: str, payload: EmailCreate) -> EmailResponse:
        self._require_email_author(author_id)
        if payload.confirm_email_binding is not True:
            raise _validation("必须明确确认邮箱绑定关系")
        original = str(payload.email).strip()
        email = self.repository.add(
            AuthorEmail(
                author_id=author_id,
                email=original,
                normalized_email=normalize_comparison(original),
                purpose=payload.purpose,
                is_primary=payload.is_primary,
                created_by=self.user.id,
            )
        )
        self._flush()
        self._business_audit(
            action="author.email.create",
            target_type="author_email",
            target_id=email.id,
            author_id=author_id,
            after={
                "purpose": email.purpose,
                "is_primary": email.is_primary,
                "verification_status": email.verification_status,
                "authorization_status": email.authorization_status,
            },
        )
        self._sensitive_audit(author_id=author_id, category="email")
        self._commit()
        return self._response(email)

    def update(
        self, author_id: str, email_id: str, payload: EmailUpdate
    ) -> EmailResponse:
        self._require_email_author(author_id)
        email = self._get(author_id, email_id)
        status_fields = {"verification_status", "authorization_status"}
        if status_fields & payload.model_fields_set and not self._is_admin():
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")
        values = payload.model_dump(
            exclude_unset=True, exclude={"confirm_email_binding"}
        )
        if "email" in values:
            if payload.confirm_email_binding is not True:
                raise _validation("必须明确确认邮箱绑定关系")
            if values["email"] is None:
                raise _validation("email 不能为空")
            original = str(values["email"]).strip()
            values["email"] = original
            values["normalized_email"] = normalize_comparison(original)
        for field in ("purpose", "is_primary", *status_fields):
            if field in values and values[field] is None:
                raise _validation(f"{field} 不能为空")
        before = {key: getattr(email, key) for key in values if key in self.SAFE_FIELDS}
        for key, value in values.items():
            setattr(email, key, value)
        self._flush()
        self._business_audit(
            action="author.email.update",
            target_type="author_email",
            target_id=email.id,
            author_id=author_id,
            before=before,
            after={key: values[key] for key in values if key in self.SAFE_FIELDS},
        )
        self._sensitive_audit(author_id=author_id, category="email")
        self._commit()
        return self._response(email)

    def delete(
        self, author_id: str, email_id: str, *, confirm_email_binding: bool
    ) -> None:
        self._require_email_author(author_id)
        email = self._get(author_id, email_id)
        if confirm_email_binding is not True:
            raise _validation("必须明确确认邮箱绑定关系")
        email.deleted_at = utc_now()
        self._business_audit(
            action="author.email.delete",
            target_type="author_email",
            target_id=email.id,
            author_id=author_id,
            before={"deleted": False},
            after={"deleted": True},
        )
        self._commit()


class InstitutionService(DomainService):
    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = InstitutionRepository(db)

    @staticmethod
    def _response(institution: Institution, *, detailed: bool):
        schema = InstitutionResponse if detailed else InstitutionSummaryResponse
        response = schema.model_validate(institution)
        updates = {}
        if detailed:
            updates = {
                "created_at": _utc(institution.created_at),
                "updated_at": _utc(institution.updated_at),
            }
        return response.model_copy(update=updates)

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
    ) -> InstitutionPage:
        self._require_institution_reader()
        self._validate_sort(self.repository, sort)
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            name=normalize_comparison(name) if name else None,
            country_code=country_code,
            city=city,
            sort=sort,
            order=order,
        )
        return InstitutionPage(
            items=[self._response(record, detailed=False) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, institution_id: str):
        self._require_institution_reader()
        institution = self.repository.get(institution_id)
        if institution is None:
            raise _not_found()
        return self._response(institution, detailed=self._is_admin())

    def create(self, payload: InstitutionCreate) -> InstitutionResponse:
        self._require_admin()
        values = payload.model_dump()
        values["name"] = normalize_display_name(values["name"])
        values["normalized_name"] = normalize_comparison(values["name"])
        institution = self.repository.add(
            Institution(**values, created_by=self.user.id)
        )
        self._flush()
        self._business_audit(
            action="institution.create",
            target_type="institution",
            target_id=institution.id,
            after={
                "name": institution.name,
                "institution_type": institution.institution_type,
                "country_code": institution.country_code,
            },
        )
        self._commit()
        return self._response(institution, detailed=True)

    def update(
        self, institution_id: str, payload: InstitutionUpdate
    ) -> InstitutionResponse:
        self._require_admin()
        institution = self.repository.get(institution_id)
        if institution is None:
            raise _not_found()
        values = payload.model_dump(exclude_unset=True)
        if "name" in values:
            if values["name"] is None:
                raise _validation("name 不能为空")
            values["name"] = normalize_display_name(values["name"])
            values["normalized_name"] = normalize_comparison(values["name"])
        before = {
            key: getattr(institution, key)
            for key in ("name", "institution_type", "country_code")
            if key in values
        }
        for key, value in values.items():
            setattr(institution, key, value)
        self._flush()
        self._business_audit(
            action="institution.update",
            target_type="institution",
            target_id=institution.id,
            before=before,
            after={
                key: values[key]
                for key in ("name", "institution_type", "country_code")
                if key in values
            },
        )
        self._commit()
        return self._response(institution, detailed=True)

    def delete(self, institution_id: str) -> None:
        self._require_admin()
        institution = self.repository.get(institution_id)
        if institution is None:
            raise _not_found()
        institution.deleted_at = utc_now()
        self._business_audit(
            action="institution.delete",
            target_type="institution",
            target_id=institution.id,
            before={"deleted": False},
            after={"deleted": True},
        )
        self._commit()


class AuthorInstitutionService(DomainService):
    ADDRESS_FIELDS = (
        "address_line1",
        "address_line2",
        "city",
        "region",
        "postal_code",
        "country_code",
    )

    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = AuthorInstitutionRepository(db)
        self.institutions = InstitutionRepository(db)

    def _response(
        self,
        link: AuthorInstitution,
        institution: Institution,
        *,
        include_address: bool,
    ) -> AuthorInstitutionLinkResponse:
        values = {
            **{
                field: getattr(link, field)
                for field in (
                    "id",
                    "author_id",
                    "institution_id",
                    "department",
                    "position_title",
                    "valid_from",
                    "valid_to",
                    "is_current",
                    "display_order",
                    "created_at",
                    "updated_at",
                )
            },
            "institution_name": institution.name,
            **{field: getattr(institution, field) for field in self.ADDRESS_FIELDS},
        }
        if not include_address:
            values.update({field: None for field in self.ADDRESS_FIELDS})
        values["created_at"] = _utc(link.created_at)
        values["updated_at"] = _utc(link.updated_at)
        return AuthorInstitutionLinkResponse.model_validate(values)

    def _address_response(
        self, link: AuthorInstitution, institution: Institution
    ) -> AuthorInstitutionLinkResponse:
        include_address = self._can(link.author_id, Permission.AUTHOR_ADDRESS_READ)
        if include_address and any(
            getattr(institution, field) is not None for field in self.ADDRESS_FIELDS
        ):
            self._sensitive_audit(author_id=link.author_id, category="address")
        return self._response(link, institution, include_address=include_address)

    def _require_link_author(self, author_id: str) -> Author:
        return self._require_author(
            author_id,
            Permission.AUTHOR_PROFILE_UPDATE,
            Permission.AUTHOR_PROFILE_READ,
        )

    def _active_institution(self, institution_id: str) -> Institution:
        institution = self.institutions.get(str(institution_id))
        if institution is None:
            raise _not_found()
        return institution

    def _get(
        self, author_id: str, link_id: str
    ) -> tuple[AuthorInstitution, Institution]:
        result = self.repository.get(author_id=author_id, link_id=link_id)
        if result is None:
            raise _not_found()
        return result

    def list_page(
        self, *, author_id: str, page: int, page_size: int, sort: str, order: str
    ) -> AuthorInstitutionPage:
        self._require_author(author_id, Permission.AUTHOR_PROFILE_READ)
        self._validate_sort(self.repository, sort)
        records, total = self.repository.list_page(
            author_id=author_id,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
        )
        include_address = self._can(author_id, Permission.AUTHOR_ADDRESS_READ)
        items = [
            self._response(link, institution, include_address=include_address)
            for link, institution in records
        ]
        if include_address and any(
            getattr(institution, field) is not None
            for _, institution in records
            for field in self.ADDRESS_FIELDS
        ):
            self._sensitive_audit(author_id=author_id, category="address")
            self._commit()
        return AuthorInstitutionPage(
            items=items, page=page, page_size=page_size, total=total
        )

    def create(
        self, author_id: str, payload: AuthorInstitutionLinkCreate
    ) -> AuthorInstitutionLinkResponse:
        self._require_link_author(author_id)
        institution = self._active_institution(str(payload.institution_id))
        link = self.repository.add(
            AuthorInstitution(
                **payload.model_dump(), author_id=author_id, created_by=self.user.id
            )
        )
        self._flush()
        self._business_audit(
            action="author.institution.create",
            target_type="author_institution",
            target_id=link.id,
            author_id=author_id,
            after={
                "institution_id": str(link.institution_id),
                "department": link.department,
                "is_current": link.is_current,
                "display_order": link.display_order,
            },
        )
        response = self._address_response(link, institution)
        self._commit()
        return response

    def update(
        self, author_id: str, link_id: str, payload: AuthorInstitutionLinkUpdate
    ) -> AuthorInstitutionLinkResponse:
        self._require_link_author(author_id)
        link, institution = self._get(author_id, link_id)
        values = payload.model_dump(exclude_unset=True)
        if "institution_id" in values:
            if values["institution_id"] is None:
                raise _validation("institution_id 不能为空")
            institution = self._active_institution(str(values["institution_id"]))
            values["institution_id"] = str(values["institution_id"])
        for field in ("is_current", "display_order"):
            if field in values and values[field] is None:
                raise _validation(f"{field} 不能为空")
        valid_from = values.get("valid_from", link.valid_from)
        valid_to = values.get("valid_to", link.valid_to)
        if valid_from is not None and valid_to is not None and valid_to < valid_from:
            raise _validation("valid_to 不得早于 valid_from")
        before = {
            key: getattr(link, key)
            for key in ("institution_id", "department", "is_current", "display_order")
            if key in values
        }
        for key, value in values.items():
            setattr(link, key, value)
        self._flush()
        self._business_audit(
            action="author.institution.update",
            target_type="author_institution",
            target_id=link.id,
            author_id=author_id,
            before=before,
            after={
                key: str(values[key]) if key == "institution_id" else values[key]
                for key in (
                    "institution_id",
                    "department",
                    "is_current",
                    "display_order",
                )
                if key in values
            },
        )
        response = self._address_response(link, institution)
        self._commit()
        return response

    def delete(self, author_id: str, link_id: str) -> None:
        self._require_link_author(author_id)
        link, _ = self._get(author_id, link_id)
        link.deleted_at = utc_now()
        self._business_audit(
            action="author.institution.delete",
            target_type="author_institution",
            target_id=link.id,
            author_id=author_id,
            before={"deleted": False},
            after={"deleted": True},
        )
        self._commit()
