"""One-time registration confirmations bind the actor, task, and summary."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Author,
    AuthorAuthorization,
    Journal,
    JournalSubmissionPortal,
    Publisher,
    RegistrationConfirmation,
    RegistrationTask,
    User,
    utc_now,
)
from app.services.registration_confirmation import ConfirmationService


@pytest.fixture
def registration_records(db_session, admin):
    now = utc_now()
    author = Author(display_name="Confirmation Author", alternate_names=[])
    publisher = Publisher(name="Confirmation Publisher", normalized_name="confirmation")
    db_session.add_all([author, publisher])
    db_session.flush()
    journal = Journal(
        publisher_id=publisher.id,
        name="Confirmation Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(journal)
    db_session.flush()
    portal = JournalSubmissionPortal(
        journal_id=journal.id,
        original_url="https://register.example/confirm",
        final_url="https://register.example/confirm",
        redirect_chain=[],
        verification_status="VERIFIED",
        access_status="ACCESSIBLE",
        platform_code="TEST_PLATFORM",
        confidence=1.0,
        evidence_summary=[],
        normalized_host="register.example",
        support_status="SUPPORTED",
    )
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=admin.id,
        permissions=["account:register"],
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
    )
    db_session.add_all([portal, grant])
    db_session.commit()
    return author, publisher, journal, portal, grant


@pytest.fixture
def task_factory(db_session, registration_records):
    author, publisher, journal, portal, grant = registration_records

    def create():
        task_portal = JournalSubmissionPortal(
            journal_id=journal.id,
            original_url=f"https://register.example/confirm/{uuid4()}",
            final_url=f"https://register.example/confirm/{uuid4()}",
            redirect_chain=[],
            verification_status="VERIFIED",
            access_status="ACCESSIBLE",
            platform_code="TEST_PLATFORM",
            confidence=1.0,
            evidence_summary=[],
            normalized_host="register.example",
            support_status="SUPPORTED",
        )
        db_session.add(task_portal)
        db_session.flush()
        task = RegistrationTask(
            author_id=author.id,
            publisher_id=publisher.id,
            journal_id=journal.id,
            portal_id=task_portal.id,
            authorization_id=grant.id,
            platform_code="TEST_PLATFORM",
            task_status="READY_TO_SUBMIT",
            idempotency_key=f"confirmation-{uuid4()}",
        )
        db_session.add(task)
        db_session.commit()
        return task

    return create


@pytest.fixture
def task(task_factory):
    return task_factory()


@pytest.fixture
def other_task(task_factory):
    return task_factory()


def create_challenge(service, task, user, **overrides):
    arguments = {
        "task": task,
        "action_type": "SUBMIT_REGISTRATION",
        "summary": {"author_id": task.author_id, "email": "author@example.com"},
        "user": user,
    }
    arguments.update(overrides)
    challenge = service.create_challenge(**arguments)
    service.db.commit()
    return challenge


def test_create_challenge_hashes_canonical_summary_and_persists_only_hashes(
    db_session, admin, task, monkeypatch
):
    raw_token = "test-only-raw-confirmation-token"

    def deterministic_token(size):
        assert size == 32
        return raw_token

    monkeypatch.setattr(
        "app.services.registration_confirmation.secrets.token_urlsafe",
        deterministic_token,
    )
    service = ConfirmationService(db_session)
    summary = {"z": "最后", "nested": {"b": 2, "a": 1}, "a": "x y"}

    challenge = create_challenge(service, task, admin, summary=summary)

    expected_summary_hash = (
        "6332c5a034ff18a436a955348aa9b9f29147a9ea9d4fb2095294e06a5b3e0c01"
    )
    assert challenge.token == raw_token
    assert challenge.summary_hash == expected_summary_hash
    record = db_session.get(RegistrationConfirmation, challenge.id)
    assert record.summary_hash == expected_summary_hash
    assert record.token_hash == (
        "181b02e00fbd7769ec3ba3150acabbb77a0601c147e9d6eb68cf13aa75241d31"
    )
    assert raw_token not in repr(vars(record))
    assert raw_token not in repr(vars(task))
    assert "author@example.com" not in repr(vars(record))


def test_default_challenge_ttl_is_ten_minutes(db_session, admin, task):
    service = ConfirmationService(db_session)
    before = utc_now()

    challenge = create_challenge(service, task, admin)

    after = utc_now()
    record = db_session.get(RegistrationConfirmation, challenge.id)
    assert before + timedelta(seconds=600) <= record.expires_at
    assert record.expires_at <= after + timedelta(seconds=600)


def test_successful_consume_does_not_log_or_write_raw_token_to_task(
    db_session, admin, task, caplog
):
    caplog.set_level(logging.DEBUG)
    service = ConfirmationService(db_session)
    challenge = create_challenge(service, task, admin)
    db_session.refresh(task)
    original_task_values = vars(task).copy()

    consumed = service.consume(
        task,
        challenge.id,
        challenge.token,
        challenge.summary_hash,
        admin,
        expected_action="SUBMIT_REGISTRATION",
        legal_states={"READY_TO_SUBMIT"},
    )

    assert consumed.consumed_at is not None
    assert challenge.token not in caplog.text
    assert vars(task) == original_task_values


def test_confirmation_cannot_be_replayed_or_used_after_summary_change(
    db_session, admin, task
):
    service = ConfirmationService(db_session)
    challenge = create_challenge(service, task, admin)
    consumed = service.consume(
        task,
        challenge.id,
        challenge.token,
        challenge.summary_hash,
        admin,
        expected_action="SUBMIT_REGISTRATION",
        legal_states={"READY_TO_SUBMIT"},
    )
    assert consumed.consumed_at is not None

    with pytest.raises(AppError):
        service.consume(
            task,
            challenge.id,
            challenge.token,
            challenge.summary_hash,
            admin,
            expected_action="SUBMIT_REGISTRATION",
            legal_states={"READY_TO_SUBMIT"},
        )
    with pytest.raises(AppError):
        service.consume(
            task,
            challenge.id,
            challenge.token,
            "0" * 64,
            admin,
            expected_action="SUBMIT_REGISTRATION",
            legal_states={"READY_TO_SUBMIT"},
        )


def test_expired_confirmation_is_rejected(db_session, admin, task):
    service = ConfirmationService(db_session)
    challenge = create_challenge(service, task, admin, ttl_seconds=-1)

    with pytest.raises(AppError) as caught:
        service.consume(
            task,
            challenge.id,
            challenge.token,
            challenge.summary_hash,
            admin,
            expected_action="SUBMIT_REGISTRATION",
            legal_states={"READY_TO_SUBMIT"},
        )

    assert caught.value.code == "CONFIRMATION_EXPIRED"
    assert db_session.get(RegistrationConfirmation, challenge.id).consumed_at is None


@pytest.mark.parametrize(
    "binding",
    ["wrong_task", "wrong_user", "wrong_token", "changed_summary"],
)
def test_confirmation_rejects_changed_bindings_without_consuming(
    db_session, admin, operator, task, other_task, binding
):
    service = ConfirmationService(db_session)
    challenge = create_challenge(service, task, admin)
    target_task = other_task if binding == "wrong_task" else task
    user = operator if binding == "wrong_user" else admin
    token = "wrong-token" if binding == "wrong_token" else challenge.token
    summary_hash = "0" * 64 if binding == "changed_summary" else challenge.summary_hash

    with pytest.raises(AppError) as caught:
        service.consume(
            target_task,
            challenge.id,
            token,
            summary_hash,
            user,
            expected_action="SUBMIT_REGISTRATION",
            legal_states={"READY_TO_SUBMIT"},
        )

    assert caught.value.code == "CONFIRMATION_INVALID"
    db_session.expire_all()
    assert db_session.get(RegistrationConfirmation, challenge.id).consumed_at is None


def test_concurrent_consume_has_exactly_one_winner(
    db_engine, db_session, admin, task
):
    service = ConfirmationService(db_session)
    challenge = create_challenge(service, task, admin)
    db_session.commit()
    task_id = task.id
    user_id = admin.id

    def consume_once(_):
        with Session(bind=db_engine, expire_on_commit=False) as session:
            try:
                ConfirmationService(session).consume(
                    session.get(RegistrationTask, task_id),
                    challenge.id,
                    challenge.token,
                    challenge.summary_hash,
                    session.get(User, user_id),
                    expected_action="SUBMIT_REGISTRATION",
                    legal_states={"READY_TO_SUBMIT"},
                )
                return "CONSUMED"
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume_once, range(2)))

    assert results.count("CONSUMED") == 1
    db_session.expire_all()
    record = db_session.get(RegistrationConfirmation, challenge.id)
    assert record.consumed_at is not None


def test_confirmation_binds_expected_action_and_legal_task_state(
    db_session, admin, task
):
    service = ConfirmationService(db_session)
    challenge = create_challenge(
        service, task, admin, action_type="VERIFY_EMAIL"
    )

    with pytest.raises(AppError) as caught:
        service.consume(
            task,
            challenge.id,
            challenge.token,
            challenge.summary_hash,
            admin,
            expected_action="SUBMIT_REGISTRATION",
            legal_states={"READY_TO_SUBMIT"},
        )

    assert caught.value.code == "CONFIRMATION_INVALID"
    assert db_session.get(RegistrationConfirmation, challenge.id).consumed_at is None


def test_cancelled_task_cannot_consume_confirmation(
    db_session, admin, task
):
    service = ConfirmationService(db_session)
    challenge = create_challenge(service, task, admin)
    task.task_status = "CANCELLED"
    db_session.commit()

    with pytest.raises(AppError) as caught:
        service.consume(
            task,
            challenge.id,
            challenge.token,
            challenge.summary_hash,
            admin,
            expected_action="SUBMIT_REGISTRATION",
            legal_states={"READY_TO_SUBMIT"},
        )

    assert caught.value.code == "INVALID_TASK_STATE"
    db_session.expire_all()
    assert db_session.get(RegistrationConfirmation, challenge.id).consumed_at is None
