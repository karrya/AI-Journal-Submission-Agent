import hashlib
import json
import time
from datetime import UTC
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError

from app.models import (
    DiscoveryTask,
    Journal,
    JournalAlias,
    JournalIdentifier,
    Publisher,
    PublisherAlias,
    utc_now,
)
from app.repositories.identification import IdentificationRepository
from app.schemas.identification import (
    ConfirmIdentityRequest,
    IdentifyRequest,
    IdentifyResponse,
    JournalCandidate,
    JournalSearchResponse,
    PublisherCandidate,
    PublisherSearchResponse,
    TaskResponse,
    normalize_domain,
)
from app.schemas.journals import normalize_issn
from app.services.authors import (
    DomainService,
    normalize_comparison,
    normalize_display_name,
)
from app.services.permissions import Permission, require_author_permission


def _domain(value: str | None) -> str | None:
    try:
        return normalize_domain(value)
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc)) from None


class PublisherIdentificationService(DomainService):
    def __init__(self, db, user, request_id):
        super().__init__(db, user, request_id)
        self.repository = IdentificationRepository(db)

    def _require_reader(self) -> None:
        if self._roles().isdisjoint({"system_admin", "submission_operator", "reviewer"}):
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")

    def create_publisher(
        self, *, name: str, website_url: str | None, aliases: list[str]
    ) -> Publisher:
        self._require_admin()
        publisher = Publisher(
            name=normalize_display_name(name),
            normalized_name=normalize_comparison(name),
            website_url=website_url,
            primary_domain=_domain(website_url),
            created_by=self.user.id,
        )
        self.db.add(publisher)
        self._flush()
        self.replace_publisher_aliases(publisher, aliases)
        self._business_audit(
            action="publisher.identify.create",
            target_type="publisher",
            target_id=publisher.id,
            after={"name": publisher.name, "website_url": publisher.website_url},
        )
        self._commit()
        return publisher

    def replace_publisher_aliases(
        self, publisher: Publisher, aliases: list[str]
    ) -> None:
        self.db.execute(
            delete(PublisherAlias).where(PublisherAlias.publisher_id == publisher.id)
        )
        for alias in dict.fromkeys(
            alias.strip() for alias in aliases if alias.strip()
        ):
            self.db.add(
                PublisherAlias(
                    publisher_id=publisher.id,
                    alias=alias,
                    normalized_alias=normalize_comparison(alias),
                )
            )
        self._flush()

    def _candidate(
        self, publisher: Publisher, name: str | None, domain: str | None
    ) -> PublisherCandidate:
        reasons = []
        if name:
            normalized = normalize_comparison(name)
            if publisher.normalized_name == normalized:
                reasons.append("名称精确匹配")
            if self.db.scalar(
                select(PublisherAlias).where(
                    PublisherAlias.publisher_id == publisher.id,
                    PublisherAlias.normalized_alias == normalized,
                )
            ):
                reasons.append("别名精确匹配")
        if domain and publisher.primary_domain == domain:
            reasons.append("官方域名匹配")
        return PublisherCandidate(
            id=UUID(publisher.id),
            name=publisher.name,
            website_url=publisher.website_url,
            primary_domain=publisher.primary_domain,
            status=publisher.status,
            match_reasons=reasons,
        )

    def search(
        self, *, name: str | None, website_url: str | None, page: int, page_size: int
    ) -> PublisherSearchResponse:
        self._require_reader()
        domain = _domain(website_url)
        records, total = self.repository.search_publishers(name, domain, page, page_size)
        return PublisherSearchResponse(
            items=[self._candidate(record, name, domain) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )


class JournalIdentificationService(DomainService):
    def __init__(self, db, user, request_id):
        super().__init__(db, user, request_id)
        self.repository = IdentificationRepository(db)

    def _require_reader(self) -> None:
        if self._roles().isdisjoint({"system_admin", "submission_operator", "reviewer"}):
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")

    @staticmethod
    def _utc(value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _identifier(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_issn(value)
        except ValueError as exc:
            raise AppError(422, "VALIDATION_ERROR", str(exc)) from None

    def _find_or_create_publisher(self, name: str) -> Publisher:
        publisher = self.repository.publisher_by_normalized_name(name)
        if publisher is not None:
            return publisher
        publisher = Publisher(
            name=normalize_display_name(name),
            normalized_name=normalize_comparison(name),
            created_by=self.user.id,
        )
        self.db.add(publisher)
        self.db.flush()
        return publisher

    def _create_journal(
        self,
        *,
        publisher_name: str,
        name: str,
        website_url: str | None,
        issn: str | None,
        eissn: str | None,
        aliases: list[str],
    ) -> Journal:
        publisher = self._find_or_create_publisher(publisher_name)
        journal = Journal(
            publisher_id=publisher.id,
            name=normalize_display_name(name),
            website_url=website_url,
            source_url=website_url,
            issn=self._identifier(issn),
            eissn=self._identifier(eissn),
            identity_status="UNVERIFIED",
            created_by=self.user.id,
        )
        self.db.add(journal)
        self.db.flush()
        for identifier_type, value in (("ISSN", journal.issn), ("EISSN", journal.eissn)):
            if value:
                self.db.add(
                    JournalIdentifier(
                        journal_id=journal.id,
                        identifier_type=identifier_type,
                        identifier_value=value,
                    )
                )
        for alias in dict.fromkeys(alias.strip() for alias in aliases if alias.strip()):
            self.db.add(
                JournalAlias(
                    journal_id=journal.id,
                    alias=alias,
                    normalized_alias=normalize_comparison(alias),
                )
            )
        self.db.flush()
        return journal

    def replace_journal_identifiers(self, journal: Journal) -> None:
        self.db.execute(
            delete(JournalIdentifier).where(JournalIdentifier.journal_id == journal.id)
        )
        for identifier_type, value in (("ISSN", journal.issn), ("EISSN", journal.eissn)):
            if value:
                self.db.add(
                    JournalIdentifier(
                        journal_id=journal.id,
                        identifier_type=identifier_type,
                        identifier_value=value,
                    )
                )
        self.db.flush()

    def replace_journal_aliases(self, journal: Journal, aliases: list[str]) -> None:
        self.db.execute(delete(JournalAlias).where(JournalAlias.journal_id == journal.id))
        for alias in dict.fromkeys(alias.strip() for alias in aliases if alias.strip()):
            self.db.add(
                JournalAlias(
                    journal_id=journal.id,
                    alias=alias,
                    normalized_alias=normalize_comparison(alias),
                )
            )
        self.db.flush()

    def create_journal(
        self,
        *,
        publisher_name: str,
        name: str,
        website_url: str | None = None,
        issn: str | None = None,
        eissn: str | None = None,
        aliases: list[str],
    ) -> Journal:
        self._require_admin()
        journal = self._create_journal(
            publisher_name=publisher_name,
            name=name,
            website_url=website_url,
            issn=issn,
            eissn=eissn,
            aliases=aliases,
        )
        self._business_audit(
            action="journal.identify.create",
            target_type="journal",
            target_id=journal.id,
            after={"name": journal.name, "identity_status": journal.identity_status},
        )
        self._commit()
        return journal

    def _journal_domain(self, journal: Journal) -> str | None:
        try:
            return normalize_domain(journal.website_url)
        except ValueError:
            return None

    def _candidate(
        self,
        journal: Journal,
        publisher_name: str,
        *,
        name: str | None,
        issn: str | None,
        eissn: str | None,
        domain: str | None,
        status: str,
        conflict_reason: str | None,
    ) -> JournalCandidate:
        reasons = []
        if issn and journal.issn == issn:
            reasons.append("ISSN 精确匹配")
        if eissn and journal.eissn == eissn:
            reasons.append("EISSN 精确匹配")
        if domain and self._journal_domain(journal) == domain:
            reasons.append("官方域名匹配")
        if name:
            normalized = normalize_comparison(name)
            if normalize_comparison(journal.name) == normalized:
                reasons.append("名称精确匹配")
            if self.db.scalar(
                select(JournalAlias).where(
                    JournalAlias.journal_id == journal.id,
                    JournalAlias.normalized_alias == normalized,
                )
            ):
                reasons.append("别名精确匹配")
        return JournalCandidate(
            id=UUID(journal.id),
            name=journal.name,
            publisher_id=UUID(journal.publisher_id),
            publisher_name=publisher_name,
            issn=journal.issn,
            eissn=journal.eissn,
            website_url=journal.website_url,
            identity_status=status,
            match_reasons=reasons,
            conflict_reason=conflict_reason,
            updated_at=self._utc(journal.updated_at),
            verified_at=self._utc(journal.verified_at),
        )

    def _name_or_alias_matches(self, journal: Journal, name: str) -> bool:
        normalized = normalize_comparison(name)
        if normalize_comparison(journal.name) == normalized:
            return True
        return self.db.scalar(
            select(JournalAlias.id).where(
                JournalAlias.journal_id == journal.id,
                JournalAlias.normalized_alias == normalized,
            )
        ) is not None

    def _candidates(
        self,
        *,
        name: str | None,
        issn: str | None,
        eissn: str | None,
        publisher_id: str | None,
        domain: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[JournalCandidate], int]:
        records, total = self.repository.search_journals(
            name=name,
            issn=issn,
            eissn=eissn,
            publisher_id=publisher_id,
            domain=domain,
            page=page,
            page_size=page_size,
        )
        candidates = []
        multiple_identifier_matches = len(records) > 1 and (issn or eissn)
        for journal, publisher_name in records:
            if domain and self._journal_domain(journal) != domain:
                continue
            status = "NEEDS_CONFIRMATION"
            conflict = None
            if multiple_identifier_matches:
                status = "CONFLICT"
                conflict = "同一标识关联多个期刊"
            elif (issn or eissn) and len(records) == 1:
                if name and not self._name_or_alias_matches(journal, name):
                    status = "CONFLICT"
                    conflict = "标识与期刊名称不一致"
                else:
                    status = "VERIFIED"
            candidates.append(
                self._candidate(
                    journal,
                    publisher_name,
                    name=name,
                    issn=issn,
                    eissn=eissn,
                    domain=domain,
                    status=status,
                    conflict_reason=conflict,
                )
            )
        return candidates, total

    def search(
        self,
        *,
        name: str | None,
        issn: str | None,
        eissn: str | None,
        publisher_id: str | None,
        website_url: str | None,
        page: int,
        page_size: int,
    ) -> JournalSearchResponse:
        self._require_reader()
        normalized_issn = self._identifier(issn)
        normalized_eissn = self._identifier(eissn)
        domain = _domain(website_url)
        candidates, total = self._candidates(
            name=name,
            issn=normalized_issn,
            eissn=normalized_eissn,
            publisher_id=publisher_id,
            domain=domain,
            page=page,
            page_size=page_size,
        )
        return JournalSearchResponse(
            items=candidates, page=page, page_size=page_size, total=total
        )

    def get_task(self, task_id: str) -> TaskResponse:
        self._require_reader()
        task = self.db.get(DiscoveryTask, task_id)
        if task is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        if task.owner_author_id:
            require_author_permission(
                self.db,
                self.user,
                task.owner_author_id,
                Permission.MANUSCRIPT_READ,
                request_id=self.request_id,
            )
        checkpoint = task.checkpoint or {}
        response = checkpoint.get("response", {})
        return TaskResponse(
            task_id=UUID(task.id),
            task_type=task.task_type,
            status=task.status,
            progress=task.progress,
            message=task.last_error_message,
            candidates=response.get("candidates", []),
        )

    def _persist_candidate_states(self, candidates: list[JournalCandidate]) -> None:
        for candidate in candidates:
            journal = self.db.get(Journal, str(candidate.id))
            if journal is None:
                continue
            if candidate.identity_status == "VERIFIED":
                journal.identity_status = "VERIFIED"
                journal.verified_at = utc_now()
            elif candidate.identity_status == "CONFLICT":
                journal.identity_status = "CONFLICT"
            elif candidate.identity_status == "NEEDS_CONFIRMATION":
                if journal.identity_status == "UNVERIFIED":
                    journal.identity_status = "NEEDS_CONFIRMATION"
            candidate.updated_at = self._utc(journal.updated_at)
            candidate.verified_at = self._utc(journal.verified_at)
        self.db.flush()

    def _has_duplicate_identifiers(self, journal: Journal) -> bool:
        for identifier_type, value in (("ISSN", journal.issn), ("EISSN", journal.eissn)):
            if not value:
                continue
            other = self.db.scalar(
                select(JournalIdentifier).where(
                    JournalIdentifier.identifier_type == identifier_type,
                    JournalIdentifier.identifier_value == value,
                    JournalIdentifier.journal_id != journal.id,
                )
            )
            if other is not None:
                return True
        return False

    def confirm_identity(
        self, journal_id: str, payload: ConfirmIdentityRequest
    ) -> JournalCandidate:
        self._require_admin()
        try:
            journal = self.db.scalar(
                select(Journal).where(Journal.id == journal_id).with_for_update()
            )
            if journal is None or journal.deleted_at is not None:
                raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
            current = self._utc(journal.updated_at)
            if current != payload.expected_updated_at:
                raise AppError(409, "CONCURRENT_MODIFICATION", "期刊已被修改，请刷新后重试")
            if journal.identity_status not in {
                "UNVERIFIED",
                "NEEDS_CONFIRMATION",
                "CONFLICT",
            }:
                raise AppError(409, "INVALID_IDENTITY_STATE", "当前身份状态不允许确认")
            if journal.identity_status == "CONFLICT" or self._has_duplicate_identifiers(journal):
                raise AppError(409, "IDENTITY_CONFLICT", "请先处理身份冲突")
            before = {"identity_status": journal.identity_status}
            journal.identity_status = "VERIFIED"
            journal.verified_at = utc_now()
            self._business_audit(
                action="journal.identity.confirm",
                target_type="journal",
                target_id=journal.id,
                before=before,
                after={"identity_status": "VERIFIED"},
            )
            self._commit()
            publisher = self.db.get(Publisher, journal.publisher_id)
            return self._candidate(
                journal,
                publisher.name if publisher else "",
                name=None,
                issn=None,
                eissn=None,
                domain=None,
                status="VERIFIED",
                conflict_reason=None,
            )
        except Exception:
            self.db.rollback()
            raise

    def _wait_for_existing_task(self, key: str) -> IdentifyResponse:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            task = self.db.scalar(
                select(DiscoveryTask).where(
                    DiscoveryTask.task_type == "journal.identify",
                    DiscoveryTask.idempotency_key == key,
                )
            )
            if task and task.checkpoint and task.checkpoint.get("response", {}).get("task_id"):
                return IdentifyResponse.model_validate(task.checkpoint["response"])
            self.db.rollback()
            time.sleep(0.05)
        raise AppError(409, "CONCURRENT_IDENTIFICATION", "识别任务正在处理中，请稍后查询")

    def _reserve_task(self, key: str, payload: dict) -> DiscoveryTask | IdentifyResponse:
        try:
            task = DiscoveryTask(
                task_type="journal.identify",
                idempotency_key=key,
                payload=payload,
                status="PROCESSING",
                progress=0,
                checkpoint=None,
                created_by=self.user.id,
            )
            self.db.add(task)
            self.db.flush()
            return task
        except IntegrityError:
            self.db.rollback()
            return self._wait_for_existing_task(key)

    def identify(self, payload: IdentifyRequest, _retry: int = 0) -> IdentifyResponse:
        self._require_admin()
        normalized_issn = self._identifier(payload.issn)
        normalized_eissn = self._identifier(payload.eissn)
        canonical_values = {
            "publisher_name": normalize_comparison(payload.publisher_name or ""),
            "journal_name": normalize_comparison(payload.journal_name),
            "issn": normalized_issn,
            "eissn": normalized_eissn,
            "website_url": _domain(payload.website_url),
            "article_type": payload.article_type,
        }
        canonical = json.dumps(canonical_values, sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(f"journal.identify:{canonical}".encode()).hexdigest()
        existing = self.db.scalar(
            select(DiscoveryTask).where(
                DiscoveryTask.task_type == "journal.identify",
                DiscoveryTask.idempotency_key == key,
            )
        )
        if existing:
            return IdentifyResponse.model_validate((existing.checkpoint or {})["response"])
        try:
            candidates, _ = self._candidates(
                name=payload.journal_name,
                issn=normalized_issn,
                eissn=normalized_eissn,
                publisher_id=None,
                domain=_domain(payload.website_url),
                page=1,
                page_size=100,
            )
            if not candidates:
                if not payload.publisher_name or not payload.publisher_name.strip():
                    raise AppError(422, "VALIDATION_ERROR", "无法确定出版社")
                journal = self._create_journal(
                    publisher_name=payload.publisher_name,
                    name=payload.journal_name,
                    website_url=payload.website_url,
                    issn=payload.issn,
                    eissn=payload.eissn,
                    aliases=[],
                )
                candidates = [
                    self._candidate(
                        journal,
                        payload.publisher_name,
                        name=payload.journal_name,
                        issn=normalized_issn,
                        eissn=normalized_eissn,
                        domain=_domain(payload.website_url),
                        status="UNVERIFIED",
                        conflict_reason=None,
                    )
                ]
            self._persist_candidate_states(candidates)
            task = self._reserve_task(key, canonical_values)
            if isinstance(task, IdentifyResponse):
                return task
            task.journal_id = str(candidates[0].id) if candidates else None
            task.status = "SUCCEEDED"
            task.progress = 100
            self._persist_candidate_states(candidates)
            response = IdentifyResponse(
                task_id=UUID(task.id), status=task.status, candidates=candidates
            )
            task.checkpoint = {"response": response.model_dump(mode="json")}
            self.db.flush()
            assert task.journal_id is not None
            self._business_audit(
                action="journal.identify",
                target_type="journal",
                target_id=task.journal_id,
                after={"task_id": task.id, "status": task.status},
            )
            self._commit()
            return response
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_discovery_task_idempotency" in str(exc.orig):
                return self._wait_for_existing_task(key)
            if _retry < 2:
                time.sleep(0.05)
                return self.identify(payload, _retry=_retry + 1)
            raise AppError(409, "CONFLICT", "资源唯一性冲突") from None
        except Exception:
            self.db.rollback()
            raise
