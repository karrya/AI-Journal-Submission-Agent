import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    Author,
    AuthorEmail,
    AuthorInstitution,
    Institution,
    OperationLog,
)


def address(local, domain="example.org"):
    return local + "@" + domain


def create_author(client, **overrides):
    payload = {
        "display_name": "API Test Author",
        "confirm_identity_change": True,
    }
    payload.update(overrides)
    return client.post("/api/v1/authors", json=payload)


def active_grant(grant_factory, *, user, author, permissions):
    now = datetime.now(UTC)
    return grant_factory(
        user=user,
        author=author,
        permissions=permissions,
        valid_from=now - timedelta(minutes=5),
        valid_to=now + timedelta(hours=1),
    )


def operation_logs(db_session, *, action=None, category=None):
    db_session.commit()
    db_session.expire_all()
    statement = select(OperationLog)
    if action is not None:
        statement = statement.where(OperationLog.action == action)
    if category is not None:
        statement = statement.where(OperationLog.category == category)
    return list(db_session.scalars(statement))


def test_orcid_and_name_are_normalized(client, admin_context):
    response = client.post(
        "/api/v1/authors",
        json={
            "display_name": "  张三  ",
            "orcid": "https://orcid.org/0000-0002-1825-0097",
            "confirm_identity_change": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["display_name"] == "张三"
    assert response.json()["orcid"] == "0000-0002-1825-0097"


def test_email_confirmation_is_not_implicit(client, admin_context, author):
    response = client.post(
        f"/api/v1/authors/{author.id}/emails",
        json={"email": address("Test", "Example.org")},
    )
    assert response.status_code == 422


def test_institution_summary_never_exposes_address(
    client, operator_context, institution
):
    response = client.get(f"/api/v1/institutions/{institution.id}")
    assert response.status_code == 200
    assert "address_line1" not in response.json()
    assert "postal_code" not in response.json()


def test_display_names_use_nfc_and_comparison_fields_are_normalized(
    client, admin_context, db_session
):
    response = create_author(
        client,
        display_name="  Café  ",
        alternate_names=[{"display_name": "  José  "}],
    )
    assert response.status_code == 201
    assert response.json()["display_name"] == unicodedata.normalize("NFC", "Café")
    assert response.json()["alternate_names"][0]["display_name"] == "José"

    email = client.post(
        f"/api/v1/authors/{response.json()['id']}/emails",
        json={
            "email": address("Test", "Example.org"),
            "confirm_email_binding": True,
        },
    )
    assert email.status_code == 201
    assert email.json()["normalized_email"] == address("test")


@pytest.mark.parametrize("confirmation", [None, False])
def test_author_identity_confirmation_is_literal_and_required(
    client, admin_context, confirmation
):
    payload = {"display_name": "Unconfirmed Author"}
    if confirmation is not None:
        payload["confirm_identity_change"] = confirmation
    assert client.post("/api/v1/authors", json=payload).status_code == 422


@pytest.mark.parametrize(
    "orcid",
    ["0000-0002-1825-0098", "0000-0002-1825-009", "not-an-orcid"],
)
def test_orcid_check_digits_and_format_are_enforced(client, admin_context, orcid):
    response = create_author(client, orcid=orcid)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_author_list_is_isolated_and_phone_access_is_audited(
    client,
    db_session,
    author,
    user_factory,
    auth_context_factory,
    grant_factory,
):
    other = Author(
        display_name="Hidden Author",
        alternate_names=[],
        phone_number="123456",
    )
    author.phone_country_code = "+86"
    author.phone_number = "987654"
    db_session.add(other)
    db_session.commit()
    operator = user_factory("list-operator", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:read", "author:phone:read"],
    )
    auth_context_factory(operator)

    response = client.get("/api/v1/authors?page=1&page_size=20")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == author.id
    assert response.json()["items"][0]["phone_number"] == "987654"

    logs = operation_logs(db_session, action="author.phone.read")
    assert len(logs) == 1
    assert logs[0].author_id == author.id
    assert logs[0].category == "sensitive_access"
    assert logs[0].before_summary is None
    assert logs[0].after_summary is None


def test_phone_is_omitted_without_permission_and_not_audited(
    client, db_session, operator_context, operator, author, grant_factory
):
    author.phone_number = "123456"
    db_session.commit()
    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:read"],
    )
    response = client.get(f"/api/v1/authors/{author.id}")
    assert response.status_code == 200
    assert "phone_number" not in response.json()
    assert "phone_country_code" not in response.json()
    assert operation_logs(db_session, action="author.phone.read") == []


def test_author_patch_requires_read_as_well_as_update(
    client, operator_context, operator, author, grant_factory
):
    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:update"],
    )
    response = client.patch(
        f"/api/v1/authors/{author.id}",
        json={"display_name": "Changed", "confirm_identity_change": True},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"

    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:read"],
    )
    response = client.patch(
        f"/api/v1/authors/{author.id}",
        json={"display_name": "Changed", "confirm_identity_change": True},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Changed"


def test_expired_grant_and_cross_author_access_follow_error_contract(
    client,
    operator_context,
    operator,
    author,
    grant_factory,
    frozen_now,
):
    active = client.get(f"/api/v1/authors/{uuid4()}")
    assert active.status_code == 404
    assert active.json()["code"] == "RESOURCE_NOT_FOUND"

    grant_factory(
        user=operator,
        author=author,
        permission="author:profile:read",
        valid_from=frozen_now - timedelta(hours=2),
        valid_to=frozen_now - timedelta(hours=1),
    )
    expired = client.get(f"/api/v1/authors/{author.id}")
    assert expired.status_code == 403
    assert expired.json()["code"] == "AUTHORIZATION_EXPIRED"


def test_admin_can_soft_delete_author(client, admin_context, author, db_session):
    assert client.delete(f"/api/v1/authors/{author.id}").status_code == 204
    db_session.expire_all()
    assert db_session.get(Author, author.id).deleted_at is not None
    assert client.get(f"/api/v1/authors/{author.id}").status_code == 404


def test_duplicate_normalized_email_returns_flat_conflict(
    client, admin_context, author
):
    first = client.post(
        f"/api/v1/authors/{author.id}/emails",
        json={"email": address("Test", "Example.org"), "confirm_email_binding": True},
    )
    assert first.status_code == 201
    duplicate = client.post(
        f"/api/v1/authors/{author.id}/emails",
        json={"email": address("test"), "confirm_email_binding": True},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONFLICT"
    assert set(duplicate.json()) == {"code", "message", "request_id", "details"}


def test_generated_column_allows_only_one_primary_email(
    client, admin_context, author, db_session
):
    for local in ("first", "second"):
        response = client.post(
            f"/api/v1/authors/{author.id}/emails",
            json={
                "email": address(local),
                "is_primary": True,
                "confirm_email_binding": True,
            },
        )
    assert response.status_code == 409
    db_session.expire_all()
    emails = list(db_session.scalars(select(AuthorEmail)))
    assert len(emails) == 1
    assert emails[0].is_primary is True


def test_email_writes_require_update_and_email_read(
    client, operator_context, operator, author, grant_factory
):
    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:update"],
    )
    payload = {"email": address("test"), "confirm_email_binding": True}
    denied = client.post(f"/api/v1/authors/{author.id}/emails", json=payload)
    assert denied.status_code == 403

    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:email:read"],
    )
    created = client.post(f"/api/v1/authors/{author.id}/emails", json=payload)
    assert created.status_code == 201


def test_email_update_confirmation_status_rules_and_cross_author_isolation(
    client,
    db_session,
    operator_context,
    operator,
    author,
    grant_factory,
):
    other = Author(display_name="Other", alternate_names=[])
    email = AuthorEmail(
        author_id=author.id,
        email=address("old"),
        normalized_email=address("old"),
    )
    db_session.add_all([other, email])
    db_session.commit()
    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:update", "author:email:read"],
    )
    active_grant(
        grant_factory,
        user=operator,
        author=other,
        permissions=["author:profile:update", "author:email:read"],
    )

    base = f"/api/v1/authors/{author.id}/emails/{email.id}"
    assert client.patch(base, json={"email": address("new")}).status_code == 422
    changed = client.patch(
        base,
        json={"email": address("new"), "confirm_email_binding": True},
    )
    assert changed.status_code == 200
    assert changed.json()["normalized_email"] == address("new")
    assert (
        client.patch(base, json={"verification_status": "verified"}).status_code == 403
    )
    cross_author = client.patch(
        f"/api/v1/authors/{other.id}/emails/{email.id}",
        json={"purpose": "backup"},
    )
    assert cross_author.status_code == 404


def test_email_delete_requires_body_confirmation_and_soft_deletes(
    client, admin_context, author, db_session
):
    created = client.post(
        f"/api/v1/authors/{author.id}/emails",
        json={"email": address("delete"), "confirm_email_binding": True},
    )
    email_id = created.json()["id"]
    path = f"/api/v1/authors/{author.id}/emails/{email_id}"
    assert client.request("DELETE", path, json={}).status_code == 422
    deleted = client.request("DELETE", path, json={"confirm_email_binding": True})
    assert deleted.status_code == 204
    db_session.expire_all()
    assert db_session.get(AuthorEmail, email_id).deleted_at is not None


def test_email_list_audits_once_per_author_without_values(
    client, admin_context, author, db_session
):
    for local in ("one", "two"):
        assert (
            client.post(
                f"/api/v1/authors/{author.id}/emails",
                json={"email": address(local), "confirm_email_binding": True},
            ).status_code
            == 201
        )
    before = len(operation_logs(db_session, action="author.email.read"))
    response = client.get(f"/api/v1/authors/{author.id}/emails")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 2
    all_logs = operation_logs(db_session)
    assert response.headers["x-request-id"] in {log.request_id for log in all_logs}, [
        (log.action, log.request_id) for log in all_logs
    ]
    logs = operation_logs(db_session, action="author.email.read")
    assert len(logs) == before + 1
    assert logs[-1].author_id == author.id
    assert logs[-1].before_summary is None
    assert logs[-1].after_summary is None


def test_sensitive_read_fails_when_audit_cannot_be_written(
    client, admin_context, author, monkeypatch
):
    created = client.post(
        f"/api/v1/authors/{author.id}/emails",
        json={"email": address("audit"), "confirm_email_binding": True},
    )
    assert created.status_code == 201
    from app.services.audit import AuditService

    def fail_audit(self, **kwargs):
        if kwargs.get("category") == "sensitive_access":
            raise RuntimeError("forced sensitive audit failure")

    monkeypatch.setattr(AuditService, "record", fail_audit)
    with pytest.raises(RuntimeError, match="forced sensitive audit failure"):
        client.get(f"/api/v1/authors/{author.id}/emails")


def test_institution_admin_crud_and_non_admin_list_summary(
    client, db_session, admin, auth_context_factory, operator
):
    auth_context_factory(admin)
    created = client.post(
        "/api/v1/institutions",
        json={
            "name": "  New Institute  ",
            "address_line1": "Secret Address",
            "postal_code": "000000",
            "country_code": "CN",
        },
    )
    assert created.status_code == 201
    institution_id = created.json()["id"]
    assert created.json()["address_line1"] == "Secret Address"
    patched = client.patch(
        f"/api/v1/institutions/{institution_id}", json={"city": "New City"}
    )
    assert patched.status_code == 200

    auth_context_factory(operator)
    detail = client.get(f"/api/v1/institutions/{institution_id}")
    listed = client.get("/api/v1/institutions")
    assert detail.status_code == listed.status_code == 200
    assert "address_line1" not in detail.json()
    assert "postal_code" not in listed.json()["items"][0]
    assert client.delete(f"/api/v1/institutions/{institution_id}").status_code == 403

    auth_context_factory(admin)
    assert client.delete(f"/api/v1/institutions/{institution_id}").status_code == 204
    db_session.expire_all()
    assert db_session.get(Institution, institution_id).deleted_at is not None


def test_institution_link_permissions_address_filtering_and_audit(
    client,
    db_session,
    operator_context,
    operator,
    author,
    institution,
    grant_factory,
):
    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:update"],
    )
    payload = {"institution_id": institution.id, "department": "Research"}
    path = f"/api/v1/authors/{author.id}/institutions"
    assert client.post(path, json=payload).status_code == 403

    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:profile:read"],
    )
    created = client.post(path, json=payload)
    assert created.status_code == 201
    assert created.json()["institution_name"] == institution.name
    assert "address_line1" not in created.json()
    link_id = created.json()["id"]
    second = client.post(path, json={"institution_id": institution.id})
    assert second.status_code == 201

    active_grant(
        grant_factory,
        user=operator,
        author=author,
        permissions=["author:address:read"],
    )
    detailed = client.get(path)
    assert detailed.status_code == 200
    assert detailed.json()["items"][0]["address_line1"] == institution.address_line1
    logs = operation_logs(db_session, action="author.address.read")
    assert len(logs) == 1
    assert logs[0].author_id == author.id
    assert logs[0].after_summary is None

    patched = client.patch(f"{path}/{link_id}", json={"position_title": "Professor"})
    assert patched.status_code == 200
    assert client.delete(f"{path}/{link_id}").status_code == 204
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(AuthorInstitution, link_id).deleted_at is not None


def test_institution_link_rejects_deleted_institution_and_cross_author_ids(
    client,
    db_session,
    admin_context,
    author,
    institution,
):
    created = client.post(
        f"/api/v1/authors/{author.id}/institutions",
        json={"institution_id": institution.id},
    )
    assert created.status_code == 201
    other = Author(display_name="Other Author", alternate_names=[])
    db_session.add(other)
    db_session.commit()
    cross_author = client.patch(
        f"/api/v1/authors/{other.id}/institutions/{created.json()['id']}",
        json={"department": "Wrong"},
    )
    assert cross_author.status_code == 404

    institution.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    db_session.commit()
    response = client.post(
        f"/api/v1/authors/{author.id}/institutions",
        json={"institution_id": institution.id},
    )
    assert response.status_code == 404
