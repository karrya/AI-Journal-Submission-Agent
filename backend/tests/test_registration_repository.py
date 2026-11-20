"""Registration schemas expose safe fields and repositories query active records."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import (
    Author,
    AuthorAuthorization,
    Journal,
    JournalSubmissionPortal,
    Publisher,
    RegistrationTask,
    utc_now,
)
from app.repositories.registration import RegistrationRepository
from app.schemas.registration import (
    PublisherSupportResponse,
    RegistrationTaskCreate,
    RegistrationTaskPage,
    RegistrationTaskResponse,
)


@pytest.fixture
def registration_records(db_session, operator):
    now = utc_now()
    author = Author(display_name="Registration Author", alternate_names=[])
    publisher = Publisher(
        name="Registration Publisher",
        normalized_name="registration publisher",
        registration_code="REGISTRATION_PUBLISHER",
        registration_support_status="SUPPORTED",
        registration_support_level="V0_1",
        registration_official_domains=["journal.example"],
    )
    db_session.add_all([author, publisher])
    db_session.flush()
    journal = Journal(
        publisher_id=publisher.id,
        name="Registration Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(journal)
    db_session.flush()
    portal = JournalSubmissionPortal(
        journal_id=journal.id,
        original_url="https://journal.example/register",
        final_url="https://journal.example/register",
        redirect_chain=[],
        verification_status="VERIFIED",
        access_status="ACCESSIBLE",
        platform_code="TEST_PLATFORM",
        confidence=1.0,
        evidence_summary=[],
        normalized_host="journal.example",
        adapter_code="TEST_ADAPTER",
        adapter_name="Test Adapter",
        adapter_version="1.0.0",
        adapter_support_status="SUPPORTED",
        adapter_allowed_domains=["journal.example"],
        adapter_capability_config={"registration": True},
        adapter_last_verified_at=now,
        support_status="SUPPORTED",
    )
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=operator.id,
        permissions=["account:register"],
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
    )
    db_session.add_all([portal, grant])
    db_session.flush()
    task = RegistrationTask(
        author_id=author.id,
        publisher_id=publisher.id,
        journal_id=journal.id,
        portal_id=portal.id,
        authorization_id=grant.id,
        platform_code="TEST_PLATFORM",
        adapter_code=portal.adapter_code,
        adapter_version=portal.adapter_version,
        idempotency_key="registration-key-0001",
        task_status="PENDING",
        current_step="WAITING",
        retryable=False,
    )
    db_session.add(task)
    db_session.commit()
    return SimpleNamespace(
        author=author,
        publisher=publisher,
        journal=journal,
        support=publisher,
        portal=portal,
        grant=grant,
        task=task,
        user=operator,
    )


@pytest.fixture
def supported_portal(registration_records):
    return registration_records.portal


def create_task(records, db_session, **overrides):
    values = {
        "author_id": records.author.id,
        "publisher_id": records.publisher.id,
        "journal_id": records.journal.id,
        "portal_id": records.portal.id,
        "authorization_id": records.grant.id,
        "platform_code": "TEST_PLATFORM",
        "idempotency_key": "registration-key-0002",
        "task_status": "PENDING",
        "retryable": False,
    }
    values.update(overrides)
    task = RegistrationTask(**values)
    db_session.add(task)
    db_session.commit()
    return task


def test_task_response_has_no_credential_or_full_verification_link():
    assert "credential_ref" not in RegistrationTaskResponse.model_fields
    assert "verification_url" not in RegistrationTaskResponse.model_fields
    assert RegistrationTaskPage.model_fields["items"].annotation is not None


def test_registration_create_rejects_extra_and_sensitive_fields(registration_records):
    payload = {
        "author_id": registration_records.author.id,
        "publisher_id": registration_records.publisher.id,
        "journal_id": registration_records.journal.id,
        "authorization_id": registration_records.grant.id,
        "platform_code": "TEST_PLATFORM",
        "idempotency_key": "registration-key-0003",
    }
    assert RegistrationTaskCreate(**payload).platform_code == "TEST_PLATFORM"
    with pytest.raises(ValidationError):
        RegistrationTaskCreate(**payload, credential_ref="must-not-be-accepted")
    with pytest.raises(ValidationError):
        RegistrationTaskCreate(**(payload | {"idempotency_key": "too-short"}))


def test_response_models_map_orm_without_exposing_credentials(registration_records):
    task = RegistrationTaskResponse.model_validate(registration_records.task)

    assert str(task.id) == registration_records.task.id
    assert "credential_ref" not in task.model_fields_set
    assert "verification_url" not in task.model_dump_json()
    assert "capability_config" not in task.model_dump_json()


def test_support_response_rejects_incomplete_wide_row(db_session):
    publisher = Publisher(name="Incomplete", normalized_name="incomplete")
    db_session.add(publisher)
    db_session.flush()

    with pytest.raises(ValueError, match="注册支持配置不完整"):
        PublisherSupportResponse.from_publisher(publisher)


def test_repository_finds_publisher_support(db_session, registration_records):
    repository = RegistrationRepository(db_session)

    support = repository.publisher_support(registration_records.publisher.id)

    assert support is registration_records.publisher
    assert support.registration_code == "REGISTRATION_PUBLISHER"
    assert repository.publisher_support(str(uuid4())) is None


def test_publisher_support_excludes_soft_deleted_publisher(
    db_session, registration_records
):
    registration_records.publisher.deleted_at = utc_now()
    db_session.commit()

    assert (
        RegistrationRepository(db_session).publisher_support(
            registration_records.publisher.id
        )
        is None
    )


def test_repository_finds_supported_portal(db_session, supported_portal):
    repository = RegistrationRepository(db_session)
    result = repository.supported_portal(supported_portal.id)
    assert result.adapter_code == supported_portal.adapter_code
    assert repository.supported_portal(str(uuid4())) is None


@pytest.mark.parametrize("master_name", ["publisher", "journal"])
def test_supported_portal_excludes_soft_deleted_master_data(
    db_session, registration_records, master_name
):
    getattr(registration_records, master_name).deleted_at = utc_now()
    db_session.commit()

    assert (
        RegistrationRepository(db_session).supported_portal(
            registration_records.portal.id
        )
        is None
    )


def test_task_by_idempotency_uses_exact_key(db_session, registration_records):
    repository = RegistrationRepository(db_session)

    assert (
        repository.task_by_idempotency("registration-key-0001").id
        == registration_records.task.id
    )
    assert repository.task_by_idempotency("registration-key-missing") is None


def test_task_page_applies_all_documented_filters(db_session, registration_records):
    repository = RegistrationRepository(db_session)
    task = registration_records.task
    matching = {
        "author_id": task.author_id,
        "publisher_id": task.publisher_id,
        "journal_id": task.journal_id,
        "task_status": "PENDING",
        "created_from": task.created_at - timedelta(seconds=1),
        "created_to": task.created_at + timedelta(seconds=1),
    }

    records, total = repository.task_page(matching, page=1, page_size=20)
    assert [record.id for record in records] == [task.id]
    assert total == 1

    for field, value in (
        ("author_id", str(uuid4())),
        ("publisher_id", str(uuid4())),
        ("journal_id", str(uuid4())),
        ("task_status", "COMPLETED"),
        ("created_from", task.created_at + timedelta(seconds=1)),
        ("created_to", task.created_at - timedelta(seconds=1)),
    ):
        records, total = repository.task_page({field: value}, page=1, page_size=20)
        assert records == []
        assert total == 0


def test_task_page_is_deterministic_and_paginates(db_session, registration_records):
    first = registration_records.task
    first.created_at = utc_now() - timedelta(hours=1)
    first.task_status = "CANCELLED"
    db_session.commit()
    second = create_task(registration_records, db_session, created_at=utc_now())
    db_session.commit()
    repository = RegistrationRepository(db_session)

    page_one, total = repository.task_page({}, page=1, page_size=1)
    page_two, _ = repository.task_page({}, page=2, page_size=1)

    assert total == 2
    assert [record.id for record in page_one] == [second.id]
    assert [record.id for record in page_two] == [first.id]


@pytest.mark.parametrize("master_name", ["author", "publisher", "journal"])
def test_task_page_excludes_soft_deleted_master_data(
    db_session, registration_records, master_name
):
    getattr(registration_records, master_name).deleted_at = utc_now()
    db_session.commit()

    records, total = RegistrationRepository(db_session).task_page(
        {}, page=1, page_size=20
    )
    assert records == []
    assert total == 0


def test_task_page_enforces_page_size_limit(db_session, registration_records):
    repository = RegistrationRepository(db_session)

    with pytest.raises(ValueError, match="page_size"):
        repository.task_page({}, page=1, page_size=101)

    records, _ = repository.task_page({}, page=1, page_size=100)
    assert len(records) == 1
