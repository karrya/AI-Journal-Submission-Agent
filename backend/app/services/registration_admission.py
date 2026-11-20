"""Validate that a registration target is supported and verified."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Journal, JournalSubmissionPortal, Publisher
from app.repositories.registration import RegistrationRepository

V01_PUBLISHER_CODES = frozenset(
    {"SPRINGER_NATURE", "ELSEVIER", "WILEY", "TAYLOR_FRANCIS", "SAGE"}
)


@dataclass(frozen=True)
class AdmissionResult:
    publisher: Publisher
    journal: Journal
    portal: JournalSubmissionPortal


def require_supported_registration_target(
    db: Session,
    publisher_id: str,
    journal_id: str,
    portal_id: str,
    platform_code: str,
) -> AdmissionResult:
    repository = RegistrationRepository(db)
    publisher = repository.publisher_support(publisher_id)
    if (
        publisher is None
        or publisher.registration_code not in V01_PUBLISHER_CODES
        or publisher.registration_support_level != "V0_1"
        or publisher.registration_support_status != "SUPPORTED"
    ):
        raise AppError(
            403, "PUBLISHER_NOT_IN_V01_WHITELIST", "出版社不在 V0.1 支持范围"
        )

    journal = db.get(Journal, journal_id)
    if journal is None or journal.deleted_at is not None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "期刊不存在")
    if journal.publisher_id != publisher_id:
        raise AppError(409, "JOURNAL_PUBLISHER_MISMATCH", "期刊与出版社归属不一致")

    portal = repository.supported_portal(portal_id)
    if portal is None or portal.journal_id != journal_id:
        raise AppError(404, "JOURNAL_ENDPOINT_NOT_FOUND", "期刊入口不存在")
    if portal.support_status != "SUPPORTED":
        raise AppError(409, "JOURNAL_ENDPOINT_NOT_SUPPORTED", "期刊入口尚未开放")
    if portal.verification_status != "VERIFIED":
        raise AppError(409, "JOURNAL_ENDPOINT_NOT_VERIFIED", "期刊入口尚未核验")

    if (
        not portal.adapter_code
        or not portal.adapter_version
        or portal.adapter_support_status != "SUPPORTED"
        or portal.platform_code != platform_code
    ):
        raise AppError(409, "PLATFORM_ADAPTER_NOT_SUPPORTED", "平台适配器尚未验收")

    try:
        parsed = urlsplit(portal.final_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise AppError(
            403, "PLATFORM_DOMAIN_NOT_ALLOWED", "目标入口 URL 或端口不受信任"
        ) from None
    normalized_host = (portal.normalized_host or "").lower().rstrip(".")
    allowed_domains = {
        str(domain).lower().rstrip(".") for domain in portal.adapter_allowed_domains or []
    }
    if (
        parsed.scheme.lower() != "https"
        or port not in {None, 443}
        or not host
        or normalized_host != host
        or host not in allowed_domains
    ):
        raise AppError(403, "PLATFORM_DOMAIN_NOT_ALLOWED", "目标域名不在适配器白名单")

    return AdmissionResult(publisher=publisher, journal=journal, portal=portal)
