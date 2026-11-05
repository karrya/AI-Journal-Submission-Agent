"""ROLE-01, AUTHZ-01, AUTHZ-02, AUTHZ-03, ISO-01, ISO-02, ISO-03,
ISO-04, ISO-05, and ISO-06 authorization-matrix rows.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import (
    Author,
    AuthorAuthorization,
    FileFamily,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptFile,
    ManuscriptVersion,
    OperationLog,
)
from test_files_api import PDF, post_pdf
from test_manuscripts_api import author_input, manuscript_payload
from test_security_matrix import ERROR_FIELDS, assert_error

MINIMAL_AUTHOR_FIELDS = {"author_id", "display_name", "position", "is_corresponding"}
SENSITIVE_VALUES = (
    "private-owner@example.invalid",
    "private-coauthor@example.invalid",
    "private-other@example.invalid",
    "private-owner-phone",
    "private-coauthor-phone",
    "private-other-phone",
    "private-owner-notes",
    "private-coauthor-notes",
    "private-other-notes",
)


def grant_now(grant_factory, *, user, author, permissions, **overrides):
    now = datetime.now(UTC)
    return grant_factory(
        user=user,
        author=author,
        permissions=permissions,
        valid_from=now - timedelta(minutes=5),
        valid_to=now + timedelta(hours=1),
        **overrides,
    )


def add_manuscript_graph(db_session, test_storage_root, owner, coauthor, marker, user):
    manuscript = Manuscript(
        internal_number=f"MS-MATRIX-{marker}",
        owner_author_id=owner.id,
        title=f"Matrix manuscript {marker}",
        abstract="Matrix abstract",
        keywords=["matrix"],
        article_type="research",
        language="en",
    )
    db_session.add(manuscript)
    db_session.flush()
    links = [
        ManuscriptAuthor(
            manuscript_id=manuscript.id,
            author_id=owner.id,
            position=1,
            is_corresponding=True,
        ),
        ManuscriptAuthor(
            manuscript_id=manuscript.id,
            author_id=coauthor.id,
            position=2,
            is_corresponding=False,
        ),
    ]
    minimal_authors = [
        {
            "author_id": link.author_id,
            "display_name": owner.display_name if link.position == 1 else coauthor.display_name,
            "position": link.position,
            "is_corresponding": link.is_corresponding,
        }
        for link in links
    ]
    version = ManuscriptVersion(
        manuscript_id=manuscript.id,
        version_number=1,
        metadata_snapshot={
            "owner_author_id": owner.id,
            "title": manuscript.title,
            "abstract": manuscript.abstract,
            "keywords": manuscript.keywords,
            "article_type": manuscript.article_type,
            "language": manuscript.language,
            "authors": minimal_authors,
        },
        created_by=user.id,
    )
    db_session.add_all([*links, version])
    db_session.flush()
    manuscript.current_version_id = version.id
    family = FileFamily(
        author_id=owner.id,
        manuscript_id=manuscript.id,
        file_type="main_manuscript",
        display_name="Matrix main",
    )
    db_session.add(family)
    db_session.flush()
    record = ManuscriptFile(
        file_family_id=family.id,
        manuscript_id=manuscript.id,
        manuscript_version_id=version.id,
        file_version=1,
        original_filename="matrix.pdf",
        stored_filename="matrix.pdf",
        storage_path=f"matrix/{marker}/matrix.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=len(PDF),
        sha256=hashlib.sha256(PDF).hexdigest(),
        uploaded_by=user.id,
    )
    db_session.add(record)
    db_session.flush()
    formal = test_storage_root / record.storage_path
    formal.parent.mkdir(parents=True, exist_ok=True)
    formal.write_bytes(PDF)
    return SimpleNamespace(
        manuscript=manuscript,
        version=version,
        family=family,
        file=record,
        authors=minimal_authors,
    )


@pytest.fixture
def isolation_workspace(client, db_session, test_storage_root, operator, operator_context, grant_factory):
    owner = Author(
        display_name="Matrix Owner",
        alternate_names=[],
        orcid="0000-0002-1825-0097",
        phone_number="private-owner-phone",
        notes="private-owner-notes",
    )
    coauthor = Author(
        display_name="Matrix Coauthor",
        alternate_names=[],
        phone_number="private-coauthor-phone",
        notes="private-coauthor-notes",
    )
    other = Author(
        display_name="Matrix Other",
        alternate_names=[],
        phone_number="private-other-phone",
        notes="private-other-notes",
    )
    db_session.add_all([owner, coauthor, other])
    db_session.flush()
    from app.models import AuthorEmail

    db_session.add_all(
        [
            AuthorEmail(
                author_id=owner.id,
                email="private-owner@example.invalid",
                normalized_email="private-owner@example.invalid",
            ),
            AuthorEmail(
                author_id=coauthor.id,
                email="private-coauthor@example.invalid",
                normalized_email="private-coauthor@example.invalid",
            ),
            AuthorEmail(
                author_id=other.id,
                email="private-other@example.invalid",
                normalized_email="private-other@example.invalid",
            ),
        ]
    )
    grant_now(
        grant_factory,
        user=operator,
        author=owner,
        permissions=[
            "author:profile:read",
            "author:address:read",
            "manuscript:create",
            "manuscript:read",
            "manuscript:update",
            "manuscript:file:manage",
        ],
    )
    coauthor_grant = grant_now(
        grant_factory,
        user=operator,
        author=coauthor,
        permissions=["author:profile:read"],
    )
    db_session.commit()

    created = client.post(
        "/api/v1/manuscripts",
        json=manuscript_payload(
            owner,
            authors=[
                author_input(owner, 1, corresponding=True),
                author_input(coauthor, 2),
            ],
        ),
    )
    assert created.status_code == 201, created.text
    db_session.expire_all()
    manuscript = db_session.get(Manuscript, created.json()["id"])
    assert manuscript is not None
    version = db_session.get(ManuscriptVersion, manuscript.current_version_id)
    assert version is not None
    uploaded = post_pdf(client, manuscript)
    assert uploaded.status_code == 201, uploaded.text
    db_session.commit()
    record = db_session.get(ManuscriptFile, uploaded.json()["id"])
    assert record is not None
    family = db_session.get(FileFamily, record.file_family_id)
    assert family is not None
    own = SimpleNamespace(
        manuscript=manuscript,
        version=version,
        family=family,
        file=record,
        authors=created.json()["authors"],
    )
    # Snapshot creation used the real API; reads must remain owner-only.
    db_session.delete(coauthor_grant)
    db_session.flush()
    hidden = add_manuscript_graph(db_session, test_storage_root, other, coauthor, "HIDDEN", operator)
    db_session.commit()
    return SimpleNamespace(owner=owner, coauthor=coauthor, other=other, own=own, hidden=hidden)


def assert_no_sensitive_values(response):
    serialized = response.text
    for value in SENSITIVE_VALUES:
        assert value not in serialized
    for key in ("email", "phone_number", "phone_country_code", "orcid", "storage_path", "stored_filename"):
        assert key not in serialized


def test_role_01_system_admin_precedes_auditor_without_grants(
    client, user_factory, auth_context_factory, isolation_workspace
):
    user = user_factory("matrix-admin-auditor", roles=("system_admin", "auditor"))
    auth_context_factory(user)
    response = client.get(f"/api/v1/authors/{isolation_workspace.other.id}")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Matrix Other"
    assert client.get("/api/v1/audit-logs").status_code == 200


def test_role_01_non_admin_capabilities_are_united_but_grants_still_apply(
    client,
    user_factory,
    auth_context_factory,
    grant_factory,
    isolation_workspace,
):
    user = user_factory("matrix-operator-auditor", roles=("submission_operator", "auditor"))
    grant_now(
        grant_factory,
        user=user,
        author=isolation_workspace.owner,
        permissions=["manuscript:read", "manuscript:update"],
    )
    auth_context_factory(user)
    assert client.get("/api/v1/audit-logs").status_code == 200
    updated = client.patch(
        f"/api/v1/manuscripts/{isolation_workspace.own.manuscript.id}",
        json={"title": "Mixed role union update"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Mixed role union update"
    assert_error(
        client.get(f"/api/v1/manuscripts/{isolation_workspace.hidden.manuscript.id}"),
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_role_01_reviewer_alone_remains_read_only_even_with_write_grant(
    client,
    db_session,
    reviewer,
    auth_context_factory,
    grant_factory,
    isolation_workspace,
):
    grant_now(
        grant_factory,
        user=reviewer,
        author=isolation_workspace.owner,
        permissions=["manuscript:read", "manuscript:update"],
    )
    auth_context_factory(reviewer)
    original_title = isolation_workspace.own.manuscript.title
    response = client.patch(
        f"/api/v1/manuscripts/{isolation_workspace.own.manuscript.id}",
        json={"title": "Reviewer must not write"},
    )
    assert_error(response, 403, "PERMISSION_DENIED")
    assert "title" not in response.json()
    db_session.expire_all()
    assert db_session.get(Manuscript, isolation_workspace.own.manuscript.id).title == original_title


@pytest.mark.parametrize("resource", ["author", "manuscript"])
def test_authz_01_unauthorized_and_missing_uuids_are_indistinguishable(
    client, isolation_workspace, resource
):
    existing_id = (
        isolation_workspace.other.id
        if resource == "author"
        else isolation_workspace.hidden.manuscript.id
    )
    prefix = "authors" if resource == "author" else "manuscripts"
    existing = client.get(f"/api/v1/{prefix}/{existing_id}")
    missing = client.get(f"/api/v1/{prefix}/{uuid4()}")
    existing_body = assert_error(existing, 404, "RESOURCE_NOT_FOUND")
    missing_body = assert_error(missing, 404, "RESOURCE_NOT_FOUND")
    existing_body.pop("request_id")
    missing_body.pop("request_id")
    assert existing_body == missing_body


@pytest.mark.parametrize("state", ["not_yet_active", "expired", "revoked"])
def test_authz_02_inactive_grant_returns_authorization_expired(
    client,
    user_factory,
    auth_context_factory,
    grant_factory,
    isolation_workspace,
    state,
):
    user = user_factory(f"matrix-{state}", roles=("submission_operator",))
    now = datetime.now(UTC)
    dates = {
        "not_yet_active": (now + timedelta(hours=1), now + timedelta(hours=2), None),
        "expired": (now - timedelta(hours=2), now - timedelta(hours=1), None),
        "revoked": (now - timedelta(hours=1), now + timedelta(hours=1), now),
    }
    valid_from, valid_to, revoked_at = dates[state]
    grant_factory(
        user=user,
        author=isolation_workspace.owner,
        permission="author:profile:read",
        valid_from=valid_from,
        valid_to=valid_to,
        revoked_at=revoked_at,
    )
    auth_context_factory(user)
    response = client.get(f"/api/v1/authors/{isolation_workspace.owner.id}")
    body = assert_error(response, 403, "AUTHORIZATION_EXPIRED")
    assert "display_name" not in body and "phone_number" not in body


def test_authz_03_read_only_mutation_is_denied_without_data_or_sensitive_audit(
    client,
    db_session,
    user_factory,
    auth_context_factory,
    grant_factory,
    isolation_workspace,
):
    user = user_factory("matrix-read-only", roles=("submission_operator",))
    grant_now(
        grant_factory,
        user=user,
        author=isolation_workspace.owner,
        permissions=["manuscript:read"],
    )
    auth_context_factory(user)
    original_title = isolation_workspace.own.manuscript.title
    response = client.patch(
        f"/api/v1/manuscripts/{isolation_workspace.own.manuscript.id}",
        json={"title": "Denied sensitive replacement"},
    )
    assert_error(response, 403, "PERMISSION_DENIED")
    assert "title" not in response.json()
    db_session.expire_all()
    assert db_session.get(Manuscript, isolation_workspace.own.manuscript.id).title == original_title
    for log in db_session.scalars(select(OperationLog)):
        serialized = json.dumps([log.before_summary, log.after_summary, log.error_message])
        assert "Denied sensitive replacement" not in serialized
        assert all(value not in serialized for value in SENSITIVE_VALUES)


def test_iso_01_manuscript_returns_minimal_coauthor_attribution_only(
    client, isolation_workspace
):
    response = client.get(f"/api/v1/manuscripts/{isolation_workspace.own.manuscript.id}")
    assert response.status_code == 200, response.text
    assert response.json()["authors"] == isolation_workspace.own.authors
    assert all(set(item) == MINIMAL_AUTHOR_FIELDS for item in response.json()["authors"])
    assert_no_sensitive_values(response)


def test_iso_02_snapshot_file_list_and_dashboard_have_no_coauthor_secrets(
    client, db_session, isolation_workspace
):
    own = isolation_workspace.own
    assert db_session.scalar(
        select(func.count())
        .select_from(AuthorAuthorization)
        .where(AuthorAuthorization.author_id == isolation_workspace.coauthor.id)
    ) == 0
    responses = [
        client.get(
            f"/api/v1/manuscripts/{own.manuscript.id}/versions/{own.version.id}"
        ),
        client.get(f"/api/v1/manuscripts/{own.manuscript.id}/versions/{own.version.id}/files"),
        client.get("/api/v1/dashboard/summary"),
    ]
    assert [response.status_code for response in responses] == [200, 200, 200]
    snapshot_authors = responses[0].json()["metadata_snapshot"]["authors"]
    assert all(set(item) == MINIMAL_AUTHOR_FIELDS for item in snapshot_authors)
    assert set(responses[1].json()["items"][0]).isdisjoint(
        {"storage_path", "stored_filename", "email", "phone_number", "orcid"}
    )
    assert set(responses[2].json()) == {
        "author_count",
        "manuscript_count",
        "current_version_file_count",
        "expiring_authorization_count",
        "recent_operations",
    }
    for response in responses:
        assert_no_sensitive_values(response)


def test_iso_03_substituting_every_resource_family_never_crosses_author_boundary(
    client, db_session, isolation_workspace
):
    own = isolation_workspace.own
    hidden = isolation_workspace.hidden
    before_count = db_session.scalar(select(func.count()).select_from(ManuscriptFile))
    responses = [
        client.get(f"/api/v1/authors/{isolation_workspace.other.id}"),
        client.get(f"/api/v1/manuscripts/{hidden.manuscript.id}"),
        client.get(f"/api/v1/manuscripts/{own.manuscript.id}/versions/{hidden.version.id}"),
        client.get(f"/api/v1/files/{hidden.file.id}"),
        client.get(f"/api/v1/files/{hidden.file.id}/download"),
        client.post(
            f"/api/v1/manuscripts/{own.manuscript.id}/versions/{own.version.id}/files",
            files={"file": ("matrix.pdf", PDF, "application/pdf")},
            data={"file_family_id": hidden.family.id},
        ),
    ]
    for response in responses:
        body = assert_error(response, 404, "RESOURCE_NOT_FOUND")
        assert set(body) == ERROR_FIELDS
        assert_no_sensitive_values(response)
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == before_count


def test_iso_04_unauthorized_new_coauthor_is_not_enumerable_or_linked(
    client, db_session, isolation_workspace
):
    before = db_session.scalar(select(func.count()).select_from(Manuscript))

    def create_with(candidate_id):
        return client.post(
            "/api/v1/manuscripts",
            json=manuscript_payload(
                isolation_workspace.owner,
                authors=[
                    author_input(isolation_workspace.owner, 1, corresponding=True),
                    {"author_id": str(candidate_id), "position": 2, "is_corresponding": False},
                ],
            ),
        )

    real = create_with(isolation_workspace.other.id)
    missing = create_with(uuid4())
    real_body = assert_error(real, 404, "RESOURCE_NOT_FOUND")
    missing_body = assert_error(missing, 404, "RESOURCE_NOT_FOUND")
    real_body.pop("request_id")
    missing_body.pop("request_id")
    assert real_body == missing_body
    assert_no_sensitive_values(real)
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == before
    assert db_session.scalar(
        select(func.count())
        .select_from(ManuscriptAuthor)
        .where(ManuscriptAuthor.author_id == isolation_workspace.other.id)
    ) == 1


def test_iso_05_write_only_grants_cannot_read_through_write_responses(
    client,
    db_session,
    user_factory,
    auth_context_factory,
    grant_factory,
    isolation_workspace,
):
    user = user_factory("matrix-write-only", roles=("submission_operator",))
    grant_now(
        grant_factory,
        user=user,
        author=isolation_workspace.owner,
        permissions=["manuscript:create", "manuscript:update"],
    )
    auth_context_factory(user)
    original_title = isolation_workspace.own.manuscript.title
    before = db_session.scalar(select(func.count()).select_from(Manuscript))
    created = client.post(
        "/api/v1/manuscripts", json=manuscript_payload(isolation_workspace.owner)
    )
    updated = client.patch(
        f"/api/v1/manuscripts/{isolation_workspace.own.manuscript.id}",
        json={"title": "Write-only must not leak"},
    )
    for response in (created, updated):
        body = assert_error(response, 403, "PERMISSION_DENIED")
        assert "title" not in body and "authors" not in body and "current_version_id" not in body
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == before
    db_session.expire_all()
    assert db_session.get(Manuscript, isolation_workspace.own.manuscript.id).title == original_title


def test_iso_06_global_institutions_never_expose_detailed_address_to_non_admin(
    client, institution, isolation_workspace
):
    listing = client.get("/api/v1/institutions")
    detail = client.get(f"/api/v1/institutions/{institution.id}")
    assert listing.status_code == detail.status_code == 200
    summary = listing.json()["items"][0]
    summary_fields = {"id", "name", "institution_type", "website_url", "country_code", "city"}
    assert set(summary) == summary_fields
    assert detail.json() == {key: value for key, value in summary.items() if value is not None}
    for response in (listing, detail):
        for forbidden in ("address_line1", "address_line2", "region", "postal_code", "1 Test Road", "123456"):
            assert forbidden not in response.text
