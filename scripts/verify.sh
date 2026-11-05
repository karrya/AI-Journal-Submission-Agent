#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
RUFF="$ROOT_DIR/.venv/bin/ruff"
MYPY="$ROOT_DIR/.venv/bin/mypy"

for tool in "$PYTHON" "$RUFF" "$MYPY"; do
    if [[ ! -x "$tool" ]]; then
        printf '缺少必需的开发工具：%s\n' "$tool" >&2
        exit 1
    fi
done

run() {
    local rendered status
    printf -v rendered '%q ' "$@"
    printf '+ %s\n' "$rendered"
    "$@" || {
        status=$?
        printf '验证失败（退出码 %d）：%s\n' "$status" "$rendered" >&2
        return "$status"
    }
}

cd "$ROOT_DIR/backend"
run "$RUFF" check app tests
run "$MYPY" app
run env ENVIRONMENT=test PYTHONPATH=. "$PYTHON" -m pytest \
    --cov=app --cov-report=json:coverage.json --cov-report=term
run "$PYTHON" ../scripts/check_coverage.py

cd "$ROOT_DIR"
OPENAPI_SNAPSHOT="$(mktemp "${TMPDIR:-/tmp}/asa-openapi.XXXXXX")"
trap 'rm -f "$OPENAPI_SNAPSHOT"' EXIT
cp docs/api/v0.1-openapi.json "$OPENAPI_SNAPSHOT"
run env PYTHONPATH=backend "$PYTHON" scripts/export_openapi.py
run "$PYTHON" -c \
    'import json, sys; from pathlib import Path; from openapi_spec_validator import validate_spec; validate_spec(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))' \
    docs/api/v0.1-openapi.json
run cmp "$OPENAPI_SNAPSHOT" docs/api/v0.1-openapi.json
run bash scripts/test_api.sh
run npm --prefix frontend test
run npm --prefix frontend run test:coverage
run npm --prefix frontend run build

printf '所有验证检查均已通过。\n'
