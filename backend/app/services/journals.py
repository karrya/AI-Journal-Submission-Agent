"""提供期刊资源事务服务、角色校验和审计记录。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Journal, Publisher, User, utc_now
from app.repositories.journals import JournalRepository, PublisherRepository
from app.schemas.journals import (
    JournalCreate,
    JournalPage,
    JournalResponse,
    JournalUpdate,
    PublisherCreate,
    PublisherPage,
    PublisherResponse,
    PublisherUpdate,
    normalize_issn,
)
from app.services.authors import (
    DomainService,
    normalize_comparison,
    normalize_display_name,
)
from app.schemas.identification import normalize_domain
from app.services.identification import (
    JournalIdentificationService,
    PublisherIdentificationService,
)


def _not_found() -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")


def _validation(message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message)


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _mysql_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class JournalResourceService(DomainService):
    def _require_reader(self) -> None:
        if self._roles().isdisjoint(
            {"system_admin", "submission_operator", "reviewer"}
        ):
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")

    @staticmethod
    def _timestamped_response(response):
        return response.model_copy(
            update={
                "created_at": _utc(response.created_at),
                "updated_at": _utc(response.updated_at),
            }
        )


class PublisherService(JournalResourceService):
    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = PublisherRepository(db)

    def _response(self, publisher: Publisher) -> PublisherResponse:
        return self._timestamped_response(PublisherResponse.model_validate(publisher))

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        sort: str,
        order: str,
    ) -> PublisherPage:
        self._require_reader()
        self._validate_sort(self.repository, sort)
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            name=normalize_comparison(name) if name else None,
            sort=sort,
            order=order,
        )
        return PublisherPage(
            items=[self._response(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, publisher_id: str) -> PublisherResponse:
        self._require_reader()
        publisher = self.repository.get(publisher_id)
        if publisher is None:
            raise _not_found()
        return self._response(publisher)

    def create(self, payload: PublisherCreate) -> PublisherResponse:
        self._require_admin()
        values = payload.model_dump()
        aliases = values.pop("aliases", [])
        values["name"] = normalize_display_name(values["name"])
        values["primary_domain"] = normalize_domain(values["website_url"])
        publisher = self.repository.add(
            Publisher(
                **values,
                normalized_name=normalize_comparison(values["name"]),
                created_by=self.user.id,
            )
        )
        self._flush()
        PublisherIdentificationService(
            self.db, self.user, self.request_id
        ).replace_publisher_aliases(publisher, aliases)
        self._business_audit(
            action="publisher.create",
            target_type="publisher",
            target_id=publisher.id,
            after={"name": publisher.name, "website_url": publisher.website_url},
        )
        self._commit()
        return self._response(publisher)

    def update(self, publisher_id: str, payload: PublisherUpdate) -> PublisherResponse:
        self._require_admin()
        publisher = self.repository.get(publisher_id)
        if publisher is None:
            raise _not_found()
        values = payload.model_dump(exclude_unset=True)
        aliases = values.pop("aliases", None)
        if "name" in values:
            if values["name"] is None:
                raise _validation("name 不能为空")
            values["name"] = normalize_display_name(values["name"])
            values["normalized_name"] = normalize_comparison(values["name"])
        if "website_url" in values:
            values["primary_domain"] = normalize_domain(values["website_url"])
        before = {
            key: getattr(publisher, key)
            for key in ("name", "website_url")
            if key in values
        }
        for key, value in values.items():
            setattr(publisher, key, value)
        if aliases is not None:
            PublisherIdentificationService(
                self.db, self.user, self.request_id
            ).replace_publisher_aliases(publisher, aliases)
        self._flush()
        self._business_audit(
            action="publisher.update",
            target_type="publisher",
            target_id=publisher.id,
            before=before,
            after={
                key: values[key] for key in ("name", "website_url") if key in values
            },
        )
        self._commit()
        return self._response(publisher)

    def delete(self, publisher_id: str) -> None:
        self._require_admin()
        publisher = self.repository.get(publisher_id)
        if publisher is None:
            raise _not_found()
        publisher.deleted_at = utc_now()
        self._business_audit(
            action="publisher.delete",
            target_type="publisher",
            target_id=publisher.id,
            before={"deleted": False},
            after={"deleted": True},
        )
        self._commit()


class JournalService(JournalResourceService):
    def __init__(self, db: Session, user: User, request_id: str):
        super().__init__(db, user, request_id)
        self.repository = JournalRepository(db)
        self.publishers = PublisherRepository(db)

    @staticmethod
    def _response(journal: Journal) -> JournalResponse:
        response = JournalResponse.model_validate(journal)
        return response.model_copy(
            update={
                "requirements_verified_at": _utc(journal.requirements_verified_at),
                "created_at": _utc(journal.created_at),
                "updated_at": _utc(journal.updated_at),
            }
        )

    @staticmethod
    def _database_values(values: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        if "requirements" in normalized and normalized["requirements"] is not None:
            requirements = []
            for requirement in normalized["requirements"]:
                item = dict(requirement)
                verified_at = item["verified_at"]
                if verified_at.tzinfo is None or verified_at.utcoffset() is None:
                    raise _validation("投稿要求的 verified_at 必须包含时区信息")
                item["verified_at"] = verified_at.astimezone(UTC).isoformat()
                requirements.append(item)
            normalized["requirements"] = requirements
        if "requirements_verified_at" in normalized:
            normalized["requirements_verified_at"] = _mysql_utc(
                normalized["requirements_verified_at"]
            )
        return normalized

    def _require_related(self, values: dict[str, Any]) -> None:
        if "publisher_id" in values:
            if values["publisher_id"] is None:
                raise _validation("publisher_id 不能为空")
            publisher_id = str(values["publisher_id"])
            if self.publishers.get(publisher_id) is None:
                raise _not_found()
            values["publisher_id"] = publisher_id

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
    ) -> JournalPage:
        self._require_reader()
        self._validate_sort(self.repository, sort)
        normalized_issn = None
        if issn:
            try:
                normalized_issn = normalize_issn(issn)
            except ValueError:
                raise _validation("ISSN（国际标准连续出版物号）筛选条件无效") from None
        records, total = self.repository.list_page(
            page=page,
            page_size=page_size,
            name=normalize_display_name(name) if name else None,
            publisher_id=publisher_id,
            platform_code=platform_code,
            issn=normalized_issn,
            status=status,
            sort=sort,
            order=order,
        )
        return JournalPage(
            items=[self._response(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, journal_id: str) -> JournalResponse:
        self._require_reader()
        journal = self.repository.get(journal_id)
        if journal is None:
            raise _not_found()
        return self._response(journal)

    def create(self, payload: JournalCreate) -> JournalResponse:
        self._require_admin()
        values = payload.model_dump()
        aliases = values.pop("aliases", [])
        if "name" in values:
            values["name"] = normalize_display_name(values["name"])
        self._require_related(values)
        values = self._database_values(values)
        journal = self.repository.add(Journal(**values, created_by=self.user.id))
        self._flush()
        identification = JournalIdentificationService(self.db, self.user, self.request_id)
        identification.replace_journal_aliases(journal, aliases)
        self._business_audit(
            action="journal.create",
            target_type="journal",
            target_id=journal.id,
            after={
                "publisher_id": journal.publisher_id,
                "platform_code": journal.platform_code,
                "name": journal.name,
                "issn": journal.issn,
                "eissn": journal.eissn,
                "status": journal.status,
            },
        )
        self._commit()
        return self._response(journal)

    def update(self, journal_id: str, payload: JournalUpdate) -> JournalResponse:
        self._require_admin()
        journal = self.repository.get(journal_id)
        if journal is None:
            raise _not_found()
        values = payload.model_dump(exclude_unset=True)
        aliases = values.pop("aliases", None)
        for field in (
            "name",
            "subject_categories",
            "article_types",
            "requirements",
            "status",
        ):
            if field in values and values[field] is None:
                raise _validation(f"{field} 不能为空")
        if "name" in values:
            values["name"] = normalize_display_name(values["name"])
        self._require_related(values)
        values = self._database_values(values)
        safe_fields = ("publisher_id", "platform_code", "name", "issn", "eissn", "status")
        before = {key: getattr(journal, key) for key in safe_fields if key in values}
        for key, value in values.items():
            setattr(journal, key, value)
        identification = JournalIdentificationService(self.db, self.user, self.request_id)
        if aliases is not None:
            identification.replace_journal_aliases(journal, aliases)
        self._flush()
        self._business_audit(
            action="journal.update",
            target_type="journal",
            target_id=journal.id,
            before=before,
            after={key: values[key] for key in safe_fields if key in values},
        )
        self._commit()
        return self._response(journal)

    def delete(self, journal_id: str) -> None:
        self._require_admin()
        journal = self.repository.get(journal_id)
        if journal is None:
            raise _not_found()
        journal.deleted_at = utc_now()
        self._business_audit(
            action="journal.delete",
            target_type="journal",
            target_id=journal.id,
            before={"deleted": False},
            after={"deleted": True},
        )
        self._commit()
