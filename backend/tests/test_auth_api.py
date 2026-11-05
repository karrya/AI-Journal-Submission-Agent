import base64
import hashlib
import hmac
import importlib.util
from datetime import timedelta
from http.cookies import SimpleCookie
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuthSession, OperationLog, Role, User, UserRole, utc_now

TRUSTED_ORIGIN = "http://localhost:5173"
NEW_PASSWORD = "Test-Replacement-Passphrase-2026!"


def login(client, credentials, *, username=None, password=None):
    return client.post(
        "/api/v1/auth/login",
        json={
            "username": username or credentials["username"],
            "password": password or credentials["password"],
        },
        headers={"Origin": TRUSTED_ORIGIN},
    )


def mutation_headers(csrf_token):
    return {"Origin": TRUSTED_ORIGIN, "X-CSRF-Token": csrf_token}


def change_password(
    client, login_body, new_password=NEW_PASSWORD, current_password=None
):
    return client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": current_password or "Test-Initial-Passphrase-2026!",
            "new_password": new_password,
        },
        headers=mutation_headers(login_body["csrf_token"]),
    )


def only_session(db_session):
    db_session.expire_all()
    return db_session.scalar(select(AuthSession))


def only_user(db_session):
    db_session.expire_all()
    return db_session.scalar(select(User).where(User.username == "initial-admin"))


def test_session_is_hashed_and_csrf_is_stable(
    client, db_session, admin_with_initial_password
):
    first = login(client, admin_with_initial_password)
    assert first.status_code == 200
    body = first.json()
    assert body["user"]["roles"] == ["system_admin"]
    assert body["user"]["must_change_password"] is True
    assert body["user"]["last_login_at"].endswith("Z")
    assert body["idle_expires_at"].endswith("Z")
    assert body["absolute_expires_at"].endswith("Z")
    assert "session_token" not in body
    assert "password_hash" not in body["user"]

    cookie = SimpleCookie(first.headers["set-cookie"])
    morsel = cookie["asa_session"]
    assert morsel["path"] == "/"
    assert morsel["httponly"]
    assert morsel["samesite"].lower() == "lax"
    assert not morsel["domain"]
    assert not morsel["secure"]

    raw_session = client.cookies.get("asa_session")
    assert len(raw_session) >= 43
    stored = only_session(db_session)
    assert stored.token_hash == hashlib.sha256(raw_session.encode()).hexdigest()
    assert (
        stored.csrf_token_hash
        == hashlib.sha256(body["csrf_token"].encode()).hexdigest()
    )
    assert raw_session != stored.token_hash
    assert body["csrf_token"] != stored.csrf_token_hash
    login_audit = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "auth.login", OperationLog.result == "success"
        )
    )
    assert login_audit.actor_user_id == only_user(db_session).id
    assert login_audit.request_id == first.headers["x-request-id"]
    assert login_audit.after_summary is None

    second = client.get("/api/v1/auth/csrf")
    assert second.status_code == 200
    assert second.json()["csrf_token"] == body["csrf_token"]


def test_two_tabs_share_stable_csrf_and_both_mutations_pass(
    client, second_client, db_session, login_initial_admin
):
    from fastapi import Depends, Response

    from app.api.v1.deps import Principal, require_csrf
    from app.main import app

    def csrf_probe(
        principal: Principal = Depends(require_csrf),
    ) -> Response:
        return Response(status_code=204)

    app.add_api_route(
        "/__tests__/csrf-probe",
        csrf_probe,
        methods=["POST"],
        include_in_schema=False,
    )
    only_user(db_session).must_change_password = False
    db_session.commit()
    raw_session = client.cookies.get("asa_session")
    csrf = login_initial_admin["csrf_token"]
    original_csrf_hash = only_session(db_session).csrf_token_hash
    second_client.cookies.set("asa_session", raw_session, path="/")

    first = client.post("/__tests__/csrf-probe", headers=mutation_headers(csrf))
    second = second_client.post("/__tests__/csrf-probe", headers=mutation_headers(csrf))
    assert first.status_code == 204
    assert second.status_code == 204
    refreshed = second_client.get("/api/v1/auth/csrf")
    assert refreshed.status_code == 200
    assert refreshed.json()["csrf_token"] == csrf
    assert only_session(db_session).csrf_token_hash == original_csrf_hash


def test_production_session_cookie_is_secure(
    client, admin_with_initial_password, monkeypatch
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    response = login(client, admin_with_initial_password)
    assert response.status_code == 200
    cookie = SimpleCookie(response.headers["set-cookie"])
    assert cookie["asa_session"]["secure"]


def test_first_password_gate_blocks_business_api(client, login_initial_admin):
    response = client.get("/api/v1/authors", headers={"Origin": TRUSTED_ORIGIN})
    assert response.status_code == 403
    assert response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert response.headers["access-control-allow-origin"] == TRUSTED_ORIGIN
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/csrf").status_code == 200

    changed = change_password(client, login_initial_admin)
    assert changed.status_code == 204
    logged_in = login(
        client,
        {"username": "initial-admin", "password": NEW_PASSWORD},
    )
    assert logged_in.status_code == 200
    assert client.get("/api/v1/authors").status_code == 200


@pytest.mark.parametrize("origin", ["https://attacker.invalid", "null", None])
def test_login_rejects_untrusted_origin(
    client, db_session, admin_with_initial_password, origin
):
    headers = {} if origin is None else {"Origin": origin}
    response = client.post(
        "/api/v1/auth/login", json=admin_with_initial_password, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SECURITY_CHECK_FAILED"
    assert db_session.scalar(select(AuthSession)) is None


def test_me_requires_a_valid_session(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.json()["details"] is None


@pytest.mark.parametrize(
    ("headers", "use_valid_csrf"),
    [
        ({"Origin": TRUSTED_ORIGIN}, False),
        ({"Origin": TRUSTED_ORIGIN, "X-CSRF-Token": "wrong-token"}, False),
        ({}, True),
        ({"Origin": "https://attacker.invalid"}, True),
        ({"Origin": "null"}, True),
    ],
)
def test_logout_requires_csrf_and_trusted_origin(
    client, db_session, login_initial_admin, headers, use_valid_csrf
):
    if use_valid_csrf:
        headers["X-CSRF-Token"] = login_initial_admin["csrf_token"]
    before = only_session(db_session)
    previous_activity = (before.last_seen_at, before.idle_expires_at)
    db_session.commit()
    response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "SECURITY_CHECK_FAILED"
    after = only_session(db_session)
    assert after.revoked_at is None
    assert (after.last_seen_at, after.idle_expires_at) == previous_activity


def test_change_password_requires_csrf(client, db_session, login_initial_admin):
    original_hash = only_user(db_session).password_hash
    before = only_session(db_session)
    previous_activity = (before.last_seen_at, before.idle_expires_at)
    db_session.commit()
    response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Test-Initial-Passphrase-2026!",
            "new_password": NEW_PASSWORD,
        },
        headers={"Origin": TRUSTED_ORIGIN},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SECURITY_CHECK_FAILED"
    assert only_user(db_session).password_hash == original_hash
    after = only_session(db_session)
    assert after.revoked_at is None
    assert (after.last_seen_at, after.idle_expires_at) == previous_activity


def test_logout_revokes_only_the_current_session(
    client, second_client, db_session, admin_with_initial_password
):
    first = login(client, admin_with_initial_password)
    first_token = client.cookies.get("asa_session")
    second = login(second_client, admin_with_initial_password)
    assert second.status_code == 200
    assert second_client.cookies.get("asa_session") != first_token

    response = client.post(
        "/api/v1/auth/logout",
        headers=mutation_headers(first.json()["csrf_token"]),
    )
    assert response.status_code == 204
    assert not response.content
    assert "asa_session" not in client.cookies
    client.cookies.set("asa_session", first_token, path="/")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert second_client.get("/api/v1/auth/me").status_code == 200

    db_session.expire_all()
    sessions = db_session.scalars(select(AuthSession)).all()
    revoked = [item for item in sessions if item.revoked_at is not None]
    assert len(revoked) == 1
    assert revoked[0].token_hash == hashlib.sha256(first_token.encode()).hexdigest()
    assert db_session.scalar(
        select(OperationLog).where(OperationLog.action == "auth.logout")
    )


def test_password_change_revokes_all_sessions_and_accepts_only_new_password(
    client, second_client, db_session, admin_with_initial_password
):
    first = login(client, admin_with_initial_password)
    first_token = client.cookies.get("asa_session")
    assert login(second_client, admin_with_initial_password).status_code == 200

    response = change_password(client, first.json())
    assert response.status_code == 204
    assert not response.content
    assert second_client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("asa_session", first_token, path="/")
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()

    db_session.expire_all()
    sessions = db_session.scalars(select(AuthSession)).all()
    assert len(sessions) == 2
    assert all(item.revoked_at is not None for item in sessions)
    user = only_user(db_session)
    assert user.must_change_password is False
    assert user.password_hash.startswith("$argon2id$")
    PasswordHasher().verify(user.password_hash, NEW_PASSWORD)

    assert login(client, admin_with_initial_password).status_code == 401
    replacement = login(client, {"username": "initial-admin", "password": NEW_PASSWORD})
    assert replacement.status_code == 200
    assert replacement.json()["user"]["must_change_password"] is False
    assert db_session.scalar(
        select(OperationLog).where(OperationLog.action == "auth.change_password")
    )


def test_wrong_current_password_does_not_change_credentials_or_revoke_session(
    client, db_session, login_initial_admin
):
    original_hash = only_user(db_session).password_hash
    response = change_password(
        client, login_initial_admin, current_password="incorrect-password"
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert only_user(db_session).password_hash == original_hash
    assert only_session(db_session).revoked_at is None
    assert client.get("/api/v1/auth/me").status_code == 200


def test_password_fields_preserve_significant_whitespace():
    from app.schemas.auth import ChangePasswordRequest, LoginRequest

    login_request = LoginRequest(
        username="  initial-admin  ", password="  password with spaces  "
    )
    change_request = ChangePasswordRequest(
        current_password="  old password  ", new_password="  new password  "
    )
    assert login_request.username == "initial-admin"
    assert login_request.password == "  password with spaces  "
    assert change_request.current_password == "  old password  "
    assert change_request.new_password == "  new password  "


@pytest.mark.parametrize(
    "new_password",
    ["short", "initial-admin", "Password123!"],
)
def test_password_change_rejects_weak_or_invalid_new_passwords(
    client, db_session, login_initial_admin, new_password
):
    original_hash = only_user(db_session).password_hash
    response = change_password(client, login_initial_admin, new_password=new_password)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert new_password not in response.text
    assert only_user(db_session).password_hash == original_hash


@pytest.mark.parametrize("state", ["idle", "absolute", "revoked", "disabled"])
def test_invalid_or_inactive_sessions_are_unauthorized(
    client, db_session, login_initial_admin, state
):
    session = only_session(db_session)
    if state == "idle":
        session.idle_expires_at = utc_now() - timedelta(microseconds=1)
    elif state == "absolute":
        session.absolute_expires_at = utc_now() - timedelta(microseconds=1)
    elif state == "revoked":
        session.revoked_at = utc_now()
    else:
        only_user(db_session).status = "disabled"
    db_session.commit()

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_authenticated_request_refreshes_idle_activity(
    client, db_session, login_initial_admin
):
    session = only_session(db_session)
    previous_seen = utc_now() - timedelta(minutes=10)
    session.last_seen_at = previous_seen
    session.idle_expires_at = previous_seen + timedelta(minutes=30)
    db_session.commit()

    assert client.get("/api/v1/auth/me").status_code == 200
    refreshed = only_session(db_session)
    assert refreshed.last_seen_at > previous_seen
    assert refreshed.idle_expires_at > previous_seen + timedelta(minutes=39)
    assert refreshed.idle_expires_at <= refreshed.absolute_expires_at


def test_login_normalizes_username_and_returns_generic_failures_without_secrets(
    client, db_session, admin_with_initial_password, caplog
):
    normalized = login(
        client, admin_with_initial_password, username="  INITIAL-ADMIN  "
    )
    assert normalized.status_code == 200
    client.cookies.clear()

    wrong = login(client, admin_with_initial_password, password="wrong-password")
    unknown = login(
        client,
        admin_with_initial_password,
        username="unknown-user",
        password="wrong-password",
    )
    for response in (wrong, unknown):
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHORIZED"
    assert wrong.json()["message"] == unknown.json()["message"]
    assert wrong.json()["details"] == unknown.json()["details"] is None

    failures = db_session.scalars(
        select(OperationLog).where(
            OperationLog.action == "auth.login", OperationLog.result == "failure"
        )
    ).all()
    assert len(failures) == 2
    persisted = " ".join(
        str(getattr(log, column.name))
        for log in failures
        for column in OperationLog.__table__.columns
    )
    for secret in ("initial-admin", "unknown-user", "wrong-password"):
        assert secret not in persisted
        assert secret not in caplog.text


def test_login_rate_limit_is_keyed_by_normalized_username_and_source_ip(
    client, admin_with_initial_password
):
    for _ in range(5):
        response = login(
            client,
            admin_with_initial_password,
            username=" INITIAL-ADMIN ",
            password="wrong-password",
        )
        assert response.status_code == 401
    blocked = login(client, admin_with_initial_password, username="Initial-Admin")
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_ATTEMPTS"

    other_key = login(
        client,
        admin_with_initial_password,
        username="different-user",
        password="wrong-password",
    )
    assert other_key.status_code == 401


def test_successful_login_resets_its_rate_limit_key(
    client, admin_with_initial_password
):
    for _ in range(2):
        for _ in range(4):
            assert (
                login(
                    client, admin_with_initial_password, password="wrong-password"
                ).status_code
                == 401
            )
        assert login(client, admin_with_initial_password).status_code == 200
        client.cookies.clear()


def test_login_rate_limiter_sweeps_stale_keys_globally():
    from app.services.auth import LoginRateLimiter

    now = [1_000.0]
    limiter = LoginRateLimiter(window_seconds=60, clock=lambda: now[0])
    limiter.record_failure("stale-user", "192.0.2.1")
    now[0] = 1_050.0
    limiter.record_failure("recent-user", "192.0.2.2")
    now[0] = 1_061.0

    assert limiter.retry_after("probe-user", "192.0.2.3") is None
    keys = set(limiter._attempts)
    assert ("stale-user", "192.0.2.1") not in keys
    assert ("recent-user", "192.0.2.2") in keys


@pytest.mark.parametrize("secret", ["", "x" * 31])
def test_authentication_rejects_short_csrf_secret_but_health_remains_available(
    client, db_session, admin_with_initial_password, monkeypatch, secret
):
    monkeypatch.setenv("CSRF_SECRET_KEY", secret)
    get_settings.cache_clear()
    assert client.get("/api/v1/health").status_code == 200
    response = login(client, admin_with_initial_password)
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    if secret:
        assert secret not in response.text
    assert db_session.scalar(select(AuthSession)) is None


def test_password_and_csrf_primitives_match_the_security_contract():
    from app.security.csrf import csrf_token, token_hash
    from app.security.passwords import hash_password, verify_password

    password_hash = hash_password("a-secure-test-password")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "a-secure-test-password") is True
    assert verify_password(password_hash, "incorrect") is False
    assert verify_password("not-an-argon-hash", "incorrect") is False

    assert token_hash("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    expected = (
        base64.urlsafe_b64encode(
            hmac.new(
                b"test-secret-that-is-long-enough",
                b"csrf:" + hashlib.sha256(b"session").hexdigest().encode(),
                hashlib.sha256,
            ).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    session_hash = hashlib.sha256(b"session").hexdigest()
    assert csrf_token(session_hash, "test-secret-that-is-long-enough") == expected


def load_create_admin_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "create_admin.py"
    spec = importlib.util.spec_from_file_location("create_admin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_admin_seeds_five_roles_and_one_initial_system_admin(db_session):
    create_admin = load_create_admin_module()
    user = create_admin.initialize_admin(
        db_session,
        username="Script.Admin",
        password="Test-Script-Passphrase-2026!",
    )
    assert user.normalized_username == "script.admin"
    assert user.must_change_password is True
    assert user.password_hash.startswith("$argon2id$")
    assert set(db_session.scalars(select(Role.code)).all()) == {
        "system_admin",
        "submission_operator",
        "reviewer",
        "author",
        "auditor",
    }
    admin_role = db_session.scalar(select(Role).where(Role.code == "system_admin"))
    assert db_session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id, UserRole.role_id == admin_role.id
        )
    )

    with pytest.raises(ValueError, match="已经完成"):
        create_admin.initialize_admin(
            db_session,
            username="another-admin",
            password="Test-Script-Passphrase-2026!",
        )
    assert len(db_session.scalars(select(User)).all()) == 1


def test_create_admin_main_uses_hidden_password_prompts_and_safe_output(
    db_engine, db_session, monkeypatch, capsys
):
    create_admin = load_create_admin_module()
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(
        create_admin,
        "SessionLocal",
        sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "Prompt.Admin")
    prompts = []
    passwords = iter(["Test-Prompt-Passphrase-2026!", "Test-Prompt-Passphrase-2026!"])

    def hidden_prompt(prompt):
        prompts.append(prompt)
        return next(passwords)

    monkeypatch.setattr(create_admin.getpass, "getpass", hidden_prompt)
    create_admin.main()
    assert len(prompts) == 2
    output = capsys.readouterr().out
    assert "Prompt.Admin" not in output
    assert "Test-Prompt-Passphrase-2026!" not in output
    assert db_session.scalar(select(User).where(User.username == "Prompt.Admin"))
