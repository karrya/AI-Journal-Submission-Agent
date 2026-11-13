from threading import Event, Thread

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthSession, User
from app.schemas.users import UserPasswordReset
from app.security.passwords import hash_password, verify_password
from app.services.auth import AuthService
from app.services.users import UserManagementService

OLD_PASSWORD = "Old-Credential-2026!"
SELF_PASSWORD = "Self-Change-2026!"
ADMIN_PASSWORD = "Admin-Reset-2026!"


@pytest.fixture
def credential_user(db_session, username="credential-user"):
    user = User(
        username=username,
        normalized_username=username,
        display_name=username,
        password_hash=hash_password(OLD_PASSWORD),
        status="active",
        must_change_password=False,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_reset_serializes_login_and_revokes_new_session(
    db_engine, db_session, credential_user, admin
):
    verified = Event()
    reset_done = Event()
    login_connection = db_engine.connect()
    reset_connection = db_engine.connect()
    login_session = Session(bind=login_connection)
    reset_session = Session(bind=reset_connection)
    auth = AuthService(login_session)
    original_create = auth.sessions.create_session

    def gated_create(user):
        verified.set()
        reset_done.wait(timeout=0.5)
        return original_create(user)

    auth.sessions.create_session = gated_create
    errors = []

    def reset():
        try:
            assert verified.wait(timeout=5)
            UserManagementService(reset_session, admin, "reset-race").reset_password(
                credential_user.id,
                UserPasswordReset(
                    new_password=ADMIN_PASSWORD,
                    password_confirmation=ADMIN_PASSWORD,
                ),
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            reset_done.set()

    reset_thread = Thread(target=reset)
    login_thread = Thread(
        target=lambda: auth.login(
            credential_user.username, OLD_PASSWORD, "127.0.0.1", "login-race"
        )
    )
    reset_thread.start()
    login_thread.start()
    login_thread.join(timeout=20)
    reset_thread.join(timeout=20)

    assert not login_thread.is_alive() and not reset_thread.is_alive()
    assert errors == []
    db_session.expire_all()
    sessions = db_session.scalars(
        select(AuthSession).where(AuthSession.user_id == credential_user.id)
    ).all()
    assert sessions
    assert all(session.revoked_at is not None for session in sessions)
    login_session.close()
    reset_session.close()
    login_connection.close()
    reset_connection.close()


def test_reset_serializes_self_service_password_change(
    db_engine,
    db_session,
    credential_user,
    admin,
    auth_context_factory,
    monkeypatch,
):
    context = auth_context_factory(credential_user)
    verified = Event()
    reset_done = Event()
    change_connection = db_engine.connect()
    reset_connection = db_engine.connect()
    change_session = Session(bind=change_connection)
    reset_session = Session(bind=reset_connection)
    auth = AuthService(change_session)
    original_verify = verify_password

    def gated_verify(hashed, password):
        verified.set()
        reset_done.wait(timeout=0.5)
        return original_verify(hashed, password)

    monkeypatch.setattr("app.services.auth.verify_password", gated_verify)
    errors = []

    def reset():
        try:
            assert verified.wait(timeout=5)
            UserManagementService(reset_session, admin, "reset-change-race").reset_password(
                credential_user.id,
                UserPasswordReset(
                    new_password=ADMIN_PASSWORD,
                    password_confirmation=ADMIN_PASSWORD,
                ),
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            reset_done.set()

    reset_thread = Thread(target=reset)
    change_thread = Thread(
        target=lambda: auth.change_password(
            change_session.get(User, credential_user.id),
            context.session,
            OLD_PASSWORD,
            SELF_PASSWORD,
            "change-race",
        )
    )
    reset_thread.start()
    change_thread.start()
    change_thread.join(timeout=20)
    reset_thread.join(timeout=20)

    assert not change_thread.is_alive() and not reset_thread.is_alive()
    assert errors == []
    db_session.expire_all()
    assert verify_password(credential_user.password_hash, ADMIN_PASSWORD)
    assert credential_user.must_change_password is True
    change_session.close()
    reset_session.close()
    change_connection.close()
    reset_connection.close()
