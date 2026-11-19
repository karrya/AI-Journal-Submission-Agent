"""Admission checks limit registration to verified, supported V0.1 targets."""

from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.models import (
    Journal,
    JournalSubmissionPortal,
    PlatformAdapter,
    Publisher,
    PublisherRegistrationSupport,
    utc_now,
)
from app.services.registration_admission import require_supported_registration_target


@pytest.fixture
def publisher(db_session):
    record = Publisher(name="Elsevier", normalized_name="elsevier")
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def support(db_session, publisher):
    record = PublisherRegistrationSupport(
        publisher_id=publisher.id,
        publisher_code="ELSEVIER",
        display_name=publisher.name,
        support_status="SUPPORTED",
        support_level="V0_1",
        official_domains=["example.com"],
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def journal(db_session, publisher):
    record = Journal(
        publisher_id=publisher.id,
        name="Admission Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def other_journal(db_session):
    other_publisher = Publisher(
        name="Other Publisher", normalized_name="other publisher"
    )
    db_session.add(other_publisher)
    db_session.flush()
    record = Journal(
        publisher_id=other_publisher.id,
        name="Other Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def adapter(db_session):
    record = PlatformAdapter(
        adapter_code="TEST_ADAPTER",
        adapter_name="Test Adapter",
        platform_type="TEST_PLATFORM",
        adapter_version="1.0.0",
        support_status="SUPPORTED",
        allowed_domains=["example.com"],
        last_verified_at=utc_now(),
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def portal(db_session, journal, support, adapter):
    record = JournalSubmissionPortal(
        journal_id=journal.id,
        original_url="https://example.com/register",
        final_url="https://example.com/register",
        redirect_chain=[],
        verification_status="VERIFIED",
        access_status="ACCESSIBLE",
        platform_code="TEST_PLATFORM",
        confidence=1.0,
        evidence_summary=[],
        normalized_host="example.com",
        platform_adapter_id=adapter.id,
        support_status="SUPPORTED",
    )
    db_session.add(record)
    db_session.commit()
    return record


def assert_admission_error(
    db_session,
    publisher_id,
    journal_id,
    portal_id,
    platform_code,
    expected_status,
    expected_code,
):
    with pytest.raises(AppError) as caught:
        require_supported_registration_target(
            db_session, publisher_id, journal_id, portal_id, platform_code
        )
    assert caught.value.status_code == expected_status
    assert caught.value.code == expected_code


def test_supported_target_returns_bound_records(
    db_session, publisher, journal, portal, adapter
):
    result = require_supported_registration_target(
        db_session, publisher.id, journal.id, portal.id, portal.platform_code
    )

    assert result.publisher is publisher
    assert result.journal is journal
    assert result.portal is portal
    assert result.adapter is adapter


@pytest.mark.parametrize(
    ("field", "value"),
    [("support_status", "DISABLED"), ("support_level", "V0_2")],
)
def test_unsupported_publisher_is_rejected(
    db_session, publisher, journal, portal, support, field, value
):
    setattr(support, field, value)
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        portal.platform_code,
        403,
        "PUBLISHER_NOT_IN_V01_WHITELIST",
    )


def test_sixth_publisher_is_rejected_even_with_supported_record(db_session):
    publisher = Publisher(name="Sixth Publisher", normalized_name="sixth publisher")
    db_session.add(publisher)
    db_session.flush()
    db_session.add(
        PublisherRegistrationSupport(
            publisher_id=publisher.id,
            publisher_code="MDPI",
            display_name=publisher.name,
            support_status="SUPPORTED",
            support_level="V0_1",
        )
    )
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        str(uuid4()),
        str(uuid4()),
        "TEST_PLATFORM",
        403,
        "PUBLISHER_NOT_IN_V01_WHITELIST",
    )


@pytest.mark.parametrize("journal_id", [None, "deleted"])
def test_missing_or_deleted_journal_is_not_found(
    db_session, publisher, journal, portal, journal_id
):
    if journal_id == "deleted":
        journal.deleted_at = utc_now()
        db_session.commit()
        journal_id = journal.id
    else:
        journal_id = str(uuid4())

    assert_admission_error(
        db_session,
        publisher.id,
        journal_id,
        portal.id,
        portal.platform_code,
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_publisher_journal_mismatch_is_rejected(
    db_session, publisher, other_journal, portal
):
    assert_admission_error(
        db_session,
        publisher.id,
        other_journal.id,
        portal.id,
        portal.platform_code,
        409,
        "JOURNAL_PUBLISHER_MISMATCH",
    )


def test_portal_from_another_journal_is_not_found(
    db_session, publisher, journal, portal, other_journal
):
    portal.journal_id = other_journal.id
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        portal.platform_code,
        404,
        "JOURNAL_ENDPOINT_NOT_FOUND",
    )


def test_unsupported_portal_is_rejected(db_session, publisher, journal, portal):
    portal.support_status = "TESTING"
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        portal.platform_code,
        409,
        "JOURNAL_ENDPOINT_NOT_SUPPORTED",
    )


def test_unverified_portal_is_rejected(db_session, publisher, journal, portal):
    portal.verification_status = "NEEDS_REVIEW"
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        portal.platform_code,
        409,
        "JOURNAL_ENDPOINT_NOT_VERIFIED",
    )


def test_disabled_adapter_version_is_rejected(
    db_session, publisher, journal, portal, adapter
):
    adapter.support_status = "DISABLED"
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        portal.platform_code,
        409,
        "PLATFORM_ADAPTER_NOT_SUPPORTED",
    )


def test_platform_code_must_match_portal(db_session, publisher, journal, portal):
    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        "OTHER_PLATFORM",
        409,
        "PLATFORM_ADAPTER_NOT_SUPPORTED",
    )


@pytest.mark.parametrize(
    "final_url",
    [
        "https://example.com.evil.test/register",
        "https://sub.example.com/register",
        "not-a-valid-absolute-url",
    ],
)
def test_non_exact_or_missing_hostname_is_rejected(
    db_session, publisher, journal, portal, final_url
):
    portal.final_url = final_url
    db_session.commit()

    assert_admission_error(
        db_session,
        publisher.id,
        journal.id,
        portal.id,
        portal.platform_code,
        403,
        "PLATFORM_DOMAIN_NOT_ALLOWED",
    )


def test_hostname_matching_normalizes_case_and_trailing_dot(
    db_session, publisher, journal, portal
):
    portal.final_url = "https://Example.COM./register"
    db_session.commit()

    result = require_supported_registration_target(
        db_session, publisher.id, journal.id, portal.id, portal.platform_code
    )

    assert result.portal is portal
