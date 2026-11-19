from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.models import (
    Author,
    AuthorAuthorization,
    Journal,
    JournalSubmissionPortal,
    PlatformAdapter,
    Publisher,
    PublisherRegistrationSupport,
    RegistrationTask,
    utc_now,
)
from app.schemas.registration import RegistrationTaskCreate
from app.services.registration import RegistrationService
from app.workers.registration_worker import (
    RegistrationExecutionError,
    RegistrationExecutionResult,
    RegistrationWorker,
    TaskLeaseLost,
)
from app.workers.run_registration_worker import default_worker_id


@pytest.fixture
def registration_records(db_session, operator):
    now = utc_now()
    author = Author(display_name="Worker Author", alternate_names=[])
    publisher = Publisher(name="Elsevier", normalized_name="elsevier")
    adapter = PlatformAdapter(
        adapter_code="TEST_ADAPTER",
        adapter_name="Test Adapter",
        platform_type="TEST_PLATFORM",
        adapter_version="1.2.3",
        support_status="SUPPORTED",
        allowed_domains=["register.example"],
        last_verified_at=now,
    )
    db_session.add_all([author, publisher, adapter])
    db_session.flush()
    journal = Journal(
        publisher_id=publisher.id,
        name="Worker Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(journal)
    db_session.flush()
    support = PublisherRegistrationSupport(
        publisher_id=publisher.id,
        publisher_code="ELSEVIER",
        display_name=publisher.name,
        support_status="SUPPORTED",
        support_level="V0_1",
        official_domains=["register.example"],
    )
    portal = JournalSubmissionPortal(
        journal_id=journal.id,
        original_url="https://register.example/start",
        final_url="https://register.example/register",
        redirect_chain=[],
        verification_status="VERIFIED",
        access_status="ACCESSIBLE",
        platform_code="TEST_PLATFORM",
        confidence=1.0,
        evidence_summary=[],
        normalized_host="register.example",
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
    db_session.commit()
    return SimpleNamespace(
        author=author,
        publisher=publisher,
        journal=journal,
        adapter=adapter,
        support=support,
        portal=portal,
        grant=grant,
        user=operator,
    )


@pytest.fixture
def task(db_session, operator, registration_records):
    payload = RegistrationTaskCreate(
        author_id=registration_records.author.id,
        publisher_id=registration_records.publisher.id,
        journal_id=registration_records.journal.id,
        authorization_id=registration_records.grant.id,
        platform_code="TEST_PLATFORM",
        idempotency_key="registration-worker-test",
    )
    return RegistrationService(db_session, operator, "worker-fixture").create_task(payload)


def refresh_task(db_session, task_id):
    db_session.expire_all()
    return db_session.get(RegistrationTask, task_id)


def test_default_worker_id_contains_process_identity():
    import os
    import socket

    assert default_worker_id() == f"{socket.gethostname()}:{os.getpid()}"


def test_only_one_worker_claims_registration_task(db_engine, db_session, task):
    first = RegistrationWorker(
        db_engine, worker_id="worker-1", executor=lambda task, db: None
    )
    second = RegistrationWorker(
        db_engine, worker_id="worker-2", executor=lambda task, db: None
    )

    assert first.claim_next() == task.id
    assert second.claim_next() is None

    claimed = refresh_task(db_session, task.id)
    assert claimed.task_status == "PROCESSING"
    assert claimed.worker_id == "worker-1"
    assert claimed.retry_count == 1
    assert claimed.last_heartbeat_at is not None
    assert claimed.lease_expires_at > utc_now()


def test_worker_persists_successful_execution(db_engine, db_session, task):
    worker = RegistrationWorker(
        db_engine,
        worker_id="worker-success",
        executor=lambda task, db: RegistrationExecutionResult(
            "REGISTERED", checkpoint={"current_step": "COMPLETED"}
        ),
    )

    assert worker.run_once() is True

    completed = refresh_task(db_session, task.id)
    assert completed.task_status == "REGISTERED"
    assert completed.current_step == "COMPLETED"
    assert completed.completed_at is not None
    assert completed.worker_id is None
    assert completed.lease_expires_at is None
    assert completed.retryable is False


def test_expired_lease_can_be_reclaimed(db_engine, db_session, task):
    task.task_status = "PROCESSING"
    task.worker_id = "dead-worker"
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    worker = RegistrationWorker(
        db_engine,
        worker_id="live-worker",
        executor=lambda task, db: RegistrationExecutionResult("REGISTERED"),
    )

    assert worker.run_once() is True

    recovered = refresh_task(db_session, task.id)
    assert recovered.task_status == "REGISTERED"
    assert recovered.retry_count == 1


def test_lost_lease_cannot_overwrite_new_owner(db_engine, db_session, task):
    first = RegistrationWorker(
        db_engine,
        worker_id="worker-a",
        executor=lambda task, db: RegistrationExecutionResult("REGISTERED"),
    )
    second = RegistrationWorker(
        db_engine,
        worker_id="worker-b",
        executor=lambda task, db: RegistrationExecutionResult("REGISTERED"),
    )
    assert first.claim_next() == task.id
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert second.claim_next() == task.id

    first.execute_claimed(task.id)

    owned_by_second = refresh_task(db_session, task.id)
    assert owned_by_second.task_status == "PROCESSING"
    assert owned_by_second.worker_id == "worker-b"


def test_stale_worker_cannot_write_checkpoint(db_engine, db_session, task):
    first = RegistrationWorker(db_engine, worker_id="worker-a")
    second = RegistrationWorker(db_engine, worker_id="worker-b")
    assert first.claim_next() == task.id
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert second.claim_next() == task.id

    with pytest.raises(TaskLeaseLost):
        first.save_checkpoint(task.id, {"current_step": "STALE_WRITE"})

    owned_by_second = refresh_task(db_session, task.id)
    assert owned_by_second.current_step == "CLAIMED"
    assert owned_by_second.worker_id == "worker-b"


def test_cancellation_during_execution_wins_over_final_result(
    db_engine, db_session, task
):
    def cancel_before_result(claimed, session):
        db_session.get(RegistrationTask, task.id).cancel_requested = True
        db_session.commit()
        return RegistrationExecutionResult("REGISTERED")

    worker = RegistrationWorker(
        db_engine, worker_id="worker-cancel", executor=cancel_before_result
    )
    assert worker.claim_next() == task.id
    worker.execute_claimed(task.id)

    cancelled = refresh_task(db_session, task.id)
    assert cancelled.task_status == "CANCELLED"
    assert cancelled.worker_id is None
    assert cancelled.lease_expires_at is None


def test_authorization_revocation_during_execution_stops_at_checkpoint(
    db_engine, db_session, task, registration_records
):
    def revoke_before_result(claimed, session):
        registration_records.grant.revoked_at = utc_now()
        db_session.commit()
        return RegistrationExecutionResult("REGISTERED")

    worker = RegistrationWorker(
        db_engine, worker_id="worker-revoked", executor=revoke_before_result
    )
    assert worker.claim_next() == task.id
    worker.execute_claimed(task.id)

    failed = refresh_task(db_session, task.id)
    assert failed.task_status == "FAILED"
    assert failed.error_code == "PERMISSION_DENIED"
    assert failed.worker_id is None


def test_portal_disablement_during_execution_stops_at_checkpoint(
    db_engine, db_session, task, registration_records
):
    def disable_before_result(claimed, session):
        registration_records.portal.support_status = "DISABLED"
        db_session.commit()
        return RegistrationExecutionResult("REGISTERED")

    worker = RegistrationWorker(
        db_engine, worker_id="worker-disabled", executor=disable_before_result
    )
    assert worker.claim_next() == task.id
    worker.execute_claimed(task.id)

    failed = refresh_task(db_session, task.id)
    assert failed.task_status == "FAILED"
    assert failed.error_code == "JOURNAL_ENDPOINT_NOT_SUPPORTED"
    assert failed.worker_id is None


def test_retryable_failures_use_bounded_exponential_backoff(
    db_engine, db_session, task
):
    def fail(claimed, session):
        raise RegistrationExecutionError("temporary outage", retryable=True)

    worker = RegistrationWorker(
        db_engine,
        worker_id="worker-retry",
        executor=fail,
        retry_base_seconds=2,
        max_retry_delay_seconds=3,
    )

    assert worker.run_once() is True
    first_attempt = refresh_task(db_session, task.id)
    assert first_attempt.task_status == "PENDING"
    assert first_attempt.retryable is True
    assert first_attempt.available_at - first_attempt.last_heartbeat_at == timedelta(
        seconds=2
    )
    assert worker.run_once() is False

    first_attempt.available_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert worker.run_once() is True
    second_attempt = refresh_task(db_session, task.id)
    assert second_attempt.retry_count == 2
    assert second_attempt.available_at - second_attempt.last_heartbeat_at == timedelta(
        seconds=3
    )


def test_retryable_error_after_submit_becomes_unknown_without_replay(
    db_engine, db_session, task
):
    worker = RegistrationWorker(db_engine, worker_id="worker-unknown")

    def fail_after_submit(claimed, session):
        worker.save_checkpoint(claimed.id, {"last_external_action": "SUBMIT"})
        raise RegistrationExecutionError("connection lost", retryable=True)

    worker.executor = fail_after_submit

    assert worker.run_once() is True

    unknown = refresh_task(db_session, task.id)
    assert unknown.task_status == "SUBMISSION_UNKNOWN"
    assert unknown.retryable is False
    assert unknown.available_at is None
    assert unknown.worker_id is None
    assert worker.run_once() is False


def test_non_retryable_execution_failure_is_terminal(db_engine, db_session, task):
    def fail(claimed, session):
        raise RegistrationExecutionError("invalid response", retryable=False)

    worker = RegistrationWorker(db_engine, worker_id="worker-failed", executor=fail)
    worker.run_once()

    failed = refresh_task(db_session, task.id)
    assert failed.task_status == "FAILED"
    assert failed.retryable is False
    assert failed.available_at is None
    assert failed.completed_at is not None


def test_default_executor_only_admits_then_requests_manual_review(
    db_engine, db_session, task
):
    worker = RegistrationWorker(db_engine, worker_id="worker-default")

    assert worker.run_once() is True

    review = refresh_task(db_session, task.id)
    assert review.task_status == "NEEDS_MANUAL_REVIEW"
    assert review.current_step == "MANUAL_REVIEW_REQUIRED"
    assert review.error_code is None
    assert review.worker_id is None


@pytest.mark.parametrize("status", ["SUBMITTING", "SUBMISSION_UNKNOWN"])
def test_external_submission_states_are_never_resubmitted(
    db_engine, db_session, task, status
):
    task.task_status = status
    db_session.commit()
    executed = False

    def execute(claimed, session):
        nonlocal executed
        executed = True
        return RegistrationExecutionResult("REGISTERED")

    worker = RegistrationWorker(db_engine, worker_id="worker-safe", executor=execute)

    assert worker.run_once() is False
    assert executed is False
    assert refresh_task(db_session, task.id).task_status == status


def test_recovered_task_with_submission_action_is_not_executed(
    db_engine, db_session, task
):
    task.task_status = "PROCESSING"
    task.worker_id = "dead-worker"
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    task.last_external_action = "SUBMIT"
    db_session.commit()
    executed = False

    def execute(claimed, session):
        nonlocal executed
        executed = True
        return RegistrationExecutionResult("REGISTERED")

    worker = RegistrationWorker(db_engine, worker_id="worker-safe", executor=execute)

    assert worker.run_once() is False
    assert executed is False
    recovered = refresh_task(db_session, task.id)
    assert recovered.task_status == "PROCESSING"
    assert recovered.worker_id == "dead-worker"
