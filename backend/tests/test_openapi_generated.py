import json
import re
from pathlib import Path

from app.api.v1.contract_manifest import CONTRACTS
from app.main import app


def test_fastapi_paths_match_manifest():
    actual = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            actual.add((method.upper(), path.removeprefix("/api/v1")))
    expected = {(item.method, item.path) for item in CONTRACTS}
    assert actual == expected


def test_exported_openapi_matches_generated_schema():
    project_root = Path(__file__).resolve().parents[2]
    artifact = project_root / "docs" / "api" / "v0.1-openapi.json"
    assert json.loads(artifact.read_text(encoding="utf-8")) == app.openapi()


def test_openapi_titles_are_localized_for_readers():
    document = app.openapi()
    untranslated = []

    def check_titles(value, location="document"):
        if isinstance(value, dict):
            for key, item in value.items():
                item_location = f"{location}.{key}"
                if key == "title" and isinstance(item, str):
                    if re.search(r"[一-鿿]", item) is None:
                        untranslated.append((item_location, item))
                else:
                    check_titles(item, item_location)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                check_titles(item, f"{location}[{index}]")

    check_titles(document)
    assert untranslated == []

    schemas = document["components"]["schemas"]
    assert schemas["AuthorUpdate"]["properties"]["display_name"]["title"] == "显示名称"
    assert schemas["ChangePasswordRequest"]["properties"]["current_password"]["title"] == "当前密码"
    assert schemas["FileResponse"]["properties"]["original_filename"]["title"] == "原始文件名"
    assert schemas["FileResponse"]["properties"]["uploaded_by"]["title"] == "上传用户 ID"
    page_size = next(
        parameter
        for parameter in document["paths"]["/api/v1/authors"]["get"]["parameters"]
        if parameter["name"] == "page_size"
    )
    assert page_size["schema"]["title"] == "每页数量"


def test_failed_audit_error_fields_are_in_the_openapi_schema():
    schema = app.openapi()["components"]["schemas"]["AuditLogResponse"]
    assert schema["properties"]["error_code"]["anyOf"][0] == {
        "type": "string",
        "maxLength": 64,
    }
    assert schema["properties"]["error_message"]["anyOf"][0] == {
        "type": "string",
        "maxLength": 1024,
    }


def test_institutional_email_purpose_is_in_openapi_contract():
    schemas = app.openapi()["components"]["schemas"]
    for schema_name in ("EmailCreate", "EmailUpdate", "EmailResponse"):
        purpose = schemas[schema_name]["properties"]["purpose"]
        if "anyOf" in purpose:
            purpose = purpose["anyOf"][0]
        assert "institutional" in purpose["enum"]


def test_extended_manuscript_metadata_is_in_openapi_contract():
    schemas = app.openapi()["components"]["schemas"]
    expected_fields = {
        "funding_number",
        "funding_name",
        "publication_statement",
        "acknowledgements",
        "author_contributions",
        "clinical_trial_number",
    }
    for schema_name in (
        "ManuscriptCreate",
        "ManuscriptUpdate",
        "ManuscriptResponse",
        "ManuscriptSnapshot",
    ):
        assert expected_fields <= set(schemas[schema_name]["properties"])


def test_file_upload_multipart_field_matches_approved_contract():
    document = app.openapi()
    operation = document["paths"][
        "/api/v1/manuscripts/{manuscript_id}/versions/{version_id}/files"
    ]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    if "$ref" in schema:
        component_name = schema["$ref"].rsplit("/", maxsplit=1)[-1]
        schema = document["components"]["schemas"][component_name]

    assert schema["properties"]["file"]["format"] == "binary"
    assert "upload" not in schema["properties"]
    assert set(schema["required"]) == {"file"}


def test_user_management_contract_hides_password_storage():
    document = app.openapi()
    paths = document["paths"]
    assert "/api/v1/users" in paths
    assert "/api/v1/users/{user_id}/reset-password" in paths
    properties = document["components"]["schemas"]["ManagedUserResponse"]["properties"]
    assert "password_hash" not in properties
    assert "password" not in properties
    assert "last_login_at" in properties


def test_identification_contract_present():
    paths = app.openapi()["paths"]
    assert "/api/v1/publishers/options" in paths
    assert "/api/v1/journals/options" in paths
    assert "/api/v1/publishers/search" in paths
    assert "/api/v1/journals/search" in paths
    assert "/api/v1/journals/identify" in paths
    assert "/api/v1/journals/{journal_id}/confirm-identity" in paths
    assert "/api/v1/tasks/{task_id}" in paths


def test_options_contract_binds_response_schemas_and_operation_metadata():
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/publishers/options": (
            "publisher_options_api_v1_publishers_options_get",
            "获取出版社下拉选项",
            "PublisherOptionsResponse",
        ),
        "/api/v1/journals/options": (
            "journal_options_api_v1_journals_options_get",
            "获取期刊下拉选项",
            "JournalOptionsResponse",
        ),
    }
    for path, (operation_id, summary, response_name) in expected.items():
        operation = paths[path]["get"]
        assert operation["operationId"] == operation_id
        assert operation["summary"] == summary
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{response_name}"
        }


def test_options_validation_errors_use_standard_error_schema():
    paths = app.openapi()["paths"]
    for path in ("/api/v1/publishers/options", "/api/v1/journals/options"):
        response = paths[path]["get"]["responses"]["422"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }


def test_manual_portal_create_contract_binds_request_and_response_schemas():
    operation = app.openapi()["paths"]["/api/v1/journals/{journal_id}/submission-portals"]["post"]

    assert operation["summary"] == "人工核验并创建投稿入口"
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RegistrationPortalCreate"
    }
    assert operation["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SubmissionPortalResponse"
    }
    assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
