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
    PlatformAdapter,
    Publisher,
    PublisherAccount,
    PublisherRegistrationSupport,
    RegistrationTask,
    utc_now,
)
from app.repositories.authorizations import AuthorizationRepository
from app.repositories.registration import RegistrationRepository
from app.schemas.registration import (
    PlatformAdapterResponse,
    PublisherAccountResponse,
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
    )
    adapter = PlatformAdapter(
        adapter_code="TEST_ADAPTER",
        adapter_name="Test Adapter",
        platform_type="TEST_PLATFORM",
        adapter_version="1.0.0",
        support_status="SUPPORTED",
        allowed_domains=["journal.example"],
        capability_config={"registration": True},
        last_verified_at=now,
    )
    db_session.add_all([author, publisher, adapter])
    db_session.flush()
    journal = Journal(
        publisher_id=publisher.id,
        name="Registration Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(journal)
    db_session.flush()
    support = PublisherRegistrationSupport(
        publisher_id=publisher.id,
        publisher_code="REGISTRATION_PUBLISHER",
        display_name=publisher.name,
        support_status="SUPPORTED",
        support_level="V0_1",
        official_domains=["journal.example"],
    )
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
        platform_adapter_id=adapter.id,
        support_status="SUPPORTED",
    )
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=operator.id,
        permissions=["account:register"],
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
    )
    db_session.add_all([support, portal, grant])
    db_session.flush()
    task = RegistrationTask(
        author_id=author.id,
        publisher_id=publisher.id,
        journal_id=journal.id,
        portal_id=portal.id,
        authorization_id=grant.id,
        platform_code="TEST_PLATFORM",
        adapter_code=adapter.adapter_code,
        adapter_version=adapter.adapter_version,
        idempotency_key="registration-key-0001",
        task_status="PENDING",
        current_step="WAITING",
        retryable=False,
    )
    account = PublisherAccount(
        author_id=author.id,
        publisher_id=publisher.id,
        journal_id=journal.id,
        platform_code="TEST_PLATFORM",
        account_namespace="journal.example",
        account_email="author@example.com",
        normalized_email="author@example.com",
        credential_ref="secret-credential-reference",
        account_status="REGISTERED",
    )
    db_session.add_all([task, account])
    db_session.commit()
    return SimpleNamespace(
        author=author,
        publisher=publisher,
        journal=journal,
        adapter=adapter,
        support=support,
        portal=portal,
        grant=grant,
        task=task,
        account=account,
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
    account = PublisherAccountResponse.model_validate(registration_records.account)
    support = PublisherSupportResponse.model_validate(registration_records.support)
    adapter = PlatformAdapterResponse.model_validate(registration_records.adapter)

    assert str(task.id) == registration_records.task.id
    assert str(account.id) == registration_records.account.id
    assert str(support.publisher_id) == registration_records.publisher.id
    assert str(adapter.id) == registration_records.adapter.id
    assert "credential_ref" not in account.model_fields_set
    assert "secret-credential-reference" not in account.model_dump_json()
    assert "verification_url" not in task.model_dump_json()


def test_repository_finds_publisher_support_and_adapter(
    db_session, registration_records
):
    repository = RegistrationRepository(db_session)

    support = repository.publisher_support(registration_records.publisher.id)
    adapter = repository.adapter(registration_records.adapter.id)

    assert support.id == registration_records.support.id
    assert adapter.id == registration_records.adapter.id
    assert repository.publisher_support(str(uuid4())) is None
    assert repository.adapter(str(uuid4())) is None


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
    assert result.platform_adapter_id == supported_portal.platform_adapter_id
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


def test_account_page_uses_current_user_authorization(db_session, registration_records):
    repository = RegistrationRepository(db_session)

    records, total = repository.account_page(
        registration_records.user.id, page=1, page_size=20
    )
    other_records, other_total = repository.account_page(
        str(uuid4()), page=1, page_size=20
    )

    assert [record.id for record in records] == [registration_records.account.id]
    assert total == 1
    assert other_records == []
    assert other_total == 0


@pytest.mark.parametrize(
    "state",
    [
        "active",
        "not_yet_active",
        "expired",
        "revoked",
        "wrong_permission",
        "disabled_user",
        "deleted_user",
        "inactive_author",
        "deleted_author",
    ],
)
def test_account_page_matches_task2_active_grant_semantics(
    db_session, registration_records, state
):
    now = utc_now()
    grant = registration_records.grant
    if state == "not_yet_active":
        grant.valid_from = now + timedelta(hours=1)
        grant.valid_to = now + timedelta(hours=2)
    elif state == "expired":
        grant.valid_from = now - timedelta(hours=2)
        grant.valid_to = now - timedelta(hours=1)
    elif state == "revoked":
        grant.revoked_at = now
    elif state == "wrong_permission":
        grant.permissions = ["manuscript:read"]
    elif state == "disabled_user":
        registration_records.user.status = "disabled"
    elif state == "deleted_user":
        registration_records.user.deleted_at = now
    elif state == "inactive_author":
        registration_records.author.status = "disabled"
    elif state == "deleted_author":
        registration_records.author.deleted_at = now
    db_session.commit()

    task2_allows = AuthorizationRepository(db_session).any_active(
        user_id=registration_records.user.id,
        author_id=registration_records.author.id,
        permission="account:register",
        now_utc=now,
    )
    records, total = RegistrationRepository(db_session).account_page(
        registration_records.user.id, page=1, page_size=20
    )

    assert task2_allows is (state == "active")
    assert (total == 1) is task2_allows
    assert (len(records) == 1) is task2_allows


@pytest.mark.parametrize("master_name", ["account", "author", "publisher", "journal"])
def test_account_page_excludes_soft_deleted_records(
    db_session, registration_records, master_name
):
    getattr(registration_records, master_name).deleted_at = utc_now()
    db_session.commit()

    records, total = RegistrationRepository(db_session).account_page(
        registration_records.user.id, page=1, page_size=20
    )
    assert records == []
    assert total == 0


@pytest.mark.parametrize("method", ["task_page", "account_page"])
def test_list_queries_enforce_page_size_limit(db_session, registration_records, method):
    repository = RegistrationRepository(db_session)
    args = ({},) if method == "task_page" else (registration_records.user.id,)

    with pytest.raises(ValueError, match="page_size"):
        getattr(repository, method)(*args, page=1, page_size=101)

    records, _ = getattr(repository, method)(*args, page=1, page_size=100)
    assert len(records) == 1
