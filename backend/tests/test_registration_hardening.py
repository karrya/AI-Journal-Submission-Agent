"""Regression coverage for the module 3 whole-branch review fixes."""

# ruff: noqa: F811 - pytest fixture wrappers intentionally share public fixture names.

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import OperationLog, RegistrationTask, User, utc_now
from app.services.registration import RegistrationService
from app.services.registration_workflow import RegistrationWorkflowService
from app.workers.registration_worker import (
    RegistrationExecutionError,
    RegistrationExecutionResult,
    RegistrationWorker,
)
from test_registration_service import (  # noqa: F401
    approved_input as approved_input_fixture,
    registration_records as registration_records_fixture,
    task as task_fixture,
)


@pytest.fixture
def approved_input(approved_input_fixture):
    return approved_input_fixture


@pytest.fixture
def registration_records(registration_records_fixture):
    return registration_records_fixture


@pytest.fixture
def task(task_fixture):
    return task_fixture


def test_registered_task_is_terminal_and_retry_rejection_is_audited(
    db_session, operator, task
):
    task.task_status = "REGISTERED"
    db_session.commit()

    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, operator, "request-retry").retry_task(task.id)

    assert caught.value.code == "INVALID_TASK_STATE"
    assert db_session.get(RegistrationTask, task.id).task_status == "REGISTERED"
    log = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "registration.task.retry",
            OperationLog.target_id == task.id,
            OperationLog.result == "failure",
        )
    )
    assert log is not None
    assert log.actor_user_id == operator.id
    assert log.request_id == "request-retry"
    assert log.error_code == "INVALID_TASK_STATE"


def test_retry_with_external_action_requires_platform_reconciliation(
    db_session, operator, task
):
    task.task_status = "FAILED"
    task.retryable = True
    task.last_external_action = "SUBMIT"
    db_session.commit()

    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, operator, "request-retry").retry_task(task.id)

    assert caught.value.code == "PLATFORM_RECONCILIATION_REQUIRED"
    assert db_session.get(RegistrationTask, task.id).task_status == "FAILED"


def test_create_success_and_failure_have_whitelisted_audit_records(
    db_session, operator, approved_input, registration_records
):
    service = RegistrationService(db_session, operator, "request-audit")
    created = service.create_task(approved_input)
    success = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "registration.task.create",
            OperationLog.target_id == created.id,
            OperationLog.result == "success",
        )
    )
    assert success is not None
    assert success.after_summary == {"task_status": "PENDING", "reused": False}
    assert success.author_id == created.author_id

    registration_records.portal.support_status = "DISABLED"
    db_session.commit()
    rejected_input = approved_input.model_copy(
        update={"idempotency_key": "registration-service-key-rejected"}
    )
    with pytest.raises(AppError):
        service.create_task(rejected_input)

    failures = list(
        db_session.scalars(
            select(OperationLog).where(
                OperationLog.action == "registration.task.create",
                OperationLog.result == "failure",
            )
        )
    )
    assert len(failures) == 1
    assert failures[0].error_code == "JOURNAL_ENDPOINT_NOT_SUPPORTED"
    assert failures[0].after_summary is None


def test_different_idempotency_keys_cannot_create_conflicting_scope(
    db_session, operator, approved_input
):
    service = RegistrationService(db_session, operator, "request-conflict")
    service.create_task(approved_input)

    with pytest.raises(AppError) as caught:
        service.create_task(
            approved_input.model_copy(
                update={"idempotency_key": "registration-service-key-other"}
            )
        )

    assert caught.value.code == "REGISTRATION_TASK_CONFLICT"
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_cancelled_submission_marker_still_blocks_a_replacement_task(
    db_session, operator, approved_input, task
):
    task.task_status = "CANCELLED"
    task.cancel_requested = True
    task.last_external_action = "SUBMIT"
    db_session.commit()

    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, operator, "request-uncertain").create_task(
            approved_input.model_copy(
                update={"idempotency_key": "registration-uncertain-replacement"}
            )
        )

    assert caught.value.code == "REGISTRATION_TASK_CONFLICT"
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_concurrent_different_keys_have_one_database_enforced_winner(
    db_engine, db_session, registration_records, approved_input
):
    barrier = Barrier(2)
    user_id = registration_records.user.id

    def create(key):
        with Session(bind=db_engine, expire_on_commit=False) as session:
            user = session.get(User, user_id)
            payload = approved_input.model_copy(update={"idempotency_key": key})
            barrier.wait(timeout=10)
            try:
                created = RegistrationService(
                    session, user, "request-concurrent-different-key"
                ).create_task(payload)
                return created.id
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                create,
                ["registration-concurrent-key-a", "registration-concurrent-key-b"],
            )
        )

    assert results.count("REGISTRATION_TASK_CONFLICT") == 1
    assert sum(result != "REGISTRATION_TASK_CONFLICT" for result in results) == 1
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_generic_workflow_rejects_skipping_required_states(task):
    task.task_status = "PENDING"
    with pytest.raises(AppError) as caught:
        RegistrationWorkflowService().transition(
            task, "REGISTERED", actor_id=str(uuid4()), reason="跳过流程"
        )
    assert caught.value.code == "INVALID_TASK_STATE"


def test_submission_requires_consumed_matching_confirmation(task):
    task.task_status = "FILLING_FORM"
    task.external_evidence_ref = "controlled-form-evidence"
    workflow = RegistrationWorkflowService()
    workflow.mark_ready_to_submit(task, actor_id=str(uuid4()))

    with pytest.raises(AppError) as caught:
        workflow.start_submission(task, actor_id=str(uuid4()), confirmation=None)
    assert caught.value.code == "CONFIRMATION_REQUIRED"


def test_worker_rejects_arbitrary_or_unevidenced_executor_results(
    db_engine, db_session, task
):
    worker = RegistrationWorker(
        db_engine,
        worker_id="worker-invalid-result",
        executor=lambda claimed, session: RegistrationExecutionResult("REGISTERED"),
    )
    worker.run_once()
    db_session.expire_all()
    failed = db_session.get(RegistrationTask, task.id)
    assert failed.task_status == "FAILED"
    assert failed.error_code == "REGISTRATION_EVIDENCE_REQUIRED"

    failed.task_status = "PENDING"
    failed.worker_id = None
    failed.available_at = utc_now()
    db_session.commit()
    worker.executor = lambda claimed, session: RegistrationExecutionResult("REGISTERED")
    # A valid result needs explicit platform evidence, not just a status string.
    worker.executor = lambda claimed, session: RegistrationExecutionResult(
        "SUBMITTED", checkpoint={"external_evidence_ref": "accepted-submission"}
    )
    # SUBMITTED is not a legal direct result from phase-one PROCESSING either.
    worker.run_once()
    db_session.expire_all()
    assert db_session.get(RegistrationTask, task.id).task_status == "FAILED"


def test_worker_retries_are_jitter_bounded_and_stop_at_maximum(
    db_engine, db_session, task, monkeypatch
):
    monkeypatch.setattr(
        "app.workers.registration_worker.random.uniform", lambda low, high: high
    )
    worker = RegistrationWorker(
        db_engine,
        worker_id="worker-retry-limit",
        executor=lambda claimed, session: (_ for _ in ()).throw(
            RegistrationExecutionError("temporary", retryable=True)
        ),
        retry_base_seconds=10,
        max_retry_delay_seconds=20,
        retry_jitter_ratio=0.5,
        max_retries=2,
    )

    worker.run_once()
    db_session.expire_all()
    first = db_session.get(RegistrationTask, task.id)
    assert first.task_status == "PENDING"
    assert first.available_at - first.last_heartbeat_at == timedelta(seconds=15)

    first.available_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    worker.run_once()
    db_session.expire_all()
    exhausted = db_session.get(RegistrationTask, task.id)
    assert exhausted.retry_count == 2
    assert exhausted.task_status == "NEEDS_MANUAL_REVIEW"
    assert exhausted.retryable is False
    assert exhausted.available_at is None


def test_expired_submission_marker_recovers_to_unknown_with_audit(
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
        return RegistrationExecutionResult("NEEDS_MANUAL_REVIEW")

    worker = RegistrationWorker(db_engine, worker_id="worker-safe", executor=execute)
    assert worker.run_once() is False

    db_session.expire_all()
    recovered = db_session.get(RegistrationTask, task.id)
    assert recovered.task_status == "SUBMISSION_UNKNOWN"
    assert recovered.retryable is False
    assert recovered.worker_id is None
    assert recovered.lease_expires_at is None
    assert executed is False
    log = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "registration.task.recover_submission_unknown",
            OperationLog.target_id == task.id,
            OperationLog.result == "success",
        )
    )
    assert log is not None
    assert log.actor_type == "system"


def test_barrier_synchronized_worker_claim_has_one_owner(
    db_engine, db_session, task
):
    barrier = Barrier(2)

    def claim(worker_id):
        barrier.wait(timeout=10)
        return RegistrationWorker(db_engine, worker_id=worker_id).claim_next()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["worker-thread-a", "worker-thread-b"]))

    assert results.count(task.id) == 1
    assert results.count(None) == 1
    db_session.expire_all()
    claimed = db_session.get(RegistrationTask, task.id)
    assert claimed.worker_id in {"worker-thread-a", "worker-thread-b"}


def test_worker_claim_result_and_failure_emit_audit_events(
    db_engine, db_session, task
):
    worker = RegistrationWorker(db_engine, worker_id="worker-audit")
    worker.run_once()
    actions = set(
        db_session.scalars(
            select(OperationLog.action).where(OperationLog.target_id == task.id)
        )
    )
    assert "registration.task.claim" in actions
    assert "registration.task.result" in actions

    db_session.expire_all()
    task = db_session.get(RegistrationTask, task.id)
    task.task_status = "PENDING"
    task.available_at = utc_now()
    db_session.commit()
    worker.executor = lambda claimed, session: (_ for _ in ()).throw(
        RegistrationExecutionError("sensitive details must not be audited", retryable=False)
    )
    worker.run_once()
    failure = db_session.scalar(
        select(OperationLog).where(
            OperationLog.target_id == task.id,
            OperationLog.action == "registration.task.failure",
            OperationLog.result == "failure",
        )
    )
    assert failure is not None
    assert failure.error_code == "REGISTRATION_EXECUTION_ERROR"
    assert "sensitive details" not in str(failure.error_message)
    assert failure.after_summary["task_status"] == "FAILED"
