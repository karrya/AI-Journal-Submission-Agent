"""Executable AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, FILE-01,
FILE-02, FILE-03, FILE-04, FILE-05, and TX-01 security-matrix rows.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuthSession,
    Author,
    FileFamily,
    Manuscript,
    ManuscriptFile,
    OperationLog,
    utc_now,
)
from app.services.audit import AuditService
from app.services.file_validation import FileValidator
from app.services.storage import StorageService
from scripts.reconcile_files import reconcile
from test_file_failures import direct_service, run_concurrently, upload_direct
from test_files_api import PDF, SECOND_PDF, post_pdf

TRUSTED_ORIGIN = "http://localhost:5173"
ERROR_FIELDS = {"code", "message", "request_id", "details"}


def assert_error(response, status: int, code: str) -> dict:
    body = response.json()
    assert response.status_code == status, response.text
    assert body["code"] == code
    assert set(body) == ERROR_FIELDS
    assert body["details"] is None
    return body


def author_payload(**overrides) -> dict:
    payload = {"display_name": "Matrix Author", "confirm_identity_change": True}
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("state", ["missing", "idle", "absolute"])
def test_auth_01_missing_or_expired_session_has_no_business_data(
    client, db_session, operator_context, state
):
    if state == "missing":
        client.cookies.clear()
    else:
        session = db_session.get(AuthSession, operator_context.session.id)
        assert session is not None
        if state == "idle":
            session.idle_expires_at = utc_now() - timedelta(microseconds=1)
        else:
            session.absolute_expires_at = utc_now() - timedelta(microseconds=1)
        db_session.commit()
    response = client.get("/api/v1/manuscripts")
    body = assert_error(response, 401, "UNAUTHORIZED")
    assert "items" not in body and "manuscripts" not in body


@pytest.mark.parametrize("mode", ["missing_csrf", "wrong_csrf", "untrusted_origin"])
def test_auth_02_csrf_and_origin_failures_do_not_change_database(
    client, db_session, admin_context, mode
):
    headers = {"Origin": TRUSTED_ORIGIN}
    if mode == "missing_csrf":
        client.headers.pop("X-CSRF-Token", None)
    elif mode == "wrong_csrf":
        headers["X-CSRF-Token"] = "definitely-wrong"
    else:
        headers["Origin"] = "https://attacker.invalid"
    response = client.post("/api/v1/authors", json=author_payload(), headers=headers)
    assert_error(response, 403, "SECURITY_CHECK_FAILED")
    assert db_session.scalar(select(func.count()).select_from(Author)) == 0
    assert db_session.scalar(select(func.count()).select_from(OperationLog)) == 0


@pytest.mark.parametrize("action", ["logout", "change_password"])
def test_auth_03_revoked_sessions_cannot_be_reused(
    client, db_session, login_initial_admin, action
):
    raw_token = client.cookies.get("asa_session")
    assert raw_token
    client.headers.update(
        {"Origin": TRUSTED_ORIGIN, "X-CSRF-Token": login_initial_admin["csrf_token"]}
    )
    if action == "logout":
        response = client.post("/api/v1/auth/logout")
    else:
        response = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "Test-Initial-Passphrase-2026!",
                "new_password": "Matrix-Replacement-Passphrase-2026!",
            },
        )
    assert response.status_code == 204, response.text
    client.cookies.set("asa_session", raw_token, path="/")
    assert_error(client.get("/api/v1/auth/me"), 401, "UNAUTHORIZED")
    db_session.expire_all()
    sessions = list(db_session.scalars(select(AuthSession)))
    if action == "change_password":
        assert sessions and all(item.revoked_at is not None for item in sessions)
    else:
        current = db_session.scalar(select(AuthSession))
        assert current is not None and current.revoked_at is not None


@pytest.mark.parametrize(
    "path",
    ["/api/v1/authors", "/api/v1/manuscripts", "/api/v1/dashboard/summary"],
)
def test_auth_04_initial_password_gate_is_global(client, login_initial_admin, path):
    response = client.get(path)
    body = assert_error(response, 403, "PASSWORD_CHANGE_REQUIRED")
    assert "items" not in body and "author_count" not in body
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/csrf").status_code == 200


def test_auth_05_two_tabs_share_csrf_and_both_real_mutations_pass(
    client, second_client, admin_context
):
    raw_token = client.cookies.get("asa_session")
    assert raw_token
    second_client.cookies.set("asa_session", raw_token, path="/")
    first_csrf = client.get("/api/v1/auth/csrf")
    second_csrf = second_client.get("/api/v1/auth/csrf")
    assert first_csrf.status_code == second_csrf.status_code == 200
    assert first_csrf.json()["csrf_token"] == second_csrf.json()["csrf_token"]
    second_client.headers.update(
        {"Origin": TRUSTED_ORIGIN, "X-CSRF-Token": second_csrf.json()["csrf_token"]}
    )
    first = client.post(
        "/api/v1/institutions", json={"name": "Matrix Tab One", "country_code": "CN"}
    )
    second = second_client.post(
        "/api/v1/institutions", json={"name": "Matrix Tab Two", "country_code": "CN"}
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]


def test_file_01_spoofed_upload_is_415_without_temp_or_database_record(
    client, db_session, test_storage_root, manuscript
):
    response = post_pdf(client, manuscript, content=b"<html>not a pdf</html>")
    assert_error(response, 415, "UNSUPPORTED_FILE_TYPE")
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0
    assert not list((test_storage_root / "temp").iterdir())


def test_file_02_malicious_filename_cannot_control_paths_or_download_headers(
    client, db_session, test_storage_root, manuscript
):
    filename = "../../matrix-\r\n-injected.pdf"
    uploaded = post_pdf(client, manuscript, filename=filename)
    assert uploaded.status_code == 201, uploaded.text
    record = db_session.get(ManuscriptFile, uploaded.json()["id"])
    assert record is not None
    assert record.storage_path.endswith(f"/{record.id}.pdf")
    assert "matrix-" not in record.storage_path and ".." not in record.storage_path
    assert not (test_storage_root / "matrix-\r\n-injected.pdf").exists()
    response = client.get(f"/api/v1/files/{record.id}/download")
    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert "../" not in disposition and response.headers["x-content-type-options"] == "nosniff"


def test_file_03_real_connections_allocate_versions_one_and_two_without_overwrite(
    client, second_client, db_session, test_storage_root, manuscript, operator, auth_context_factory
):
    family = FileFamily(
        author_id=manuscript.owner_author_id,
        manuscript_id=manuscript.id,
        file_type="main_manuscript",
        display_name="Matrix shared family",
        created_by=operator.id,
    )
    db_session.add(family)
    db_session.commit()
    auth_context_factory(operator, target_client=client)
    auth_context_factory(operator, target_client=second_client)

    def upload(target, content):
        return target.post(
            f"/api/v1/manuscripts/{manuscript.id}/versions/"
            f"{manuscript.current_version_id}/files",
            files={"file": ("paper.pdf", content, "application/pdf")},
            data={"file_family_id": family.id},
        )

    first, second = run_concurrently(
        lambda: upload(client, PDF), lambda: upload(second_client, SECOND_PDF)
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert {first.json()["file_version"], second.json()["file_version"]} == {1, 2}
    records = list(
        db_session.scalars(
            select(ManuscriptFile).where(ManuscriptFile.file_family_id == family.id)
        )
    )
    assert len(records) == 2
    assert len({record.storage_path for record in records}) == 2
    assert {
        (test_storage_root / record.storage_path).read_bytes() for record in records
    } == {PDF, SECOND_PDF}


@pytest.mark.parametrize("after_move", [False, True])
def test_file_04_move_failure_and_certain_rollback_compensate_exactly(
    db_session, test_storage_root, manuscript, operator, monkeypatch, after_move
):
    service = direct_service(db_session, operator, test_storage_root)
    original_move = service.storage.move_into_place
    moved = []

    def fail_move(temporary, relative):
        if after_move:
            moved.append(original_move(temporary, relative))
        raise OSError("matrix move failure")

    monkeypatch.setattr(service.storage, "move_into_place", fail_move)
    with pytest.raises(OSError, match="matrix move failure"):
        upload_direct(service, manuscript)
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0
    assert not list((test_storage_root / "temp").iterdir())
    assert all(not path.exists() for path in moved)
    assert not (test_storage_root / "reconciliation.jsonl").exists()


def test_file_04_unknown_commit_preserves_formal_file_for_reconciliation(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)
    original_commit = db_session.commit

    def commit_then_lose_outcome():
        original_commit()
        raise ConnectionError("matrix commit outcome unknown")

    monkeypatch.setattr(db_session, "commit", commit_then_lose_outcome)
    with pytest.raises(ConnectionError, match="matrix commit outcome unknown"):
        upload_direct(service, manuscript)
    record = db_session.scalar(select(ManuscriptFile))
    assert record is not None
    assert (test_storage_root / record.storage_path).read_bytes() == PDF
    entries = [
        json.loads(line)
        for line in (test_storage_root / "reconciliation.jsonl").read_text().splitlines()
    ]
    assert entries[-1]["event"] == "unknown_commit"
    assert entries[-1]["file_id"] == record.id


def test_file_04_orphans_are_reported_and_missing_formal_files_cannot_download(
    client, db_engine, db_session, test_storage_root, manuscript
):
    uploaded = post_pdf(client, manuscript).json()
    record = db_session.get(ManuscriptFile, uploaded["id"])
    assert record is not None
    (test_storage_root / record.storage_path).unlink()
    orphan = test_storage_root / "authors" / "matrix-orphan.pdf"
    orphan.parent.mkdir(exist_ok=True)
    orphan.write_bytes(PDF)
    report = reconcile(
        storage=StorageService(test_storage_root),
        session_factory=sessionmaker(bind=db_engine, expire_on_commit=False),
    )
    assert report["missing"] == [record.id]
    assert report["orphans"] == ["authors/matrix-orphan.pdf"]
    assert orphan.read_bytes() == PDF
    with Session(bind=db_engine) as verification:
        assert verification.get(ManuscriptFile, record.id).integrity_status == "missing"
    assert_error(
        client.get(f"/api/v1/files/{record.id}/download"), 409, "FILE_INTEGRITY_ERROR"
    )


def test_file_05_version_change_during_validation_is_409_and_cleans_temp(
    client,
    second_client,
    db_session,
    test_storage_root,
    manuscript,
    operator,
    auth_context_factory,
    monkeypatch,
):
    auth_context_factory(operator, target_client=second_client)
    validating = threading.Event()
    continue_upload = threading.Event()
    original = FileValidator.inspect

    def paused_inspect(self, path, filename, declared_mime):
        result = original(self, path, filename, declared_mime)
        validating.set()
        assert continue_upload.wait(timeout=15)
        return result

    monkeypatch.setattr(FileValidator, "inspect", paused_inspect)
    with ThreadPoolExecutor(max_workers=2) as executor:
        upload_future = executor.submit(post_pdf, client, manuscript)
        assert validating.wait(timeout=10)
        version_future = executor.submit(
            second_client.post,
            f"/api/v1/manuscripts/{manuscript.id}/versions",
            json={"label": "Matrix concurrent version"},
        )
        assert version_future.result(timeout=20).status_code == 201
        continue_upload.set()
        response = upload_future.result(timeout=20)
    assert_error(response, 409, "INVALID_MANUSCRIPT_STATE")
    assert not list((test_storage_root / "temp").iterdir())
    with Session(bind=db_session.get_bind()) as verification:
        assert verification.scalar(select(func.count()).select_from(ManuscriptFile)) == 0


def test_tx_01_audit_insert_failure_rolls_back_author_and_audit(
    client, db_session, admin_context, monkeypatch
):
    original_record = AuditService.record

    def fail_business_audit(self, **kwargs):
        if kwargs.get("action") == "author.create":
            raise RuntimeError("matrix audit insert failure")
        return original_record(self, **kwargs)

    monkeypatch.setattr(AuditService, "record", fail_business_audit)
    with pytest.raises(RuntimeError, match="matrix audit insert failure"):
        client.post("/api/v1/authors", json=author_payload())
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Author)) == 0
    assert db_session.scalar(select(func.count()).select_from(Manuscript)) == 0
    assert db_session.scalar(select(func.count()).select_from(OperationLog)) == 0
