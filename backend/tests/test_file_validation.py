import base64
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.file_validation import (
    FileTooLarge,
    FileValidator,
    UnsupportedFileType,
    content_disposition,
    safe_download_filename,
)
from app.services.storage import StorageService

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_ooxml(path: Path, *, spreadsheet: bool = False) -> None:
    main = "xl/workbook.xml" if spreadsheet else "word/document.xml"
    main_mime = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
        if spreadsheet
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    )
    main_xml = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets/></workbook>'
        if spreadsheet
        else '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Override PartName="/{main}" ContentType="{main_mime}"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            f'Target="{main}"/></Relationships>',
        )
        archive.writestr(main, main_xml)


def rewrite_ooxml_entry(path: Path, name: str, content: bytes) -> None:
    with zipfile.ZipFile(path) as archive:
        entries = {entry.filename: archive.read(entry) for entry in archive.infolist()}
    entries[name] = content
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry_name, entry_content in entries.items():
            archive.writestr(entry_name, entry_content)


@pytest.mark.parametrize(
    "filename", ["../../etc/passwd", "bad\r\nContent-Disposition: x", "a/b.pdf"]
)
def test_download_filename_cannot_inject_headers_or_paths(filename):
    safe = safe_download_filename(filename)
    assert "\r" not in safe and "\n" not in safe
    assert "/" not in safe and "\\" not in safe
    assert "\x00" not in safe


def test_content_disposition_has_ascii_fallback_and_utf8_international_name():
    header = content_disposition('研究 "final".pdf')
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''" in header
    assert "%E7%A0%94%E7%A9%B6" in header
    assert "\r" not in header and "\n" not in header


def test_mime_spoof_is_rejected(tmp_path):
    payload = tmp_path / "fake.pdf"
    payload.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "fake.pdf", "application/pdf")


def test_valid_pdf_returns_canonical_metadata_and_streamed_hash(tmp_path):
    payload = tmp_path / "paper.pdf"
    payload.write_bytes(PDF)
    result = FileValidator().inspect(payload, "paper.pdf", "application/pdf")
    assert result.extension == ".pdf"
    assert result.mime_type == "application/pdf"
    assert result.size_bytes == len(PDF)
    assert result.sha256 == hashlib.sha256(PDF).hexdigest()


def test_valid_extension_with_wrong_declared_mime_is_rejected(tmp_path):
    payload = tmp_path / "paper.pdf"
    payload.write_bytes(PDF)
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "paper.pdf", "text/plain")


@pytest.mark.parametrize(
    ("filename", "mime", "payload"),
    [
        ("page.html", "text/html", b"<!doctype html><html/>"),
        ("image.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
        ("script.py", "text/x-python", b"print('hello')"),
        ("program.exe", "application/vnd.microsoft.portable-executable", b"MZ"),
        ("archive.zip", "application/zip", b"PK\x03\x04"),
        ("notes.txt", "text/plain", b"<html><script>alert(1)</script></html>"),
    ],
)
def test_general_active_content_is_rejected(tmp_path, filename, mime, payload):
    path = tmp_path / filename
    path.write_bytes(payload)
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(path, filename, mime)


@pytest.mark.parametrize("payload", [b"abcd", b"abcde"])
def test_streaming_enforces_exact_size_limit_and_limit_plus_one(tmp_path, payload):
    destination = tmp_path / "upload.part"
    validator = FileValidator(max_bytes=4)
    if len(payload) == 4:
        assert validator.store(io.BytesIO(payload), destination).size_bytes == 4
        assert destination.read_bytes() == payload
    else:
        with pytest.raises(FileTooLarge):
            validator.store(io.BytesIO(payload), destination)
        assert not destination.exists()


def test_store_reads_one_mib_chunks_and_hashes(tmp_path):
    class RecordingStream(io.BytesIO):
        def __init__(self, value):
            super().__init__(value)
            self.requested = []

        def read(self, size=-1):
            self.requested.append(size)
            return super().read(size)

    stream = RecordingStream(b"abc")
    result = FileValidator().store(stream, tmp_path / "upload.part")
    assert stream.requested == [1024 * 1024, 1024 * 1024]
    assert result.sha256 == hashlib.sha256(b"abc").hexdigest()


def test_store_cleans_partial_file_when_stream_fails(tmp_path):
    class BrokenStream:
        def read(self, size):
            raise OSError("read failed")

    destination = tmp_path / "upload.part"
    with pytest.raises(OSError, match="read failed"):
        FileValidator().store(BrokenStream(), destination)
    assert not destination.exists()


def test_valid_docx_and_xlsx_structures_are_accepted(tmp_path):
    docx = tmp_path / "paper.docx"
    xlsx = tmp_path / "data.xlsx"
    make_ooxml(docx)
    make_ooxml(xlsx, spreadsheet=True)
    assert FileValidator().inspect(docx, "paper.docx", DOCX_MIME).extension == ".docx"
    assert FileValidator().inspect(xlsx, "data.xlsx", XLSX_MIME).extension == ".xlsx"


def test_ooxml_main_part_must_match_extension(tmp_path):
    payload = tmp_path / "wrong.docx"
    make_ooxml(payload, spreadsheet=True)
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "wrong.docx", DOCX_MIME)


def test_ooxml_rejects_more_than_2000_entries(tmp_path):
    payload = tmp_path / "entries.docx"
    make_ooxml(payload)
    with zipfile.ZipFile(payload, "a") as archive:
        for index in range(2000):
            archive.writestr(f"entry-{index}", "")
    with pytest.raises(UnsupportedFileType, match="entries"):
        FileValidator().inspect(payload, "entries.docx", DOCX_MIME)


def test_ooxml_rejects_expanded_size_over_500_mib(tmp_path, monkeypatch):
    payload = tmp_path / "expanded.docx"
    make_ooxml(payload)
    oversized = zipfile.ZipInfo("word/document.xml")
    oversized.file_size = 500 * 1024 * 1024 + 1
    oversized.compress_size = oversized.file_size
    monkeypatch.setattr(zipfile.ZipFile, "infolist", lambda self: [oversized])
    with pytest.raises(UnsupportedFileType, match="expanded"):
        FileValidator().inspect(payload, "expanded.docx", DOCX_MIME)


def test_ooxml_rejects_per_entry_ratio_over_100_to_1(tmp_path):
    payload = tmp_path / "ratio.docx"
    make_ooxml(payload)
    with zipfile.ZipFile(payload, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.bin", b"0" * (1024 * 1024))
    with pytest.raises(UnsupportedFileType, match="ratio"):
        FileValidator().inspect(payload, "ratio.docx", DOCX_MIME)


@pytest.mark.parametrize("nested_name", ["nested.zip", "nested.bin"])
def test_ooxml_rejects_nested_zip_by_extension_or_magic(tmp_path, nested_name):
    payload = tmp_path / "nested.docx"
    make_ooxml(payload)
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("payload", "bad")
    with zipfile.ZipFile(payload, "a") as archive:
        archive.writestr(nested_name, nested.getvalue())
    with pytest.raises(UnsupportedFileType, match="nested"):
        FileValidator().inspect(payload, "nested.docx", DOCX_MIME)


def test_ooxml_rejects_empty_nested_zip_disguised_by_extension(tmp_path):
    payload = tmp_path / "empty-nested.docx"
    make_ooxml(payload)
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w"):
        pass
    with zipfile.ZipFile(payload, "a") as archive:
        archive.writestr("nested.bin", nested.getvalue())
    with pytest.raises(UnsupportedFileType, match="nested"):
        FileValidator().inspect(payload, "empty-nested.docx", DOCX_MIME)


def test_ooxml_main_part_content_type_must_match_extension(tmp_path):
    payload = tmp_path / "macro.docx"
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types><Override PartName="/word/document.xml" '
            'ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/></Types>',
        )
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "macro.docx", DOCX_MIME)


def test_active_content_after_first_chunk_is_rejected(tmp_path):
    payload = tmp_path / "late-html.txt"
    payload.write_bytes(b"a" * (1024 * 1024) + b"<html><script>alert(1)</script></html>")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "late-html.txt", "text/plain")


def test_ooxml_placeholder_relationship_and_arbitrary_main_part_are_rejected(tmp_path):
    payload = tmp_path / "placeholder.docx"
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/document.xml", b"not a Word document")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "placeholder.docx", DOCX_MIME)


def test_ooxml_malicious_main_part_xml_is_rejected_safely(tmp_path):
    payload = tmp_path / "entity.docx"
    make_ooxml(payload)
    rewrite_ooxml_entry(
        payload,
        "word/document.xml",
        b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>',
    )
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "entity.docx", DOCX_MIME)


def test_ooxml_relationship_must_target_expected_main_document(tmp_path):
    payload = tmp_path / "wrong-relationship.xlsx"
    make_ooxml(payload, spreadsheet=True)
    rewrite_ooxml_entry(
        payload,
        "_rels/.rels",
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        b'Target="word/document.xml" TargetMode="External"/></Relationships>',
    )
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "wrong-relationship.xlsx", XLSX_MIME)


def test_ooxml_foreign_namespace_override_is_rejected(tmp_path):
    payload = tmp_path / "foreign-override.docx"
    make_ooxml(payload)
    rewrite_ooxml_entry(
        payload,
        "[Content_Types].xml",
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types" '
        b'xmlns:evil="urn:evil"><evil:Override PartName="/word/document.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b'</Types>',
    )
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "foreign-override.docx", DOCX_MIME)


def test_ooxml_foreign_namespace_relationship_is_rejected(tmp_path):
    payload = tmp_path / "foreign-relationship.docx"
    make_ooxml(payload)
    rewrite_ooxml_entry(
        payload,
        "_rels/.rels",
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" '
        b'xmlns:evil="urn:evil"><evil:Relationship Id="rId1" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        b'Target="word/document.xml"/></Relationships>',
    )
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "foreign-relationship.docx", DOCX_MIME)


def test_ooxml_prefixed_nested_zip_is_rejected(tmp_path):
    payload = tmp_path / "prefixed-nested.docx"
    make_ooxml(payload)
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("payload", "bad")
    with zipfile.ZipFile(payload, "a") as archive:
        archive.writestr("nested.bin", b"MZ" + b"\x00" * 30 + nested.getvalue())
    with pytest.raises(UnsupportedFileType, match="nested"):
        FileValidator().inspect(payload, "prefixed-nested.docx", DOCX_MIME)


@pytest.mark.parametrize("compression", [zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2])
def test_ooxml_truncated_compressed_entry_is_controlled_415(tmp_path, compression):
    payload = tmp_path / "truncated-entry.docx"
    make_ooxml(payload)
    with zipfile.ZipFile(payload) as archive:
        entries = [(entry.filename, archive.read(entry)) for entry in archive.infolist()]
    with zipfile.ZipFile(payload, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    with zipfile.ZipFile(payload) as archive:
        entry = archive.getinfo("word/document.xml")
        with payload.open("rb") as source:
            source.seek(entry.header_offset)
            header = source.read(30)
        name_length = int.from_bytes(header[26:28], "little")
        extra_length = int.from_bytes(header[28:30], "little")
        data_offset = entry.header_offset + 30 + name_length + extra_length
    corrupted = bytearray(payload.read_bytes())
    corrupted[data_offset : data_offset + entry.compress_size] = (
        b"\x00" * entry.compress_size
    )
    payload.write_bytes(corrupted)
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "truncated-entry.docx", DOCX_MIME)


@pytest.mark.parametrize("prefix", [b"\xef\xbb\xbf", b" \t"])
def test_shebang_with_bom_or_leading_whitespace_is_rejected(tmp_path, prefix):
    payload = tmp_path / "script.txt"
    payload.write_bytes(prefix + b"#!/bin/sh\necho unsafe")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "script.txt", "text/plain")


def test_shebang_split_exactly_at_chunk_boundary_is_rejected(tmp_path):
    payload = tmp_path / "boundary-script.txt"
    payload.write_bytes(b" " * (1024 * 1024 - 1) + b"#!/bin/sh\necho unsafe")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "boundary-script.txt", "text/plain")


def test_ole_word_and_excel_structures_cannot_be_swapped(tmp_path):
    payload = tmp_path / "sheet.doc"
    payload.write_bytes(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512 + "Workbook".encode("utf-16le")
    )
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "sheet.doc", "application/msword")


@pytest.mark.parametrize(
    ("filename", "mime", "stream_name"),
    [
        ("fake.doc", "application/msword", "WordDocument"),
        ("fake.xls", "application/vnd.ms-excel", "Workbook"),
    ],
)
def test_ole_signature_and_stream_name_alone_are_not_a_valid_document(
    tmp_path, filename, mime, stream_name
):
    payload = tmp_path / filename
    payload.write_bytes(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        + b"\x00" * 512
        + stream_name.encode("utf-16le")
    )
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, filename, mime)


def test_rtf_text_and_image_structures_are_checked(tmp_path):
    cases = [
        ("note.rtf", "application/rtf", b"{\\rtf1\\ansi safe}"),
        ("note.tex", "application/x-tex", "\\documentclass{article}".encode()),
        (
            "pixel.png",
            "image/png",
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ),
        ),
        ("pixel.jpg", "image/jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"),
        ("pixel.tiff", "image/tiff", b"II*\x00\x08\x00\x00\x00\x00\x00"),
    ]
    for filename, mime, content in cases:
        path = tmp_path / filename
        path.write_bytes(content)
        assert FileValidator().inspect(path, filename, mime).size_bytes == len(content)


@pytest.mark.parametrize(
    ("filename", "mime", "payload"),
    [
        ("short.png", "image/png", b"\x89PNG\r\n\x1a\n"),
        ("short.jpg", "image/jpeg", b"\xff\xd8\xff"),
    ],
)
def test_truncated_image_is_type_error_not_io_error(tmp_path, filename, mime, payload):
    path = tmp_path / filename
    path.write_bytes(payload)
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(path, filename, mime)


def test_storage_generates_only_server_controlled_relative_paths(tmp_path):
    storage = StorageService(tmp_path)
    ids = [str(uuid4()) for _ in range(4)]
    relative = storage.relative_path(*ids, ".pdf")
    assert relative == Path("authors") / ids[0] / "manuscripts" / ids[1] / "versions" / ids[2] / f"{ids[3]}.pdf"
    assert not relative.is_absolute()
    assert storage.resolve(relative).is_relative_to(tmp_path.resolve())


def test_storage_rejects_traversal_absolute_paths_and_invalid_identifiers(tmp_path):
    storage = StorageService(tmp_path)
    with pytest.raises(ValueError):
        storage.resolve(Path("../../secret"))
    with pytest.raises(ValueError):
        storage.resolve(Path("/etc/passwd"))
    with pytest.raises(ValueError):
        storage.relative_path("../author", str(uuid4()), str(uuid4()), str(uuid4()), ".pdf")
    with pytest.raises(ValueError):
        storage.relative_path(str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), ".html")


def test_storage_integrity_streams_and_distinguishes_missing_and_mismatch(tmp_path):
    storage = StorageService(tmp_path)
    path = tmp_path / "payload"
    path.write_bytes(b"abc")
    digest = hashlib.sha256(b"abc").hexdigest()
    assert storage.integrity(path, 3, digest) == "normal"
    assert storage.integrity(path, 4, digest) == "hash_mismatch"
    assert storage.integrity(path, 3, "0" * 64) == "hash_mismatch"
    assert storage.integrity(tmp_path / "missing", 3, digest) == "missing"


def test_reconciliation_manifest_is_append_only_jsonl_with_utc(tmp_path):
    storage = StorageService(tmp_path)
    file_id = str(uuid4())
    storage.append_reconciliation(
        file_id=file_id,
        relative_path=Path("authors/a/file.pdf"),
        sha256="a" * 64,
        event="unknown_commit",
    )
    storage.append_reconciliation(
        file_id=file_id,
        relative_path=Path("authors/a/file.pdf"),
        sha256="a" * 64,
        event="unknown_commit",
    )
    lines = (tmp_path / "reconciliation.jsonl").read_text().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["file_id"] == file_id
    assert record["relative_path"] == "authors/a/file.pdf"
    assert record["sha256"] == "a" * 64
    assert datetime.fromisoformat(record["time"].replace("Z", "+00:00")).tzinfo == UTC
