"""Streaming upload checks and safe download filename construction."""

from __future__ import annotations

import codecs
import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

import magic

from app.core.errors import AppError

CHUNK_SIZE = 1024 * 1024
MAX_OOXML_ENTRIES = 2_000
MAX_OOXML_EXPANDED_BYTES = 500 * 1024 * 1024
MAX_OOXML_COMPRESSION_RATIO = 100

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_EXTENSION_MIMES = {
    ".pdf": frozenset({"application/pdf"}),
    ".doc": frozenset({"application/msword"}),
    ".docx": frozenset({DOCX_MIME}),
    ".rtf": frozenset({"application/rtf", "text/rtf"}),
    ".txt": frozenset({"text/plain"}),
    ".tex": frozenset({"application/x-tex", "text/x-tex"}),
    ".csv": frozenset({"text/csv", "application/csv"}),
    ".xls": frozenset({"application/vnd.ms-excel"}),
    ".xlsx": frozenset({XLSX_MIME}),
    ".png": frozenset({"image/png"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".tif": frozenset({"image/tiff"}),
    ".tiff": frozenset({"image/tiff"}),
}
ALLOWED_EXTENSIONS = frozenset(_EXTENSION_MIMES)
_NESTED_ARCHIVE_EXTENSIONS = frozenset(
    {".zip", ".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm", ".odt"}
)
_ACTIVE_TEXT = re.compile(
    rb"<\s*(?:!doctype\s+html|html|script|svg)\b|<\?php|^#!",
    re.IGNORECASE | re.MULTILINE,
)


class UnsupportedFileType(AppError):
    def __init__(self, message: str = "文件类型或内容不受支持"):
        super().__init__(415, "UNSUPPORTED_FILE_TYPE", message)


class FileTooLarge(AppError):
    def __init__(self):
        super().__init__(413, "FILE_TOO_LARGE", "文件超过大小限制")


@dataclass(frozen=True)
class FileDigest:
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ValidatedFile:
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str


def safe_download_filename(filename: str) -> str:
    """Remove header/path controls without using the name as a filesystem path."""
    cleaned = "".join(
        character
        for character in unicodedata.normalize("NFC", filename)
        if character not in {'/', '\\', '"'} and unicodedata.category(character) != "Cc"
    ).strip()
    return cleaned[:255] or "download"


def content_disposition(filename: str) -> str:
    safe = safe_download_filename(filename)
    fallback = unicodedata.normalize("NFKD", safe).encode("ascii", "ignore").decode()
    fallback = re.sub(r"[^A-Za-z0-9._ -]+", "_", fallback).strip(" .")
    fallback = fallback.lstrip(".")[:180] or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(safe, safe='')}"


class FileValidator:
    def __init__(self, *, max_bytes: int = 100 * 1024 * 1024):
        if not 0 < max_bytes <= 500 * 1024 * 1024:
            raise ValueError("max_bytes must be between 1 byte and 500 MiB")
        self.max_bytes = max_bytes

    def store(self, stream, destination: Path) -> FileDigest:
        """Write at most 1 MiB per read, removing all partial output on failure."""
        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("xb") as output:
                while chunk := stream.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise FileTooLarge()
                    digest.update(chunk)
                    output.write(chunk)
            return FileDigest(size, digest.hexdigest())
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def inspect(self, path: Path, filename: str, declared_mime: str) -> ValidatedFile:
        extension = Path(filename).suffix.lower()
        declared = declared_mime.lower().split(";", 1)[0].strip()
        if extension not in ALLOWED_EXTENSIONS or declared not in _EXTENSION_MIMES[extension]:
            raise UnsupportedFileType()
        digest = self._digest(path)
        if digest.size_bytes == 0:
            raise UnsupportedFileType()
        detected = magic.from_file(str(path), mime=True).lower().split(";", 1)[0]
        self._verify_structure(path, extension, detected)
        return ValidatedFile(extension, declared, digest.size_bytes, digest.sha256)

    def _digest(self, path: Path) -> FileDigest:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                size += len(chunk)
                if size > self.max_bytes:
                    raise FileTooLarge()
                digest.update(chunk)
        return FileDigest(size, digest.hexdigest())

    def _verify_structure(self, path: Path, extension: str, detected: str) -> None:
        if extension == ".pdf":
            self._verify_pdf(path, detected)
        elif extension in {".docx", ".xlsx"}:
            self._verify_ooxml(path, extension, detected)
        elif extension in {".doc", ".xls"}:
            self._verify_ole(path, extension, detected)
        elif extension == ".rtf":
            with path.open("rb") as source:
                if source.read(6) != b"{\\rtf1":
                    raise UnsupportedFileType()
        elif extension in {".txt", ".tex", ".csv"}:
            self._verify_text(path, detected)
        elif extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            self._verify_image(path, extension, detected)

    @staticmethod
    def _verify_pdf(path: Path, detected: str) -> None:
        with path.open("rb") as source:
            header = source.read(1024)
            source.seek(-1024, io.SEEK_END) if path.stat().st_size > 1024 else source.seek(0)
            trailer = source.read(1024)
        if detected != "application/pdf" or not header.startswith(b"%PDF-") or b"%%EOF" not in trailer:
            raise UnsupportedFileType()

    @staticmethod
    def _verify_text(path: Path, detected: str) -> None:
        if not detected.startswith("text/"):
            raise UnsupportedFileType()
        decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
        carry = b""
        try:
            with path.open("rb") as source:
                while chunk := source.read(CHUNK_SIZE):
                    decoder.decode(chunk)
                    scanned = carry + chunk
                    if b"\x00" in chunk or _ACTIVE_TEXT.search(scanned):
                        raise UnsupportedFileType()
                    carry = scanned[-64:]
                decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            raise UnsupportedFileType() from None

    @staticmethod
    def _verify_ole(path: Path, extension: str, detected: str) -> None:
        expected_detected = (
            "application/msword" if extension == ".doc" else "application/vnd.ms-excel"
        )
        with path.open("rb") as source:
            header = source.read(8)
            if not header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or detected != expected_detected:
                raise UnsupportedFileType()
            markers = (
                ("WordDocument".encode("utf-16le"),)
                if extension == ".doc"
                else tuple(marker.encode("utf-16le") for marker in ("Workbook", "Book"))
            )
            carry = b""
            found = set()
            while chunk := source.read(CHUNK_SIZE):
                scanned = carry + chunk
                found.update(marker for marker in markers if marker in scanned)
                carry = scanned[-max(map(len, markers)) + 1 :]
        if not found:
            raise UnsupportedFileType()

    @staticmethod
    def _verify_image(path: Path, extension: str, detected: str) -> None:
        expected_mime = _EXTENSION_MIMES[extension]
        valid = detected in expected_mime
        minimum_size = 28 if extension == ".png" else 5 if extension in {".jpg", ".jpeg"} else 4
        if path.stat().st_size < minimum_size:
            raise UnsupportedFileType()
        with path.open("rb") as source:
            header = source.read(16)
            if extension == ".png":
                source.seek(-12, io.SEEK_END)
                trailer = source.read(12)
                valid = (
                    valid
                    and header.startswith(b"\x89PNG\r\n\x1a\n")
                    and header[12:16] == b"IHDR"
                    and trailer.endswith(b"IEND\xaeB`\x82")
                )
            elif extension in {".jpg", ".jpeg"}:
                source.seek(-2, io.SEEK_END)
                valid = (
                    valid
                    and header.startswith(b"\xff\xd8\xff")
                    and source.read(2) == b"\xff\xd9"
                )
            else:
                valid = valid and header.startswith((b"II*\x00", b"MM\x00*"))
        if not valid:
            raise UnsupportedFileType()

    @staticmethod
    def _verify_ooxml(path: Path, extension: str, detected: str) -> None:
        expected_mime = DOCX_MIME if extension == ".docx" else XLSX_MIME
        if detected not in {expected_mime, "application/zip", "application/x-zip-compressed"}:
            raise UnsupportedFileType()
        required_main = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_OOXML_ENTRIES:
                    raise UnsupportedFileType("OOXML entries exceed the 2,000-entry limit")
                expanded = sum(entry.file_size for entry in entries)
                if expanded > MAX_OOXML_EXPANDED_BYTES:
                    raise UnsupportedFileType("OOXML expanded size exceeds the 500 MiB limit")
                for entry in entries:
                    if entry.flag_bits & 1:
                        raise UnsupportedFileType("OOXML 文件不能包含加密条目")
                    if entry.file_size and (
                        entry.compress_size == 0
                        or entry.file_size / entry.compress_size > MAX_OOXML_COMPRESSION_RATIO
                    ):
                        raise UnsupportedFileType("OOXML entry compression ratio exceeds 100:1")
                names = {entry.filename for entry in entries}
                if not {"[Content_Types].xml", "_rels/.rels", required_main} <= names:
                    raise UnsupportedFileType()
                content_types_entry = archive.getinfo("[Content_Types].xml")
                if content_types_entry.file_size > CHUNK_SIZE:
                    raise UnsupportedFileType()
                content_types = archive.read(content_types_entry)
                if b"<!DOCTYPE" in content_types.upper() or b"<!ENTITY" in content_types.upper():
                    raise UnsupportedFileType()
                try:
                    root = ElementTree.fromstring(content_types)
                except ElementTree.ParseError:
                    raise UnsupportedFileType() from None
                expected_main_mime = (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document.main+xml"
                    if extension == ".docx"
                    else "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet.main+xml"
                )
                if not any(
                    element.tag.rsplit("}", 1)[-1] == "Override"
                    and element.attrib.get("PartName") == f"/{required_main}"
                    and element.attrib.get("ContentType") == expected_main_mime
                    for element in root.iter()
                ):
                    raise UnsupportedFileType()
                for entry in entries:
                    if entry.is_dir():
                        continue
                    suffix = Path(entry.filename).suffix.lower()
                    with archive.open(entry) as nested:
                        magic_bytes = nested.read(4)
                    if suffix in _NESTED_ARCHIVE_EXTENSIONS or magic_bytes.startswith(
                        (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
                    ):
                        raise UnsupportedFileType("OOXML nested ZIP containers are forbidden")
        except (zipfile.BadZipFile, KeyError, NotImplementedError, RuntimeError):
            raise UnsupportedFileType() from None
