from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Author, OperationLog
from app.services.audit import AuditService


def record_business_audit(db_session, operator, **overrides):
    arguments = {
        "actor_user_id": operator.id,
        "actor_type": "user",
        "category": "business",
        "action": "author.update",
        "target_type": "author",
        "target_id": str(uuid4()),
        "request_id": str(uuid4()),
        "result": "success",
    }
    arguments.update(overrides)
    return AuditService(db_session).record(**arguments)


def test_audit_persists_only_explicitly_allowlisted_summaries(db_session, operator):
    log = record_business_audit(
        db_session,
        operator,
        before={"title": "Before"},
        after={
            "title": "After",
            "authors": [
                {
                    "author_id": str(uuid4()),
                    "display_name": "Minimal Author",
                    "position": 1,
                    "is_corresponding": True,
                }
            ],
        },
        allowed_fields={
            "title",
            "authors",
            "author_id",
            "display_name",
            "position",
            "is_corresponding",
        },
    )
    db_session.commit()

    stored = db_session.scalar(select(OperationLog).where(OperationLog.id == log.id))
    assert stored.before_summary == {"title": "Before"}
    assert stored.after_summary["title"] == "After"
    assert stored.after_summary["authors"][0]["display_name"] == "Minimal Author"
    assert stored.actor_user_id == operator.id
    assert stored.category == "business"


def test_audit_rejects_fields_outside_explicit_allowlist(db_session, operator):
    with pytest.raises(ValueError, match="允许列表"):
        record_business_audit(
            db_session,
            operator,
            after={"title": "Safe", "internal_note": "Not allowlisted"},
            allowed_fields={"title"},
        )
    db_session.rollback()
    assert db_session.scalar(select(OperationLog)) is None


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "session_token",
        "cookie_value",
        "client_secret",
        "contact_email",
        "phone_number",
        "address_line1",
        "storage_path",
        "storagePath",
        "csrf",
    ],
)
def test_audit_rejects_sensitive_keys_recursively(db_session, operator, key):
    with pytest.raises(ValueError, match="敏感字段键"):
        record_business_audit(
            db_session,
            operator,
            before={"metadata": {key: "must-not-be-persisted"}},
            allowed_fields={"metadata", key},
        )
    db_session.rollback()
    assert db_session.scalar(select(OperationLog)) is None


def test_sensitive_access_audit_omits_values(db_session, operator, author):
    log = record_business_audit(
        db_session,
        operator,
        category="sensitive_access",
        action="author.email.read",
        author_id=author.id,
    )
    db_session.commit()
    stored = db_session.scalar(select(OperationLog).where(OperationLog.id == log.id))
    assert stored.before_summary is None
    assert stored.after_summary is None


def test_audit_insert_failure_rolls_back_business_change(
    db_session, operator, monkeypatch
):
    business_row = Author(display_name="Transactional Audit Author", alternate_names=[])
    original_add = db_session.add

    def fail_audit_add(instance):
        if isinstance(instance, OperationLog):
            raise RuntimeError("forced audit insert failure")
        return original_add(instance)

    monkeypatch.setattr(db_session, "add", fail_audit_add)
    with pytest.raises(RuntimeError, match="forced audit insert failure"):
        try:
            db_session.add(business_row)
            db_session.flush()
            business_id = business_row.id
            record_business_audit(
                db_session,
                operator,
                target_id=business_id,
                author_id=business_id,
                after={"display_name": business_row.display_name},
                allowed_fields={"display_name"},
            )
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    monkeypatch.setattr(db_session, "add", original_add)
    assert db_session.get(Author, business_id) is None
    assert db_session.scalar(select(OperationLog)) is None


def test_audit_service_uses_caller_transaction_without_committing(
    db_session, operator
):
    business_row = Author(display_name="Caller Transaction Author", alternate_names=[])
    db_session.add(business_row)
    db_session.flush()
    business_id = business_row.id
    record_business_audit(
        db_session,
        operator,
        target_id=business_id,
        after={"display_name": business_row.display_name},
        allowed_fields={"display_name"},
    )
    db_session.rollback()

    assert db_session.get(Author, business_id) is None
    assert db_session.scalar(select(OperationLog)) is None
