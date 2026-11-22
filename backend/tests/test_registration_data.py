from datetime import timedelta

import pytest

from app.automation.registration_contracts import RegistrationAutomationError
from app.automation.registration_data import RegistrationDataProvider
from app.models import (
    Author,
    AuthorAuthorization,
    AuthorEmail,
    Journal,
    JournalSubmissionPortal,
    Publisher,
    RegistrationTask,
    User,
    utc_now,
)


class FakeCredentialStore:
    def __init__(self):
        self.values = {}

    def put(self, *, login_name: str, secret: str) -> str:
        self.values[login_name] = secret
        return login_name

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


def build_task(db_session):
    user = User(
        username="registration-data-user",
        normalized_username="registration-data-user",
        display_name="Registration Data User",
        password_hash="test-only",
    )
    author = Author(
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
        alternate_names=[],
    )
    publisher = Publisher(name="Data Publisher", normalized_name="data publisher")
    db_session.add_all([user, author, publisher])
    db_session.flush()
    db_session.add(AuthorEmail(
        author_id=author.id,
        email="synthetic-login",
        normalized_email="synthetic-login",
        purpose="registration",
        is_primary=True,
        verification_status="verified",
        authorization_status="authorized",
    ))
    journal = Journal(
        publisher_id=publisher.id,
        name="Data Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(journal)
    db_session.flush()
    portal = JournalSubmissionPortal(
        journal_id=journal.id,
        original_url="https://register.example/start",
        final_url="https://register.example/start",
        redirect_chain=[],
        verification_status="VERIFIED",
        access_status="PUBLIC_ACCESS",
        platform_code="TEST_PLATFORM",
        confidence=1.0,
        evidence_summary=[],
        normalized_host="register.example",
        adapter_code="TEST_ADAPTER",
        adapter_name="Test Adapter",
        adapter_version="1.0.0",
        adapter_support_status="SUPPORTED",
        adapter_allowed_domains=["register.example"],
        support_status="SUPPORTED",
    )
    now = utc_now()
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=user.id,
        permissions=["account:register"],
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=1),
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
        adapter_code="TEST_ADAPTER",
        adapter_version="1.0.0",
        idempotency_key="registration-data-task-0001",
    )
    db_session.add(task)
    db_session.commit()
    return task


def test_loads_author_data_and_keeps_secret_out_of_checkpoint(db_session):
    task = build_task(db_session)
    store = FakeCredentialStore()
    provider = RegistrationDataProvider(store=store)

    data = provider.load(task, db_session)
    retried = provider.load(task, db_session)

    assert data.login_name == "synthetic-login"
    assert data.profile["given_name"] == "Ada"
    assert data.profile["family_name"] == "Lovelace"
    assert data.portal_url == "https://register.example/start"
    assert data.allowed_hosts == ("register.example",)
    assert data.adapter_code == "TEST_ADAPTER"
    assert data.adapter_version == "1.0.0"
    assert data.secret
    assert retried.secret == data.secret
    assert len(store.values) == 1
    assert "secret" not in data.checkpoint
    assert "password" not in data.checkpoint


def test_missing_registration_email_returns_manual_error_without_secret(db_session):
    task = build_task(db_session)
    db_session.query(AuthorEmail).delete()
    db_session.commit()
    store = FakeCredentialStore()
    provider = RegistrationDataProvider(store=store)

    with pytest.raises(RegistrationAutomationError) as error:
        provider.load(task, db_session)

    assert error.value.code == "REGISTRATION_DATA_INCOMPLETE"
    assert store.values == {}
