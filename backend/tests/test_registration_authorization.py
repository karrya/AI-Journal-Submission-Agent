"""Registration actions require both role capability and explicit author consent."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.models import Author, AuthorAuthorization, utc_now
from app.services.registration_authorization import require_registration_consent


def create_grant(db, user, author, permissions):
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=user.id,
        permissions=permissions,
        valid_from=utc_now() - timedelta(minutes=1),
        valid_to=utc_now() + timedelta(hours=1),
    )
    db.add(grant)
    db.commit()
    return grant


def assert_denied(db, user, author_id, authorization_id, permissions):
    with pytest.raises(AppError) as caught:
        require_registration_consent(
            db,
            user,
            author_id,
            authorization_id,
            permissions,
            "request-id",
        )
    assert caught.value.status_code == 403
    return caught.value


def test_admin_without_author_registration_grant_is_denied(db_session, admin, author):
    error = assert_denied(
        db_session, admin, author.id, str(uuid4()), {"account:register"}
    )
    assert error.code == "AUTHORIZATION_INVALID"


def test_admin_with_explicit_author_registration_grant_is_allowed(
    db_session, admin, author
):
    grant = create_grant(db_session, admin, author, ["account:register"])
    result = require_registration_consent(
        db_session,
        admin,
        author.id,
        grant.id,
        {"account:register"},
        "request-id",
    )
    assert result.id == author.id


def test_explicit_grant_allows_operator(db_session, operator, author):
    grant = create_grant(
        db_session, operator, author, ["account:register", "author:profile:read"]
    )
    result = require_registration_consent(
        db_session,
        operator,
        author.id,
        grant.id,
        {"account:register", "author:profile:read"},
        "request-id",
    )
    assert result.id == author.id


def test_read_only_role_is_denied_even_with_registration_grant(
    db_session, reviewer, author
):
    grant = create_grant(db_session, reviewer, author, ["account:register"])
    error = assert_denied(
        db_session, reviewer, author.id, grant.id, {"account:register"}
    )
    assert error.code == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    ("requested", "granted"),
    [
        ("account:register", ["email:verification:read", "credential:use"]),
        ("email:verification:read", ["account:register", "credential:use"]),
        ("credential:use", ["account:register", "email:verification:read"]),
    ],
)
def test_registration_permissions_require_their_own_explicit_grants(
    db_session, operator, author, requested, granted
):
    grant = create_grant(db_session, operator, author, granted)
    assert_denied(db_session, operator, author.id, grant.id, {requested})


def test_manuscript_read_cannot_replace_registration_consent(
    db_session, operator, author
):
    grant = create_grant(db_session, operator, author, ["manuscript:read"])
    assert_denied(
        db_session, operator, author.id, grant.id, {"account:register"}
    )


@pytest.mark.parametrize("state", ["not_yet_active", "expired", "revoked"])
def test_inactive_registration_grant_is_denied(
    db_session, operator, author, state
):
    grant = create_grant(db_session, operator, author, ["account:register"])
    now = utc_now()
    if state == "not_yet_active":
        grant.valid_from = now + timedelta(hours=1)
        grant.valid_to = now + timedelta(hours=2)
    elif state == "expired":
        grant.valid_from = now - timedelta(hours=2)
        grant.valid_to = now - timedelta(hours=1)
    else:
        grant.revoked_at = now
    db_session.commit()

    assert_denied(db_session, operator, author.id, grant.id, {"account:register"})


def test_grant_for_another_author_does_not_leak_or_authorize(
    db_session, operator, author
):
    other = Author(display_name="Other private author", alternate_names=[])
    db_session.add(other)
    db_session.commit()
    grant = create_grant(db_session, operator, other, ["account:register"])

    existing_error = assert_denied(
        db_session, operator, author.id, grant.id, {"account:register"}
    )
    missing_error = assert_denied(
        db_session, operator, str(uuid4()), grant.id, {"account:register"}
    )
    assert (existing_error.code, existing_error.message, existing_error.details) == (
        missing_error.code,
        missing_error.message,
        missing_error.details,
    )
    assert other.display_name not in existing_error.message


def test_active_grant_id_must_match_the_requested_authorization(
    db_session, operator, author
):
    other = Author(display_name="Other author", alternate_names=[])
    db_session.add(other)
    db_session.commit()
    create_grant(db_session, operator, author, ["account:register"])
    wrong_grant = create_grant(db_session, operator, other, ["account:register"])

    assert_denied(
        db_session, operator, author.id, wrong_grant.id, {"account:register"}
    )
