"""Report file/database divergence without deleting uncertain formal files."""

from __future__ import annotations

import json
from pathlib import Path
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import create_mysql_engine
from app.models import ManuscriptFile
from app.services.storage import StorageService


def reconcile(*, storage: StorageService, session_factory: sessionmaker) -> dict:
    session = session_factory()
    report = {
        "missing": [],
        "hash_mismatch": [],
        "orphans": [],
        "resolved_manifest_entries": 0,
    }
    try:
        records = session.query(ManuscriptFile).all()
        expected_paths = {record.storage_path for record in records}
        by_id = {record.id: record for record in records}
        for record in records:
            if record.status != "active" or record.deleted_at is not None:
                continue
            try:
                path = storage.resolve(record.storage_path)
                status = storage.integrity(path, record.size_bytes, record.sha256)
            except (ValueError, OSError):
                status = "missing"
            if status != "normal":
                report[status].append(record.id)
                record.integrity_status = status
        for path in storage.root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(storage.root)
            if relative.parts[0] != "authors":
                continue
            relative_string = relative.as_posix()
            if relative_string not in expected_paths:
                report["orphans"].append(relative_string)
        report["orphans"].sort()
        manifest = storage.root / "reconciliation.jsonl"
        if manifest.exists():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record = by_id.get(entry.get("file_id"))
                if (
                    record is not None
                    and record.storage_path == entry.get("relative_path")
                    and record.sha256 == entry.get("sha256")
                ):
                    report["resolved_manifest_entries"] += 1
        session.commit()
        return report
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    settings = get_settings()
    engine = create_mysql_engine(settings.database_url)
    try:
        report = reconcile(
            storage=StorageService(Path(settings.storage_root)),
            session_factory=sessionmaker(bind=engine, expire_on_commit=False),
        )
        # IDs and counts are safe for logs; server-side storage paths are not printed.
        print(
            json.dumps(
                {
                    "missing": report["missing"],
                    "hash_mismatch": report["hash_mismatch"],
                    "orphan_count": len(report["orphans"]),
                    "resolved_manifest_entries": report["resolved_manifest_entries"],
                }
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
