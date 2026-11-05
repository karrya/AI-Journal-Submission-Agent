from uuid import uuid4

import pytest


@pytest.fixture
def publisher(db_session):
    from app.models import Publisher

    record = Publisher(name="Existing Publisher", normalized_name="existing publisher")
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def platform(db_session):
    from app.models import JournalPlatform

    record = JournalPlatform(code="EXISTING", name="Existing Platform")
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def journal(db_session, publisher, platform):
    from app.models import Journal

    record = Journal(
        publisher_id=publisher.id,
        platform_id=platform.id,
        name="Existing Journal",
        issn="03785955",
        requirements=[
            {
                "key": "abstract_words",
                "value": 250,
                "scope": "research",
                "source_url": "https://journal.example/guide",
                "verified_at": "2026-11-04T00:00:00Z",
            }
        ],
    )
    db_session.add(record)
    db_session.commit()
    return record


def journal_payload(publisher, platform=None, **overrides):
    payload = {
        "publisher_id": publisher.id,
        "platform_id": platform.id if platform else None,
        "name": "New Journal",
        "issn": "0378-5955",
        "eissn": "2434-561X",
        "website_url": "https://journal.example",
        "submission_url": "https://journal.example/submit",
        "author_guidelines_url": "https://journal.example/guide",
        "subject_categories": ["Computer Science"],
        "article_types": ["research"],
        "requirements": [
            {
                "key": "abstract_words",
                "value": 250,
                "scope": "research",
                "source_url": "https://journal.example/guide",
                "verified_at": "2026-11-04T00:00:00Z",
            }
        ],
        "requirements_source_url": "https://journal.example/guide",
        "requirements_verified_at": "2026-11-04T00:00:00Z",
        "status": "active",
        "notes": "Verified against the author guide",
    }
    payload.update(overrides)
    return payload


def test_publisher_crud_filtering_and_soft_delete(client, admin_context):
    created = client.post(
        "/api/v1/publishers",
        json={"name": "  Academic Press  ", "website_url": "https://press.example"},
    )
    assert created.status_code == 201, created.text
    publisher_id = created.json()["id"]
    assert created.json()["name"] == "Academic Press"

    listed = client.get(
        "/api/v1/publishers",
        params={"name": "academic", "sort": "name", "order": "desc"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == publisher_id

    detail = client.get(f"/api/v1/publishers/{publisher_id}")
    assert detail.status_code == 200
    assert detail.json()["website_url"] == "https://press.example"

    updated = client.patch(
        f"/api/v1/publishers/{publisher_id}", json={"notes": "Independent"}
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Independent"

    deleted = client.delete(f"/api/v1/publishers/{publisher_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/publishers/{publisher_id}").status_code == 404
    assert client.get("/api/v1/publishers").json()["total"] == 0


def test_platform_crud_filtering_and_soft_delete(client, admin_context):
    created = client.post(
        "/api/v1/journal-platforms",
        json={"code": "OJS", "name": "Open Journal Systems", "status": "active"},
    )
    assert created.status_code == 201, created.text
    platform_id = created.json()["id"]

    listed = client.get(
        "/api/v1/journal-platforms", params={"code": "OJS", "status": "active"}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/api/v1/journal-platforms/{platform_id}",
        json={"status": "needs_review", "description": "Review configuration"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "needs_review"
    assert client.get(f"/api/v1/journal-platforms/{platform_id}").status_code == 200
    assert client.delete(f"/api/v1/journal-platforms/{platform_id}").status_code == 204
    assert client.get(f"/api/v1/journal-platforms/{platform_id}").status_code == 404


def test_journal_crud_normalizes_issn_and_preserves_provenance(
    client, admin_context, publisher, platform
):
    created = client.post("/api/v1/journals", json=journal_payload(publisher, platform))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["issn"] == "03785955"
    assert body["eissn"] == "2434561X"
    assert body["requirements"][0]["value"] == 250
    assert body["requirements"][0]["source_url"].endswith("/guide")
    assert body["requirements"][0]["verified_at"].startswith("2026-11-04T00:00:00")

    listed = client.get(
        "/api/v1/journals",
        params={
            "name": "new",
            "publisher_id": publisher.id,
            "platform_id": platform.id,
            "issn": "0378-5955",
            "status": "active",
        },
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/api/v1/journals/{body['id']}",
        json={
            "name": "Updated Journal",
            "platform_id": None,
            "issn": None,
            "eissn": None,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated Journal"
    assert "platform_id" not in updated.json() or updated.json()["platform_id"] is None
    assert "issn" not in updated.json() or updated.json()["issn"] is None
    assert "eissn" not in updated.json() or updated.json()["eissn"] is None
    assert client.delete(f"/api/v1/journals/{body['id']}").status_code == 204
    assert client.get(f"/api/v1/journals/{body['id']}").status_code == 404


@pytest.mark.parametrize("role", ["system_admin", "submission_operator", "reviewer"])
@pytest.mark.parametrize(
    "path", ["/api/v1/publishers", "/api/v1/journal-platforms", "/api/v1/journals"]
)
def test_business_roles_can_read_journal_resources(
    client, user_factory, auth_context_factory, publisher, platform, journal, role, path
):
    user = user_factory(f"reader-{role}-{path.rsplit('/', 1)[-1]}", roles=(role,))
    auth_context_factory(user)
    response = client.get(path)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", ["auditor", "author"])
@pytest.mark.parametrize(
    "path", ["/api/v1/publishers", "/api/v1/journal-platforms", "/api/v1/journals"]
)
def test_auditor_and_author_cannot_read_journal_resources(
    client, user_factory, auth_context_factory, role, path
):
    user = user_factory(f"denied-{role}-{path.rsplit('/', 1)[-1]}", roles=(role,))
    auth_context_factory(user)
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert set(response.json()) == {"code", "message", "request_id", "details"}


@pytest.mark.parametrize("role", ["submission_operator", "reviewer", "auditor", "author"])
def test_only_system_admin_can_create_journal_resources(
    client, user_factory, auth_context_factory, publisher, role
):
    user = user_factory(f"writer-{role}", roles=(role,))
    auth_context_factory(user)
    assert (
        client.post("/api/v1/publishers", json={"name": "Denied Publisher"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/journal-platforms", json={"code": "DENIED", "name": "Denied"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/journals", json=journal_payload(publisher)).status_code
        == 403
    )


def test_non_admin_cannot_update_or_delete_journal_resources(
    client, operator_context, publisher, platform, journal
):
    assert client.patch(f"/api/v1/publishers/{publisher.id}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/v1/publishers/{publisher.id}").status_code == 403
    assert client.patch(f"/api/v1/journal-platforms/{platform.id}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/v1/journal-platforms/{platform.id}").status_code == 403
    assert client.patch(f"/api/v1/journals/{journal.id}", json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/v1/journals/{journal.id}").status_code == 403


@pytest.mark.parametrize("field", ["issn", "eissn"])
@pytest.mark.parametrize("value", ["0378-5954", "not-an-issn", "12345678"])
def test_journal_rejects_invalid_issn_checksum_or_format(
    client, admin_context, publisher, field, value
):
    response = client.post(
        "/api/v1/journals", json=journal_payload(publisher, **{field: value})
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "requirement",
    [
        {"key": "abstract", "value": 250, "scope": "research", "verified_at": "2026-11-04T00:00:00Z"},
        {"key": "abstract", "value": 250, "scope": "research", "source_url": "https://journal.example/guide"},
        {"key": "abstract", "value": 250, "scope": "research", "source_url": "http://journal.example/guide", "verified_at": "2026-11-04T00:00:00Z"},
    ],
)
def test_every_requirement_requires_secure_source_and_verification_time(
    client, admin_context, publisher, requirement
):
    response = client.post(
        "/api/v1/journals",
        json=journal_payload(publisher, requirements=[requirement]),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "url", ["http://example.com/guide", "javascript:alert(1)", "https://user:secret" + "@example.com/guide"]
)
def test_journal_urls_follow_approved_url_rules(client, admin_context, publisher, url):
    response = client.post(
        "/api/v1/journals", json=journal_payload(publisher, submission_url=url)
    )
    assert response.status_code == 422


def test_local_development_http_url_is_allowed(client, admin_context):
    response = client.post(
        "/api/v1/publishers",
        json={"name": "Local Press", "website_url": "http://127.0.0.1:8000/docs"},
    )
    assert response.status_code == 201


def test_journal_rejects_missing_or_deleted_related_resources(
    client, admin_context, publisher, platform
):
    missing = client.post(
        "/api/v1/journals", json=journal_payload(publisher, publisher_id=str(uuid4()))
    )
    assert missing.status_code == 404
    assert client.delete(f"/api/v1/journal-platforms/{platform.id}").status_code == 204
    deleted_platform = client.post(
        "/api/v1/journals", json=journal_payload(publisher, platform)
    )
    assert deleted_platform.status_code == 404


def test_duplicate_publisher_name_returns_flat_conflict(client, admin_context, publisher):
    response = client.post("/api/v1/publishers", json={"name": " existing publisher "})
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"
    assert set(response.json()) == {"code", "message", "request_id", "details"}


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/publishers", {}),
        ("/api/v1/journal-platforms", {}),
        ("/api/v1/journals", {}),
    ],
)
def test_create_requires_mandatory_fields(client, admin_context, path, payload):
    assert client.post(path, json=payload).status_code == 422


def test_patch_rejects_empty_and_null_required_fields(
    client, admin_context, publisher, journal
):
    assert client.patch(f"/api/v1/publishers/{publisher.id}", json={}).status_code == 422
    assert client.patch(f"/api/v1/publishers/{publisher.id}", json={"name": None}).status_code == 422
    assert client.patch(f"/api/v1/journals/{journal.id}", json={"publisher_id": None}).status_code == 422
    assert client.patch(f"/api/v1/journals/{journal.id}", json={"requirements": None}).status_code == 422


@pytest.mark.parametrize(
    "path", ["/api/v1/publishers", "/api/v1/journal-platforms", "/api/v1/journals"]
)
def test_lists_reject_unsupported_sort_fields(client, admin_context, path):
    response = client.get(path, params={"sort": "created_by"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_journal_resources_require_authentication(client):
    assert client.get("/api/v1/journals").status_code == 401
    assert client.post("/api/v1/publishers", json={"name": "No Auth"}).status_code == 401
