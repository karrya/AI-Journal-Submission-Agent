"""Registration API authorization, safe responses, and OpenAPI contracts."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    Author,
    AuthorAuthorization,
    Journal,
    JournalSubmissionPortal,
    PlatformAdapter,
    Publisher,
    PublisherAccount,
    PublisherRegistrationSupport,
    OperationLog,
    utc_now,
)


@pytest.fixture
def registration_records(db_session, operator):
    now = utc_now()
    author = Author(display_name="Registration API Author", alternate_names=[])
    publisher = Publisher(name="Elsevier", normalized_name="elsevier")
    adapter = PlatformAdapter(
        adapter_code="TEST_ADAPTER",
        adapter_name="Test Adapter",
        platform_type="TEST_PLATFORM",
        adapter_version="1.0.0",
        support_status="SUPPORTED",
        allowed_domains=["register.example"],
        last_verified_at=now,
    )
    db_session.add_all([author, publisher, adapter])
    db_session.flush()
    journal = Journal(
        publisher_id=publisher.id,
        name="Registration API Journal",
        subject_categories=[],
        article_types=[],
    )
    db_session.add(journal)
    db_session.flush()
    support = PublisherRegistrationSupport(
        publisher_id=publisher.id,
        publisher_code="ELSEVIER",
        display_name=publisher.name,
        support_status="SUPPORTED",
        support_level="V0_1",
        official_domains=["register.example"],
    )
    portal = JournalSubmissionPortal(
        journal_id=journal.id,
        original_url="https://register.example/start",
        final_url="https://register.example/register",
        redirect_chain=[],
        verification_status="VERIFIED",
        access_status="ACCESSIBLE",
        platform_code="TEST_PLATFORM",
        confidence=1.0,
        evidence_summary=[],
        normalized_host="register.example",
        platform_adapter_id=adapter.id,
        support_status="SUPPORTED",
    )
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=operator.id,
        permissions=["account:register"],
        valid_from=now - timedelta(minutes=1),
        valid_to=now + timedelta(hours=1),
    )
    account = PublisherAccount(
        author_id=author.id,
        publisher_id=publisher.id,
        journal_id=journal.id,
        platform_code="TEST_PLATFORM",
        account_namespace="register.example",
        account_email="author@example.com",
        normalized_email="author@example.com",
        credential_ref="secret-credential-reference",
        account_status="REGISTERED",
    )
    db_session.add_all([support, portal, grant, account])
    db_session.commit()
    return SimpleNamespace(
        author=author,
        publisher=publisher,
        journal=journal,
        adapter=adapter,
        support=support,
        portal=portal,
        grant=grant,
        account=account,
        user=operator,
    )


@pytest.fixture
def approved_input(registration_records):
    return {
        "author_id": registration_records.author.id,
        "publisher_id": registration_records.publisher.id,
        "journal_id": registration_records.journal.id,
        "authorization_id": registration_records.grant.id,
        "platform_code": "TEST_PLATFORM",
        "idempotency_key": "registration-api-key-0001",
    }


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert set(response.json()) == {"code", "message", "request_id", "details"}
    assert response.json()["code"] == code


def create_task(client, approved_input):
    response = client.post("/api/v1/registration/tasks", json=approved_input)
    assert response.status_code == 202, response.text
    return response.json()


def test_registration_task_api_hides_secrets_and_enforces_csrf(
    client, operator_context, approved_input
):
    denied = client.post(
        "/api/v1/registration/tasks",
        json=approved_input,
        headers={"X-CSRF-Token": "wrong"},
    )
    assert_error(denied, 403, "SECURITY_CHECK_FAILED")

    created = client.post("/api/v1/registration/tasks", json=approved_input)
    assert created.status_code == 202, created.text
    assert created.json()["task_status"] == "PENDING"
    assert "credential_ref" not in created.text
    assert "verification_url" not in created.text
    assert "password" not in created.text
    assert "token" not in created.text.lower()
    assert "cookie" not in created.text.lower()


def test_registration_catalogs_expose_only_safe_target_metadata(
    client, operator_context, registration_records
):
    publishers = client.get("/api/v1/registration/publishers")
    adapters = client.get("/api/v1/registration/platform-adapters")
    journals = client.get(
        f"/api/v1/registration/publishers/{registration_records.publisher.id}/journals"
    )

    assert publishers.status_code == 200, publishers.text
    assert [item["id"] for item in publishers.json()["items"]] == [
        registration_records.support.id
    ]
    assert adapters.status_code == 200, adapters.text
    assert [item["id"] for item in adapters.json()["items"]] == [
        registration_records.adapter.id
    ]
    assert journals.status_code == 200, journals.text
    assert [item["id"] for item in journals.json()["items"]] == [
        registration_records.journal.id
    ]
    for response in (publishers, adapters, journals):
        assert "credential_ref" not in response.text
        assert "verification_url" not in response.text
        assert "password" not in response.text
        assert "cookie" not in response.text.lower()


def test_registration_task_queries_are_limited_to_current_authorization(
    client,
    operator_context,
    approved_input,
    registration_records,
    user_factory,
    auth_context_factory,
):
    created = create_task(client, approved_input)

    listed = client.get(
        "/api/v1/registration/tasks",
        params={
            "author_id": registration_records.author.id,
            "publisher_id": registration_records.publisher.id,
            "journal_id": registration_records.journal.id,
            "task_status": "PENDING",
        },
    )
    detail = client.get(f"/api/v1/registration/tasks/{created['id']}")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == created["id"]

    other = user_factory("other-registration-operator", roles=("submission_operator",))
    auth_context_factory(other)
    other_list = client.get("/api/v1/registration/tasks")
    other_detail = client.get(f"/api/v1/registration/tasks/{created['id']}")
    assert other_list.status_code == 200, other_list.text
    assert other_list.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}
    assert_error(other_detail, 403, "PERMISSION_DENIED")


def test_registration_task_cancel_and_retry_require_csrf(
    client, operator_context, approved_input
):
    created = create_task(client, approved_input)
    cancel_path = f"/api/v1/registration/tasks/{created['id']}/cancel"
    retry_path = f"/api/v1/registration/tasks/{created['id']}/retry"

    denied = client.post(cancel_path, headers={"X-CSRF-Token": "wrong"})
    assert_error(denied, 403, "SECURITY_CHECK_FAILED")
    cancelled = client.post(cancel_path)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["task_status"] == "CANCELLED"
    retried = client.post(retry_path)
    assert retried.status_code == 200, retried.text
    assert retried.json()["task_status"] == "PENDING"


def test_publisher_accounts_are_scoped_and_hide_credentials(
    client,
    operator_context,
    registration_records,
    user_factory,
    auth_context_factory,
):
    response = client.get("/api/v1/publisher-accounts")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert [item["id"] for item in response.json()["items"]] == [
        registration_records.account.id
    ]
    assert "credential_ref" not in response.text
    assert "secret-credential-reference" not in response.text
    assert "password" not in response.text
    assert "token" not in response.text.lower()
    assert "cookie" not in response.text.lower()

    other = user_factory("other-account-operator", roles=("submission_operator",))
    auth_context_factory(other)
    other_response = client.get("/api/v1/publisher-accounts")
    assert other_response.status_code == 200, other_response.text
    assert other_response.json()["items"] == []
    assert other_response.json()["total"] == 0


def test_only_admins_with_csrf_can_change_registration_configuration(
    client,
    db_session,
    operator_context,
    admin_context,
    registration_records,
    auth_context_factory,
):
    auth_context_factory(operator_context.user)
    support_path = (
        f"/api/v1/registration/publishers/{registration_records.publisher.id}/support"
    )
    support_payload = {
        "publisher_code": "ELSEVIER",
        "display_name": "Elsevier Registration",
        "support_status": "DISABLED",
        "support_level": "V0_1",
        "official_domains": ["register.example"],
        "notes": "temporarily disabled",
    }
    operator_denied = client.put(support_path, json=support_payload)
    assert_error(operator_denied, 403, "PERMISSION_DENIED")

    auth_context_factory(admin_context.user)
    csrf_denied = client.put(
        support_path, json=support_payload, headers={"X-CSRF-Token": "wrong"}
    )
    assert_error(csrf_denied, 403, "SECURITY_CHECK_FAILED")
    updated = client.put(support_path, json=support_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["support_status"] == "DISABLED"

    portal_path = f"/api/v1/registration/submission-portals/{registration_records.portal.id}"
    portal_payload = {
        "platform_adapter_id": registration_records.adapter.id,
        "support_status": "DISABLED",
        "disabled_reason": "adapter maintenance",
    }
    portal_updated = client.patch(portal_path, json=portal_payload)
    assert portal_updated.status_code == 200, portal_updated.text
    db_session.expire_all()
    portal = db_session.get(JournalSubmissionPortal, registration_records.portal.id)
    assert portal is not None
    assert portal.platform_adapter_id == registration_records.adapter.id
    assert portal.support_status == "DISABLED"
    assert portal.disabled_reason == "adapter maintenance"


def test_registration_api_validation_uses_error_response(
    client, operator_context, approved_input
):
    invalid = client.post(
        "/api/v1/registration/tasks",
        json=approved_input | {"idempotency_key": "short"},
    )
    assert_error(invalid, 422, "VALIDATION_ERROR")
    assert invalid.json()["details"]

    invalid_page = client.get("/api/v1/registration/tasks", params={"page_size": 101})
    assert_error(invalid_page, 422, "VALIDATION_ERROR")


def test_registration_openapi_documents_routes_in_chinese_with_standard_errors(client):
    document = client.get("/openapi.json").json()
    expected = {
        "/api/v1/registration/publishers": {"get"},
        "/api/v1/registration/publishers/{publisher_id}/journals": {"get"},
        "/api/v1/registration/publishers/{publisher_id}/support": {"put"},
        "/api/v1/registration/platform-adapters": {"get"},
        "/api/v1/registration/tasks": {"get", "post"},
        "/api/v1/registration/tasks/{task_id}": {"get"},
        "/api/v1/registration/tasks/{task_id}/cancel": {"post"},
        "/api/v1/registration/tasks/{task_id}/retry": {"post"},
        "/api/v1/registration/submission-portals/{portal_id}": {"patch"},
        "/api/v1/publisher-accounts": {"get"},
    }
    for path, methods in expected.items():
        assert path in document["paths"]
        for method in methods:
            operation = document["paths"][path][method]
            assert any("一" <= char <= "鿿" for char in operation["summary"])
            assert operation["responses"]["422"]["content"]["application/json"][
                "schema"
            ] == {"$ref": "#/components/schemas/ErrorResponse"}


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        ("system_admin", 200),
        ("submission_operator", 200),
        ("reviewer", 403),
        ("auditor", 403),
        ("author", 403),
    ],
)
def test_adapter_catalog_role_matrix_and_safe_fields(
    client,
    db_session,
    registration_records,
    user_factory,
    auth_context_factory,
    role,
    expected_status,
):
    registration_records.adapter.capability_config = {
        "credential_ref": "must-not-be-exposed"
    }
    registration_records.adapter.verification_notes = "internal-only-note"
    db_session.commit()
    user = user_factory(f"adapter-{role}", roles=(role,))
    auth_context_factory(user)

    response = client.get("/api/v1/registration/platform-adapters")

    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        item = response.json()["items"][0]
        assert "capability_config" not in item
        assert "verification_notes" not in item
        assert "must-not-be-exposed" not in response.text
        assert "internal-only-note" not in response.text
    else:
        assert_error(response, 403, "PERMISSION_DENIED")


def registration_write_request(kind, approved_input, registration_records):
    if kind == "create":
        return "post", "/api/v1/registration/tasks", approved_input
    if kind in {"cancel", "retry"}:
        return (
            "post",
            f"/api/v1/registration/tasks/{uuid4()}/{kind}",
            None,
        )
    if kind == "publisher_config":
        return (
            "put",
            f"/api/v1/registration/publishers/{registration_records.publisher.id}/support",
            {
                "publisher_code": "ELSEVIER",
                "display_name": "Elsevier",
                "support_status": "SUPPORTED",
                "support_level": "V0_1",
            },
        )
    return (
        "patch",
        f"/api/v1/registration/submission-portals/{registration_records.portal.id}",
        {"support_status": "DISABLED", "disabled_reason": "review test"},
    )


@pytest.mark.parametrize(
    "kind", ["create", "cancel", "retry", "publisher_config", "portal_config"]
)
@pytest.mark.parametrize(
    "mode", ["missing_csrf", "wrong_csrf", "untrusted_origin", "missing_origin"]
)
def test_all_registration_writes_reject_negative_csrf_and_origin(
    client,
    admin_context,
    approved_input,
    registration_records,
    kind,
    mode,
):
    method, path, payload = registration_write_request(
        kind, approved_input, registration_records
    )
    headers = {}
    if mode == "missing_csrf":
        client.headers.pop("X-CSRF-Token", None)
    elif mode == "wrong_csrf":
        headers["X-CSRF-Token"] = "definitely-wrong"
    elif mode == "untrusted_origin":
        headers["Origin"] = "https://attacker.invalid"
    else:
        client.headers.pop("Origin", None)

    response = getattr(client, method)(path, json=payload, headers=headers)

    assert_error(response, 403, "SECURITY_CHECK_FAILED")


@pytest.mark.parametrize(
    "kind", ["create", "cancel", "retry", "publisher_config", "portal_config"]
)
def test_ordinary_users_cannot_use_registration_write_or_config_routes(
    client,
    operator_context,
    reviewer,
    auth_context_factory,
    approved_input,
    registration_records,
    kind,
):
    method, path, payload = registration_write_request(
        kind, approved_input, registration_records
    )
    if kind in {"cancel", "retry"}:
        created = create_task(client, approved_input)
        path = f"/api/v1/registration/tasks/{created['id']}/{kind}"
    auth_context_factory(reviewer)

    response = getattr(client, method)(path, json=payload)

    assert_error(response, 403, "PERMISSION_DENIED")


def test_registration_configuration_success_and_failure_are_audited(
    client,
    db_session,
    admin_context,
    registration_records,
):
    support_path = (
        f"/api/v1/registration/publishers/{registration_records.publisher.id}/support"
    )
    response = client.put(
        support_path,
        json={
            "publisher_code": "ELSEVIER",
            "display_name": "Elsevier",
            "support_status": "DISABLED",
            "support_level": "V0_1",
        },
    )
    assert response.status_code == 200, response.text
    success = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "registration.publisher.configure",
            OperationLog.result == "success",
        )
    )
    assert success is not None
    assert success.after_summary["support_status"] == "DISABLED"
    assert "notes" not in success.after_summary

    other_adapter = PlatformAdapter(
        adapter_code="WRONG_ADAPTER",
        adapter_name="Wrong Adapter",
        platform_type="OTHER_PLATFORM",
        adapter_version="1.0.0",
        support_status="SUPPORTED",
        allowed_domains=["register.example"],
    )
    db_session.add(other_adapter)
    db_session.commit()
    response = client.patch(
        f"/api/v1/registration/submission-portals/{registration_records.portal.id}",
        json={"platform_adapter_id": other_adapter.id},
    )
    assert response.status_code == 422, response.text
    failure = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "registration.portal.configure",
            OperationLog.result == "failure",
        )
    )
    assert failure is not None
    assert failure.error_code == "VALIDATION_ERROR"
