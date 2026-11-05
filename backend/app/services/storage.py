"""提供服务端控制的路径、原子移动、完整性校验和恢复记录。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
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
            raise ValueError("存储标识符必须是规范格式的 UUID")
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
            raise ValueError("不支持的存储文件扩展名")
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
            raise ValueError("无效的相对存储路径")
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("禁止存储路径穿越")
        resolved = (self.root / relative).resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise ValueError("存储路径不得超出存储根目录")
        return resolved

    def move_into_place(self, temporary: Path, relative_path: Path) -> Path:
        final = self.resolve(relative_path)
        if final.exists():
            raise FileExistsError("正式文件已存在")
        final.parent.mkdir(parents=True, exist_ok=True)
        os.link(temporary, final)
        os.unlink(temporary)
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

    def open_verified(
        self, relative_path: str | Path, expected_size: int, expected_sha256: str
    ) -> tuple[str, int | None]:
        """打开文件时禁止符号链接，并校验后续用于流式传输的同一文件描述符。"""
        relative = Path(relative_path)
        if relative.is_absolute() or not relative.parts or "\\" in str(relative):
            raise ValueError("无效的相对存储路径")
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("禁止存储路径穿越")

        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        file_flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
            file_flags |= os.O_CLOEXEC
        descriptor = None
        keep_open = False
        directory_descriptor = os.open(self.root, directory_flags)
        try:
            for part in relative.parts[:-1]:
                next_descriptor = os.open(
                    part, directory_flags, dir_fd=directory_descriptor
                )
                os.close(directory_descriptor)
                directory_descriptor = next_descriptor
            try:
                descriptor = os.open(
                    relative.parts[-1], file_flags, dir_fd=directory_descriptor
                )
            except FileNotFoundError:
                return "missing", None
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                return "missing", None
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(descriptor, CHUNK_SIZE):
                size += len(chunk)
                digest.update(chunk)
            after = os.fstat(descriptor)
            stable = all(
                getattr(before, field) == getattr(after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            )
            if (
                not stable
                or size != expected_size
                or before.st_size != expected_size
                or digest.hexdigest() != expected_sha256
            ):
                return "hash_mismatch", None
            os.lseek(descriptor, 0, os.SEEK_SET)
            keep_open = True
            return "normal", descriptor
        except FileNotFoundError:
            return "missing", None
        finally:
            os.close(directory_descriptor)
            if descriptor is not None and not keep_open:
                os.close(descriptor)

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
