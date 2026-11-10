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
