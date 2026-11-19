from app.schemas.common import ErrorResponse


def test_search_and_identification_routes(client, admin_context):
    publisher = client.post(
        "/api/v1/publishers",
        json={
            "name": "Elsevier",
            "website_url": "https://www.elsevier.com/",
            "aliases": ["RELX"],
        },
    )
    assert publisher.status_code == 201
    search = client.get("/api/v1/publishers/search?name=relx")
    assert search.status_code == 200
    assert search.json()["items"][0]["match_reasons"] == ["别名精确匹配"]
    identified = client.post(
        "/api/v1/journals/identify",
        json={
            "publisher_name": "Elsevier",
            "journal_name": "Journal One",
            "issn": "0378-5955",
        },
    )
    assert identified.status_code == 202, identified.text
    task = client.get(f"/api/v1/tasks/{identified.json()['task_id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "PENDING"


def test_confirm_identity_uses_candidate_timestamp(client, db_session, admin_context):
    from app.services.identification import JournalIdentificationService

    JournalIdentificationService(db_session, admin_context.user, "confirm-api").create_journal(
        publisher_name="Publisher", name="Candidate", aliases=[]
    )
    found = client.get("/api/v1/journals/search", params={"name": "Candidate"})
    assert found.status_code == 200
    candidate = found.json()["items"][0]
    confirmed = client.post(
        f"/api/v1/journals/{candidate['id']}/confirm-identity",
        json={
            "expected_updated_at": candidate["updated_at"],
            "confirmation_note": "confirmed",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["identity_status"] == "VERIFIED"
    assert confirmed.json()["verified_at"] is not None


def test_identification_mutations_require_admin_and_csrf(client, operator_context):
    response = client.post("/api/v1/journals/identify", json={"journal_name": "Denied"})
    assert response.status_code == 403


def test_identification_requires_valid_csrf(client, admin_context):
    response = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Denied"},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert response.status_code == 403


def test_options_validation_responses_match_standard_error_model(client, admin_context):
    responses = (
        client.get("/api/v1/publishers/options", params={"limit": 0}),
        client.get("/api/v1/journals/options", params={"publisher_id": "not-a-uuid"}),
    )
    for response in responses:
        assert response.status_code == 422
        error = ErrorResponse.model_validate(response.json())
        assert error.code == "VALIDATION_ERROR"
        assert error.details


def test_options_use_limited_minimal_queries_and_exclude_deleted(client, db_session, admin_context):
    from sqlalchemy import event

    publisher = client.post(
        "/api/v1/publishers", json={"name": "Elsevier", "website_url": None}
    )
    other = client.post("/api/v1/publishers", json={"name": "Springer"})
    assert publisher.status_code == 201 and other.status_code == 201
    publisher_id = publisher.json()["id"]
    journal = client.post(
        "/api/v1/journals",
        json={
            "publisher_id": publisher_id,
            "name": "Journal One",
            "issn": "0378-5955",
            "eissn": "2434-561X",
            "website_url": "https://journal.example",
            "subject_categories": [],
            "article_types": [],
            "requirements": [],
        },
    )
    deleted = client.post(
        "/api/v1/journals",
        json={
            "publisher_id": publisher_id,
            "name": "Journal Deleted",
            "subject_categories": [],
            "article_types": [],
            "requirements": [],
        },
    )
    assert journal.status_code == 201 and deleted.status_code == 201
    assert client.delete(f"/api/v1/journals/{deleted.json()['id']}").status_code == 204

    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", capture)
    try:
        publisher_options = client.get("/api/v1/publishers/options", params={"name": "Els"})
        journal_options = client.get(
            "/api/v1/journals/options", params={"publisher_id": publisher_id, "name": "Journal"}
        )
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", capture)

    assert publisher_options.status_code == 200
    assert publisher_options.json() == {
        "items": [{"id": publisher_id, "name": "Elsevier"}]
    }
    assert journal_options.status_code == 200
    assert journal_options.json()["items"] == [{
        "id": journal.json()["id"],
        "publisher_id": publisher_id,
        "name": "Journal One",
        "issn": "03785955",
        "eissn": "2434561X",
        "website_url": "https://journal.example",
    }]
    assert all(item["name"] != "Journal Deleted" for item in journal_options.json()["items"])
    assert not any("COUNT(" in statement.upper() for statement in statements)
    assert any("FROM publishers" in statement and "LIMIT" in statement for statement in statements)
