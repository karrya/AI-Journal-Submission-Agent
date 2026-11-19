from sqlalchemy import func, select

from app.models import DiscoveryTask


def test_identify_creates_persistent_pending_task_without_network(client, db_session, admin_context):
    payload = {"publisher_name": "Publisher", "journal_name": "Network Journal"}
    response = client.post("/api/v1/journals/identify", json=payload)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "PENDING"
    assert response.json()["candidates"] == []
    task_id = response.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    assert task.status == "PENDING"
    assert task.progress == 0
    assert task.payload["journal_name"] == "network journal"

    repeated = client.post("/api/v1/journals/identify", json=payload)
    assert repeated.status_code == 202
    assert repeated.json()["task_id"] == task_id
    assert db_session.scalar(select(func.count(DiscoveryTask.id))) == 1


def test_identify_reuses_completed_external_candidate_response(client, db_session, admin_context):
    payload = {"publisher_name": "Publisher", "journal_name": "Repeated Journal"}
    created = client.post("/api/v1/journals/identify", json=payload)
    task_id = created.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    from app.services.identification import JournalIdentificationService
    journal = JournalIdentificationService(db_session, admin_context.user, "reused-task").create_journal(
        publisher_name="Publisher", name="Repeated Journal", aliases=[]
    )
    task.status = "SUCCEEDED"
    task.journal_id = journal.id
    task.checkpoint = {
        "response": {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "candidates": [{
                "candidate_key": "external-repeated",
                "name": "Repeated Journal",
                "publisher_name": "Publisher",
                "identity_status": "NEEDS_CONFIRMATION",
                "sources": ["OPENALEX"],
            }],
        }
    }
    db_session.commit()
    repeated = client.post("/api/v1/journals/identify", json=payload)
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["task_id"] == task_id
    assert repeated.json()["candidates"][0]["candidate_key"] == "external-repeated"
    assert repeated.json()["journal_id"] == journal.id


def test_repeated_identify_uses_current_failed_status(client, db_session, admin_context):
    for status in ("FAILED",):
        payload = {"publisher_name": "Publisher", "journal_name": f"{status} Journal"}
        created = client.post("/api/v1/journals/identify", json=payload)
        task_id = created.json()["task_id"]
        task = db_session.get(DiscoveryTask, task_id)
        task.status = status
        db_session.commit()
        repeated = client.post("/api/v1/journals/identify", json=payload)
        assert repeated.status_code == 202, repeated.text
        assert repeated.json()["status"] == status


def test_starting_cancelled_identification_requeues_same_task(client, db_session, admin_context):
    payload = {"publisher_name": "Publisher", "journal_name": "Restart Cancelled"}
    created = client.post("/api/v1/journals/identify", json=payload)
    task_id = created.json()["task_id"]
    assert client.post(f"/api/v1/tasks/{task_id}/cancel").status_code == 200

    restarted = client.post("/api/v1/journals/identify", json=payload)
    assert restarted.status_code == 202, restarted.text
    assert restarted.json()["task_id"] == task_id
    assert restarted.json()["status"] == "PENDING"
    task = db_session.get(DiscoveryTask, task_id)
    assert task.status == "PENDING"
    assert task.cancel_requested is False
    assert task.completed_at is None


def test_pending_task_can_be_cancelled_and_restarted(client, db_session, admin_context):
    created = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Cancel Journal"},
    )
    task_id = created.json()["task_id"]
    cancelled = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    task = db_session.get(DiscoveryTask, task_id)
    assert task.completed_at is not None

    retry = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "PENDING"


def test_completed_journal_task_can_be_reidentified_without_deleting_journal(client, db_session, admin_context):
    from app.models import Journal
    from app.services.identification import JournalIdentificationService

    journal = JournalIdentificationService(db_session, admin_context.user, "retry-complete").create_journal(
        publisher_name="Publisher", name="Completed Journal", aliases=[]
    )
    journal.identity_status = "VERIFIED"
    created = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Completed Journal"},
    )
    task_id = created.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    task.status = "SUCCEEDED"
    task.journal_id = journal.id
    task.checkpoint = {
        "response": {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "candidates": [{
                "candidate_key": "verified-1",
                "id": journal.id,
                "name": journal.name,
                "identity_status": "VERIFIED",
            }],
        }
    }
    db_session.commit()

    response = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PENDING"
    assert response.json()["journal_id"] is None
    db_session.expire_all()
    assert db_session.get(Journal, journal.id).identity_status == "VERIFIED"
    assert db_session.get(DiscoveryTask, task_id).journal_id is None


def test_unresolved_succeeded_task_can_be_retried(client, db_session, admin_context):
    created = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Retry Unknown"},
    )
    task_id = created.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    task.status = "SUCCEEDED"
    task.journal_id = None
    task.checkpoint = {
        "response": {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "candidates": [{
                "candidate_key": "unknown-1",
                "name": "Retry Unknown",
                "identity_status": "UNKNOWN",
            }],
        }
    }
    db_session.commit()
    response = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PENDING"
    assert db_session.get(DiscoveryTask, task_id).attempt_count == 0


def test_confirm_external_candidate_creates_journal_and_lists_portals(client, db_session, admin_context):
    created = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "External Journal"},
    )
    task_id = created.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    task.status = "SUCCEEDED"
    task.progress = 100
    task.checkpoint = {
        "response": {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "candidates": [{
                "candidate_key": "external-1",
                "name": "External Journal",
                "publisher_name": "Publisher",
                "website_url": "https://journal.example",
                "author_guidelines_url": "https://journal.example/guide",
                "submission_url": "https://www.editorialmanager.com/external",
                "portal_original_url": "https://journal.example/submit",
                "portal_verification_status": "VERIFIED",
                "portal_access_status": "PUBLIC_ACCESS",
                "platform_code": "EDITORIAL_MANAGER",
                "platform_confidence": 0.99,
                "identity_status": "NEEDS_CONFIRMATION",
                "sources": ["OPENALEX"],
                "evidence": [{
                    "source_type": "JOURNAL_HOME",
                    "url": "https://journal.example",
                    "title": "External Journal",
                    "http_status": 200,
                    "content_sha256": "a" * 64,
                }],
            }],
        },
        "warnings": [],
    }
    db_session.commit()
    confirmed = client.post(
        f"/api/v1/tasks/{task_id}/confirm-candidate",
        json={"candidate_key": "external-1", "confirmation_note": "verified manually"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["journal_id"] is not None
    candidate = confirmed.json()["candidates"][0]
    assert candidate["identity_status"] == "VERIFIED"
    assert candidate["id"] == confirmed.json()["journal_id"]

    portals = client.get(f"/api/v1/journals/{candidate['id']}/submission-portals")
    assert portals.status_code == 200, portals.text
    assert portals.json()["items"][0]["platform_code"] == "EDITORIAL_MANAGER"
    assert portals.json()["items"][0]["access_status"] == "PUBLIC_ACCESS"
    assert portals.json()["items"][0]["evidence_summary"][0]["url"] == "https://journal.example"


def test_confirm_candidate_rejects_unknown_key(client, db_session, admin_context):
    created = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Missing Candidate"},
    )
    task_id = created.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    task.status = "SUCCEEDED"
    task.checkpoint = {"response": {"task_id": task_id, "status": "SUCCEEDED", "candidates": []}}
    db_session.commit()
    response = client.post(
        f"/api/v1/tasks/{task_id}/confirm-candidate",
        json={"candidate_key": "missing"},
    )
    assert response.status_code == 404


def test_task_response_exposes_stage_warnings_and_external_candidates(client, db_session, admin_context):
    created = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Candidate Journal"},
    )
    task_id = created.json()["task_id"]
    task = db_session.get(DiscoveryTask, task_id)
    task.stage = "OFFICIAL_SITE_VERIFY"
    task.progress = 45
    task.checkpoint = {
        "warnings": ["Crossref 暂时不可用"],
        "response": {
            "task_id": task_id,
            "status": "PROCESSING",
            "candidates": [{
                "candidate_key": "candidate-1",
                "name": "Candidate Journal",
                "publisher_name": "Publisher",
                "website_url": "https://journal.example",
                "identity_status": "NEEDS_CONFIRMATION",
                "sources": ["OPENALEX"],
            }],
        },
    }
    db_session.commit()
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["stage"] == "OFFICIAL_SITE_VERIFY"
    assert response.json()["progress"] == 45
    assert response.json()["warnings"] == ["Crossref 暂时不可用"]
    candidate = response.json()["candidates"][0]
    assert candidate["candidate_key"] == "candidate-1"
    assert candidate["sources"] == ["OPENALEX"]
    assert candidate["website_url"] == "https://journal.example"
