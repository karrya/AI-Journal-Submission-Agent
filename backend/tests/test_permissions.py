from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.services.permissions import (
    Permission,
    has_author_permission,
    require_author_permission,
    require_roles,
)

def assert_error(excinfo, status_code, code):
    assert excinfo.value.status_code == status_code
    assert excinfo.value.code == code


def test_exact_v01_permission_codes():
    assert {permission.value for permission in Permission} == {
        "manuscript:read",
        "manuscript:create",
        "manuscript:update",
        "manuscript:file:manage",
        "author:profile:read",
        "author:email:read",
        "author:phone:read",
        "author:address:read",
        "author:profile:update",
    }


@pytest.mark.parametrize("offset,expected", [(-1, True), (0, True), (1, False)])
def test_valid_from_boundary(
    db_session, operator, author, grant_factory, frozen_now, offset, expected
):
    grant_factory(
        user=operator,
        author=author,
        permission=Permission.MANUSCRIPT_READ,
        valid_from=frozen_now + timedelta(minutes=offset),
        valid_to=frozen_now + timedelta(hours=1),
    )
    assert (
        has_author_permission(
            db_session,
            operator,
            author.id,
            Permission.MANUSCRIPT_READ,
            frozen_now,
        )
        is expected
    )


def test_valid_to_boundary_is_exclusive(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(
        user=operator,
        author=author,
        permission=Permission.MANUSCRIPT_READ,
        valid_from=frozen_now - timedelta(hours=1),
        valid_to=frozen_now,
    )
    assert not has_author_permission(
        db_session, operator, author.id, Permission.MANUSCRIPT_READ, frozen_now
    )


def test_disabled_admin_is_never_authorized(db_session, disabled_admin, author):
    assert not has_author_permission(
        db_session, disabled_admin, author.id, Permission.MANUSCRIPT_READ
    )


def test_active_admin_bypasses_author_grants(db_session, admin, author):
    assert has_author_permission(
        db_session, admin, author.id, Permission.AUTHOR_PROFILE_UPDATE
    )


def test_soft_deleted_admin_is_not_active(db_session, admin, author):
    from app.models import utc_now

    admin.deleted_at = utc_now()
    db_session.commit()
    assert not has_author_permission(
        db_session, admin, author.id, Permission.MANUSCRIPT_READ
    )


def test_naive_utc_boundaries_are_supported(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ)
    assert has_author_permission(
        db_session,
        operator,
        author.id,
        Permission.MANUSCRIPT_READ,
        frozen_now.replace(tzinfo=None),
    )


def test_admin_permission_check_still_requires_existing_author(db_session, admin, author):
    assert (
        require_author_permission(
            db_session, admin, author.id, Permission.MANUSCRIPT_READ
        ).id
        == author.id
    )
    with pytest.raises(AppError) as caught:
        require_author_permission(
            db_session, admin, str(uuid4()), Permission.MANUSCRIPT_READ
        )
    assert_error(caught, 404, "RESOURCE_NOT_FOUND")


def test_write_permission_does_not_imply_read(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(
        user=operator,
        author=author,
        permission=Permission.MANUSCRIPT_UPDATE,
    )
    assert has_author_permission(
        db_session, operator, author.id, Permission.MANUSCRIPT_UPDATE, frozen_now
    )
    assert not has_author_permission(
        db_session, operator, author.id, Permission.MANUSCRIPT_READ, frozen_now
    )


def test_reviewer_is_read_only_even_with_write_grant(
    db_session, reviewer, author, grant_factory, frozen_now
):
    grant_factory(
        user=reviewer,
        author=author,
        permissions=[Permission.MANUSCRIPT_READ, Permission.MANUSCRIPT_UPDATE],
    )
    assert has_author_permission(
        db_session, reviewer, author.id, Permission.MANUSCRIPT_READ, frozen_now
    )
    assert not has_author_permission(
        db_session, reviewer, author.id, Permission.MANUSCRIPT_UPDATE, frozen_now
    )


def test_author_role_has_only_granted_read_capabilities(
    db_session, user_factory, author, grant_factory, frozen_now
):
    user = user_factory("author-user", roles=("author",))
    grant_factory(
        user=user,
        author=author,
        permissions=[Permission.AUTHOR_PROFILE_READ, Permission.AUTHOR_PROFILE_UPDATE],
    )
    assert has_author_permission(
        db_session, user, author.id, Permission.AUTHOR_PROFILE_READ, frozen_now
    )
    assert not has_author_permission(
        db_session, user, author.id, Permission.AUTHOR_PROFILE_UPDATE, frozen_now
    )


def test_auditor_cannot_read_business_resources_with_misconfigured_grant(
    db_session, auditor, author, grant_factory, frozen_now
):
    grant_factory(user=auditor, author=author, permission=Permission.MANUSCRIPT_READ)
    assert not has_author_permission(
        db_session, auditor, author.id, Permission.MANUSCRIPT_READ, frozen_now
    )


def test_operator_and_reviewer_roles_union_write_capabilities(
    db_session, user_factory, author, grant_factory, frozen_now
):
    user = user_factory(
        "operator-reviewer", roles=("submission_operator", "reviewer")
    )
    grant_factory(user=user, author=author, permission=Permission.MANUSCRIPT_UPDATE)
    assert has_author_permission(
        db_session, user, author.id, Permission.MANUSCRIPT_UPDATE, frozen_now
    )


def test_auditor_and_operator_roles_union_business_capabilities(
    db_session, user_factory, author, grant_factory, frozen_now
):
    user = user_factory("auditor-operator", roles=("auditor", "submission_operator"))
    grant_factory(user=user, author=author, permission=Permission.MANUSCRIPT_READ)
    assert has_author_permission(
        db_session, user, author.id, Permission.MANUSCRIPT_READ, frozen_now
    )


def test_system_admin_takes_precedence_over_auditor(
    db_session, user_factory, author
):
    user = user_factory("admin-auditor", roles=("auditor", "system_admin"))
    assert has_author_permission(
        db_session, user, author.id, Permission.MANUSCRIPT_READ
    )


def test_multiple_active_grants_union_permissions(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ)
    grant_factory(user=operator, author=author, permission=Permission.AUTHOR_EMAIL_READ)
    assert has_author_permission(
        db_session, operator, author.id, Permission.AUTHOR_EMAIL_READ, frozen_now
    )


def test_revoking_one_grant_preserves_other_active_grants(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(
        user=operator,
        author=author,
        permission=Permission.AUTHOR_EMAIL_READ,
        revoked_at=frozen_now,
    )
    grant_factory(user=operator, author=author, permission=Permission.AUTHOR_EMAIL_READ)
    assert has_author_permission(
        db_session, operator, author.id, Permission.AUTHOR_EMAIL_READ, frozen_now
    )


def test_inactive_author_invalidates_grant(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ)
    author.status = "disabled"
    db_session.commit()
    assert not has_author_permission(
        db_session, operator, author.id, Permission.MANUSCRIPT_READ, frozen_now
    )


def test_require_author_permission_returns_authorized_author(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(user=operator, author=author, permission=Permission.AUTHOR_PROFILE_READ)
    result = require_author_permission(
        db_session,
        operator,
        author.id,
        Permission.AUTHOR_PROFILE_READ,
        frozen_now,
    )
    assert result.id == author.id


def test_no_grant_and_missing_author_are_indistinguishable(
    db_session, operator, author, frozen_now
):
    for author_id in (author.id, str(uuid4())):
        with pytest.raises(AppError) as caught:
            require_author_permission(
                db_session,
                operator,
                author_id,
                Permission.MANUSCRIPT_READ,
                frozen_now,
            )
        assert_error(caught, 404, "RESOURCE_NOT_FOUND")


@pytest.mark.parametrize("state", ["not_yet_active", "expired", "revoked"])
def test_inactive_grant_returns_authorization_expired(
    db_session, operator, author, grant_factory, frozen_now, state
):
    dates = {
        "not_yet_active": (
            frozen_now + timedelta(minutes=1),
            frozen_now + timedelta(hours=1),
            None,
        ),
        "expired": (
            frozen_now - timedelta(hours=1),
            frozen_now,
            None,
        ),
        "revoked": (
            frozen_now - timedelta(hours=1),
            frozen_now + timedelta(hours=1),
            frozen_now,
        ),
    }
    valid_from, valid_to, revoked_at = dates[state]
    grant_factory(
        user=operator,
        author=author,
        permission=Permission.MANUSCRIPT_READ,
        valid_from=valid_from,
        valid_to=valid_to,
        revoked_at=revoked_at,
    )
    with pytest.raises(AppError) as caught:
        require_author_permission(
            db_session,
            operator,
            author.id,
            Permission.MANUSCRIPT_READ,
            frozen_now,
        )
    assert_error(caught, 403, "AUTHORIZATION_EXPIRED")


def test_active_grant_without_permission_returns_permission_denied(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ)
    with pytest.raises(AppError) as caught:
        require_author_permission(
            db_session,
            operator,
            author.id,
            Permission.MANUSCRIPT_UPDATE,
            frozen_now,
        )
    assert_error(caught, 403, "PERMISSION_DENIED")


def test_inactive_subject_with_grant_returns_authorization_expired(
    db_session, operator, author, grant_factory, frozen_now
):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ)
    author.status = "disabled"
    db_session.commit()
    with pytest.raises(AppError) as caught:
        require_author_permission(
            db_session,
            operator,
            author.id,
            Permission.MANUSCRIPT_READ,
            frozen_now,
        )
    assert_error(caught, 403, "AUTHORIZATION_EXPIRED")


def test_role_denial_precedes_resource_lookup(db_session, reviewer, frozen_now):
    with pytest.raises(AppError) as caught:
        require_author_permission(
            db_session,
            reviewer,
            str(uuid4()),
            Permission.MANUSCRIPT_UPDATE,
            frozen_now,
        )
    assert_error(caught, 403, "PERMISSION_DENIED")


def test_require_roles_unions_non_admin_roles(db_session, user_factory):
    user = user_factory("role-union", roles=("auditor", "submission_operator"))
    principal = SimpleNamespace(user=user)
    dependency = require_roles("submission_operator", "reviewer")
    assert dependency(principal) is principal


def test_require_roles_rejects_disabled_admin_before_admin_precedence(
    db_session, disabled_admin
):
    dependency = require_roles("system_admin")
    with pytest.raises(AppError) as caught:
        dependency(SimpleNamespace(user=disabled_admin))
    assert_error(caught, 403, "PERMISSION_DENIED")


def test_require_roles_active_admin_takes_precedence_over_allowed_roles(
    db_session, user_factory
):
    user = user_factory("admin-operator", roles=("system_admin", "submission_operator"))
    principal = SimpleNamespace(user=user)
    assert require_roles("auditor")(principal) is principal


def test_require_roles_rejects_role_outside_allowed_set(db_session, auditor):
    dependency = require_roles("system_admin", "submission_operator")
    with pytest.raises(AppError) as caught:
        dependency(SimpleNamespace(user=auditor))
    assert_error(caught, 403, "PERMISSION_DENIED")


def test_require_roles_rejects_detached_user(db_session, operator):
    db_session.expunge(operator)
    with pytest.raises(AppError) as caught:
        require_roles("submission_operator")(SimpleNamespace(user=operator))
    assert_error(caught, 403, "PERMISSION_DENIED")
