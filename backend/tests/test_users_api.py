import logging

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.models import OperationLog, Role


@pytest.fixture
def user_roles(db_session):
    for code in ("submission_operator", "reviewer", "author", "auditor"):
        if db_session.scalar(select(Role).where(Role.code == code)) is None:
            db_session.add(Role(code=code, name=code, description=f"Test {code} role"))
    db_session.commit()


def user_payload(username="api-user"):
    return {
        "username": username,
        "display_name": "API User",
        "password": "Api-Passphrase-2026!",
        "password_confirmation": "Api-Passphrase-2026!",
        "roles": ["submission_operator", "reviewer"],
    }


def test_users_require_authentication(client):
    assert client.get("/api/v1/users").status_code == 401


def test_users_require_admin(client, operator_context):
    assert client.get("/api/v1/users").status_code == 403
    assert client.post("/api/v1/users", json=user_payload()).status_code == 403


def test_create_get_patch_and_reset_user(client, db_session, admin_context, user_roles):
    created = client.post("/api/v1/users", json=user_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["roles"] == ["reviewer", "submission_operator"]
    assert "Api-Passphrase-2026!" not in created.text
    assert "password_hash" not in created.text

    detail = client.get(f"/api/v1/users/{body['id']}")
    assert detail.status_code == 200
    updated = client.patch(
        f"/api/v1/users/{body['id']}",
        json={
            "display_name": "Updated User",
            "roles": ["author"],
            "status": "disabled",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "disabled"
    reset = client.post(
        f"/api/v1/users/{body['id']}/reset-password",
        json={
            "new_password": "Reset-Api-2026!",
            "password_confirmation": "Reset-Api-2026!",
        },
    )
    assert reset.status_code == 204, reset.text
    assert b"Reset-Api-2026!" not in reset.content
    logs = db_session.scalars(select(OperationLog)).all()
    assert "Reset-Api-2026!" not in str([item.after_summary for item in logs])


def test_duplicate_normalized_username_returns_conflict(
    client, admin_context, user_roles
):
    assert client.post("/api/v1/users", json=user_payload()).status_code == 201
    duplicate = client.post("/api/v1/users", json=user_payload(" API-USER "))
    assert duplicate.status_code == 409
    assert "Api-Passphrase-2026!" not in duplicate.text


def test_password_validation_does_not_create_user(client, admin_context, user_roles):
    mismatch = client.post(
        "/api/v1/users",
        json=user_payload() | {"password_confirmation": "Different-2026!"},
    )
    assert mismatch.status_code == 422
    weak = client.post(
        "/api/v1/users",
        json=user_payload() | {"password": "short", "password_confirmation": "short"},
    )
    assert weak.status_code == 422


def test_mutations_require_csrf(client, admin_context):
    response = client.post(
        "/api/v1/users",
        json=user_payload("csrf-user"),
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert response.status_code == 403


def test_self_reset_invalidates_current_session(client, admin, admin_context):
    response = client.post(
        f"/api/v1/users/{admin.id}/reset-password",
        json={
            "new_password": "Self-Reset-2026!",
            "password_confirmation": "Self-Reset-2026!",
        },
    )
    assert response.status_code == 204, response.text
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_role_sort_and_unknown_user_return_safe_errors(client, admin_context):
    assert (
        client.post("/api/v1/users", json=user_payload() | {"roles": ["unknown"]}).status_code
        == 422
    )
    assert client.get("/api/v1/users?sort=password_hash").status_code == 422
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/v1/users/{missing}").status_code == 404


def test_create_database_failure_does_not_log_password_or_hash(
    client, admin_context, user_roles, monkeypatch, caplog
):
    sensitive_hash = "sensitive-argon2-hash-for-log-test"
    original_flush = Session.flush
    calls = 0

    def fail_flush(self):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_flush(self)
        raise DataError(
            "forced INSERT failure",
            {"password_hash": sensitive_hash},
            Exception("forced database failure"),
        )

    monkeypatch.setattr(Session, "flush", fail_flush)
    client.raise_server_exceptions = False
    with caplog.at_level(logging.ERROR):
        response = client.post("/api/v1/users", json=user_payload())

    assert response.status_code == 500
    assert "Api-Passphrase-2026!" not in caplog.text
    assert sensitive_hash not in caplog.text


def test_reset_database_failure_does_not_log_password_or_hash(
    client, admin_context, user_factory, monkeypatch, caplog
):
    target = user_factory("reset-log-target", roles=("author",))
    sensitive_hash = "sensitive-reset-hash-for-log-test"
    original_commit = Session.commit
    calls = 0

    def fail_commit(self):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_commit(self)
        raise DataError(
            "forced UPDATE failure",
            {"password_hash": sensitive_hash},
            Exception("forced database failure"),
        )

    monkeypatch.setattr(Session, "commit", fail_commit)
    client.raise_server_exceptions = False
    with caplog.at_level(logging.ERROR):
        response = client.post(
            f"/api/v1/users/{target.id}/reset-password",
            json={
                "new_password": "Reset-Api-2026!",
                "password_confirmation": "Reset-Api-2026!",
            },
        )

    assert response.status_code == 500
    assert "Reset-Api-2026!" not in caplog.text
    assert sensitive_hash not in caplog.text
