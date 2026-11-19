#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"
export PYTHONPATH=.
exec "$ROOT_DIR/.venv/bin/python" -m app.workers.run_registration_worker
