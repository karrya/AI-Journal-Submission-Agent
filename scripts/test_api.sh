#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
TEST_DATABASE_NAME="academic_submission_agent_test"

if [[ ! -x "$PYTHON" ]]; then
    printf 'Project virtualenv Python is required: %s\n' "$PYTHON" >&2
    exit 1
fi

# Reuse only the provisioned test URL when the caller did not inject one.
# The value stays in the process environment and is never written to an artifact.
if [[ -z "${TEST_DATABASE_URL:-}" ]]; then
    TEST_DATABASE_URL="$(PYTHONPATH="$ROOT_DIR/backend" "$PYTHON" -c 'from app.core.config import get_settings; print(get_settings().test_database_url or "")')"
fi
if [[ -z "$TEST_DATABASE_URL" ]]; then
    printf 'TEST_DATABASE_URL must be injected or provisioned for the test database.\n' >&2
    exit 1
fi

"$PYTHON" - "$TEST_DATABASE_URL" "$TEST_DATABASE_NAME" <<'PY'
import sys
from sqlalchemy.engine import make_url

url = make_url(sys.argv[1])
if not url.drivername.startswith("mysql+") or url.database != sys.argv[2]:
    raise SystemExit("Refusing to run API contracts against a non-test database")
if url.host not in {"localhost", "127.0.0.1", "::1"}:
    raise SystemExit(
        "Refusing to run API contracts: TEST_DATABASE_URL host must be an "
        "explicit loopback (localhost, 127.0.0.1, or ::1)"
    )
PY

"$PYTHON" - <<'PY'
import socket

with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", 8001)) == 0:
        raise SystemExit("Refusing to run API contracts: 127.0.0.1:8001 is already in use")
PY

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/asa-api-contract.XXXXXX")"
BACKEND_PID=""
cleanup() {
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$WORK_DIR/storage"
export ENVIRONMENT=test
export DATABASE_URL="$TEST_DATABASE_URL"
export ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL"
export STORAGE_ROOT="$WORK_DIR/storage"
export SESSION_COOKIE_SECURE=false
export ALLOWED_ORIGINS='["http://localhost:5173"]'
export CSRF_SECRET_KEY="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')"
export PYTHONPATH="$ROOT_DIR/backend"

new_password() {
    printf 'Aa!%s' "$("$PYTHON" -c 'import secrets; print(secrets.token_hex(16))')"
}
ADMIN_PASSWORD="$(new_password)"
NEW_ADMIN_PASSWORD="$(new_password)"
OPERATOR_PASSWORD="$(new_password)"
EXPIRED_OPERATOR_PASSWORD="$(new_password)"
WRITE_ONLY_OPERATOR_PASSWORD="$(new_password)"
BAD_CSRF_TOKEN="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')"
export ADMIN_PASSWORD NEW_ADMIN_PASSWORD OPERATOR_PASSWORD
export EXPIRED_OPERATOR_PASSWORD WRITE_ONLY_OPERATOR_PASSWORD BAD_CSRF_TOKEN

"$PYTHON" - "$ROOT_DIR" <<'PY'
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

root = Path(sys.argv[1])
os.chdir(root / "backend")
command.upgrade(Config(str(root / "backend" / "alembic.ini")), "head")

from app.core.database import SessionLocal
from app.models import Author, AuthorAuthorization, Role, User, UserRole
from app.security.passwords import hash_password

session = SessionLocal()
try:
    table_names = set(inspect(session.bind).get_table_names())
    if "manuscripts" in table_names:
        session.execute(text("UPDATE manuscripts SET current_version_id = NULL"))
    for table in (
        "operation_logs",
        "manuscript_files",
        "file_families",
        "manuscript_authors",
        "manuscript_versions",
        "manuscripts",
        "journals",
        "journal_platforms",
        "publishers",
        "author_authorizations",
        "author_institutions",
        "author_emails",
        "auth_sessions",
        "user_roles",
        "authors",
        "institutions",
        "roles",
        "users",
    ):
        if table in table_names:
            session.execute(text(f"DELETE FROM `{table}`"))

    roles = {}
    for code, name in (
        ("system_admin", "System Administrator"),
        ("submission_operator", "Submission Operator"),
        ("reviewer", "Reviewer"),
        ("author", "Author"),
        ("auditor", "Auditor"),
    ):
        role = Role(code=code, name=name, description=f"API contract {name}")
        session.add(role)
        roles[code] = role

    users = {}
    user_specs = (
        ("00000000-0000-4000-8000-000000000001", "initial-admin", "ADMIN_PASSWORD", "system_admin", True),
        ("00000000-0000-4000-8000-000000000002", "contract-operator", "OPERATOR_PASSWORD", "submission_operator", False),
        ("00000000-0000-4000-8000-000000000003", "expired-operator", "EXPIRED_OPERATOR_PASSWORD", "submission_operator", False),
        ("00000000-0000-4000-8000-000000000004", "write-only-operator", "WRITE_ONLY_OPERATOR_PASSWORD", "submission_operator", False),
    )
    for user_id, username, password_variable, role_code, must_change in user_specs:
        user = User(
            id=user_id,
            username=username,
            normalized_username=username,
            display_name=username,
            password_hash=hash_password(os.environ[password_variable]),
            status="active",
            must_change_password=must_change,
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=roles[role_code].id))
        users[username] = user

    expired_author = Author(
        id="00000000-0000-4000-8000-000000000005",
        display_name="Expired Grant Author",
        alternate_names=[],
    )
    session.add(expired_author)
    session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(AuthorAuthorization(
        user_id=users["expired-operator"].id,
        author_id=expired_author.id,
        permissions=["author:profile:read"],
        valid_from=now - timedelta(hours=2),
        valid_to=now - timedelta(hours=1),
        reviewed_by=users["initial-admin"].id,
        reviewed_at=now - timedelta(hours=2),
    ))
    session.commit()
finally:
    session.rollback()
    session.close()
PY

cd "$ROOT_DIR"
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 >"$WORK_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

ready=false
for _ in {1..60}; do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        printf 'Isolated API backend exited before becoming ready.\n' >&2
        exit 1
    fi
    if curl --silent --fail --output /dev/null "http://127.0.0.1:8001/api/v1/health"; then
        ready=true
        break
    fi
    sleep 1
done
if [[ "$ready" != true ]]; then
    printf 'Isolated API backend did not become ready within 60 seconds.\n' >&2
    exit 1
fi

npx --prefix "$ROOT_DIR/frontend" newman run \
    "$ROOT_DIR/backend/tests/postman/v0.1.postman_collection.json" \
    --environment "$ROOT_DIR/backend/tests/postman/local.postman_environment.json" \
    --env-var "base_url=http://127.0.0.1:8001" \
    --env-var "ADMIN_PASSWORD=$ADMIN_PASSWORD" \
    --env-var "NEW_ADMIN_PASSWORD=$NEW_ADMIN_PASSWORD" \
    --env-var "OPERATOR_PASSWORD=$OPERATOR_PASSWORD" \
    --env-var "EXPIRED_OPERATOR_PASSWORD=$EXPIRED_OPERATOR_PASSWORD" \
    --env-var "WRITE_ONLY_OPERATOR_PASSWORD=$WRITE_ONLY_OPERATOR_PASSWORD" \
    --env-var "CSRF_TOKEN=" \
    --env-var "BAD_CSRF_TOKEN=$BAD_CSRF_TOKEN" \
    --env-var "asa_session=" \
    --timeout-request 30000 \
    --reporters cli
