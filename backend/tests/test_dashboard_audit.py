import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


@pytest.fixture
def auditor_context(auditor, auth_context_factory):
    return auth_context_factory(auditor)


@pytest.fixture
def reviewer_context(reviewer, auth_context_factory):
    return auth_context_factory(reviewer)


def add_manuscript_with_files(db_session, owner, marker):
    from app.models import (
        FileFamily,
        Manuscript,
        ManuscriptFile,
        ManuscriptVersion,
    )

    manuscript = Manuscript(
        internal_number=marker,
        owner_author_id=owner.id,
        title=f"Manuscript {marker}",
        abstract="Abstract",
        keywords=[],
        article_type="research",
        language="en",
    )
    db_session.add(manuscript)
    db_session.flush()
    old_version = ManuscriptVersion(
        manuscript_id=manuscript.id,
        version_number=1,
        metadata_snapshot={},
    )
    current_version = ManuscriptVersion(
        manuscript_id=manuscript.id,
        version_number=2,
        metadata_snapshot={},
    )
    db_session.add_all([old_version, current_version])
    db_session.flush()
    manuscript.current_version_id = current_version.id
    family = FileFamily(
        manuscript_id=manuscript.id,
        author_id=owner.id,
        file_type="main_manuscript",
        display_name="Main",
    )
    db_session.add(family)
    db_session.flush()
    old_file = ManuscriptFile(
        file_family_id=family.id,
        manuscript_id=manuscript.id,
        manuscript_version_id=old_version.id,
        file_version=1,
        original_filename="old.pdf",
        stored_filename="old.pdf",
        storage_path=f"test/{marker}/old.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=10,
        sha256="a" * 64,
    )
    current_file = ManuscriptFile(
        file_family_id=family.id,
        manuscript_id=manuscript.id,
        manuscript_version_id=current_version.id,
        file_version=2,
        original_filename="current.pdf",
        stored_filename="current.pdf",
        storage_path=f"test/{marker}/current.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=10,
        sha256="b" * 64,
    )
    deleted_file = ManuscriptFile(
        file_family_id=family.id,
        manuscript_id=manuscript.id,
        manuscript_version_id=current_version.id,
        file_version=3,
        original_filename="deleted.pdf",
        stored_filename="deleted.pdf",
        storage_path=f"test/{marker}/deleted.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=10,
        sha256="c" * 64,
        deleted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add_all([old_file, current_file, deleted_file])
    db_session.commit()
    return manuscript


def add_log(db_session, **overrides):
    from app.models import OperationLog

    values = {
        "actor_type": "user",
        "category": "business",
        "action": "journal.update",
        "request_id": str(uuid4()),
        "result": "success",
        "created_at": datetime(2026, 11, 4, 12, 0),
    }
    values.update(overrides)
    record = OperationLog(**values)
    db_session.add(record)
    db_session.commit()
    return record


def seed_dashboard_records(db_session, operator, other_user, grant_factory):
    from app.models import Author

    visible_author = Author(display_name="Visible Author", alternate_names=[])
    hidden_author = Author(display_name="Hidden Author", alternate_names=[])
    db_session.add_all([visible_author, hidden_author])
    db_session.commit()
    visible_manuscript = add_manuscript_with_files(
        db_session, visible_author, "visible"
    )
    add_manuscript_with_files(db_session, hidden_author, "hidden")
    now = datetime.now(UTC)
    grant_factory(
        user=operator,
        author=visible_author,
        permissions=["author:profile:read", "manuscript:read"],
        valid_from=now - timedelta(hours=1),
        valid_to=now + timedelta(days=2),
    )
    grant_factory(
        user=other_user,
        author=hidden_author,
        permissions=["author:profile:read", "manuscript:read"],
        valid_from=now - timedelta(hours=1),
        valid_to=now + timedelta(days=3),
    )
    return visible_author, visible_manuscript


def test_auditor_cannot_read_business_dashboard(client, auditor_context):
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert set(response.json()) == {"code", "message", "request_id", "details"}


def test_dashboard_uses_list_authorization_predicates_and_safe_recent_operations(
    client,
    db_session,
    operator_context,
    operator,
    user_factory,
    grant_factory,
):
    other_user = user_factory("other-operator", roles=("submission_operator",))
    _, visible_manuscript = seed_dashboard_records(
        db_session, operator, other_user, grant_factory
    )
    own_log = add_log(
        db_session,
        actor_user_id=operator.id,
        action="manuscript.update",
        target_type="manuscript",
        target_id=visible_manuscript.id,
        after_summary={"notes": "private-value-not-for-dashboard"},
    )
    add_log(
        db_session,
        actor_user_id=other_user.id,
        action="journal.delete",
        target_id=visible_manuscript.id,
    )

    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["author_count"] == 1
    assert body["manuscript_count"] == 1
    assert body["current_version_file_count"] == 1
    assert body["expiring_authorization_count"] == 1
    assert body["recent_operations"] == [
        {
            "action": own_log.action,
            "target_id": visible_manuscript.id,
            "result": "success",
            "created_at": body["recent_operations"][0]["created_at"],
        }
    ]
    serialized = json.dumps(body)
    assert "private-value-not-for-dashboard" not in serialized
    assert "journal.delete" not in serialized
    assert set(body["recent_operations"][0]) == {
        "action",
        "target_id",
        "result",
        "created_at",
    }


def test_admin_dashboard_counts_all_business_records(
    client,
    db_session,
    admin_context,
    operator,
    user_factory,
    grant_factory,
):
    other_user = user_factory("another-operator", roles=("submission_operator",))
    seed_dashboard_records(db_session, operator, other_user, grant_factory)
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200, response.text
    assert response.json()["author_count"] == 2
    assert response.json()["manuscript_count"] == 2
    assert response.json()["current_version_file_count"] == 2
    assert response.json()["expiring_authorization_count"] == 2


def test_reviewer_without_grants_receives_empty_aggregates(
    client, db_session, reviewer_context, operator, user_factory, grant_factory
):
    other_user = user_factory("third-operator", roles=("submission_operator",))
    seed_dashboard_records(db_session, operator, other_user, grant_factory)
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    assert response.json()["author_count"] == 0
    assert response.json()["manuscript_count"] == 0
    assert response.json()["current_version_file_count"] == 0
    assert response.json()["expiring_authorization_count"] == 0
    assert response.json()["recent_operations"] == []


def test_author_role_cannot_read_business_dashboard(
    client, user_factory, auth_context_factory
):
    user = user_factory("author-dashboard", roles=("author",))
    auth_context_factory(user)
    assert client.get("/api/v1/dashboard/summary").status_code == 403


@pytest.fixture
def audit_records(db_session, operator, admin):
    from app.models import Author

    first_author = Author(display_name="Audit Author One", alternate_names=[])
    second_author = Author(display_name="Audit Author Two", alternate_names=[])
    db_session.add_all([first_author, second_author])
    db_session.commit()
    first_target = str(uuid4())
    first_request = str(uuid4())
    first = add_log(
        db_session,
        actor_user_id=operator.id,
        author_id=first_author.id,
        category="business",
        action="journal.create",
        target_type="journal",
        target_id=first_target,
        request_id=first_request,
        result="success",
        before_summary={"status": "draft"},
        after_summary={"status": "active"},
        created_at=datetime(2026, 11, 1, 12, 0),
    )
    second = add_log(
        db_session,
        actor_user_id=admin.id,
        author_id=second_author.id,
        category="authentication",
        action="auth.login",
        target_type="user",
        target_id=admin.id,
        result="failure",
        error_code="UNAUTHORIZED",
        error_message="Login failed",
        created_at=datetime(2026, 11, 3, 12, 0),
    )
    return {
        "first": first,
        "second": second,
        "first_author": first_author,
        "first_target": first_target,
        "first_request": first_request,
    }


@pytest.mark.parametrize("role", ["system_admin", "auditor"])
def test_admin_and_auditor_can_query_audit_list_and_detail(
    client,
    user_factory,
    auth_context_factory,
    audit_records,
    role,
):
    user = user_factory(f"audit-reader-{role}", roles=(role,))
    auth_context_factory(user)
    listed = client.get("/api/v1/audit-logs")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 2
    detail = client.get(f"/api/v1/audit-logs/{audit_records['first'].id}")
    assert detail.status_code == 200
    assert detail.json()["before_summary"] == {"status": "draft"}


@pytest.mark.parametrize("role", ["submission_operator", "reviewer", "author"])
def test_business_roles_cannot_query_audit_logs(
    client,
    user_factory,
    auth_context_factory,
    audit_records,
    role,
):
    user = user_factory(f"audit-denied-{role}", roles=(role,))
    auth_context_factory(user)
    assert client.get("/api/v1/audit-logs").status_code == 403
    assert (
        client.get(f"/api/v1/audit-logs/{audit_records['first'].id}").status_code == 403
    )


def test_audit_list_supports_every_approved_filter(
    client, auditor_context, audit_records, operator
):
    expected_id = audit_records["first"].id
    queries = [
        {"actor_user_id": operator.id},
        {"author_id": audit_records["first_author"].id},
        {"category": "business"},
        {"action": "journal.create"},
        {"target_type": "journal"},
        {"target_id": audit_records["first_target"]},
        {"result": "success"},
        {"request_id": audit_records["first_request"]},
        {
            "created_from": "2026-11-01T00:00:00Z",
            "created_to": "2026-11-02T00:00:00Z",
        },
        {
            "created_from": "2026-11-01T13:00:00+01:00",
            "created_to": "2026-11-01T14:00:00+01:00",
        },
    ]
    for query in queries:
        response = client.get("/api/v1/audit-logs", params=query)
        assert response.status_code == 200, (query, response.text)
        assert response.json()["total"] == 1, query
        assert response.json()["items"][0]["id"] == expected_id, query


def test_audit_list_paginates_and_sorts(client, auditor_context, audit_records):
    response = client.get(
        "/api/v1/audit-logs",
        params={"page": 2, "page_size": 1, "sort": "created_at", "order": "asc"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["id"] == audit_records["second"].id
    descending = client.get("/api/v1/audit-logs")
    assert descending.json()["items"][0]["id"] == audit_records["second"].id


def test_audit_detail_returns_only_the_approved_schema(
    client, auditor_context, audit_records
):
    response = client.get(f"/api/v1/audit-logs/{audit_records['first'].id}")
    assert response.status_code == 200
    assert set(response.json()) == {
        "id",
        "actor_user_id",
        "actor_type",
        "category",
        "action",
        "target_type",
        "target_id",
        "author_id",
        "request_id",
        "result",
        "before_summary",
        "after_summary",
        "created_at",
    }
    assert response.json()["after_summary"] == {"status": "active"}
    assert response.json()["created_at"].startswith("2026-11-01T12:00:00")


def test_failed_audit_detail_returns_error_code_and_message(
    client, auditor_context, audit_records
):
    response = client.get(f"/api/v1/audit-logs/{audit_records['second'].id}")
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "failure"
    assert body["error_code"] == "UNAUTHORIZED"
    assert body["error_message"] == "Login failed"


def test_audit_rejects_invalid_utc_ranges_and_sorts(client, auditor_context):
    naive = client.get(
        "/api/v1/audit-logs", params={"created_from": "2026-11-01T00:00:00"}
    )
    assert naive.status_code == 422
    reversed_range = client.get(
        "/api/v1/audit-logs",
        params={
            "created_from": "2026-11-03T00:00:00Z",
            "created_to": "2026-11-01T00:00:00Z",
        },
    )
    assert reversed_range.status_code == 422
    assert client.get("/api/v1/audit-logs", params={"sort": "action"}).status_code == 422


def test_audit_logs_have_no_create_update_or_delete_routes(
    client, db_session, auditor_context, audit_records
):
    from app.models import OperationLog

    log_id = audit_records["first"].id
    assert client.delete(f"/api/v1/audit-logs/{log_id}").status_code == 405
    assert client.patch(f"/api/v1/audit-logs/{log_id}", json={}).status_code == 405
    assert client.post("/api/v1/audit-logs", json={}).status_code == 405
    assert db_session.get(OperationLog, log_id) is not None


def test_audit_missing_log_returns_flat_not_found(client, auditor_context):
    response = client.get(f"/api/v1/audit-logs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert set(response.json()) == {"code", "message", "request_id", "details"}


def test_journal_requirement_requires_source_and_writes_audit(
    client, admin_context, admin, db_session
):
    from app.models import Publisher

    publisher = Publisher(name="Audit Press", normalized_name="audit press")
    db_session.add(publisher)
    db_session.commit()
    response = client.post(
        "/api/v1/journals",
        json={
            "publisher_id": str(publisher.id),
            "name": "Journal",
            "requirements": [
                {
                    "key": "abstract_words",
                    "value": 250,
                    "scope": "research",
                    "source_url": "https://journal.example/guide",
                    "verified_at": "2026-11-04T00:00:00Z",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["requirements"][0]["source_url"].endswith("/guide")
    audited = client.get(
        "/api/v1/audit-logs",
        params={"action": "journal.create", "target_id": response.json()["id"]},
    )
    assert audited.status_code == 200
    assert audited.json()["total"] == 1
    assert audited.json()["items"][0]["actor_user_id"] == admin.id
