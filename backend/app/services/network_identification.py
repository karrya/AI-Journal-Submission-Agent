import hashlib
from datetime import UTC, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.crawlers.html_parser import discover_page_links, parse_page
from app.crawlers.browser import PlaywrightBrowserClient
from app.crawlers.url_security import SafeHttpClient, UrlSecurityError
from app.models import (
    DiscoveryTask,
    Journal,
    JournalDiscoveryLog,
    JournalSourceSnapshot,
    JournalSubmissionPortal,
    Publisher,
    User,
    new_uuid,
    utc_now,
)
from app.schemas.identification import DiscoveryCandidate, EvidenceSummary
from app.services.authors import normalize_comparison, normalize_display_name
from app.services.discovery_providers import (
    CandidateSeed,
    CrossrefProvider,
    DoajProvider,
    KimiSearchProvider,
    KimiCodingProvider,
    OpenAlexProvider,
    ProviderError,
    merge_candidate_seeds,
)
from app.services.identification import JournalIdentificationService
from app.services.platform_detection import detect_platform
from app.workers.discovery_worker import ExecutionResult, TaskCancelled, TaskLeaseLost


class NetworkIdentificationService:
    def __init__(
        self,
        session,
        *,
        providers=None,
        http_client=None,
        browser_client=None,
        worker_id=None,
        lease_seconds=300,
    ):
        self.session = session
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.settings = get_settings()
        self.browser_client = browser_client or PlaywrightBrowserClient()
        self.http_client = http_client or SafeHttpClient(
            allow_local_http=self.settings.environment == "test"
        )
        if providers is None:
            providers = [
                OpenAlexProvider(self.http_client),
                CrossrefProvider(self.http_client),
                DoajProvider(self.http_client),
            ]
            if getattr(self.settings, "kimi_api_key", None):
                providers.append(KimiSearchProvider(
                    self.http_client,
                    api_key=self.settings.kimi_api_key,
                    base_url=getattr(
                        self.settings,
                        "kimi_base_url",
                        "https://api.moonshot.ai/v1",
                    ),
                    coding_provider=KimiCodingProvider(
                        self.http_client,
                        api_key=self.settings.kimi_api_key,
                        base_url="https://api.kimi.com/coding",
                        model=getattr(self.settings, "kimi_model", "kimi-k3.1-pro"),
                    ),
                ))
        self.providers = providers

    def execute(self, task: DiscoveryTask) -> ExecutionResult:
        warnings: list[str] = []
        provider_errors: list[ProviderError] = []
        payload = task.payload
        journal_name = payload.get("input_journal_name") or payload["journal_name"]
        publisher_name = payload.get("input_publisher_name") or payload.get("publisher_name")
        issn = payload.get("issn")
        eissn = payload.get("eissn")
        self._checkpoint(task, "LOCAL_MATCH", 5, warnings=warnings)
        seeds: list[CandidateSeed] = []
        for provider in self.providers:
            try:
                seeds.extend(provider.discover(journal_name, issn, eissn))
            except ProviderError as exc:
                provider_errors.append(exc)
                warnings.append(str(exc))
                self._log(task, "PROVIDER_FAILED", str(exc), {"retryable": exc.retryable})
            except UrlSecurityError as exc:
                error = ProviderError(str(exc), retryable=True)
                provider_errors.append(error)
                warnings.append(str(exc))
        input_url = payload.get("input_website_url")
        if input_url:
            seeds.append(CandidateSeed(
                name=journal_name,
                publisher_name=publisher_name,
                issn=issn,
                eissn=eissn,
                website_url=input_url,
                sources=("USER",),
            ))
        seeds = self._rank_seeds(
            merge_candidate_seeds(seeds), journal_name, publisher_name, issn, eissn
        )[:5]
        if not seeds:
            if provider_errors and any(error.retryable for error in provider_errors):
                raise next(error for error in provider_errors if error.retryable)
            warnings.append("未发现可用的网络候选")
            return self._result(task, [], warnings, stage="METADATA_DISCOVERY")
        self._checkpoint(task, "METADATA_DISCOVERY", 25, warnings=warnings)

        candidates: list[DiscoveryCandidate] = []
        official_errors: list[Exception] = []
        successful_pages = 0
        for index, seed in enumerate(seeds):
            candidate, fetched = self._evaluate_seed(
                task,
                seed,
                journal_name=journal_name,
                publisher_name=publisher_name,
                input_issn=issn,
                input_eissn=eissn,
                warnings=warnings,
                errors=official_errors,
            )
            successful_pages += fetched
            candidates.append(candidate)
            progress = 35 + int((index + 1) / len(seeds) * 45)
            self._checkpoint(
                task,
                "OFFICIAL_SITE_VERIFY",
                progress,
                candidates=candidates,
                warnings=warnings,
            )
        if successful_pages == 0 and official_errors:
            retryable = [
                error for error in official_errors
                if isinstance(error, ProviderError) and error.retryable
            ]
            if retryable:
                raise retryable[0]

        verified = [candidate for candidate in candidates if candidate.identity_status == "VERIFIED"]
        if len(verified) > 1:
            for candidate in verified:
                candidate.identity_status = "NEEDS_CONFIRMATION"
                candidate.conflict_reason = "多个官网候选均具有身份证据"
        journal = None
        if len(verified) == 1:
            selected = verified[0]
            if not selected.publisher_name:
                selected.publisher_name = publisher_name
            if not selected.publisher_name:
                selected.identity_status = "NEEDS_CONFIRMATION"
                selected.conflict_reason = "缺少出版社信息"
            else:
                self._checkpoint(
                    task,
                    "PERSIST",
                    90,
                    candidates=candidates,
                    warnings=warnings,
                )
                journal = self._persist_candidate(task, selected)
        self._log(
            task,
            "DISCOVERY_COMPLETED",
            "网络识别流程完成",
            {"candidate_count": len(candidates), "journal_id": journal.id if journal else None},
        )
        return self._result(
            task,
            candidates,
            warnings,
            journal=journal,
            stage="PERSIST",
        )

    def _rank_seeds(self, seeds, journal_name, publisher_name, issn, eissn):
        target_name = normalize_comparison(journal_name)
        target_publisher = normalize_comparison(publisher_name or "")
        def score(seed):
            value = len(seed.sources) * 10
            if issn and seed.issn == issn:
                value += 100
            if eissn and seed.eissn == eissn:
                value += 100
            if normalize_comparison(seed.name) == target_name:
                value += 50
            if seed.publisher_name and normalize_comparison(seed.publisher_name) == target_publisher:
                value += 20
            if seed.website_url:
                value += 20
            return value
        return sorted(seeds, key=score, reverse=True)

    def _evaluate_seed(
        self,
        task,
        seed,
        *,
        journal_name,
        publisher_name,
        input_issn,
        input_eissn,
        warnings,
        errors,
    ) -> tuple[DiscoveryCandidate, int]:
        candidate = DiscoveryCandidate(
            candidate_key=hashlib.sha256(
                f"{seed.website_url}|{seed.name}|{seed.issn or seed.eissn}".encode()
            ).hexdigest()[:32],
            name=seed.name or journal_name,
            publisher_name=seed.publisher_name or publisher_name,
            issn=seed.issn or input_issn,
            eissn=seed.eissn or input_eissn,
            website_url=seed.website_url,
            identity_status="UNKNOWN",
            sources=list(seed.sources),
        )
        if not seed.website_url:
            candidate.conflict_reason = "候选缺少可访问官网"
            return candidate, 0
        try:
            result, page, evidence = self._fetch_page(task, seed.website_url, "JOURNAL_HOME")
        except (UrlSecurityError, ProviderError) as exc:
            errors.append(exc)
            warnings.append(f"官网访问失败：{exc}")
            candidate.conflict_reason = str(exc)
            return candidate, 0
        if result.status != 200:
            error = ProviderError(
                f"官网返回 HTTP {result.status}",
                retryable=result.status == 429 or result.status >= 500,
            )
            errors.append(error)
            warnings.append(f"官网返回 HTTP {result.status}：{seed.website_url}")
            candidate.conflict_reason = f"官网返回 HTTP {result.status}"
            return candidate, 0
        candidate.website_url = result.final_url
        candidate.evidence.append(evidence)
        candidate.sources.append("OFFICIAL_SITE")
        normalized_name = normalize_comparison(journal_name)
        normalized_title = normalize_comparison(page.title)
        title_parts = [normalized_title, *(
            normalize_comparison(part) for part in page.title.split("|")
        )]
        name_match = normalized_name in title_parts
        compact_page = "".join(character for character in page.text.upper() if character.isalnum())
        issn_match = bool(input_issn and input_issn in compact_page)
        eissn_match = bool(input_eissn and input_eissn in compact_page)
        exact_seed_name = normalize_comparison(seed.name) == normalized_name
        metadata_identifier_match = exact_seed_name and bool(
            (input_issn and seed.issn == input_issn)
            or (input_eissn and seed.eissn == input_eissn)
        )
        metadata_sources = set(seed.sources).intersection({"OPENALEX", "CROSSREF", "DOAJ"})
        multi_source_match = exact_seed_name and len(metadata_sources) >= 2
        publisher_match = bool(
            publisher_name
            and normalize_comparison(publisher_name) in normalize_comparison(
                f"{page.title} {page.text[:20000]}"
            )
        )
        if issn_match or eissn_match:
            candidate.match_reasons.append("官方页面 ISSN/EISSN 匹配")
        if name_match:
            candidate.match_reasons.append("官方页面名称匹配")
        if metadata_identifier_match:
            candidate.match_reasons.append("开放数据标识匹配")
        if issn_match or eissn_match or (
            name_match and (metadata_identifier_match or multi_source_match or publisher_match)
        ):
            candidate.identity_status = "VERIFIED"
        else:
            candidate.identity_status = "NEEDS_CONFIRMATION"
            candidate.conflict_reason = "官网身份证据不足"

        links = discover_page_links(page)
        guideline_url = links.guideline_urls[0] if links.guideline_urls else None
        submission_url = links.submission_urls[0] if links.submission_urls else None
        if guideline_url:
            try:
                guideline_result, guideline_page, guideline_evidence = self._fetch_page(
                    task, guideline_url, "AUTHOR_GUIDELINES"
                )
                if guideline_result.status == 200:
                    candidate.author_guidelines_url = guideline_result.final_url
                    candidate.evidence.append(guideline_evidence)
                    if not submission_url:
                        guideline_links = discover_page_links(guideline_page)
                        submission_url = (
                            guideline_links.submission_urls[0]
                            if guideline_links.submission_urls
                            else None
                        )
            except (UrlSecurityError, ProviderError) as exc:
                warnings.append(f"作者指南访问失败：{exc}")
        if submission_url:
            self._evaluate_portal(task, candidate, submission_url, warnings)
        return candidate, 1

    def _evaluate_portal(self, task, candidate, submission_url, warnings) -> None:
        try:
            result, page, evidence = self._fetch_page(task, submission_url, "SUBMISSION_PORTAL")
        except (UrlSecurityError, ProviderError) as exc:
            warnings.append(f"投稿入口访问失败：{exc}")
            return
        candidate.submission_url = result.final_url
        candidate.portal_original_url = submission_url
        candidate.redirect_chain = list(result.redirects)
        candidate.evidence.append(evidence)
        detection = detect_platform(result.final_url, page.title, page.text)
        candidate.platform_code = detection.code
        candidate.platform_confidence = detection.confidence
        if page.has_captcha:
            candidate.portal_access_status = "BLOCKED"
        elif page.requires_login:
            candidate.portal_access_status = "LOGIN_REQUIRED"
        else:
            candidate.portal_access_status = "PUBLIC_ACCESS"
        candidate.portal_verification_status = (
            "NEEDS_REVIEW"
            if page.has_captcha or result.status != 200 or candidate.identity_status != "VERIFIED"
            else "VERIFIED"
        )
        if detection.reasons:
            candidate.match_reasons.extend(detection.reasons)

    def _fetch_page(self, task, url, source_type):
        try:
            result = self.http_client.get(url)
        except UrlSecurityError:
            raise
        except Exception as exc:
            raise ProviderError("目标网站访问失败", retryable=True) from exc
        page = parse_page(result.text, result.final_url)
        lowered = page.text.lower()
        needs_browser = any(
            marker in lowered
            for marker in ("enable javascript", "javascript required", "需要启用 javascript", "请启用 javascript")
        ) or (not page.title and not page.links and len(page.text) < 200)
        if needs_browser and result.status == 200:
            result = self.browser_client.get(result.final_url)
            page = parse_page(result.text, result.final_url)
        snapshot_id = new_uuid()
        relative_path = Path("discovery") / task.id / f"{snapshot_id}.txt"
        absolute_path = Path(self.settings.storage_root) / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(page.text, encoding="utf-8")
        content_hash = result.content_sha256 or hashlib.sha256(result.body).hexdigest()
        snapshot = JournalSourceSnapshot(
            id=snapshot_id,
            task_id=task.id,
            source_type=source_type,
            original_url=url,
            final_url=result.final_url,
            http_status=result.status,
            title=page.title[:500],
            text_excerpt=page.text[:20000],
            content_sha256=content_hash,
            storage_path=relative_path.as_posix(),
            parser_version="html-parser-v1",
            fetched_at=utc_now(),
        )
        self.session.add(snapshot)
        evidence = EvidenceSummary(
            source_type=source_type,
            url=result.final_url,
            title=page.title[:500] or None,
            http_status=result.status,
            content_sha256=content_hash,
        )
        return result, page, evidence

    def _conflicting_journal(self, candidate: DiscoveryCandidate) -> bool:
        conditions: list[ColumnElement[bool]] = []
        if candidate.issn:
            conditions.append(Journal.issn == candidate.issn)
        if candidate.eissn:
            conditions.append(Journal.eissn == candidate.eissn)
        if not conditions:
            return False
        journals = self.session.scalars(
            select(Journal).where(Journal.deleted_at.is_(None), or_(*conditions))
        ).all()
        normalized_name = normalize_comparison(candidate.name)
        for journal in journals:
            if normalize_comparison(journal.name) == normalized_name:
                continue
            if not any(
                item.get("normalized_alias") == normalized_name
                for item in journal.aliases or []
            ):
                return True
        return False

    def _persist_candidate(self, task, candidate: DiscoveryCandidate) -> Journal | None:
        if self._conflicting_journal(candidate):
            candidate.identity_status = "CONFLICT"
            candidate.conflict_reason = "标识与现有期刊名称不一致"
            return None
        publisher_name = candidate.publisher_name
        if not publisher_name:
            raise ValueError("候选缺少出版社信息")
        publisher = self.session.scalar(
            select(Publisher).where(
                Publisher.normalized_name == normalize_comparison(publisher_name),
                Publisher.deleted_at.is_(None),
            )
        )
        if publisher is None:
            publisher = Publisher(
                name=normalize_display_name(publisher_name),
                normalized_name=normalize_comparison(publisher_name),
                created_by=task.created_by,
            )
            self.session.add(publisher)
            self.session.flush()
        conditions: list[ColumnElement[bool]] = []
        if candidate.issn:
            conditions.append(Journal.issn == candidate.issn)
        if candidate.eissn:
            conditions.append(Journal.eissn == candidate.eissn)
        journal = None
        if conditions:
            journal = self.session.scalar(
                select(Journal).where(Journal.deleted_at.is_(None), or_(*conditions))
            )
        if journal is None:
            journal = Journal(
                publisher_id=publisher.id,
                name=normalize_display_name(candidate.name),
                created_by=task.created_by,
            )
            self.session.add(journal)
            self.session.flush()
        journal.publisher_id = publisher.id
        journal.issn = journal.issn or candidate.issn
        journal.eissn = journal.eissn or candidate.eissn
        journal.website_url = candidate.website_url
        journal.author_guidelines_url = candidate.author_guidelines_url or journal.author_guidelines_url
        journal.submission_url = candidate.submission_url or journal.submission_url
        journal.source_url = candidate.website_url
        journal.identity_status = "VERIFIED"
        journal.verified_at = utc_now()
        if candidate.platform_code and candidate.platform_code != "UNKNOWN":
            journal.platform_code = candidate.platform_code
        if candidate.submission_url:
            portal = JournalSubmissionPortal(
                journal_id=journal.id,
                task_id=task.id,
                original_url=candidate.portal_original_url or candidate.submission_url,
                final_url=candidate.submission_url,
                redirect_chain=candidate.redirect_chain,
                verification_status=candidate.portal_verification_status,
                access_status=candidate.portal_access_status,
                platform_code=candidate.platform_code or "UNKNOWN",
                confidence=candidate.platform_confidence,
                evidence_summary=[
                    evidence.model_dump(mode="json") for evidence in candidate.evidence
                ],
                created_by=task.created_by,
            )
            self.session.add(portal)
        for snapshot in self.session.scalars(
            select(JournalSourceSnapshot).where(JournalSourceSnapshot.task_id == task.id)
        ):
            snapshot.journal_id = journal.id
        self.session.flush()
        candidate.id = UUID(journal.id)
        candidate.publisher_id = UUID(publisher.id)
        candidate.updated_at = (journal.updated_at or utc_now()).replace(tzinfo=UTC)
        candidate.verified_at = journal.verified_at.replace(tzinfo=UTC)
        task.journal_id = journal.id
        user = self.session.get(User, task.created_by) if task.created_by else None
        if user is not None:
            JournalIdentificationService(
                self.session, user, task.id
            )._business_audit(
                action="journal.network_identify",
                target_type="journal",
                target_id=journal.id,
                after={
                    "identity_status": "VERIFIED",
                    "website_url": journal.website_url,
                    "platform_code": candidate.platform_code,
                },
            )
        return journal

    def _checkpoint(self, task, stage, progress, *, candidates=None, warnings) -> None:
        checkpoint = {
            "response": {
                "task_id": task.id,
                "status": task.status,
                "candidates": [
                    candidate.model_dump(mode="json") for candidate in (candidates or [])
                ],
            },
            "warnings": warnings,
        }
        owner_id = self.worker_id if self.worker_id is not None else task.worker_id
        conditions = [DiscoveryTask.id == task.id]
        if owner_id is None:
            conditions.extend([
                DiscoveryTask.worker_id.is_(None),
                DiscoveryTask.status.in_(["PENDING", "PROCESSING"]),
            ])
        else:
            conditions.extend([
                DiscoveryTask.worker_id == owner_id,
                DiscoveryTask.status == "PROCESSING",
            ])
        conditions.append(DiscoveryTask.cancel_requested.is_(False))
        self._log(task, stage, f"识别阶段：{stage}", {"progress": progress})
        updated = self.session.execute(
            update(DiscoveryTask)
            .where(*conditions)
            .values(
                stage=stage,
                progress=progress,
                lease_expires_at=utc_now() + timedelta(seconds=self.lease_seconds),
                checkpoint=checkpoint,
            )
        )
        if updated.rowcount != 1:
            self.session.rollback()
            fresh = self.session.get(DiscoveryTask, task.id)
            if fresh and (fresh.cancel_requested or fresh.status == "CANCELLED"):
                raise TaskCancelled()
            raise TaskLeaseLost()
        task.stage = stage
        task.progress = progress
        task.lease_expires_at = utc_now() + timedelta(seconds=self.lease_seconds)
        task.checkpoint = checkpoint
        self.session.commit()

    def _log(self, task, event_type, message, details=None) -> None:
        self.session.add(JournalDiscoveryLog(
            task_id=task.id,
            journal_id=task.journal_id,
            actor_user_id=task.created_by,
            event_type=event_type,
            message=message[:2000],
            details=details,
        ))

    def _result(self, task, candidates, warnings, *, journal=None, stage) -> ExecutionResult:
        return ExecutionResult(
            checkpoint={
                "response": {
                    "task_id": task.id,
                    "status": "SUCCEEDED",
                    "candidates": [
                        candidate.model_dump(mode="json") for candidate in candidates
                    ],
                },
                "warnings": warnings,
            },
            journal_id=journal.id if journal else None,
            stage=stage,
        )
