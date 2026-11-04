from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.models import (
    Author,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    OperationLog,
)
from app.services.manuscripts import ManuscriptService
from app.services.permissions import Permission


def active_grant(grant_factory, *, user, author, permissions):
    now = datetime.now(UTC)
    return grant_factory(
        user=user,
        author=author,
        permissions=permissions,
        valid_from=now - timedelta(minutes=5),
        valid_to=now + timedelta(hours=1),
    )


def manuscript_payload(owner, *, authors=None, **overrides):
    payload = {
        "owner_author_id": str(owner.id),
        "title": "A study",
        "abstract": "Original abstract",
        "keywords": ["ai", "methods"],
        "article_type": "research",
        "language": "en",
        "funding_statement": "No external funding",
    }
    if authors is not None:
        payload["authors"] = authors
    payload.update(overrides)
    return payload


def author_input(author, position, *, corresponding=False):
    return {
        "author_id": str(author.id),
        "position": position,
        "is_corresponding": corresponding,
    }


@pytest.fixture
def owner(db_session):
    record = Author(
        display_name="Database Owner Name",
        alternate_names=[],
        orcid="0000-0002-1825-0097",
        phone_country_code="+00",
        phone_number="private-owner-phone",
        notes="owner private notes",
    )
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def coauthor(db_session):
    record = Author(
        display_name="Database Coauthor Name",
        alternate_names=[],
        phone_number="private-coauthor-phone",
        notes="coauthor private notes",
    )
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def owner_permissions(grant_factory, operator, owner):
    return active_grant(
        grant_factory,
        user=operator,
        author=owner,
        permissions=["manuscript:create", "manuscript:read", "manuscript:update"],
    )


@pytest.fixture
def coauthor_permission(grant_factory, operator, coauthor):
    return active_grant(
        grant_factory,
        user=operator,
        author=coauthor,
        permissions=["author:profile:read"],
    )


@pytest.fixture
def manuscript(
    client,
    db_session,
    operator_context,
    owner_permissions,
    coauthor_permission,
    owner,
    coauthor,
):
    response = client.post(
        "/api/v1/manuscripts",
        json=manuscript_payload(
            owner,
            authors=[
                author_input(owner, 1, corresponding=True),
                author_input(coauthor, 2),
            ],
        ),
    )
    assert response.status_code == 201
    record = db_session.get(Manuscript, response.json()["id"])
    db_session.commit()
    return record


@pytest.fixture
def write_only_operator_context(
    client,
    user_factory,
    auth_context_factory,
    grant_factory,
    owner,
    manuscript,
):
    user = user_factory("write-only-operator", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=user,
        author=owner,
        permissions=["manuscript:update"],
    )
    return auth_context_factory(user)


def test_create_builds_initial_version_and_minimal_authors(
    client,
    db_session,
    operator_context,
    owner_permissions,
    coauthor_permission,
    owner,
    coauthor,
):
    response = client.post(
        "/api/v1/manuscripts",
        json=manuscript_payload(
            owner,
            authors=[
                author_input(coauthor, 2),
                author_input(owner, 1, corresponding=True),
            ],
        ),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["current_version_id"]
    assert body["internal_number"]
    assert body["status"] == "draft"
    assert [item["position"] for item in body["authors"]] == [1, 2]
    assert body["authors"][1]["display_name"] == coauthor.display_name
    assert all(
        set(item) == {"author_id", "display_name", "position", "is_corresponding"}
        for item in body["authors"]
    )
    assert "email" not in body["authors"][1]
    assert "phone_number" not in body["authors"][1]

    version = db_session.get(ManuscriptVersion, body["current_version_id"])
    assert version.version_number == 1
    assert version.metadata_snapshot["title"] == "A study"
    assert version.metadata_snapshot["authors"] == body["authors"]
    serialized = str(version.metadata_snapshot)
    for forbidden in ("phone_number", "orcid", "address", "email"):
        assert forbidden not in serialized
    assert all("notes" not in author for author in version.metadata_snapshot["authors"])
    assert db_session.scalar(select(func.count()).select_from(ManuscriptAuthor)) == 2


def test_create_defaults_to_owner_as_first_corresponding_author(
    client, operator_context, owner_permissions, owner
):
    response = client.post("/api/v1/manuscripts", json=manuscript_payload(owner))
    assert response.status_code == 201
    assert response.json()["authors"] == [
        {
            "author_id": str(owner.id),
            "display_name": "Database Owner Name",
            "position": 1,
            "is_corresponding": True,
        }
    ]


def test_authorship_input_rejects_client_supplied_display_name(
    client, db_session, operator_context, owner_permissions, owner
):
    payload = manuscript_payload(
        owner,
        authors=[
            {
                **author_input(owner, 1, corresponding=True),
                "display_name": "Client Controlled Name",
            }
        ],
    )
    response = client.post("/api/v1/manuscripts", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == 0


def test_create_rejects_empty_authorship(
    client, operator_context, owner_permissions, owner
):
    response = client.post(
        "/api/v1/manuscripts", json=manuscript_payload(owner, authors=[])
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_create_requires_owner_in_authorship(
    client,
    operator_context,
    owner_permissions,
    coauthor_permission,
    owner,
    coauthor,
):
    response = client.post(
        "/api/v1/manuscripts",
        json=manuscript_payload(
            owner, authors=[author_input(coauthor, 1, corresponding=True)]
        ),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("case", ["duplicate_author", "gap", "duplicate_position"])
def test_create_rejects_nonunique_or_noncontiguous_authorship(
    client,
    operator_context,
    owner_permissions,
    coauthor_permission,
    owner,
    coauthor,
    case,
):
    entries = [author_input(owner, 1, corresponding=True)]
    if case == "duplicate_author":
        entries.append(author_input(owner, 2))
    elif case == "gap":
        entries.append(author_input(coauthor, 3))
    else:
        entries.append(author_input(coauthor, 1))
    response = client.post(
        "/api/v1/manuscripts", json=manuscript_payload(owner, authors=entries)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_create_requires_at_least_one_corresponding_author(
    client, operator_context, owner_permissions, owner
):
    response = client.post(
        "/api/v1/manuscripts",
        json=manuscript_payload(owner, authors=[author_input(owner, 1)]),
    )
    assert response.status_code == 422


def test_create_rolls_back_without_coauthor_profile_read(
    client,
    db_session,
    operator_context,
    owner_permissions,
    owner,
    coauthor,
):
    payload = manuscript_payload(
        owner,
        authors=[
            author_input(owner, 1, corresponding=True),
            author_input(coauthor, 2),
        ],
    )
    response = client.post("/api/v1/manuscripts", json=payload)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == 0
    assert db_session.scalar(select(func.count()).select_from(ManuscriptVersion)) == 0


def test_create_write_without_read_cannot_leak_response(
    client, db_session, operator_context, grant_factory, operator, owner
):
    active_grant(
        grant_factory,
        user=operator,
        author=owner,
        permissions=["manuscript:create"],
    )
    response = client.post("/api/v1/manuscripts", json=manuscript_payload(owner))
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert "title" not in response.json()
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == 0


def test_create_and_initial_version_roll_back_together_when_audit_fails(
    client,
    db_session,
    operator_context,
    owner_permissions,
    owner,
    monkeypatch,
):
    from app.services import manuscripts as service_module

    original_record = service_module.AuditService.record

    def fail_version_audit(self, **kwargs):
        if kwargs.get("action") == "manuscript.version.create":
            raise RuntimeError("forced version audit failure")
        return original_record(self, **kwargs)

    monkeypatch.setattr(service_module.AuditService, "record", fail_version_audit)
    with pytest.raises(RuntimeError, match="forced version audit failure"):
        client.post("/api/v1/manuscripts", json=manuscript_payload(owner))
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == 0
    assert db_session.scalar(select(func.count()).select_from(ManuscriptAuthor)) == 0
    assert db_session.scalar(select(func.count()).select_from(ManuscriptVersion)) == 0


def test_write_without_read_cannot_leak_response(
    client, write_only_operator_context, manuscript
):
    response = client.patch(
        f"/api/v1/manuscripts/{manuscript.id}", json={"title": "new"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert "title" not in response.json()


def test_get_and_list_return_only_accessible_manuscripts(
    client, db_session, manuscript, coauthor
):
    hidden = Manuscript(
        internal_number="MS-HIDDEN",
        owner_author_id=coauthor.id,
        title="Hidden title",
        abstract="Hidden abstract",
        keywords=[],
        article_type="research",
        language="en",
    )
    db_session.add(hidden)
    db_session.commit()

    detail = client.get(f"/api/v1/manuscripts/{manuscript.id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "A study"
    assert client.get(f"/api/v1/manuscripts/{hidden.id}").status_code == 404

    listed = client.get("/api/v1/manuscripts?page=1&page_size=20")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert [item["id"] for item in listed.json()["items"]] == [manuscript.id]


def test_patch_changes_working_metadata_without_rewriting_history(
    client, db_session, manuscript
):
    old_version_id = manuscript.current_version_id
    response = client.patch(
        f"/api/v1/manuscripts/{manuscript.id}",
        json={"title": "Changed title", "keywords": ["updated"], "notes": None},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Changed title"
    assert response.json()["current_version_id"] == old_version_id
    db_session.expire_all()
    version = db_session.get(ManuscriptVersion, old_version_id)
    assert version.metadata_snapshot["title"] == "A study"
    assert version.metadata_snapshot["keywords"] == ["ai", "methods"]
    log = db_session.scalar(
        select(OperationLog).where(OperationLog.action == "manuscript.update")
    )
    assert log.before_summary["title"] == "A study"
    assert log.after_summary == {"title": "Changed title", "keywords": ["updated"]}


def test_soft_delete_requires_update_but_not_read(
    client,
    db_session,
    manuscript,
    owner,
    user_factory,
    grant_factory,
    auth_context_factory,
):
    user = user_factory("delete-only-operator", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=user,
        author=owner,
        permissions=["manuscript:update"],
    )
    auth_context_factory(user)
    response = client.delete(f"/api/v1/manuscripts/{manuscript.id}")
    assert response.status_code == 204
    assert response.content == b""
    db_session.expire_all()
    deleted = db_session.get(Manuscript, manuscript.id)
    assert deleted.deleted_at is not None
    assert db_session.get(ManuscriptVersion, deleted.current_version_id) is not None
    assert client.get(f"/api/v1/manuscripts/{manuscript.id}").status_code == 404


def test_authorship_get_and_atomic_replacement_use_minimal_audits(
    client, db_session, manuscript, owner, coauthor, operator, grant_factory
):
    third = Author(
        display_name="Third Database Name",
        alternate_names=[],
        phone_number="private-third-phone",
        notes="third private notes",
    )
    db_session.add(third)
    db_session.commit()
    active_grant(
        grant_factory,
        user=operator,
        author=third,
        permissions=["author:profile:read"],
    )

    response = client.put(
        f"/api/v1/manuscripts/{manuscript.id}/authors",
        json={
            "authors": [
                author_input(owner, 2, corresponding=True),
                author_input(third, 1),
            ],
            "confirm_authorship_change": True,
        },
    )
    assert response.status_code == 200
    assert response.json() == [
        {
            "author_id": str(third.id),
            "display_name": "Third Database Name",
            "position": 1,
            "is_corresponding": False,
        },
        {
            "author_id": str(owner.id),
            "display_name": "Database Owner Name",
            "position": 2,
            "is_corresponding": True,
        },
    ]
    current = client.get(f"/api/v1/manuscripts/{manuscript.id}/authors")
    assert current.status_code == 200
    assert current.json() == response.json()
    db_session.expire_all()
    links = list(
        db_session.scalars(
            select(ManuscriptAuthor).where(
                ManuscriptAuthor.manuscript_id == manuscript.id
            )
        )
    )
    assert len(links) == 2
    assert {link.author_id for link in links} == {owner.id, third.id}

    log = db_session.scalar(
        select(OperationLog).where(OperationLog.action == "manuscript.authors.replace")
    )
    assert [item["author_id"] for item in log.before_summary["authors"]] == [
        owner.id,
        coauthor.id,
    ]
    assert [item["author_id"] for item in log.after_summary["authors"]] == [
        third.id,
        owner.id,
    ]
    for summary in (log.before_summary, log.after_summary):
        assert set(summary) == {"authors"}
        assert all(
            set(item) == {"author_id", "display_name", "position", "is_corresponding"}
            for item in summary["authors"]
        )
        assert "phone_number" not in str(summary)
        assert "notes" not in str(summary)


def test_existing_coauthor_can_be_removed_without_profile_read(
    client,
    manuscript,
    owner,
    user_factory,
    grant_factory,
    auth_context_factory,
):
    user = user_factory("reorder-operator", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=user,
        author=owner,
        permissions=["manuscript:read", "manuscript:update"],
    )
    auth_context_factory(user)
    response = client.put(
        f"/api/v1/manuscripts/{manuscript.id}/authors",
        json={
            "authors": [author_input(owner, 1, corresponding=True)],
            "confirm_authorship_change": True,
        },
    )
    assert response.status_code == 200
    assert [item["author_id"] for item in response.json()] == [owner.id]


def test_new_coauthor_requires_profile_read_and_failed_put_changes_nothing(
    client, db_session, manuscript, coauthor
):
    third = Author(display_name="Unapproved Third", alternate_names=[])
    db_session.add(third)
    db_session.commit()
    response = client.put(
        f"/api/v1/manuscripts/{manuscript.id}/authors",
        json={
            "authors": [
                {
                    "author_id": manuscript.owner_author_id,
                    "position": 1,
                    "is_corresponding": True,
                },
                author_input(third, 2),
            ],
            "confirm_authorship_change": True,
        },
    )
    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.scalar(
        select(func.count())
        .select_from(ManuscriptAuthor)
        .where(ManuscriptAuthor.manuscript_id == manuscript.id)
    ) == 2
    assert db_session.scalar(
        select(OperationLog).where(OperationLog.action == "manuscript.authors.replace")
    ) is None


def test_authorship_change_requires_explicit_confirmation(client, manuscript, owner):
    response = client.put(
        f"/api/v1/manuscripts/{manuscript.id}/authors",
        json={"authors": [author_input(owner, 1, corresponding=True)]},
    )
    assert response.status_code == 422


def test_version_creation_is_immutable_and_returns_current_safe_snapshot(
    client, db_session, manuscript, coauthor
):
    patched = client.patch(
        f"/api/v1/manuscripts/{manuscript.id}",
        json={"title": "Version two title", "abstract": "Version two abstract"},
    )
    assert patched.status_code == 200
    response = client.post(
        f"/api/v1/manuscripts/{manuscript.id}/versions",
        json={"label": "Revision", "change_note": "Updated metadata"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 2
    assert body["metadata_snapshot"]["title"] == "Version two title"
    assert body["metadata_snapshot"]["abstract"] == "Version two abstract"
    assert body["metadata_snapshot"]["authors"][1]["display_name"] == coauthor.display_name
    assert "phone_number" not in str(body)
    assert "orcid" not in str(body)
    assert "notes" not in str(body["metadata_snapshot"]["authors"])

    detail = client.get(
        f"/api/v1/manuscripts/{manuscript.id}/versions/{body['id']}"
    )
    assert detail.status_code == 200
    assert detail.json() == body
    page = client.get(f"/api/v1/manuscripts/{manuscript.id}/versions")
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert [item["version_number"] for item in page.json()["items"]] == [2, 1]
    assert client.get(f"/api/v1/manuscripts/{manuscript.id}").json()[
        "current_version_id"
    ] == body["id"]

    version_id = body["id"]
    snapshot = dict(body["metadata_snapshot"])
    assert client.patch(
        f"/api/v1/manuscripts/{manuscript.id}/versions/{version_id}",
        json={"metadata_snapshot": {}},
    ).status_code == 405
    assert client.delete(
        f"/api/v1/manuscripts/{manuscript.id}/versions/{version_id}"
    ).status_code == 405
    assert client.get(
        f"/api/v1/manuscripts/{manuscript.id}/versions/{version_id}"
    ).json()["metadata_snapshot"] == snapshot


def test_version_creation_requires_read_and_does_not_write_without_it(
    client, db_session, manuscript, write_only_operator_context
):
    response = client.post(
        f"/api/v1/manuscripts/{manuscript.id}/versions", json={"label": "Denied"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert "metadata_snapshot" not in response.json()
    assert db_session.scalar(
        select(func.count())
        .select_from(ManuscriptVersion)
        .where(ManuscriptVersion.manuscript_id == manuscript.id)
    ) == 1


def test_cross_manuscript_version_access_is_not_found(
    client, db_session, manuscript, owner
):
    other = Manuscript(
        internal_number="MS-OTHER",
        owner_author_id=owner.id,
        title="Other",
        abstract="Other",
        keywords=[],
        article_type="research",
        language="en",
    )
    db_session.add(other)
    db_session.flush()
    other_version = ManuscriptVersion(
        manuscript_id=other.id,
        version_number=1,
        metadata_snapshot={"title": "Other", "authors": []},
    )
    db_session.add(other_version)
    db_session.commit()
    response = client.get(
        f"/api/v1/manuscripts/{manuscript.id}/versions/{other_version.id}"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_archived_manuscript_rejects_metadata_and_version_changes(
    client, db_session, manuscript
):
    manuscript.status = "archived"
    db_session.commit()
    patched = client.patch(
        f"/api/v1/manuscripts/{manuscript.id}", json={"title": "Not allowed"}
    )
    versioned = client.post(
        f"/api/v1/manuscripts/{manuscript.id}/versions", json={}
    )
    assert patched.status_code == 409
    assert patched.json()["code"] == "INVALID_MANUSCRIPT_STATE"
    assert versioned.status_code == 409
    assert versioned.json()["code"] == "INVALID_MANUSCRIPT_STATE"


def test_file_service_interfaces_lock_and_validate_current_version(
    db_session, manuscript, operator
):
    service = ManuscriptService(db_session, operator, str(uuid4()))
    owned = service.get_owned_manuscript(manuscript.id, Permission.MANUSCRIPT_READ)
    assert owned.id == manuscript.id
    locked, version = service.lock_current_version(
        manuscript.id,
        manuscript.current_version_id,
        Permission.MANUSCRIPT_READ,
        Permission.MANUSCRIPT_UPDATE,
    )
    assert locked.id == manuscript.id
    assert version.id == manuscript.current_version_id
    with pytest.raises(AppError) as caught:
        service.lock_current_version(
            manuscript.id, str(uuid4()), Permission.MANUSCRIPT_READ
        )
    assert caught.value.status_code == 409
    assert caught.value.code == "INVALID_MANUSCRIPT_STATE"
