from datetime import timedelta

from app.models import DiscoveryTask, utc_now
from app.schemas.identification import IdentifyRequest
from app.services.discovery_providers import ProviderError
from app.services.identification import JournalIdentificationService
from app.workers.discovery_worker import DiscoveryWorker, ExecutionResult, TaskCancelled
from app.workers.run_discovery_worker import default_worker_id
from app.services.network_identification import NetworkIdentificationService


def create_task(db_session, admin, name="Worker Journal"):
    service = JournalIdentificationService(db_session, admin, "worker-test")
    return service.create_network_task(
        IdentifyRequest(publisher_name="Publisher", journal_name=name)
    )


def test_default_worker_id_contains_process_identity():
    import os
    import socket

    assert default_worker_id() == f"{socket.gethostname()}:{os.getpid()}"


def test_worker_claims_pending_task_once(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    worker = DiscoveryWorker(db_engine, worker_id="worker-1", executor=lambda task, session: None)
    claimed = worker.claim_next()
    assert claimed == response.task_id
    second = DiscoveryWorker(db_engine, worker_id="worker-2", executor=lambda task, session: None)
    assert second.claim_next() is None
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "PROCESSING"
    assert task.worker_id == "worker-1"
    assert task.attempt_count == 1
    assert task.lease_expires_at > utc_now()


def test_worker_persists_successful_execution(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    def execute(task, session):
        task.stage = "PERSIST"
        task.progress = 95
        return ExecutionResult(checkpoint={"response": {"task_id": task.id, "status": "SUCCEEDED", "candidates": []}, "warnings": []})

    worker = DiscoveryWorker(db_engine, worker_id="worker-success", executor=execute)
    assert worker.run_once() is True
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "SUCCEEDED"
    assert task.progress == 100
    assert task.stage == "PERSIST"
    assert task.completed_at is not None
    assert task.worker_id is None


def test_retryable_provider_failure_waits_for_next_attempt(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    def fail(task, session):
        raise ProviderError("temporary outage", retryable=True)

    worker = DiscoveryWorker(db_engine, worker_id="worker-retry", executor=fail, retry_base_seconds=30)
    assert worker.run_once() is True
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "PENDING"
    assert task.retryable is True
    assert task.available_at > utc_now()
    assert task.last_error_code == "PROVIDER_ERROR"
    assert worker.run_once() is False


def test_non_retryable_failure_is_terminal(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    def fail(task, session):
        raise ProviderError("bad response", retryable=False)

    worker = DiscoveryWorker(db_engine, worker_id="worker-failure", executor=fail)
    worker.run_once()
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "FAILED"
    assert task.retryable is False
    assert task.completed_at is not None


def test_stale_lease_can_be_reclaimed(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    task = db_session.get(DiscoveryTask, str(response.task_id))
    task.status = "PROCESSING"
    task.worker_id = "dead-worker"
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    task.available_at = utc_now()
    db_session.commit()
    worker = DiscoveryWorker(
        db_engine,
        worker_id="live-worker",
        executor=lambda task, session: ExecutionResult(),
    )
    assert worker.run_once() is True
    db_session.expire_all()
    assert task.status == "SUCCEEDED"
    assert task.attempt_count == 1


def test_lost_lease_cannot_commit_success_or_overwrite_new_owner(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    first = DiscoveryWorker(
        db_engine,
        worker_id="worker-first",
        executor=lambda task, session: ExecutionResult(),
    )
    assert first.claim_next() == response.task_id
    task = db_session.get(DiscoveryTask, str(response.task_id))
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    second = DiscoveryWorker(
        db_engine,
        worker_id="worker-second",
        executor=lambda task, session: ExecutionResult(),
    )
    assert second.claim_next() == response.task_id

    first.execute_claimed(response.task_id)
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "PROCESSING"
    assert task.worker_id == "worker-second"


def test_checkpoint_detects_lost_lease(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    first = DiscoveryWorker(
        db_engine,
        worker_id="worker-checkpoint-first",
        executor=lambda task, session: NetworkIdentificationService(
            session,
            providers=[],
            http_client=object(),
        ).execute(task),
    )
    assert first.claim_next() == response.task_id
    task = db_session.get(DiscoveryTask, str(response.task_id))
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    second = DiscoveryWorker(
        db_engine,
        worker_id="worker-checkpoint-second",
        executor=lambda task, session: ExecutionResult(),
    )
    assert second.claim_next() == response.task_id

    first.execute_claimed(response.task_id)
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.worker_id == "worker-checkpoint-second"
    assert task.status == "PROCESSING"


def test_cancel_is_observed_at_next_checkpoint(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    worker = DiscoveryWorker(
        db_engine,
        worker_id="worker-cancel-refresh",
        executor=lambda task, session: NetworkIdentificationService(
            session,
            providers=[],
            http_client=object(),
        ).execute(task),
    )
    assert worker.claim_next() == response.task_id
    task = db_session.get(DiscoveryTask, str(response.task_id))
    task.cancel_requested = True
    db_session.commit()

    worker.execute_claimed(response.task_id)
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "CANCELLED"
    assert task.worker_id is None


def test_cancel_before_final_success_is_not_overwritten(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    def cancel_before_success(task, session):
        db_session.get(DiscoveryTask, task.id).cancel_requested = True
        db_session.commit()
        return ExecutionResult()

    worker = DiscoveryWorker(
        db_engine,
        worker_id="worker-cancel-final",
        executor=cancel_before_success,
    )
    assert worker.claim_next() == response.task_id
    worker.execute_claimed(response.task_id)
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "CANCELLED"


def test_cancellation_is_saved_at_safe_checkpoint(db_engine, db_session, admin):
    response = create_task(db_session, admin)
    def cancel(task, session):
        raise TaskCancelled()

    worker = DiscoveryWorker(db_engine, worker_id="worker-cancel", executor=cancel)
    worker.run_once()
    db_session.expire_all()
    task = db_session.get(DiscoveryTask, str(response.task_id))
    assert task.status == "CANCELLED"
    assert task.completed_at is not None
    assert task.worker_id is None
