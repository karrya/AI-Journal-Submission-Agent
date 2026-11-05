import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.models import FileFamily, ManuscriptFile
from app.services.file_validation import FileValidator
from app.services.files import FileService
from app.services.storage import StorageService
from scripts.reconcile_files import reconcile
from test_files_api import PDF, SECOND_PDF, post_pdf


def run_concurrently(first, second):
    barrier = threading.Barrier(2)

    def synchronized(call):
        barrier.wait(timeout=10)
        return call()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(synchronized, call) for call in (first, second)]
        return [future.result(timeout=30) for future in futures]


def test_two_real_mysql_uploads_to_same_family_allocate_one_and_two(
    client,
    second_client,
    db_session,
    manuscript,
    operator,
    auth_context_factory,
):
    family = FileFamily(
        author_id=manuscript.owner_author_id,
        manuscript_id=manuscript.id,
        file_type="main_manuscript",
        display_name="Shared family",
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
    with Session(bind=db_session.get_bind()) as verification:
        records = verification.scalars(
            select(ManuscriptFile).where(ManuscriptFile.file_family_id == family.id)
        ).all()
        assert sorted(record.file_version for record in records) == [1, 2]
        assert len({record.id for record in records}) == 2
        assert len({record.storage_path for record in records}) == 2


def test_current_version_change_during_validation_returns_409_and_cleans_temp(
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
            json={"label": "Changed while uploading"},
        )
        assert version_future.result(timeout=20).status_code == 201
        continue_upload.set()
        response = upload_future.result(timeout=20)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_MANUSCRIPT_STATE"
    assert not list((test_storage_root / "temp").iterdir())
    with Session(bind=db_session.get_bind()) as verification:
        assert verification.scalar(select(func.count()).select_from(ManuscriptFile)) == 0


def direct_service(db_session, operator, test_storage_root):
    return FileService(
        db_session,
        operator,
        str(uuid4()),
        storage=StorageService(test_storage_root),
        session_factory=sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
    )


def upload_direct(service, manuscript):
    return service.upload(
        manuscript_id=manuscript.id,
        version_id=manuscript.current_version_id,
        stream=io.BytesIO(PDF),
        filename="paper.pdf",
        declared_mime="application/pdf",
        file_type="main_manuscript",
        display_name="Main",
    )


def test_default_recovery_connections_never_escape_the_test_schema(
    client, db_engine, db_session, test_storage_root, operator
):
    service = FileService(
        db_session,
        operator,
        str(uuid4()),
        storage=StorageService(test_storage_root),
    )
    original_factory = service.session_factory
    observed_schemas = []

    def checked_recovery_session():
        session = original_factory()
        # Fail before issuing SQL if the production global engine escapes the fixture.
        assert session.get_bind() is db_engine
        observed_schemas.append(session.scalar(text("SELECT DATABASE()")))
        return session

    service.session_factory = checked_recovery_session
    assert service._record_absent_on_new_connection(str(uuid4())) is True
    assert observed_schemas == ["academic_submission_agent_test"]


def test_move_failure_rolls_back_and_cleans_temp(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)

    def fail_move(temporary, relative):
        raise OSError("injected move failure")

    monkeypatch.setattr(service.storage, "move_into_place", fail_move)
    with pytest.raises(OSError, match="injected move failure"):
        upload_direct(service, manuscript)
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0
    assert not list((test_storage_root / "temp").iterdir())


def test_certain_rollback_removes_formal_file_only_after_absence_is_confirmed(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)
    original = service.storage.move_into_place
    moved = []

    def move_then_report_failure(temporary, relative):
        final = original(temporary, relative)
        moved.append(final)
        raise OSError("outcome reported after move")

    monkeypatch.setattr(service.storage, "move_into_place", move_then_report_failure)
    with pytest.raises(OSError, match="outcome reported after move"):
        upload_direct(service, manuscript)
    assert len(moved) == 1
    assert not moved[0].exists()
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0
    assert not (test_storage_root / "reconciliation.jsonl").exists()


def test_temporary_unlink_failure_does_not_skip_certain_formal_compensation(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)
    original_move = service.storage.move_into_place
    original_unlink = Path.unlink
    moved = []

    def move_then_fail(temporary, relative):
        moved.append(original_move(temporary, relative))
        raise OSError("move failed after replacement")

    def fail_only_temp_unlink(path, *args, **kwargs):
        if path.suffix == ".part":
            raise OSError("temporary cleanup failed with sensitive path")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(service.storage, "move_into_place", move_then_fail)
    monkeypatch.setattr(Path, "unlink", fail_only_temp_unlink)
    with pytest.raises(OSError, match="move failed after replacement"):
        upload_direct(service, manuscript)
    assert len(moved) == 1
    assert not moved[0].exists()
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0


def test_failed_move_never_deletes_a_preexisting_formal_file(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)
    file_id = str(uuid4())
    monkeypatch.setattr("app.services.files.uuid4", lambda: UUID(file_id))
    relative = service.storage.relative_path(
        manuscript.owner_author_id,
        manuscript.id,
        manuscript.current_version_id,
        file_id,
        ".pdf",
    )
    final = service.storage.resolve(relative)
    final.parent.mkdir(parents=True)
    final.write_bytes(SECOND_PDF)

    with pytest.raises(FileExistsError):
        upload_direct(service, manuscript)
    assert final.read_bytes() == SECOND_PDF
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0


def test_destination_created_during_publication_is_never_overwritten_or_compensated(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)
    file_id = str(uuid4())
    monkeypatch.setattr("app.services.files.uuid4", lambda: UUID(file_id))
    relative = service.storage.relative_path(
        manuscript.owner_author_id,
        manuscript.id,
        manuscript.current_version_id,
        file_id,
        ".pdf",
    )
    final = service.storage.resolve(relative)
    original_replace = os.replace
    original_link = os.link

    def destination_race(operation):
        def create_then_publish(source, destination, *args, **kwargs):
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(SECOND_PDF)
            return operation(source, destination, *args, **kwargs)

        return create_then_publish

    # Hook both the vulnerable and fixed primitives so the race is deterministic.
    monkeypatch.setattr(os, "replace", destination_race(original_replace))
    monkeypatch.setattr(os, "link", destination_race(original_link))
    with pytest.raises(FileExistsError):
        upload_direct(service, manuscript)

    assert final.read_bytes() == SECOND_PDF
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0
    assert not (test_storage_root / "reconciliation.jsonl").exists()


def test_unknown_commit_outcome_preserves_file_and_appends_manifest(
    db_engine, test_storage_root, manuscript, operator, monkeypatch
):
    connection = db_engine.connect().execution_options(isolation_level="REPEATABLE READ")
    session = Session(bind=connection, expire_on_commit=False)
    sessions = sessionmaker(bind=db_engine, expire_on_commit=False)
    try:
        service = FileService(
            session,
            operator,
            str(uuid4()),
            storage=StorageService(test_storage_root),
            session_factory=sessions,
        )
        original_commit = session.commit

        def commit_then_lose_outcome():
            original_commit()
            raise ConnectionError("connection lost after commit")

        monkeypatch.setattr(session, "commit", commit_then_lose_outcome)
        with pytest.raises(ConnectionError, match="connection lost"):
            upload_direct(service, manuscript)
    finally:
        session.close()
        connection.close()

    with Session(bind=db_engine) as verification:
        record = verification.scalar(select(ManuscriptFile))
        assert record is not None
        formal = test_storage_root / record.storage_path
        assert formal.read_bytes() == PDF
        entries = [
            json.loads(line)
            for line in (test_storage_root / "reconciliation.jsonl").read_text().splitlines()
        ]
        assert entries[-1]["event"] == "unknown_commit"
        assert entries[-1]["file_id"] == record.id
        assert entries[-1]["relative_path"] == record.storage_path
        assert entries[-1]["sha256"] == record.sha256


def test_manifest_append_failure_emits_sanitized_log_and_retains_file(
    db_session,
    test_storage_root,
    manuscript,
    operator,
    monkeypatch,
    caplog,
):
    service = direct_service(db_session, operator, test_storage_root)
    original_commit = db_session.commit

    def commit_then_disconnect():
        original_commit()
        raise ConnectionError("commit outcome unknown")

    def fail_manifest(**kwargs):
        raise OSError("/secret/absolute/reconciliation-path")

    monkeypatch.setattr(db_session, "commit", commit_then_disconnect)
    monkeypatch.setattr(service.storage, "append_reconciliation", fail_manifest)
    with caplog.at_level("ERROR", logger="app.services.files"):
        with pytest.raises(ConnectionError, match="commit outcome unknown"):
            upload_direct(service, manuscript)
    record = db_session.scalar(select(ManuscriptFile))
    assert record is not None
    assert (test_storage_root / record.storage_path).read_bytes() == PDF
    assert not (test_storage_root / "reconciliation.jsonl").exists()
    assert "追加核对清单失败" in caplog.text
    assert record.id in caplog.text and "unknown_commit" in caplog.text
    assert str(test_storage_root) not in caplog.text
    assert record.storage_path not in caplog.text
    assert "/secret/absolute/reconciliation-path" not in caplog.text


def test_unknown_rollback_outcome_never_deletes_uncertain_formal_file(
    db_session, test_storage_root, manuscript, operator, monkeypatch
):
    service = direct_service(db_session, operator, test_storage_root)
    original_move = service.storage.move_into_place
    original_rollback = db_session.rollback
    moved = []

    def move_then_fail(temporary, relative):
        moved.append(original_move(temporary, relative))
        raise OSError("move outcome uncertain")

    def rollback_then_disconnect():
        original_rollback()
        raise ConnectionError("rollback outcome uncertain")

    monkeypatch.setattr(service.storage, "move_into_place", move_then_fail)
    monkeypatch.setattr(db_session, "rollback", rollback_then_disconnect)
    with pytest.raises(OSError, match="move outcome uncertain"):
        upload_direct(service, manuscript)
    assert moved[0].read_bytes() == PDF
    entries = (test_storage_root / "reconciliation.jsonl").read_text().splitlines()
    assert json.loads(entries[-1])["event"] == "unknown_rollback"
    monkeypatch.undo()


def test_missing_and_hash_mismatched_downloads_are_denied_and_marked(
    client, db_session, test_storage_root, manuscript
):
    first = post_pdf(client, manuscript).json()
    first_record = db_session.get(ManuscriptFile, first["id"])
    first_path = test_storage_root / first_record.storage_path
    first_path.unlink()
    db_session.commit()
    missing = client.get(f"/api/v1/files/{first['id']}/download")
    assert missing.status_code == 409
    assert missing.json()["code"] == "FILE_INTEGRITY_ERROR"
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(ManuscriptFile, first["id"]).integrity_status == "missing"

    second = post_pdf(client, manuscript).json()
    db_session.commit()
    second_record = db_session.get(ManuscriptFile, second["id"])
    second_path = test_storage_root / second_record.storage_path
    second_path.write_bytes(SECOND_PDF)
    db_session.commit()
    mismatch = client.get(f"/api/v1/files/{second['id']}/download")
    assert mismatch.status_code == 409
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(ManuscriptFile, second["id"]).integrity_status == "hash_mismatch"


def test_download_rejects_database_path_traversal_without_touching_outside_file(
    client, db_session, test_storage_root, manuscript, tmp_path
):
    uploaded = post_pdf(client, manuscript).json()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(PDF)
    record = db_session.get(ManuscriptFile, uploaded["id"])
    record.storage_path = "../outside.pdf"
    db_session.commit()
    response = client.get(f"/api/v1/files/{uploaded['id']}/download")
    assert response.status_code == 409
    assert outside.read_bytes() == PDF
    assert str(test_storage_root) not in response.text


def test_download_replacement_after_validation_cannot_serve_unvalidated_bytes(
    client, db_session, test_storage_root, manuscript, monkeypatch
):
    uploaded = post_pdf(client, manuscript).json()
    record = db_session.get(ManuscriptFile, uploaded["id"])
    formal = test_storage_root / record.storage_path
    db_session.commit()
    original_download = FileService.download

    def replace_after_validation(service, file_id):
        downloaded = original_download(service, file_id)
        replacement = formal.with_suffix(".replacement")
        replacement.write_bytes(SECOND_PDF)
        os.replace(replacement, formal)
        return downloaded

    monkeypatch.setattr(FileService, "download", replace_after_validation)
    response = client.get(f"/api/v1/files/{uploaded['id']}/download")
    assert response.status_code == 200
    assert response.content == PDF
    assert formal.read_bytes() == SECOND_PDF
    monkeypatch.undo()
    assert client.get(f"/api/v1/files/{uploaded['id']}/download").status_code == 409


def test_reconcile_marks_missing_and_reports_but_never_deletes_orphans(
    client, db_engine, db_session, test_storage_root, manuscript
):
    uploaded = post_pdf(client, manuscript).json()
    record = db_session.get(ManuscriptFile, uploaded["id"])
    (test_storage_root / record.storage_path).unlink()
    orphan = test_storage_root / "authors" / "unregistered.pdf"
    orphan.parent.mkdir(exist_ok=True)
    orphan.write_bytes(PDF)

    report = reconcile(
        storage=StorageService(test_storage_root),
        session_factory=sessionmaker(bind=db_engine, expire_on_commit=False),
    )
    assert report["missing"] == [uploaded["id"]]
    assert report["orphans"] == ["authors/unregistered.pdf"]
    assert orphan.read_bytes() == PDF
    with Session(bind=db_engine) as verification:
        assert verification.get(ManuscriptFile, uploaded["id"]).integrity_status == "missing"


def test_unique_file_version_conflict_is_409_and_cleans_temp(
    client, db_session, test_storage_root, manuscript, operator, monkeypatch
):
    first = post_pdf(client, manuscript).json()
    service = direct_service(db_session, operator, test_storage_root)
    monkeypatch.setattr(service.repository, "next_file_version", lambda family_id: 1)
    with pytest.raises(AppError) as exc_info:
        service.upload(
            manuscript_id=manuscript.id,
            version_id=manuscript.current_version_id,
            stream=io.BytesIO(PDF),
            filename="paper.pdf",
            declared_mime="application/pdf",
            file_family_id=first["file_family_id"],
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "CONFLICT"
    assert not list((test_storage_root / "temp").iterdir())
