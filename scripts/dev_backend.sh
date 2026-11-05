#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    printf 'Project virtualenv Python is required: %s\n' "$PYTHON" >&2
    exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON" -m uvicorn app.main:app --app-dir backend \
    --host 127.0.0.1 --port 8000
