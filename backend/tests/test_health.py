from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.core.errors import AppError


@app.get("/__tests__/validation", include_in_schema=False)
def validation_endpoint(required: int):
    return {"required": required}


@app.get("/__tests__/app-error", include_in_schema=False)
def app_error_endpoint():
    raise AppError(409, "CONFLICT", "Conflict", {"field": "example"})


@app.get("/__tests__/unhandled", include_in_schema=False)
def unhandled_endpoint():
    raise RuntimeError("sensitive stack detail")


def assert_error_envelope(response, status_code: int, code: str):
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    assert UUID(body["request_id"])
    assert set(body) == {"code", "message", "request_id", "details"}
    return body


def test_health_is_local_and_public():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_error_envelope_is_flat_and_contains_request_id():
    response = TestClient(app).get("/api/v1/missing")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "RESOURCE_NOT_FOUND"
    assert body["request_id"] == response.headers["x-request-id"]
    assert set(body) == {"code", "message", "request_id", "details"}


def test_request_id_is_a_server_generated_uuid():
    response = TestClient(app).get(
        "/api/v1/health", headers={"X-Request-ID": "client-supplied"}
    )
    request_id = response.headers["x-request-id"]
    assert UUID(request_id)
    assert request_id != "client-supplied"


def test_cors_allows_only_the_configured_local_origin():
    client = TestClient(app)
    allowed = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:5173"}
    )
    denied = client.get(
        "/api/v1/health", headers={"Origin": "https://untrusted.example"}
    )
    assert (
        allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    )
    assert "access-control-allow-origin" not in denied.headers


def test_app_error_uses_the_flat_envelope():
    response = TestClient(app).get("/__tests__/app-error")
    body = assert_error_envelope(response, 409, "CONFLICT")
    assert body["message"] == "Conflict"
    assert body["details"] == {"field": "example"}


def test_method_not_allowed_uses_the_flat_envelope():
    response = TestClient(app).post("/api/v1/health")
    assert_error_envelope(response, 405, "METHOD_NOT_ALLOWED")


def test_validation_error_contains_only_safe_location_and_message():
    response = TestClient(app).get(
        "/__tests__/validation",
        params={"required": "not-an-integer", "password": "do-not-return-this"},
    )
    body = assert_error_envelope(response, 422, "VALIDATION_ERROR")
    assert body["details"]
    assert all(set(item) == {"loc", "message"} for item in body["details"])
    assert "do-not-return-this" not in response.text
    assert "not-an-integer" not in response.text


def test_unhandled_exception_is_logged_without_exposing_a_stack(caplog):
    with caplog.at_level("ERROR", logger="app.main"):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/__tests__/unhandled"
        )
    body = assert_error_envelope(response, 500, "INTERNAL_SERVER_ERROR")
    assert body["details"] is None
    assert "Traceback" not in response.text
    assert "sensitive stack detail" not in response.text
    assert "Unhandled request exception" in caplog.text
    assert "sensitive stack detail" in caplog.text
