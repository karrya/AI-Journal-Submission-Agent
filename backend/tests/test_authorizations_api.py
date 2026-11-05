import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuthorAuthorization, OperationLog


def authorization_payload(author, user, **overrides):
    now = datetime.now(UTC)
    payload = {
        "author_id": author.id,
        "user_id": user.id,
        "permissions": ["author:profile:read"],
        "valid_from": (now - timedelta(minutes=5)).isoformat(),
        "valid_to": (now + timedelta(hours=1)).isoformat(),
    }
    payload.update(overrides)
    return payload


def create_authorization(client, author, user, **overrides):
    return client.post(
        "/api/v1/author-authorizations",
        json=authorization_payload(author, user, **overrides),
    )


def test_admin_can_create_filter_read_update_and_revoke_authorization(
    client, admin_context, admin, author, operator, db_session
):
    created = create_authorization(
        client,
        author,
        operator,
        permissions=["manuscript:update", "manuscript:read"],
        evidence_ref="controlled-evidence-reference",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["permissions"] == ["manuscript:read", "manuscript:update"]
    assert body["validity_status"] == "active"
    assert body["reviewed_by"] == admin.id
    authorization_id = body["id"]

    listed = client.get(
        "/api/v1/author-authorizations"
        f"?author_id={author.id}&user_id={operator.id}"
        "&permission=manuscript:read&validity_status=active"
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert (
        client.get(f"/api/v1/author-authorizations/{authorization_id}").status_code
        == 200
    )

    new_end = datetime.now(UTC) + timedelta(days=2)
    updated = client.patch(
        f"/api/v1/author-authorizations/{authorization_id}",
        json={
            "permissions": ["author:email:read", "author:profile:read"],
            "valid_to": new_end.isoformat(),
            "evidence_ref": "replacement-secret-evidence-reference",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["permissions"] == [
        "author:email:read",
        "author:profile:read",
    ]
    db_session.expire_all()
    audit = db_session.scalar(
        select(OperationLog)
        .where(OperationLog.action == "authorization.update")
        .order_by(OperationLog.created_at.desc())
    )
    assert audit.before_summary == {
        "permissions": ["manuscript:read", "manuscript:update"]
    }
    assert audit.after_summary == {
        "permissions": ["author:email:read", "author:profile:read"]
    }
    assert "replacement-secret-evidence-reference" not in json.dumps(
        [audit.before_summary, audit.after_summary]
    )

    revoked = client.post(
        f"/api/v1/author-authorizations/{authorization_id}/revoke",
        json={"reason": "No longer authorized"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["validity_status"] == "revoked"


def test_authorization_management_is_admin_only(
    client, operator_context, author, operator
):
    assert client.get("/api/v1/author-authorizations").status_code == 403
    response = create_authorization(client, author, operator)
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("permissions", [[], ["unknown:permission"], ["read"] * 2])
def test_authorization_rejects_empty_unknown_or_duplicate_permissions(
    client, admin_context, author, operator, permissions
):
    response = create_authorization(client, author, operator, permissions=permissions)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("valid_to", [None, "past"])
def test_authorization_requires_finite_future_end(
    client, admin_context, author, operator, valid_to
):
    overrides = {"valid_to": None}
    if valid_to == "past":
        overrides["valid_to"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    response = create_authorization(client, author, operator, **overrides)
    assert response.status_code == 422


def test_authorization_rejects_end_not_after_start(
    client, admin_context, author, operator
):
    now = datetime.now(UTC)
    response = create_authorization(
        client,
        author,
        operator,
        valid_from=(now + timedelta(hours=1)).isoformat(),
        valid_to=(now + timedelta(hours=1)).isoformat(),
    )
    assert response.status_code == 422


def test_authorization_update_validates_against_stored_dates_and_now(
    client, admin_context, author, operator
):
    created = create_authorization(client, author, operator)
    authorization_id = created.json()["id"]
    base = f"/api/v1/author-authorizations/{authorization_id}"
    past = client.patch(
        base,
        json={"valid_to": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
    )
    assert past.status_code == 422
    inverted = client.patch(
        base,
        json={"valid_from": created.json()["valid_to"]},
    )
    assert inverted.status_code == 422
    empty = client.patch(base, json={"permissions": []})
    assert empty.status_code == 422


def test_revocation_takes_effect_on_next_request_without_new_session(
    client,
    second_client,
    db_session,
    admin_context,
    author,
    operator,
    auth_context_factory,
):
    created = create_authorization(client, author, operator)
    assert created.status_code == 201
    auth_context_factory(operator, second_client)
    assert second_client.get(f"/api/v1/authors/{author.id}").status_code == 200

    revoked = client.post(
        f"/api/v1/author-authorizations/{created.json()['id']}/revoke",
        json={},
    )
    assert revoked.status_code == 200
    denied = second_client.get(f"/api/v1/authors/{author.id}")
    assert denied.status_code == 403
    assert denied.json()["code"] == "AUTHORIZATION_EXPIRED"
    assert second_client.get("/api/v1/institutions").status_code == 200


def test_permission_removal_takes_effect_without_session_cache_invalidation(
    client,
    second_client,
    admin_context,
    author,
    operator,
    auth_context_factory,
):
    created = create_authorization(client, author, operator)
    auth_context_factory(operator, second_client)
    path = f"/api/v1/authors/{author.id}"
    assert second_client.get(path).status_code == 200
    updated = client.patch(
        f"/api/v1/author-authorizations/{created.json()['id']}",
        json={"permissions": ["author:email:read"]},
    )
    assert updated.status_code == 200
    denied = second_client.get(path)
    assert denied.status_code == 403
    assert denied.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    "state",
    ["not_yet_active", "expired", "revoked", "inactive_subject"],
)
def test_authorization_response_computes_validity_status(
    client,
    db_session,
    admin_context,
    author,
    operator,
    grant_factory,
    state,
):
    now = datetime.now(UTC)
    dates = {
        "not_yet_active": (
            now + timedelta(hours=1),
            now + timedelta(hours=2),
            None,
        ),
        "expired": (
            now - timedelta(hours=2),
            now - timedelta(hours=1),
            None,
        ),
        "revoked": (
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            now,
        ),
        "inactive_subject": (
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            None,
        ),
    }
    valid_from, valid_to, revoked_at = dates[state]
    grant = grant_factory(
        user=operator,
        author=author,
        permission="author:profile:read",
        valid_from=valid_from,
        valid_to=valid_to,
        revoked_at=revoked_at,
    )
    if state == "inactive_subject":
        author.status = "inactive"
        db_session.commit()
    response = client.get(f"/api/v1/author-authorizations/{grant.id}")
    assert response.status_code == 200
    assert response.json()["validity_status"] == state


def test_validity_filter_uses_inactive_subject_precedence(
    client, db_session, admin_context, author, operator, grant_factory
):
    now = datetime.now(UTC)
    grant = grant_factory(
        user=operator,
        author=author,
        permission="author:profile:read",
        valid_from=now - timedelta(hours=2),
        valid_to=now - timedelta(hours=1),
    )
    author.status = "inactive"
    db_session.commit()

    detail = client.get(f"/api/v1/author-authorizations/{grant.id}")
    assert detail.json()["validity_status"] == "inactive_subject"
    expired = client.get("/api/v1/author-authorizations?validity_status=expired")
    inactive = client.get(
        "/api/v1/author-authorizations?validity_status=inactive_subject"
    )
    assert expired.json()["total"] == 0
    assert inactive.json()["total"] == 1


def test_authorization_flush_maps_only_known_unique_conflicts(
    db_session, admin, author, operator, monkeypatch
):
    from sqlalchemy.exc import IntegrityError

    from app.core.errors import AppError
    from app.schemas.authors import AuthorizationCreate
    from app.services.authorizations import AuthorizationService

    now = datetime.now(UTC)
    payload = AuthorizationCreate(
        author_id=author.id,
        user_id=operator.id,
        permissions=["author:profile:read"],
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
    )
    service = AuthorizationService(db_session, admin, str(AuthorAuthorization.__name__))

    original_flush = db_session.flush

    def known_unique(*args, **kwargs):
        if any(isinstance(item, AuthorAuthorization) for item in db_session.new):
            raise IntegrityError(
                "INSERT",
                {},
                Exception(
                    1062,
                    "Duplicate entry 'x' for key "
                    "'author_emails.uq_author_emails_author_normalized'",
                ),
            )
        return original_flush()

    monkeypatch.setattr(db_session, "flush", known_unique)
    with pytest.raises(AppError) as caught:
        service.create(payload)
    assert caught.value.status_code == 409
    assert caught.value.code == "CONFLICT"


def test_authorization_flush_does_not_map_foreign_key_failures_to_conflict(
    db_session, admin, author, operator, monkeypatch
):
    from sqlalchemy.exc import IntegrityError

    from app.schemas.authors import AuthorizationCreate
    from app.services.authorizations import AuthorizationService

    now = datetime.now(UTC)
    payload = AuthorizationCreate(
        author_id=author.id,
        user_id=operator.id,
        permissions=["author:profile:read"],
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
    )
    service = AuthorizationService(db_session, admin, str(AuthorAuthorization.__name__))

    original_flush = db_session.flush

    def foreign_key_failure(*args, **kwargs):
        if any(isinstance(item, AuthorAuthorization) for item in db_session.new):
            raise IntegrityError("INSERT", {}, Exception(1452, "foreign key failure"))
        return original_flush()

    monkeypatch.setattr(db_session, "flush", foreign_key_failure)
    with pytest.raises(IntegrityError):
        service.create(payload)


def test_authorization_not_found_is_flat_404(client, admin_context):
    response = client.get(
        f"/api/v1/author-authorizations/{AuthorAuthorization.__name__}"
    )
    assert response.status_code == 422
    missing = client.get(
        "/api/v1/author-authorizations/00000000-0000-0000-0000-000000000000"
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "RESOURCE_NOT_FOUND"
    assert set(missing.json()) == {"code", "message", "request_id", "details"}
