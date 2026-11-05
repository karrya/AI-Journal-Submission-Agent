# AI-Journal-Submission-Agent

Local V0.1 academic-submission workspace: FastAPI, Vue 3, MySQL 8, server-side sessions, author-scoped authorization, immutable manuscript snapshots, validated file storage, operation audit, and encrypted backups.

## Local development

The selected local installation uses **Homebrew MySQL**, not Docker. Copy `.env.example` to `.env`, fill in local-only values, and run the one-time MySQL bootstrap before migrations and administrator creation. The bootstrap prompts for the MySQL administrative password and generates the application, migration, test, and CSRF secrets; it never requires a default administrator password.

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
.venv/bin/python scripts/bootstrap_mysql.py
```

Complete the protected `.env` settings, then run the migrations twice to prove the second call is a no-op:

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent/backend"
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
cd ..
.venv/bin/python scripts/create_admin.py
```

`create_admin.py` reads the initial password without echoing it and requires a password change at first login. Do not run bootstrap or administrator initialization as part of routine startup.

Start the two development processes in separate terminals:

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/dev_backend.sh
```

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/dev_frontend.sh
```

The backend listens on `127.0.0.1:8000`; open the frontend at `http://127.0.0.1:5173`. The Vite `/api` proxy preserves the browser origin and forwards to the backend. Health is available at `http://127.0.0.1:8000/api/v1/health`.

Run every backend, contract, frontend, coverage, OpenAPI/Newman, and production-build gate with:

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/verify.sh
```

Verification is destructive only to the provisioned `academic_submission_agent_test` database and uses isolated temporary file storage. It refuses non-test or non-loopback database targets and live storage. Do not point test variables at development data.

## Operations and release evidence

- [Operations runbook](docs/operations.md): exact Homebrew setup, bootstrap/desynchronization recovery, migrations, startup, tests, OpenAPI/Postman, reconciliation, age keys, encrypted backup, isolated restore, and unknown-commit recovery.
- [Security notes and matrix](docs/security.md): trust boundaries, role behavior, secret handling, executable security gates, and residual limitations.
- [V0.1 acceptance record](docs/acceptance-v0.1.md): dated clean-install, persistence/restart, real-browser, backup/restore, test/coverage, and unresolved-limit evidence.
- [Backup format and restore safeguards](backups/README.md): archive contents, excluded sessions, SQL validation, and repeatable BACKUP-01 proof.

`docker-compose.yml` is optional and defines only MySQL 8 with a private named volume and no published port, so it does not conflict with Homebrew MySQL. Set `MYSQL_ROOT_PASSWORD` explicitly if you choose to use it; do not start both installations against the same data. The documented and acceptance-tested runtime is Homebrew `mysql@8.0`.
