"""Server-controlled paths, atomic moves, integrity checks, and recovery records."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.services.file_validation import ALLOWED_EXTENSIONS, CHUNK_SIZE


class StorageService:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or get_settings().storage_root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.temp_root = self.root / "temp"
        self.temp_root.mkdir(exist_ok=True)

    @staticmethod
    def _identifier(value: str) -> str:
        parsed = str(UUID(value))
        if parsed != value.lower():
            raise ValueError("storage identifiers must be canonical UUIDs")
        return parsed

    def temporary_path(self, file_id: str) -> Path:
        return self.temp_root / f"{self._identifier(file_id)}.part"

    def relative_path(
        self,
        author_id: str,
        manuscript_id: str,
        version_id: str,
        file_id: str,
        extension: str,
    ) -> Path:
        identifiers = [
            self._identifier(value)
            for value in (author_id, manuscript_id, version_id, file_id)
        ]
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("unsupported storage extension")
        return (
            Path("authors")
            / identifiers[0]
            / "manuscripts"
            / identifiers[1]
            / "versions"
            / identifiers[2]
            / f"{identifiers[3]}{extension}"
        )

    def resolve(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or not relative.parts or "\\" in str(relative):
            raise ValueError("invalid relative storage path")
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("storage path traversal is forbidden")
        resolved = (self.root / relative).resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise ValueError("storage path escapes the storage root")
        return resolved

    def move_into_place(self, temporary: Path, relative_path: Path) -> Path:
        final = self.resolve(relative_path)
        if final.exists():
            raise FileExistsError("formal file already exists")
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, final)
        return final

    @staticmethod
    def remove(path: Path) -> None:
        path.unlink(missing_ok=True)

    @staticmethod
    def integrity(path: Path, expected_size: int, expected_sha256: str) -> str:
        try:
            source = path.open("rb")
        except FileNotFoundError:
            return "missing"
        digest = hashlib.sha256()
        size = 0
        with source:
            while chunk := source.read(CHUNK_SIZE):
                size += len(chunk)
                digest.update(chunk)
        if size != expected_size or digest.hexdigest() != expected_sha256:
            return "hash_mismatch"
        return "normal"

    def append_reconciliation(
        self,
        *,
        file_id: str,
        relative_path: Path,
        sha256: str,
        event: str,
    ) -> None:
        record = {
            "file_id": file_id,
            "relative_path": relative_path.as_posix(),
            "sha256": sha256,
            "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "event": event,
        }
        encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        descriptor = os.open(
            self.root / "reconciliation.jsonl",
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
