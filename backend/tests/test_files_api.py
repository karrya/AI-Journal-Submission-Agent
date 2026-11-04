import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.models import FileFamily, ManuscriptFile, OperationLog
from app.services.files import FileService  # noqa: F401

PDF = (Path(__file__).parent / "fixtures" / "minimal.pdf").read_bytes()
SECOND_PDF = b"%PDF-1.5\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def active_grant(grant_factory, *, user, author, permissions):
    now = datetime.now(UTC)
    return grant_factory(
        user=user,
        author=author,
        permissions=permissions,
        valid_from=now - timedelta(minutes=5),
        valid_to=now + timedelta(hours=1),
    )


def upload_path(manuscript, version_id=None):
    return (
        f"/api/v1/manuscripts/{manuscript.id}/versions/"
        f"{version_id or manuscript.current_version_id}/files"
    )


def post_pdf(client, manuscript, *, content=PDF, data=None, filename="paper.pdf"):
    fields = {"file_type": "main_manuscript", "display_name": "Main manuscript"}
    if data is not None:
        fields = data
    return client.post(
        upload_path(manuscript),
        files={"file": (filename, content, "application/pdf")},
        data=fields,
    )


def test_upload_creates_family_metadata_audit_and_formal_file(
    client, db_session, test_storage_root, manuscript, operator
):
    response = post_pdf(client, manuscript)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["file_type"] == "main_manuscript"
    assert body["display_name"] == "Main manuscript"
    assert body["file_version"] == 1
    assert body["size_bytes"] == len(PDF)
    assert body["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert body["scan_status"] == "not_scanned"
    assert body["integrity_status"] == "normal"
    assert body["uploaded_by"] == operator.id
    assert "storage_path" not in body and "stored_filename" not in body

    record = db_session.get(ManuscriptFile, body["id"])
    family = db_session.get(FileFamily, body["file_family_id"])
    expected = (
        Path("authors")
        / family.author_id
        / "manuscripts"
        / manuscript.id
        / "versions"
        / manuscript.current_version_id
        / f"{record.id}.pdf"
    )
    assert record.storage_path == expected.as_posix()
    assert (test_storage_root / expected).read_bytes() == PDF
    assert not list((test_storage_root / "temp").iterdir())
    audit = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "file.upload", OperationLog.target_id == record.id
        )
    )
    assert audit is not None
    assert "storage_path" not in str(audit.after_summary)


def test_existing_family_upload_allocates_version_two_without_overwrite(
    client, db_session, test_storage_root, manuscript
):
    first = post_pdf(client, manuscript).json()
    first_record = db_session.get(ManuscriptFile, first["id"])
    first_path = test_storage_root / first_record.storage_path
    response = post_pdf(
        client,
        manuscript,
        content=SECOND_PDF,
        data={"file_family_id": first["file_family_id"]},
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["file_version"] == 2
    assert second["file_family_id"] == first["file_family_id"]
    assert second["id"] != first["id"]
    assert first_path.read_bytes() == PDF
    db_session.commit()
    second_record = db_session.get(ManuscriptFile, second["id"])
    assert (test_storage_root / second_record.storage_path).read_bytes() == SECOND_PDF


def test_existing_family_optional_metadata_must_match(client, manuscript):
    first = post_pdf(client, manuscript).json()
    mismatch = post_pdf(
        client,
        manuscript,
        data={"file_family_id": first["file_family_id"], "display_name": "Changed"},
    )
    assert mismatch.status_code == 422
    matching = post_pdf(
        client,
        manuscript,
        data={
            "file_family_id": first["file_family_id"],
            "file_type": "main_manuscript",
            "display_name": "Main manuscript",
        },
    )
    assert matching.status_code == 201


def test_new_family_requires_type_and_display_name(client, manuscript):
    for data in ({"display_name": "Missing type"}, {"file_type": "figure"}):
        response = post_pdf(client, manuscript, data=data)
        assert response.status_code == 422


def test_cross_manuscript_family_is_not_found(client, manuscript):
    response = post_pdf(
        client, manuscript, data={"file_family_id": str(uuid4())}
    )
    assert response.status_code == 404


def test_mime_spoof_returns_415_and_cleans_temp_and_database(
    client, db_session, test_storage_root, manuscript
):
    response = post_pdf(client, manuscript, content=b"<html>not pdf</html>")
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    assert db_session.scalar(select(func.count()).select_from(ManuscriptFile)) == 0
    assert not list((test_storage_root / "temp").iterdir())


def test_upload_rejects_historical_version_with_409(client, manuscript):
    current = manuscript.current_version_id
    created = client.post(f"/api/v1/manuscripts/{manuscript.id}/versions", json={})
    assert created.status_code == 201
    response = client.post(
        upload_path(manuscript, current),
        files={"file": ("paper.pdf", PDF, "application/pdf")},
        data={"file_type": "main_manuscript", "display_name": "Main"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_MANUSCRIPT_STATE"


def test_list_and_get_metadata_require_read_and_never_expose_path(
    client, manuscript
):
    uploaded = post_pdf(client, manuscript).json()
    listing = client.get(upload_path(manuscript))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == uploaded["id"]
    detail = client.get(f"/api/v1/files/{uploaded['id']}")
    assert detail.status_code == 200
    assert "storage_path" not in detail.text
    wrong_version = client.get(upload_path(manuscript, str(uuid4())))
    assert wrong_version.status_code == 404


def test_download_reauthorizes_and_returns_attachment_nosniff_and_safe_name(
    client, test_storage_root, manuscript
):
    uploaded = post_pdf(client, manuscript, filename="../../研究.pdf").json()
    response = client.get(f"/api/v1/files/{uploaded['id']}/download")
    assert response.status_code == 200, response.text
    assert response.content == PDF
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    assert "../" not in disposition and "\r" not in disposition and "\n" not in disposition
    assert response.headers["x-content-type-options"] == "nosniff"
    assert str(test_storage_root) not in str(response.headers)


def test_soft_delete_retains_content_and_denies_metadata_and_download(
    client, db_session, test_storage_root, manuscript
):
    uploaded = post_pdf(client, manuscript).json()
    response = client.delete(f"/api/v1/files/{uploaded['id']}")
    assert response.status_code == 204
    record = db_session.get(ManuscriptFile, uploaded["id"])
    assert record.status == "deleted" and record.deleted_at is not None
    assert (test_storage_root / record.storage_path).exists()
    assert client.get(f"/api/v1/files/{uploaded['id']}").status_code == 404
    assert client.get(f"/api/v1/files/{uploaded['id']}/download").status_code == 404
    audit = db_session.scalar(
        select(OperationLog).where(
            OperationLog.action == "file.delete", OperationLog.target_id == record.id
        )
    )
    assert audit is not None


def test_upload_requires_both_manage_and_read(
    client, user_factory, auth_context_factory, grant_factory, owner, manuscript
):
    manage_only = user_factory("file-manager", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=manage_only,
        author=owner,
        permissions=["manuscript:file:manage"],
    )
    auth_context_factory(manage_only)
    denied = post_pdf(client, manuscript)
    assert denied.status_code == 403

    read_only = user_factory("file-reader", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=read_only,
        author=owner,
        permissions=["manuscript:read"],
    )
    auth_context_factory(read_only)
    assert post_pdf(client, manuscript).status_code == 403


def test_download_requires_manage_but_not_read(
    client, user_factory, auth_context_factory, grant_factory, owner, manuscript
):
    uploaded = post_pdf(client, manuscript).json()
    manage_only = user_factory("download-manager", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=manage_only,
        author=owner,
        permissions=["manuscript:file:manage"],
    )
    auth_context_factory(manage_only)
    assert client.get(f"/api/v1/files/{uploaded['id']}/download").status_code == 200
    assert client.get(f"/api/v1/files/{uploaded['id']}").status_code == 403


def test_overlong_original_filename_is_validation_error_without_temp_files(
    client, test_storage_root, manuscript
):
    response = post_pdf(client, manuscript, filename=f"{'a' * 256}.pdf")
    assert response.status_code == 422
    assert not list((test_storage_root / "temp").iterdir())


def test_unauthorized_upload_is_denied_before_validation_or_storage_write(
    client,
    user_factory,
    auth_context_factory,
    grant_factory,
    owner,
    manuscript,
    test_storage_root,
):
    manage_only = user_factory("preauthorized-file-manager", roles=("submission_operator",))
    active_grant(
        grant_factory,
        user=manage_only,
        author=owner,
        permissions=["manuscript:file:manage"],
    )
    auth_context_factory(manage_only)
    manuscript_access = client.get(f"/api/v1/manuscripts/{manuscript.id}")
    response = post_pdf(client, manuscript, content=b"<html>unauthorized</html>")
    assert manuscript_access.status_code == 403
    assert response.status_code == manuscript_access.status_code
    assert response.json()["code"] == manuscript_access.json()["code"]
    assert response.json()["message"] == manuscript_access.json()["message"]
    assert not list((test_storage_root / "temp").iterdir())
    assert not (test_storage_root / "authors").exists()


def test_upload_requires_authentication(client, manuscript):
    client.cookies.clear()
    response = post_pdf(client, manuscript)
    assert response.status_code == 401
