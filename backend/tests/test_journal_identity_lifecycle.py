def payload(publisher, name, issn="0378-5955", eissn="2434-561X"):
    return {
        "publisher_id": publisher.id,
        "name": name,
        "issn": issn,
        "eissn": eissn,
        "status": "active",
        "subject_categories": [],
        "article_types": [],
        "requirements": [],
    }


def test_deleted_publisher_name_can_be_reused(client, db_session, admin_context):
    original = client.post("/api/v1/publishers", json={"name": "Lifecycle Publisher"})
    assert original.status_code == 201, original.text
    assert client.delete(f"/api/v1/publishers/{original.json()['id']}").status_code == 204

    reused = client.post("/api/v1/publishers", json={"name": "Lifecycle Publisher"})
    assert reused.status_code == 201, reused.text
    assert reused.json()["id"] != original.json()["id"]
    duplicate = client.post("/api/v1/publishers", json={"name": "Lifecycle Publisher"})
    assert duplicate.status_code == 409


def test_deleted_journal_identifiers_can_be_reused_without_identity_conflict(
    client, db_session, admin_context
):
    from app.models import Publisher

    publisher = Publisher(name="Lifecycle Publisher", normalized_name="lifecycle publisher")
    db_session.add(publisher)
    db_session.commit()
    old = client.post("/api/v1/journals", json=payload(publisher, "Deleted Journal"))
    assert old.status_code == 201, old.text
    assert client.delete(f"/api/v1/journals/{old.json()['id']}").status_code == 204

    reused = client.post("/api/v1/journals", json=payload(publisher, "Reused Journal"))
    assert reused.status_code == 201, reused.text
    assert reused.json()["id"] != old.json()["id"]

    search = client.get("/api/v1/journals/search", params={"issn": "0378-5955"})
    assert search.status_code == 200, search.text
    assert [item["id"] for item in search.json()["items"]] == [reused.json()["id"]]
    assert all(item["id"] != old.json()["id"] for item in search.json()["items"])

    candidates = client.get(
        "/api/v1/journals/search", params={"name": "Reused Journal"}
    )
    candidate = candidates.json()["items"][0]
    confirmed = client.post(
        f"/api/v1/journals/{candidate['id']}/confirm-identity",
        json={"expected_updated_at": candidate["updated_at"]},
    )
    assert confirmed.status_code == 200, confirmed.text

    duplicate = client.post("/api/v1/journals", json=payload(publisher, "Active Duplicate"))
    assert duplicate.status_code == 409
