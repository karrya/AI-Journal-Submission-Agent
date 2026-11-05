# Operations runbook

All commands below start at the actual project root unless a different directory is shown. Replace only explicitly marked placeholder values; never paste real passwords, session tokens, database URLs, age private keys, or personal file paths into documentation, tickets, shell history, or Git.

```bash
export PROJECT_ROOT="/Users/didi/PycharmProjects/AI Journal Submission Agent"
cd "$PROJECT_ROOT"
```

## 1. Homebrew dependencies and isolated runtime

V0.1 uses Homebrew MySQL 8.0. Docker is optional and is not the tested runtime.

```bash
brew install python@3.13 node mysql@8.0 age libmagic
export PATH="$(brew --prefix mysql@8.0)/bin:$PATH"
brew services start mysql@8.0
mysql --version
mysqldump --version
age --version
node --version
npm --version
```

Keep the MySQL package and its Homebrew dependencies ABI-compatible. If a restart reports a missing versioned `dylib`, stop application writers and run `HOMEBREW_NO_AUTO_UPDATE=1 brew upgrade mysql@8.0`, then `brew services start mysql@8.0`; do not delete or reinitialize `/opt/homebrew/var/mysql`. Verify both development and test connectivity after the package repair. The acceptance log records one such repair from 8.0.42 to 8.0.46 before the successful restart gate.

Install the pinned backend and frontend dependencies. The backend commands in this runbook always use the project virtualenv, not a system Python.

```bash
cd "$PROJECT_ROOT"
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

`backend/requirements-dev.txt` includes the runtime requirements plus pytest, coverage, Ruff, mypy, HTTPX, and OpenAPI validation. `npm ci` installs the exact lockfile, including Newman, Vitest, Vite, TypeScript, and production dependencies.

## 2. Configuration and one-time MySQL bootstrap

Review the non-secret template, then protect the local configuration:

```bash
cd "$PROJECT_ROOT"
cp -n .env.example .env
chmod 600 .env
```

Run bootstrap only for initial provisioning or deliberate credential rotation:

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/bootstrap_mysql.py
```

The script prompts for the MySQL administrative password with hidden input. `MYSQL_ADMIN_USER`, `MYSQL_ADMIN_HOST`, and `MYSQL_ADMIN_PORT` optionally select the administrative endpoint; their defaults are `root`, `localhost`, and `3306`. It creates:

- `academic_submission_agent` for development;
- `academic_submission_agent_test` for destructive automated tests;
- `asa_app@127.0.0.1` with CRUD privileges only on development;
- `asa_migrate@127.0.0.1` with migration privileges only on development;
- `asa_test@127.0.0.1` with privileges only on the fixed test database.

It generates new account passwords and a CSRF secret and writes `.env` atomically with mode `0600` only after the MySQL steps succeed. Complete the other local settings afterward, especially `STORAGE_ROOT`, `ALLOWED_ORIGINS`, and the age/restore settings needed for backup. Do not commit `.env`.

**Bootstrap is not idempotent credential preservation.** Every successful run rotates all three MySQL account passwords and rewrites `.env`; do not run it during ordinary startup or tests.

### Bootstrap password-rotation desynchronization recovery

MySQL user changes cannot participate in the later filesystem rename. If the run rotates one or more MySQL passwords but fails before `.env` is replaced, the old `.env` and new MySQL credentials are desynchronized. Recover as follows:

1. Stop the backend and all other application writers. Do not keep retrying logins or overwrite either database.
2. Check the administrative connection and fix the reason the environment write failed (for example, directory permissions or exhausted disk space). Do not copy credentials into a world-readable temporary file.
3. Run `.venv/bin/python scripts/bootstrap_mysql.py` again interactively after the write problem is fixed. This generates another complete credential set and finishes only after both MySQL and the atomic `.env` replacement succeed. A failed attempt's generated passwords are not recoverable and are never logged.
4. Restore any local non-secret settings that the rewritten `.env` needs, then run migrations/readiness and administrator login checks. Rotate the administrator's password through the application only if there is separate evidence it was exposed; bootstrap does not change application user passwords.

If the administrative connection failed before any `ALTER USER`, the existing `.env` remains authoritative. If a later bootstrap also fails, leave services stopped and repeat the repair rather than guessing passwords.

## 3. Migrations and schema verification

Run the migration command twice. The first reaches head; the second must perform no duplicate data or schema changes. `alembic check` verifies the models match the migrated head.

```bash
cd "$PROJECT_ROOT/backend"
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic check
../.venv/bin/python - <<'PY'
from sqlalchemy import inspect
from app.core.database import SessionLocal

session = SessionLocal()
try:
    names = set(inspect(session.bind).get_table_names())
    application_tables = names - {"alembic_version"}
    assert len(application_tables) == 18, sorted(application_tables)
    assert "alembic_version" in names
    print("18 application tables plus alembic_version; migration head verified")
finally:
    session.close()
PY
```

The schema has 18 application tables; `alembic_version` is migration bookkeeping, so a completely migrated MySQL schema contains 19 tables.

## 4. Hidden administrator creation and first login

After migrations, and only while no application user exists, run:

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/create_admin.py
```

Enter a unique administrator username and a 12–128 character initial password at the hidden prompts. There is no default password. The command creates the fixed role catalog and one `system_admin`, sets `must_change_password=true`, and refuses initialization if any user already exists.

Start the application, sign in at the frontend, and complete the mandatory password-change form. Changing the password revokes existing sessions; sign in again with the new password. Until this is complete, business APIs return `403 PASSWORD_CHANGE_REQUIRED`; only the session identity, CSRF, logout, and change-password routes remain available.

## 5. Backend and frontend startup

Use two terminals so both complete argument lists come from the checked-in scripts:

```bash
cd "$PROJECT_ROOT"
bash scripts/dev_backend.sh
# .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```bash
cd "$PROJECT_ROOT"
bash scripts/dev_frontend.sh
# npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

Verify:

```bash
curl --fail --silent http://127.0.0.1:8000/api/v1/health
curl --fail --silent http://127.0.0.1:5173/ >/dev/null
```

Open `http://127.0.0.1:5173`. Do not expose either development listener on a non-loopback interface. For planned persistence maintenance, stop writes, run the authorized `brew services restart mysql@8.0`, restart both scripts, then verify database records and stored-file SHA-256 values before resuming work.

## 6. Tests, coverage, OpenAPI, and Postman/Newman

The complete release gate is:

```bash
cd "$PROJECT_ROOT"
bash scripts/verify.sh
```

It runs Ruff, mypy, the full MySQL-backed pytest suite, backend total and per-layer coverage floors, deterministic OpenAPI generation and validation, the isolated Newman collection, frontend unit tests and coverage, and the frontend production build. It stops on the first failure and prints the failed command.

Tests require `ENVIRONMENT=test` and a loopback `TEST_DATABASE_URL` whose database is exactly `academic_submission_agent_test`. Pytest creates isolated temporary storage. `scripts/test_api.sh` also creates temporary storage, uses backend port `8001`, generates disposable credentials, and terminates its backend with a trap. Test guards require explicit environment and database-host arguments and reject live/nested-live storage. **These commands delete and recreate test data; never redirect them to development.**

Useful focused commands are:

```bash
cd "$PROJECT_ROOT/backend"
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_security_matrix.py tests/test_authorization_boundaries.py -q
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_backup_restore.py -q
cd "$PROJECT_ROOT"
npm --prefix frontend test
npm --prefix frontend run test:coverage
npm --prefix frontend run build
```

Generate and validate the committed OpenAPI contract independently:

```bash
cd "$PROJECT_ROOT"
PYTHONPATH=backend .venv/bin/python scripts/export_openapi.py
.venv/bin/python -c \
  'import json, sys; from pathlib import Path; from openapi_spec_validator import validate_spec; validate_spec(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))' \
  docs/api/v0.1-openapi.json
git diff --exit-code -- docs/api/v0.1-openapi.json
```

Run the real Postman collection through Newman against its isolated backend:

```bash
cd "$PROJECT_ROOT"
bash scripts/test_api.sh
```

Inputs are `backend/tests/postman/v0.1.postman_collection.json` and `backend/tests/postman/local.postman_environment.json`. Runtime passwords and cookies are generated in memory, not written to the collection or reports.

## 7. Storage reconciliation and unknown file-commit recovery

With the backend configured for the intended development database/storage, run:

```bash
cd "$PROJECT_ROOT"
PYTHONPATH=backend .venv/bin/python scripts/reconcile_files.py
```

The JSON report contains missing file IDs, hash-mismatch IDs, an orphan count (not server paths), and the number of reconciliation manifest entries resolved by matching file ID, relative path, and SHA-256. Active database files that are absent or corrupt are marked with their integrity state and cannot be downloaded until repaired. Reconciliation does not automatically delete uncertain files.

An exception after the formal file move but with an uncertain database commit outcome deliberately preserves the formal file and appends an `unknown_commit` entry to `reconciliation.jsonl`. Recover conservatively:

1. **Do not repeat the upload blindly and do not delete the formal file.** A repeated upload can create a second family version; deletion can destroy the only committed copy.
2. Restore database connectivity and run the reconciliation command. Match the manifest's file ID and SHA-256 with protected database records and the actual file digest; do not expose storage paths in logs.
3. If the database row exists and the digest matches, the commit succeeded. The resolved manifest count increases and normal authorized download can resume.
4. If no row exists after the database is stable, the file is reported as an orphan. Preserve it while investigating the audit trail and manifest. Move it to operator-controlled quarantine only after establishing that it is uncommitted; never treat automatic deletion as recovery.
5. If the row exists but the file is missing or its hash differs, keep the download blocked, quarantine damaged evidence, and restore the verified object from an encrypted backup before rerunning reconciliation.

Certain rollbacks follow a separate compensation path; only unknown outcomes require this non-destructive manifest workflow.

## 8. Age keys, encrypted backup, and isolated restore

Keep the dedicated age private key outside the project and Git. The standard paths are:

```bash
install -d -m 700 "$HOME/.config/academic-submission-agent/age"
umask 077
age-keygen -o "$HOME/.config/academic-submission-agent/age/backup-key.txt"
age-keygen -y "$HOME/.config/academic-submission-agent/age/backup-key.txt" \
  > "$HOME/.config/academic-submission-agent/age/recipient.txt"
chmod 600 "$HOME/.config/academic-submission-agent/age/backup-key.txt" \
  "$HOME/.config/academic-submission-agent/age/recipient.txt"
```

`age-keygen -o` refuses to overwrite an existing key. Never rotate or replace a key merely to run a routine backup; losing the only private key makes existing backups unrecoverable. For each maintenance shell:

```bash
read -r AGE_RECIPIENT < "$HOME/.config/academic-submission-agent/age/recipient.txt"
export AGE_RECIPIENT
export AGE_SECRET_KEY_FILE="$HOME/.config/academic-submission-agent/age/backup-key.txt"
```

The recipient is public, but neither it nor the private-key path needs to be committed. The private key file must not be a symlink, must be outside the project, and must deny group/other access.

Stop the backend, frontend, workers, and every other application writer before backup and keep them stopped through restore verification. Then run:

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/backup.py --confirm-writes-stopped
```

The default destination is the Git-ignored `backups/` directory. The archive contains a single-transaction MySQL dump, storage files, `.env.example`, and per-member SHA-256/size metadata. It excludes `.env`, plaintext passwords, reusable cookies, and `auth_sessions`. Tar bytes stream directly to age; only a completed `.tar.age` is atomically published. A failure removes temporary plaintext and `.partial` output.

For restore, provision an **empty** `academic_submission_agent_restore_test` schema and an account authorized only for that isolated target. Set `RESTORE_DATABASE_URL` in the protected environment and ensure it matches `--database`. The target directory must be new or empty and outside the configured live storage tree.

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/restore.py \
  --backup backups/REPLACE_WITH_BACKUP.tar.age \
  --database academic_submission_agent_restore_test \
  --target-directory /tmp/academic-agent-restored-storage \
  --confirm RESTORE
```

Restore rejects development/non-`_test` targets, nonempty targets, live storage, unsafe archive members, unexpected SQL, schema-qualified SQL references, and every hash mismatch. It verifies the dump, imports only into the validated target, recreates excluded sessions empty, runs `alembic upgrade head` and `alembic check`, and compares row counts, restored files, and hashes. Standalone restore checks source table names and row counts for stability; it does not by itself prove source content or schema immutability.

The stronger real BACKUP-01 proof also compares development table checksums, schema DDL hashes, and storage hashes before/after, verifies age framing and no plaintext/partial artifacts, and removes decrypted restore data:

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/test_backup_restore.py
```

The proof requires the fixed empty restore schema (or an explicitly protected `RESTORE_ADMIN_URL` that can provision only that schema) and the dedicated age key. If development storage is empty, it creates and then deletes one uniquely named proof file; it refuses to touch nonempty development storage. The encrypted archive remains in Git-ignored `backups/`. See `backups/README.md` for format details and limitations.
