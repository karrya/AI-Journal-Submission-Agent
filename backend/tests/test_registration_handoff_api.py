from uuid import uuid4

import pytest
from test_registration_api import registration_records as registration_records_fixture

from app.schemas.registration import RegistrationTaskCreate
from app.services.registration import RegistrationService

registration_records = registration_records_fixture


@pytest.fixture
def handoff_task(db_session, operator, registration_records):
    task = RegistrationService(db_session, operator, "handoff-fixture").create_task(
        RegistrationTaskCreate(
            author_id=registration_records.author.id,
            publisher_id=registration_records.publisher.id,
            journal_id=registration_records.journal.id,
            authorization_id=registration_records.grant.id,
            platform_code="TEST_PLATFORM",
            idempotency_key="registration-handoff-test",
        )
    )
    task.task_status = "NEEDS_MANUAL_REVIEW"
    task.current_step = "HANDOFF_CAPTCHA"
    task.browser_handoff_id = str(uuid4())
    db_session.commit()
    return task


def test_handoff_and_resume_keep_task_identity(client, operator_context, handoff_task):
    shown = client.get(f"/api/v1/registration/tasks/{handoff_task.id}/handoff")

    assert shown.status_code == 200, shown.text
    assert shown.json()["manual_url"] == "https://register.example/register"
    assert shown.json()["browser_handoff_id"] == handoff_task.browser_handoff_id
    assert shown.json()["resumable"] is True

    resumed = client.post(f"/api/v1/registration/tasks/{handoff_task.id}/resume")

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["id"] == handoff_task.id
    assert resumed.json()["task_status"] == "PENDING"
    assert "secret" not in resumed.text


def test_resume_requires_csrf_and_rejects_terminal_task(client, db_session, operator_context, handoff_task):
    denied = client.post(
        f"/api/v1/registration/tasks/{handoff_task.id}/resume",
        headers={"X-CSRF-Token": "wrong"},
    )
    assert denied.status_code == 403

    handoff_task.task_status = "REGISTERED"
    db_session.commit()
    terminal = client.post(f"/api/v1/registration/tasks/{handoff_task.id}/resume")
    assert terminal.status_code == 409
    assert client.get(f"/api/v1/registration/tasks/{uuid4()}/handoff").status_code == 404


def test_handoff_sanitizes_url_and_does_not_resume_robots(
    client, db_session, operator_context, handoff_task
):
    from app.models import JournalSubmissionPortal

    handoff_task.current_step = "HANDOFF_ROBOTS"
    portal = db_session.get(JournalSubmissionPortal, handoff_task.portal_id)
    portal.final_url = "https://register.example/register?token=classified-link"
    db_session.commit()

    response = client.get(f"/api/v1/registration/tasks/{handoff_task.id}/handoff")

    assert response.status_code == 200, response.text
    assert response.json()["manual_url"] == "https://register.example/register"
    assert response.json()["resumable"] is False
    assert response.json()["reason"] == "目标站点禁止自动访问，请使用官方人工页面"
    assert "classified-link" not in response.text
    resumed = client.post(f"/api/v1/registration/tasks/{handoff_task.id}/resume")
    assert resumed.status_code == 409
