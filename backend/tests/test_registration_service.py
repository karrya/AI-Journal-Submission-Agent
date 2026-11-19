"""Registration task creation, authorization, and workflow state transitions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
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
    User,
    utc_now,
)
from app.schemas.registration import RegistrationTaskCreate
from app.services.registration import RegistrationService
from app.services.registration_workflow import RegistrationWorkflowService


@pytest.fixture
def registration_records(db_session, operator):
    now = utc_now()
    author = Author(display_name="Task Author", alternate_names=[])
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
        name="Task Journal",
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
def approved_input(registration_records):
    return RegistrationTaskCreate(
        author_id=registration_records.author.id,
        publisher_id=registration_records.publisher.id,
        journal_id=registration_records.journal.id,
        authorization_id=registration_records.grant.id,
        platform_code="TEST_PLATFORM",
        idempotency_key="registration-service-key-0001",
    )


@pytest.fixture
def task(db_session, operator, approved_input):
    return RegistrationService(db_session, operator, "fixture-create").create_task(
        approved_input
    )


def assert_app_error(caught, status_code, code):
    assert caught.value.status_code == status_code
    assert caught.value.code == code


def test_create_and_reuse_registration_task(db_session, operator, approved_input):
    service = RegistrationService(db_session, operator, "request-create")

    first = service.create_task(approved_input)
    second = service.create_task(approved_input)

    assert first.id == second.id
    assert first.task_status == "PENDING"
    assert first.created_by == operator.id
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_create_binds_verified_portal_and_adapter_without_client_url(
    db_session, operator, approved_input, registration_records
):
    task = RegistrationService(db_session, operator, "request-create").create_task(
        approved_input
    )

    assert task.portal_id == registration_records.portal.id
    assert task.adapter_code == "TEST_ADAPTER"
    assert task.adapter_version == "1.2.3"
    assert not hasattr(task, "registration_url")


def test_concurrent_create_with_same_key_creates_one_task(
    db_engine, db_session, registration_records, approved_input
):
    user_id = registration_records.user.id

    def create():
        with Session(bind=db_engine, expire_on_commit=False) as session:
            user = session.get(User, user_id)
            return RegistrationService(session, user, "request-concurrent").create_task(
                approved_input
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: create(), range(2)))

    assert ids[0] == ids[1]
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_idempotency_key_cannot_be_reused_for_another_target(
    db_session, operator, approved_input, registration_records
):
    service = RegistrationService(db_session, operator, "request-create")
    service.create_task(approved_input)
    other_journal = Journal(
        publisher_id=registration_records.publisher.id,
        name="Other Task Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(other_journal)
    db_session.commit()
    changed = approved_input.model_copy(update={"journal_id": other_journal.id})

    with pytest.raises(AppError) as caught:
        service.create_task(changed)

    assert_app_error(caught, 409, "IDEMPOTENCY_KEY_REUSED")
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_admin_cannot_create_without_explicit_author_consent(
    db_session, admin, approved_input
):
    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, admin, "request-admin").create_task(
            approved_input
        )

    assert_app_error(caught, 403, "AUTHORIZATION_INVALID")
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 0


def test_read_only_role_cannot_create_even_with_author_consent(
    db_session, reviewer, approved_input, registration_records
):
    registration_records.grant.user_id = reviewer.id
    db_session.commit()

    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, reviewer, "request-reviewer").create_task(
            approved_input
        )

    assert_app_error(caught, 403, "PERMISSION_DENIED")


def test_create_rejects_unsupported_target(
    db_session, operator, approved_input, registration_records
):
    registration_records.portal.support_status = "TESTING"
    db_session.commit()

    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, operator, "request-create").create_task(
            approved_input
        )

    assert_app_error(caught, 409, "JOURNAL_ENDPOINT_NOT_SUPPORTED")


def test_client_cannot_select_task_state(approved_input):
    with pytest.raises(ValidationError):
        RegistrationTaskCreate(
            **approved_input.model_dump(), task_status="REGISTERED"
        )


def test_get_and_list_only_return_tasks_with_current_consent(
    db_session, operator, approved_input, task, registration_records
):
    service = RegistrationService(db_session, operator, "request-read")
    records, total = service.list_tasks({}, page=1, page_size=20)

    assert service.get_task(task.id).id == task.id
    assert [record.id for record in records] == [task.id]
    assert total == 1

    registration_records.grant.revoked_at = utc_now()
    db_session.commit()
    records, total = service.list_tasks({}, page=1, page_size=20)

    assert records == []
    assert total == 0
    with pytest.raises(AppError) as caught:
        service.get_task(task.id)
    assert_app_error(caught, 403, "PERMISSION_DENIED")


def test_cancel_stops_future_actions_without_deleting_external_account(
    db_session, operator, task, registration_records
):
    account = PublisherAccount(
        author_id=task.author_id,
        publisher_id=task.publisher_id,
        journal_id=task.journal_id,
        platform_code=task.platform_code,
        account_namespace="register.example",
        account_email="author@example.com",
        normalized_email="author@example.com",
        account_status="REGISTERED",
    )
    db_session.add(account)
    task.account_id = None
    task.task_status = "SUBMITTED"
    db_session.commit()
    db_session.flush()
    task.account_id = account.id
    db_session.commit()

    cancelled = RegistrationService(
        db_session, operator, "request-cancel"
    ).cancel_task(task.id, reason="停止后续外部动作")

    assert cancelled.task_status == "CANCELLED"
    assert cancelled.cancel_requested is True
    assert cancelled.current_step == "停止后续外部动作"
    assert cancelled.last_activity_at is not None
    assert db_session.get(PublisherAccount, account.id) is not None


def test_cancelled_or_completed_task_can_be_restarted(db_session, operator, task):
    service = RegistrationService(db_session, operator, "request-retry")
    task.task_status = "CANCELLED"
    task.cancel_requested = True
    task.retryable = True
    task.worker_id = "worker-a"
    task.lease_expires_at = utc_now() + timedelta(minutes=5)
    db_session.commit()

    restarted = service.retry_task(task.id, reason="人工确认后重新执行")

    assert restarted.task_status == "PENDING"
    assert restarted.cancel_requested is False
    assert restarted.retryable is False
    assert restarted.worker_id is None
    assert restarted.lease_expires_at is None
    assert restarted.current_step == "人工确认后重新执行"
    assert restarted.last_activity_at is not None


def test_registered_task_can_be_restarted(db_session, operator, task):
    task.task_status = "REGISTERED"
    db_session.commit()

    restarted = RegistrationService(
        db_session, operator, "request-retry"
    ).retry_task(task.id)

    assert restarted.task_status == "PENDING"


def test_pending_task_cannot_be_restarted(db_session, operator, task):
    with pytest.raises(AppError) as caught:
        RegistrationService(db_session, operator, "request-retry").retry_task(task.id)

    assert_app_error(caught, 409, "INVALID_TASK_STATE")


def test_terminal_task_rejects_generic_transition(task):
    task.task_status = "REGISTERED"

    with pytest.raises(AppError) as caught:
        RegistrationWorkflowService().transition(
            task, "PENDING", actor_id=str(uuid4()), reason="非法回退"
        )

    assert_app_error(caught, 409, "INVALID_TASK_STATE")


def test_submission_states_require_dedicated_workflow_methods(task):
    workflow = RegistrationWorkflowService()
    actor_id = str(uuid4())

    with pytest.raises(AppError) as caught:
        workflow.transition(
            task, "SUBMITTING", actor_id=actor_id, reason="绕过确认"
        )
    assert_app_error(caught, 409, "INVALID_TASK_STATE")

    task.task_status = "FILLING_FORM"
    workflow.mark_ready_to_submit(task, actor_id=actor_id, reason="表单已填写")
    workflow.start_submission(task, actor_id=actor_id, reason="确认令牌已核销")
    workflow.mark_submission_unknown(task, actor_id=actor_id, reason="提交结果未知")

    assert task.task_status == "SUBMISSION_UNKNOWN"
    assert task.current_step == "提交结果未知"
    assert task.last_activity_at is not None


def test_submission_cannot_start_before_ready(task):
    with pytest.raises(AppError) as caught:
        RegistrationWorkflowService().start_submission(
            task, actor_id=str(uuid4()), reason="尚未确认"
        )

    assert_app_error(caught, 409, "INVALID_TASK_STATE")
