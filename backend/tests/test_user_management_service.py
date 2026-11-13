from threading import Barrier, BrokenBarrierError, Thread

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import OperationLog, Role, User, UserRole
from app.schemas.users import UserCreate, UserPasswordReset, UserUpdate
from app.security.passwords import verify_password
from app.services.users import UserManagementService


@pytest.fixture
def management_roles(db_session):
    for code in ("submission_operator", "reviewer", "author", "auditor"):
        if db_session.scalar(select(Role).where(Role.code == code)) is None:
            db_session.add(Role(code=code, name=code, description=f"Test {code} role"))
    db_session.commit()


def test_roles_reject_empty_duplicate_and_unknown_values():
    base = {
        "username": "new-user",
        "display_name": "New User",
        "password": "Strong-Passphrase-2026!",
        "password_confirmation": "Strong-Passphrase-2026!",
    }
    for roles in ([], ["author", "author"], ["unknown"]):
        with pytest.raises(ValidationError):
            UserCreate(**base, roles=roles)


def test_update_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        UserUpdate()


def test_list_filters_sorts_and_hides_credentials(db_session, admin, user_factory):
    user_factory("z-operator", roles=("submission_operator",))
    user_factory("a-disabled", roles=("author",), status="disabled")
    service = UserManagementService(db_session, admin, "request-list")
    page = service.list_page(
        page=1,
        page_size=20,
        name="operator",
        status="active",
        sort="username",
        order="asc",
    )
    assert [item.username for item in page.items] == ["z-operator"]
    assert "password_hash" not in page.model_dump_json()


def test_read_requires_admin(db_session, operator):
    service = UserManagementService(db_session, operator, "request-denied")
    with pytest.raises(Exception) as caught:
        service.list_page(
            page=1,
            page_size=20,
            name=None,
            status=None,
            sort="username",
            order="asc",
        )
    assert caught.value.status_code == 403


def payload(username="new-user", roles=None):
    return UserCreate(
        username=username,
        display_name="New User",
        password="Strong-Passphrase-2026!",
        password_confirmation="Strong-Passphrase-2026!",
        roles=roles or ["submission_operator", "reviewer"],
    )


def test_create_hashes_password_assigns_roles_and_audits(
    db_session, admin, management_roles
):
    service = UserManagementService(db_session, admin, "request-create")
    result = service.create(payload())
    record = db_session.get(User, str(result.id))
    assert verify_password(record.password_hash, "Strong-Passphrase-2026!")
    assert record.must_change_password is True
    assert result.roles == ["reviewer", "submission_operator"]
    log = db_session.scalar(
        select(OperationLog).where(OperationLog.action == "user.create")
    )
    assert log.after_summary["username"] == "new-user"
    assert "Strong-Passphrase-2026!" not in str(log.after_summary)
    assert "Strong-Passphrase-2026!" not in result.model_dump_json()
    assert "password_hash" not in result.model_dump_json()


def test_duplicate_normalized_username_rolls_back(
    db_session, admin, user_factory, management_roles
):
    existing = user_factory("Existing-User", roles=("author",))
    existing.normalized_username = "existing-user"
    db_session.commit()
    before_count = db_session.scalar(select(func.count(User.id)))
    service = UserManagementService(db_session, admin, "request-duplicate")
    with pytest.raises(Exception) as caught:
        service.create(payload(" existing-user "))
    assert caught.value.status_code == 409
    assert db_session.scalar(select(func.count(User.id))) == before_count


def test_normalized_username_over_64_is_rejected_without_writes(
    db_session, admin, management_roles
):
    before_users = db_session.scalar(select(func.count(User.id)))
    before_roles = db_session.scalar(select(func.count(UserRole.user_id)))
    service = UserManagementService(db_session, admin, "request-long-normalized")
    with pytest.raises(AppError) as caught:
        service.create(payload("ﬃ" * 64))
    assert caught.value.status_code == 422
    assert db_session.scalar(select(func.count(User.id))) == before_users
    assert db_session.scalar(select(func.count(UserRole.user_id))) == before_roles


def test_update_roles_and_disable_revokes_sessions(
    db_session, admin, user_factory, auth_context_factory, management_roles
):
    target = user_factory("target", roles=("reviewer",))
    context = auth_context_factory(target)
    service = UserManagementService(db_session, admin, "request-update")
    result = service.update(
        target.id, UserUpdate(roles=["author", "auditor"], status="disabled")
    )
    db_session.expire_all()
    assert result.roles == ["auditor", "author"]
    assert result.status == "disabled"
    assert context.session.revoked_at is not None


def test_self_disable_and_self_admin_removal_are_rejected(db_session, admin):
    service = UserManagementService(db_session, admin, "request-self")
    with pytest.raises(Exception) as caught:
        service.update(admin.id, UserUpdate(status="disabled"))
    assert caught.value.status_code == 409
    with pytest.raises(Exception) as caught:
        service.update(admin.id, UserUpdate(roles=["auditor"]))
    assert caught.value.status_code == 409


def test_other_admin_can_be_disabled_when_actor_remains(
    db_session, admin, user_factory
):
    other = user_factory("other-admin", roles=("system_admin",))
    service = UserManagementService(db_session, admin, "request-other")
    result = service.update(other.id, UserUpdate(status="disabled"))
    assert result.status == "disabled"


def test_reset_password_revokes_sessions_without_auditing_secret(
    db_session, admin, user_factory, auth_context_factory
):
    target = user_factory("reset-target", roles=("author",))
    context = auth_context_factory(target)
    service = UserManagementService(db_session, admin, "request-reset")
    service.reset_password(
        target.id,
        UserPasswordReset(
            new_password="Reset-Passphrase-2026!",
            password_confirmation="Reset-Passphrase-2026!",
        ),
    )
    db_session.expire_all()
    assert verify_password(target.password_hash, "Reset-Passphrase-2026!")
    assert target.must_change_password is True
    assert context.session.revoked_at is not None
    logs = db_session.scalars(
        select(OperationLog).where(OperationLog.action == "user.password.reset")
    ).all()
    assert logs
    assert all(
        "Reset-Passphrase-2026!" not in str(item.after_summary) for item in logs
    )


def test_admin_protection_query_uses_row_locks(db_session, admin):
    statements = []
    event.listen(
        db_session.get_bind(),
        "before_cursor_execute",
        lambda *args: statements.append(args[2]),
    )
    service = UserManagementService(db_session, admin, "request-lock")
    service._lock_active_admin_ids()
    assert any("FOR UPDATE" in statement.upper() for statement in statements)


def test_cross_admin_demotion_has_deterministic_protection(
    db_engine, db_session, admin, user_factory
):
    other = user_factory("other-race-admin", roles=("system_admin",))
    start_barrier = Barrier(2)
    target_barrier = Barrier(2)

    class SynchronizedService(UserManagementService):
        def _require_admin(self):
            super()._require_admin()
            start_barrier.wait(timeout=5)

        def _locked_user(self, user_id: str) -> User:
            target = super()._locked_user(user_id)
            try:
                target_barrier.wait(timeout=1)
            except BrokenBarrierError:
                pass
            return target

    outcomes = []

    def demote(actor, target):
        connection = db_engine.connect()
        session = Session(bind=connection)
        try:
            SynchronizedService(session, actor, "request-race").update(
                target.id, UserUpdate(status="disabled")
            )
            outcomes.append("success")
        except AppError as exc:
            outcomes.append(exc.code)
        except Exception as exc:
            outcomes.append(type(exc).__name__)
        finally:
            session.close()
            connection.close()

    threads = [
        Thread(target=demote, args=(admin, other)),
        Thread(target=demote, args=(other, admin)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["ADMIN_PROTECTED", "success"]
    db_session.expire_all()
    statuses = sorted([admin.status, other.status])
    assert statuses == ["active", "disabled"]
