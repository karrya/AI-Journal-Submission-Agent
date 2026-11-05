import json
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
