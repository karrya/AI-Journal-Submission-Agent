from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1.contract_manifest import CONTRACTS
from app.schemas import audit, auth, authors, common, files, journals, manuscripts
from app.schemas.authors import (
    AuthorizationCreate,
    AuthorizationResponse,
    AuthorizationUpdate,
    AuthorCreate,
    InstitutionSummaryResponse,
)
from app.schemas.files import FileResponse
from app.schemas.manuscripts import ManuscriptAuthorInput

EXPECTED_ROUTES = {
    ("GET", "/health", "HealthResponse"),
    ("GET", "/health/ready", "HealthResponse"),
    ("POST", "/auth/login", "LoginResponse"),
    ("POST", "/auth/logout", "None"),
    ("GET", "/auth/me", "UserResponse"),
    ("GET", "/auth/csrf", "CsrfResponse"),
    ("POST", "/auth/change-password", "None"),
    ("GET", "/authors", "AuthorPage"),
    ("POST", "/authors", "AuthorResponse"),
    ("GET", "/authors/{author_id}", "AuthorResponse"),
    ("PATCH", "/authors/{author_id}", "AuthorResponse"),
    ("DELETE", "/authors/{author_id}", "None"),
    ("GET", "/authors/{author_id}/emails", "EmailPage"),
    ("POST", "/authors/{author_id}/emails", "EmailResponse"),
    ("PATCH", "/authors/{author_id}/emails/{email_id}", "EmailResponse"),
    ("DELETE", "/authors/{author_id}/emails/{email_id}", "None"),
    ("GET", "/institutions", "InstitutionPage"),
    ("POST", "/institutions", "InstitutionResponse"),
    ("GET", "/institutions/{institution_id}", "InstitutionResponse"),
    ("PATCH", "/institutions/{institution_id}", "InstitutionResponse"),
    ("DELETE", "/institutions/{institution_id}", "None"),
    ("GET", "/authors/{author_id}/institutions", "AuthorInstitutionPage"),
    ("POST", "/authors/{author_id}/institutions", "AuthorInstitutionResponse"),
    (
        "PATCH",
        "/authors/{author_id}/institutions/{link_id}",
        "AuthorInstitutionResponse",
    ),
    ("DELETE", "/authors/{author_id}/institutions/{link_id}", "None"),
    ("GET", "/author-authorizations", "AuthorizationPage"),
    ("POST", "/author-authorizations", "AuthorizationResponse"),
    ("GET", "/author-authorizations/{authorization_id}", "AuthorizationResponse"),
    ("PATCH", "/author-authorizations/{authorization_id}", "AuthorizationResponse"),
    (
        "POST",
        "/author-authorizations/{authorization_id}/revoke",
        "AuthorizationResponse",
    ),
    ("GET", "/manuscripts", "ManuscriptPage"),
    ("POST", "/manuscripts", "ManuscriptResponse"),
    ("GET", "/manuscripts/{manuscript_id}", "ManuscriptResponse"),
    ("PATCH", "/manuscripts/{manuscript_id}", "ManuscriptResponse"),
    ("DELETE", "/manuscripts/{manuscript_id}", "None"),
    ("GET", "/manuscripts/{manuscript_id}/authors", "ManuscriptAuthorList"),
    ("PUT", "/manuscripts/{manuscript_id}/authors", "ManuscriptAuthorList"),
    ("GET", "/manuscripts/{manuscript_id}/versions", "ManuscriptVersionPage"),
    (
        "POST",
        "/manuscripts/{manuscript_id}/versions",
        "ManuscriptVersionResponse",
    ),
    (
        "GET",
        "/manuscripts/{manuscript_id}/versions/{version_id}",
        "ManuscriptVersionResponse",
    ),
    (
        "GET",
        "/manuscripts/{manuscript_id}/versions/{version_id}/files",
        "FilePage",
    ),
    (
        "POST",
        "/manuscripts/{manuscript_id}/versions/{version_id}/files",
        "FileResponse",
    ),
    ("GET", "/files/{file_id}", "FileResponse"),
    ("GET", "/files/{file_id}/download", "FileContent"),
    ("DELETE", "/files/{file_id}", "None"),
    ("GET", "/publishers", "PublisherPage"),
    ("POST", "/publishers", "PublisherResponse"),
    ("GET", "/publishers/{publisher_id}", "PublisherResponse"),
    ("PATCH", "/publishers/{publisher_id}", "PublisherResponse"),
    ("DELETE", "/publishers/{publisher_id}", "None"),
    ("GET", "/journal-platforms", "JournalPlatformPage"),
    ("POST", "/journal-platforms", "JournalPlatformResponse"),
    ("GET", "/journal-platforms/{platform_id}", "JournalPlatformResponse"),
    ("PATCH", "/journal-platforms/{platform_id}", "JournalPlatformResponse"),
    ("DELETE", "/journal-platforms/{platform_id}", "None"),
    ("GET", "/journals", "JournalPage"),
    ("POST", "/journals", "JournalResponse"),
    ("GET", "/journals/{journal_id}", "JournalResponse"),
    ("PATCH", "/journals/{journal_id}", "JournalResponse"),
    ("DELETE", "/journals/{journal_id}", "None"),
    ("GET", "/dashboard/summary", "DashboardSummary"),
    ("GET", "/audit-logs", "AuditLogPage"),
    ("GET", "/audit-logs/{log_id}", "AuditLogResponse"),
}


def valid_authorization(**overrides):
    values = {
        "author_id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "permissions": ["manuscript:read", "manuscript:file:manage"],
        "valid_from": "2026-11-04T00:00:00Z",
        "valid_to": "2027-11-04T00:00:00Z",
        "evidence_ref": "controlled-relative-reference",
        "notes": None,
    }
    values.update(overrides)
    return values


def test_routes_are_unique_and_cover_critical_resources():
    keys = {(item.method, item.path) for item in CONTRACTS}
    assert len(keys) == len(CONTRACTS)
    assert ("POST", "/auth/login") in keys
    assert ("PUT", "/manuscripts/{manuscript_id}/authors") in keys
    assert ("GET", "/files/{file_id}/download") in keys


def test_manifest_matches_the_complete_approved_route_contract():
    actual = {(item.method, item.path, item.response_schema) for item in CONTRACTS}
    assert actual == EXPECTED_ROUTES


def test_manifest_response_names_resolve_to_schema_exports():
    modules = (audit, auth, authors, common, files, journals, manuscripts)
    exported_names = {
        name
        for module in modules
        for name in dir(module)
        if not name.startswith("_")
    }
    exported_names.update(("FileContent", "None"))
    assert {item.response_schema for item in CONTRACTS} <= exported_names


def test_author_input_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AuthorCreate(
            display_name="张三", confirm_identity_change=True, email="not-an-email"
        )


def test_manuscript_author_input_does_not_trust_client_names():
    with pytest.raises(ValidationError) as exc_info:
        ManuscriptAuthorInput(
            author_id="00000000-0000-0000-0000-000000000001",
            position=1,
            is_corresponding=True,
            display_name="伪造",
        )
    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


def test_institution_summary_exposes_only_the_six_approved_fields():
    assert set(InstitutionSummaryResponse.model_fields) == {
        "id",
        "name",
        "institution_type",
        "website_url",
        "country_code",
        "city",
    }


def test_output_model_does_not_pass_through_arbitrary_orm_attributes():
    values = {
        "id": "00000000-0000-0000-0000-000000000001",
        "file_family_id": "00000000-0000-0000-0000-000000000002",
        "manuscript_id": "00000000-0000-0000-0000-000000000003",
        "manuscript_version_id": "00000000-0000-0000-0000-000000000004",
        "file_type": "main_manuscript",
        "display_name": "Main",
        "file_version": 1,
        "original_filename": "main.pdf",
        "mime_type": "application/pdf",
        "extension": ".pdf",
        "size_bytes": 10,
        "sha256": "a" * 64,
        "scan_status": "not_scanned",
        "integrity_status": "normal",
        "status": "active",
        "created_at": "2026-11-04T00:00:00Z",
        "uploaded_by": "00000000-0000-0000-0000-000000000005",
        "storage_path": "/private/main.pdf",
    }
    response = FileResponse.model_validate(SimpleNamespace(**values))
    assert "storage_path" not in response.model_dump()
    assert str(response.id) == values["id"]


def test_authorization_requires_a_finite_validity_period():
    with pytest.raises(ValidationError):
        AuthorizationCreate(**valid_authorization(valid_to=None))
    with pytest.raises(ValidationError):
        AuthorizationCreate(
            **valid_authorization(
                valid_from="2027-11-04T00:00:00Z",
                valid_to="2027-11-04T00:00:00Z",
            )
        )
    with pytest.raises(ValidationError):
        AuthorizationUpdate(valid_to=None)


def test_authorization_create_rejects_mixed_timezone_awareness():
    with pytest.raises(ValidationError, match="时区信息"):
        AuthorizationCreate(
            **valid_authorization(
                valid_from="2026-11-04T00:00:00",
                valid_to="2027-11-04T00:00:00Z",
            )
        )


def test_authorization_update_rejects_mixed_timezone_awareness():
    with pytest.raises(ValidationError, match="时区信息"):
        AuthorizationUpdate(
            valid_from="2026-11-04T00:00:00Z",
            valid_to="2027-11-04T00:00:00",
        )


def test_authorization_permissions_are_known_nonempty_and_unique():
    for permissions in ([], ["unknown:permission"], ["manuscript:read"] * 2):
        with pytest.raises(ValidationError):
            AuthorizationCreate(**valid_authorization(permissions=permissions))


def test_authorization_response_sorts_and_deduplicates_permissions():
    response = AuthorizationResponse(
        **valid_authorization(
            permissions=["manuscript:update", "manuscript:read", "manuscript:update"]
        ),
        id="00000000-0000-0000-0000-000000000003",
        revoked_at=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at="2026-11-04T00:00:00Z",
        updated_at="2026-11-04T00:00:00Z",
        validity_status="active",
    )
    assert response.permissions == ["manuscript:read", "manuscript:update"]


def test_patch_models_reject_an_empty_change_set():
    with pytest.raises(ValidationError):
        authors.AuthorUpdate(confirm_identity_change=True)
    with pytest.raises(ValidationError):
        manuscripts.ManuscriptUpdate()
    with pytest.raises(ValidationError):
        journals.JournalUpdate()


def test_orcid_and_issn_inputs_are_normalized_and_validated():
    author = AuthorCreate(
        display_name="Researcher",
        orcid="https://orcid.org/0000-0002-1825-0097",
        confirm_identity_change=True,
    )
    journal = journals.JournalCreate(
        publisher_id="00000000-0000-0000-0000-000000000001",
        name="Journal",
        issn="0378-5955",
    )
    assert author.orcid == "0000-0002-1825-0097"
    assert journal.issn == "03785955"


def test_secure_urls_reject_unsafe_schemes_and_user_info():
    user_info_url = "https://user:secret" + "@example.com"
    with pytest.raises(ValidationError):
        journals.PublisherCreate(name="Publisher", website_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        journals.PublisherCreate(name="Publisher", website_url=user_info_url)
    assert journals.PublisherCreate(
        name="Publisher", website_url="http://localhost:8000/docs"
    ).website_url


def test_login_and_dashboard_times_use_datetime_types():
    login = auth.LoginResponse(
        user={
            "id": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "display_name": "Administrator",
            "roles": ["system_admin"],
            "status": "active",
            "must_change_password": False,
            "last_login_at": None,
        },
        csrf_token="token",
        idle_expires_at="2026-11-04T00:00:00Z",
        absolute_expires_at="2026-11-05T00:00:00Z",
    )
    summary = audit.DashboardSummary(
        author_count=0,
        manuscript_count=0,
        current_version_file_count=0,
        expiring_authorization_count=0,
        recent_operations=[],
    )
    assert login.idle_expires_at == datetime(2026, 11, 4, tzinfo=UTC)
    assert summary.recent_operations == []
