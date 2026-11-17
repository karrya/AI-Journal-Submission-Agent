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
    assert identified.status_code == 200, identified.text
    task = client.get(f"/api/v1/tasks/{identified.json()['task_id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "SUCCEEDED"


def test_confirm_identity_uses_candidate_timestamp(client, admin_context):
    identified = client.post(
        "/api/v1/journals/identify",
        json={"publisher_name": "Publisher", "journal_name": "Candidate"},
    )
    assert identified.status_code == 200, identified.text
    candidate = identified.json()["candidates"][0]
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
