# AI Academic Submission Agent V0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved macOS-local V0.1 application with 18 MySQL tables, layered authorization, author/manuscript/file management, a Vue UI, contract tests, and verified encrypted backup/restore.

**Architecture:** Build a modular FastAPI monolith and a Vue 3 SPA. Establish a machine-readable route/schema contract first, then implement SQLAlchemy models and Alembic migrations, service-layer permissions and transactions, compensating local-file storage, and finally the UI and operational acceptance. Use the running Homebrew MySQL 8 instance; Docker is optional and not required.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, MySQL 8/PyMySQL, Argon2id, Vue 3, TypeScript, Vite, Element Plus, Pinia, Axios, pytest, Postman/Newman, Vitest, age.

**Spec:** `docs/superpowers/specs/2026-11-04-v0-1-design.md`

## Global Constraints

- Implement exactly the 18 core tables and the layered-isolation rules in the approved spec; do not add submission, email-sync, AI, Playwright-business, LangGraph, or scheduler modules.
- Use the existing MySQL 8 server. Tests require a separate database whose name ends in `_test`; never substitute SQLite.
- Runtime uses `asa_app` with DML-only development-database grants; Alembic uses `asa_migrate`; tests use `asa_test` only on the test database.
- Secrets are entered through hidden local prompts or permission-`0600` `.env` files. Never print or commit passwords, raw Session/CSRF tokens, private age keys, or production-like personal files.
- Every author-related query goes through Service authorization. Write permissions never imply read permissions; protected write responses require the corresponding read permission.
- Session Cookie is `asa_session`, HttpOnly, `SameSite=Lax`, `Path=/`; authenticated mutations require Origin and `X-CSRF-Token`, except login which requires Origin and rate limiting only.
- `must_change_password=true` permits only `/auth/me`, `/auth/csrf`, `/auth/change-password`, and `/auth/logout` among authenticated APIs.
- Use UTC `DATETIME(6)`, UUID `CHAR(36)`, InnoDB, utf8mb4, finite authorization intervals, and `ON DELETE RESTRICT` for historical relations.
- Default upload limit is 100 MiB with a 500 MiB hard cap. Only the approved extensions are accepted; OOXML archives require structural and expansion checks. General ZIP files are rejected.
- Business changes and their required audit records share one transaction. Unknown database commit outcomes never trigger immediate deletion of a moved file.
- Coverage targets: permissions 95%, file core 90%, Services 85%, API 80%, backend overall 80%. Security and isolation tests are independent release gates.
- Do not initialize Git or commit until the user explicitly approves it at execution handoff. If approved, use the commit step at the end of each task; otherwise perform the same tests and request a change review without committing.

## Review Focus

1. Authorization boundaries at exact timestamps and multi-role combinations: `valid_from == now` is active, `valid_to == now` is inactive, and disabled users never inherit administrator power. Task 6 owns parametrized boundary tests.
2. Unicode and malicious names: NFC-normalize display names, preserve safe international text, and reject CR/LF or path separators in download headers without corrupting the original database filename. Task 9 owns file-name tests; Task 7 owns author-name tests.
3. Concurrent version creation and upload while the current version changes: use real committed MySQL fixtures, independent connections, and the lock order manuscript → file family. Tasks 8 and 9 own race tests.
4. Unknown commit outcomes and process interruption: preserve the file, append a local reconciliation record, and reconcile by file ID and relative path before any cleanup. Task 9 owns fault-injection tests.
5. Backup interruption and wrong restore targets: never leave a plausible unencrypted partial archive and never overwrite development data. Task 16 owns interruption and wrong-target tests.

## File Map

- `backend/app/core/`: settings, database, Request ID, errors, logging.
- `backend/app/models/`: 18 SQLAlchemy entities split by identity, authors, manuscripts, files, journals, and audit.
- `backend/app/schemas/`: request/response models and the route contract manifest.
- `backend/app/security/`: Argon2id, Session, CSRF, and principal objects.
- `backend/app/repositories/`: persistence queries only.
- `backend/app/services/`: permissions, audit, domain transactions, serializers, and storage compensation.
- `backend/app/api/v1/`: HTTP dependencies and resource routers.
- `backend/alembic/`: two explicit schema migrations and environment configuration.
- `backend/tests/`: unit, MySQL integration, API, concurrency, fault injection, and Postman assets.
- `frontend/src/`: typed API client, auth store, router, reusable forms/tables, and domain views.
- `scripts/`: MySQL bootstrap, administrator creation, OpenAPI export, file reconciliation, encrypted backup/restore, and verification.
- `docs/api/v0.1-openapi.json`: generated API contract checked against the manifest.

---

### Task 1: Backend Foundation, Configuration, and Health

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/pytest.ini`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/errors.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`
- Create: `.env.example`
- Create: `.gitignore`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `AppError`, `request_context`, `app`, and `GET /api/v1/health` returning `{"status":"ok"}`.
- Later tasks consume: `get_settings()`, the global error envelope, and the FastAPI `app`.

- [ ] **Step 1: Create the dependency and test configuration**

```text
# backend/requirements.txt
fastapi==0.115.12
uvicorn[standard]==0.34.2
SQLAlchemy==2.0.41
PyMySQL==1.1.1
alembic==1.16.1
pydantic==2.11.4
pydantic-settings==2.9.1
email-validator==2.2.0
argon2-cffi==23.1.0
python-multipart==0.0.20
python-magic==0.4.27
```

```text
# backend/requirements-dev.txt
-r requirements.txt
pytest==8.3.5
pytest-cov==6.1.1
httpx==0.28.1
ruff==0.11.8
mypy==1.15.0
openapi-spec-validator==0.7.1
```

```ini
# backend/pytest.ini
[pytest]
testpaths = tests
addopts = -q
filterwarnings = error
```

Run: `../.venv/bin/python -m pip install -r backend/requirements-dev.txt` from the project root, then `brew install node age libmagic`.

- [ ] **Step 2: Write failing health and error-envelope tests**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app


def test_health_is_local_and_public():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_error_envelope_is_flat_and_contains_request_id():
    response = TestClient(app).get("/api/v1/missing")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "RESOURCE_NOT_FOUND"
    assert body["request_id"] == response.headers["x-request-id"]
    assert set(body) == {"code", "message", "request_id", "details"}
```

- [ ] **Step 3: Run the tests and confirm the missing application failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_health.py -q`
Expected: collection fails because `app.main` does not exist.

- [ ] **Step 4: Implement settings, Request ID, errors, and health**

```python
# backend/app/core/config.py
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    app_name: str = "Academic Submission Agent"
    environment: str = "development"
    database_url: str = "mysql+pymysql://unset:unset@127.0.0.1/unset"
    alembic_database_url: str | None = None
    test_database_url: str | None = None
    csrf_secret_key: str = ""
    allowed_origins: list[str] = ["http://localhost:5173"]
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, le=500 * 1024 * 1024)
    storage_root: str = str(PROJECT_ROOT / "storage")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# backend/app/core/errors.py
from uuid import uuid4


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.request_id = str(uuid4())
```

```python
# backend/app/main.py
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.errors import AppError
from app.core.config import get_settings

app = FastAPI(title="Academic Submission Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message,
                 "request_id": request.state.request_id, "details": exc.details},
    )


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"code": "RESOURCE_NOT_FOUND", "message": "资源不存在",
                 "request_id": request.state.request_id, "details": None},
    )
```

Also register `RequestValidationError`, `StarletteHTTPException`, and unhandled-exception handlers so 405, 422, and 500 use the same envelope. Validation details contain only field location and a safe message; the 500 handler logs the exception server-side and returns `INTERNAL_SERVER_ERROR` without a stack.

Add `.env` entries only for non-secret examples. Ignore `.env`, `storage/*`, `backups/*`, logs, `.venv`, `node_modules`, and generated coverage output.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && PYTHONPATH=. pytest tests/test_health.py -q`
Expected: 2 passed.

```bash
git add backend .env.example .gitignore
git commit -m "chore: add backend foundation and health contract"
```

---

### Task 2: Machine-Readable API Contract and Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/schemas/authors.py`
- Create: `backend/app/schemas/manuscripts.py`
- Create: `backend/app/schemas/files.py`
- Create: `backend/app/schemas/journals.py`
- Create: `backend/app/schemas/audit.py`
- Create: `backend/app/api/v1/contract_manifest.py`
- Test: `backend/tests/test_contract_manifest.py`

**Interfaces:**
- Produces: all request/response Schema names in spec §3 and `CONTRACTS: tuple[RouteContract, ...]`.
- Later tasks consume: the exact Schema names and route paths; no router may silently diverge from the manifest.

- [ ] **Step 1: Write failing schema and route-coverage tests**

```python
# backend/tests/test_contract_manifest.py
from app.api.v1.contract_manifest import CONTRACTS
from app.schemas.authors import AuthorCreate, AuthorResponse
from app.schemas.manuscripts import ManuscriptAuthorInput
from pydantic import ValidationError
import pytest


def test_routes_are_unique_and_cover_critical_resources():
    keys = {(item.method, item.path) for item in CONTRACTS}
    assert len(keys) == len(CONTRACTS)
    assert ("POST", "/auth/login") in keys
    assert ("PUT", "/manuscripts/{manuscript_id}/authors") in keys
    assert ("GET", "/files/{file_id}/download") in keys


def test_author_input_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AuthorCreate(display_name="张三", confirm_identity_change=True, email="not-an-email")


def test_manuscript_author_input_does_not_trust_client_names():
    with pytest.raises(ValidationError):
        ManuscriptAuthorInput(author_id="00000000-0000-0000-0000-000000000001", position=1,
                              is_corresponding=True, display_name="伪造")
```

- [ ] **Step 2: Run contract tests and confirm failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_contract_manifest.py -q`
Expected: imports fail because the schemas and manifest do not exist.

- [ ] **Step 3: Implement strict common schemas and domain models**

```python
# backend/app/schemas/common.py
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorResponse(OutputModel):
    code: str
    message: str
    request_id: str
    details: list[dict] | dict | None


class HealthResponse(OutputModel):
    status: str


class Page(OutputModel, Generic[T]):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
```

```python
# backend/app/schemas/manuscripts.py
from uuid import UUID
from pydantic import Field
from app.schemas.common import InputModel, OutputModel


class ManuscriptAuthorInput(InputModel):
    author_id: UUID
    position: int = Field(ge=1)
    is_corresponding: bool


class ManuscriptAuthorResponse(OutputModel):
    author_id: UUID
    display_name: str
    position: int
    is_corresponding: bool
```

Implement the approved fields for `AuthorCreate`, `AuthorUpdate`, `AuthorResponse`, email/institution models, finite `AuthorizationCreate`, manuscript/version models, `FileResponse`, journal models, `AuditLogResponse`, and `DashboardSummary`. `InstitutionSummaryResponse` contains only `id`, `name`, `institution_type`, `website_url`, `country_code`, and `city`; `InstitutionResponse` is administrator-only. Optional sensitive response fields are never populated without their specific permission.

- [ ] **Step 4: Encode the complete route manifest**

```python
# backend/app/api/v1/contract_manifest.py
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteContract:
    method: str
    path: str
    response_schema: str


CONTRACTS = (
    RouteContract("GET", "/health", "HealthResponse"),
    RouteContract("GET", "/health/ready", "HealthResponse"),
    RouteContract("POST", "/auth/login", "LoginResponse"),
    RouteContract("POST", "/auth/logout", "None"),
    RouteContract("GET", "/auth/me", "UserResponse"),
    RouteContract("GET", "/auth/csrf", "CsrfResponse"),
    RouteContract("POST", "/auth/change-password", "None"),
    RouteContract("GET", "/authors", "AuthorPage"),
    RouteContract("POST", "/authors", "AuthorResponse"),
    RouteContract("GET", "/authors/{author_id}", "AuthorResponse"),
    RouteContract("PATCH", "/authors/{author_id}", "AuthorResponse"),
    RouteContract("DELETE", "/authors/{author_id}", "None"),
    RouteContract("GET", "/authors/{author_id}/emails", "EmailPage"),
    RouteContract("POST", "/authors/{author_id}/emails", "EmailResponse"),
    RouteContract("PATCH", "/authors/{author_id}/emails/{email_id}", "EmailResponse"),
    RouteContract("DELETE", "/authors/{author_id}/emails/{email_id}", "None"),
    RouteContract("GET", "/institutions", "InstitutionPage"),
    RouteContract("POST", "/institutions", "InstitutionResponse"),
    RouteContract("GET", "/institutions/{institution_id}", "InstitutionResponse"),
    RouteContract("PATCH", "/institutions/{institution_id}", "InstitutionResponse"),
    RouteContract("DELETE", "/institutions/{institution_id}", "None"),
    RouteContract("GET", "/authors/{author_id}/institutions", "AuthorInstitutionPage"),
    RouteContract("POST", "/authors/{author_id}/institutions", "AuthorInstitutionResponse"),
    RouteContract("PATCH", "/authors/{author_id}/institutions/{link_id}", "AuthorInstitutionResponse"),
    RouteContract("DELETE", "/authors/{author_id}/institutions/{link_id}", "None"),
    RouteContract("GET", "/author-authorizations", "AuthorizationPage"),
    RouteContract("POST", "/author-authorizations", "AuthorizationResponse"),
    RouteContract("GET", "/author-authorizations/{authorization_id}", "AuthorizationResponse"),
    RouteContract("PATCH", "/author-authorizations/{authorization_id}", "AuthorizationResponse"),
    RouteContract("POST", "/author-authorizations/{authorization_id}/revoke", "AuthorizationResponse"),
    RouteContract("GET", "/manuscripts", "ManuscriptPage"),
    RouteContract("POST", "/manuscripts", "ManuscriptResponse"),
    RouteContract("GET", "/manuscripts/{manuscript_id}", "ManuscriptResponse"),
    RouteContract("PATCH", "/manuscripts/{manuscript_id}", "ManuscriptResponse"),
    RouteContract("DELETE", "/manuscripts/{manuscript_id}", "None"),
    RouteContract("GET", "/manuscripts/{manuscript_id}/authors", "ManuscriptAuthorList"),
    RouteContract("PUT", "/manuscripts/{manuscript_id}/authors", "ManuscriptAuthorList"),
    RouteContract("GET", "/manuscripts/{manuscript_id}/versions", "ManuscriptVersionPage"),
    RouteContract("POST", "/manuscripts/{manuscript_id}/versions", "ManuscriptVersionResponse"),
    RouteContract("GET", "/manuscripts/{manuscript_id}/versions/{version_id}", "ManuscriptVersionResponse"),
    RouteContract("GET", "/manuscripts/{manuscript_id}/versions/{version_id}/files", "FilePage"),
    RouteContract("POST", "/manuscripts/{manuscript_id}/versions/{version_id}/files", "FileResponse"),
    RouteContract("GET", "/files/{file_id}", "FileResponse"),
    RouteContract("GET", "/files/{file_id}/download", "FileContent"),
    RouteContract("DELETE", "/files/{file_id}", "None"),
    RouteContract("GET", "/publishers", "PublisherPage"),
    RouteContract("POST", "/publishers", "PublisherResponse"),
    RouteContract("GET", "/publishers/{publisher_id}", "PublisherResponse"),
    RouteContract("PATCH", "/publishers/{publisher_id}", "PublisherResponse"),
    RouteContract("DELETE", "/publishers/{publisher_id}", "None"),
    RouteContract("GET", "/journal-platforms", "JournalPlatformPage"),
    RouteContract("POST", "/journal-platforms", "JournalPlatformResponse"),
    RouteContract("GET", "/journal-platforms/{platform_id}", "JournalPlatformResponse"),
    RouteContract("PATCH", "/journal-platforms/{platform_id}", "JournalPlatformResponse"),
    RouteContract("DELETE", "/journal-platforms/{platform_id}", "None"),
    RouteContract("GET", "/journals", "JournalPage"),
    RouteContract("POST", "/journals", "JournalResponse"),
    RouteContract("GET", "/journals/{journal_id}", "JournalResponse"),
    RouteContract("PATCH", "/journals/{journal_id}", "JournalResponse"),
    RouteContract("DELETE", "/journals/{journal_id}", "None"),
    RouteContract("GET", "/dashboard/summary", "DashboardSummary"),
    RouteContract("GET", "/audit-logs", "AuditLogPage"),
    RouteContract("GET", "/audit-logs/{log_id}", "AuditLogResponse"),
)
```

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && PYTHONPATH=. pytest tests/test_contract_manifest.py -q`
Expected: 3 passed.

```bash
git add backend/app/schemas backend/app/api/v1/contract_manifest.py backend/tests/test_contract_manifest.py
git commit -m "feat: define strict v0.1 API contract"
```

---

### Task 3: MySQL Bootstrap and Identity/Author Migration

**Files:**
- Create: `scripts/bootstrap_mysql.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/auth.py`
- Create: `backend/app/models/authors.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_identity_authors.py`
- Create: `backend/app/api/v1/readiness.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_mysql_bootstrap.py`
- Test: `backend/tests/test_identity_models.py`

**Interfaces:**
- Produces: `Base`, `SessionLocal`, `get_db()`, the first 9 tables, and `bootstrap_mysql.py` writing permission-`0600` `.env` without echoing secrets.
- Later tasks consume: `User`, `Role`, `UserRole`, `AuthSession`, `Author`, `AuthorEmail`, `Institution`, `AuthorInstitution`, `AuthorAuthorization`.

- [ ] **Step 1: Write failing safety and model tests**

```python
# backend/tests/test_mysql_bootstrap.py
from scripts.bootstrap_mysql import validate_database_name, build_grants


def test_database_names_are_fixed_and_test_is_distinct():
    assert validate_database_name("academic_submission_agent")
    assert validate_database_name("academic_submission_agent_test")
    assert not validate_database_name("academic_submission_agent; DROP DATABASE mysql")


def test_runtime_user_has_no_ddl_grants():
    grants = build_grants("asa_app", "academic_submission_agent")
    assert "SELECT" in grants and "INSERT" in grants and "UPDATE" in grants
    assert "DROP" not in grants and "ALTER" not in grants
```

- [ ] **Step 2: Run the safety test and confirm failure**

Run: `PYTHONPATH=backend pytest backend/tests/test_mysql_bootstrap.py -q`
Expected: import failure for `scripts.bootstrap_mysql`.

- [ ] **Step 3: Implement hidden-input database bootstrap**

Use fixed identifiers `academic_submission_agent`, `academic_submission_agent_test`, `asa_app`, `asa_migrate`, and `asa_test`. Prompt for the MySQL administrative password with `getpass.getpass()`, generate three passwords with `secrets.token_urlsafe(32)`, and create the two databases and three users through parameterized PyMySQL statements. Grant DML-only development access to `asa_app`, DDL/DML development access to `asa_migrate`, and full test-database-only access to `asa_test`.

```python
# scripts/bootstrap_mysql.py
import re


def validate_database_name(name: str) -> bool:
    return bool(re.fullmatch(r"academic_submission_agent(?:_test)?", name))


def build_grants(user: str, database: str) -> str:
    if user == "asa_app":
        privileges = "SELECT, INSERT, UPDATE, DELETE"
    elif user == "asa_migrate":
        privileges = "SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES"
    elif user == "asa_test" and database.endswith("_test"):
        privileges = "ALL PRIVILEGES"
    else:
        raise ValueError("unsupported database identity")
    return f"GRANT {privileges} ON `{database}`.* TO %s@%s"
```

Write `.env` with `DATABASE_URL`, `ALEMBIC_DATABASE_URL`, `TEST_DATABASE_URL`, a random `CSRF_SECRET_KEY`, and `ENVIRONMENT=development`; call `os.chmod(".env", 0o600)` and never print the generated values.

- [ ] **Step 4: Implement models and migration, then verify on MySQL**

Define `Base`, UUID defaults, UTC helpers, mixins, and the nine models with every field and constraint in spec §2.4. Use `DATETIME(6)`, JSON permission arrays, the ORCID unique index, and this generated primary-email column:

```python
active_primary_author_id = mapped_column(
    CHAR(36),
    Computed("IF(is_primary = 1 AND deleted_at IS NULL, author_id, NULL)", persisted=True),
)
__table_args__ = (
    UniqueConstraint("author_id", "normalized_email"),
    UniqueConstraint("active_primary_author_id"),
    Index("ix_author_emails_normalized", "normalized_email"),
)
```

`alembic/env.py` must read only `ALEMBIC_DATABASE_URL`; runtime `get_db()` must read only `DATABASE_URL`. Add `GET /api/v1/health/ready` in `readiness.py`, executing `SELECT 1` and returning `DATABASE_UNAVAILABLE` without connection details on failure; include its router in `main.py`. `tests/conftest.py` loads `TEST_DATABASE_URL`, rejects non-`_test` targets and live storage, runs migrations once per test session, and provides independent engine/session fixtures plus a temporary test storage root. Run `python scripts/bootstrap_mysql.py` with local hidden input, then `cd backend && alembic upgrade head`.

Add an integration assertion:

```python
def test_first_migration_has_nine_tables(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert {"users", "roles", "user_roles", "auth_sessions", "authors",
            "author_emails", "institutions", "author_institutions",
            "author_authorizations"}.issubset(names)
```

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_mysql_bootstrap.py tests/test_identity_models.py -q`
Expected: safety tests and first-migration integration tests pass against `academic_submission_agent_test`.

```bash
git add scripts/bootstrap_mysql.py backend/app/core/database.py backend/app/models backend/alembic backend/tests
git commit -m "feat: add identity and author database schema"
```

---

### Task 4: Manuscript, File, Journal, and Audit Migration

**Files:**
- Create: `backend/app/models/manuscripts.py`
- Create: `backend/app/models/files.py`
- Create: `backend/app/models/journals.py`
- Create: `backend/app/models/audit.py`
- Create: `backend/alembic/versions/0002_manuscripts_files_journals_audit.py`
- Test: `backend/tests/test_schema_constraints.py`

**Interfaces:**
- Produces: the remaining 9 tables and their composite foreign keys, completing exactly 18 tables.
- Later tasks consume: all manuscript/file/journal/audit model classes and migration `head=0002`.

- [ ] **Step 1: Write failing migration and cross-manuscript constraint tests**

```python
# backend/tests/test_schema_constraints.py
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_all_eighteen_tables_exist(db_engine):
    expected = {"users", "roles", "user_roles", "auth_sessions", "authors",
                "author_emails", "institutions", "author_institutions",
                "author_authorizations", "manuscripts", "manuscript_authors",
                "manuscript_versions", "file_families", "manuscript_files",
                "publishers", "journal_platforms", "journals", "operation_logs"}
    assert set(inspect(db_engine).get_table_names()) == expected


def test_current_version_must_belong_to_same_manuscript(db_session, two_manuscript_versions):
    manuscript_id, other_version_id = two_manuscript_versions
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE manuscripts SET current_version_id=:version WHERE id=:id"),
            {"version": other_version_id, "id": manuscript_id},
        )
```

- [ ] **Step 2: Run and confirm the second migration is absent**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_schema_constraints.py -q`
Expected: table-set assertion fails and manuscript models are unavailable.

- [ ] **Step 3: Implement the nine models and ordered migration**

Create `manuscripts` without the current-version foreign key, then `manuscript_versions`, then add `(id, current_version_id) → (manuscript_id, id)`. Create file families and files with:

```python
__table_args__ = (
    UniqueConstraint("file_family_id", "file_version"),
    ForeignKeyConstraint(["file_family_id", "manuscript_id"],
                         ["file_families.id", "file_families.manuscript_id"]),
    ForeignKeyConstraint(["manuscript_id", "manuscript_version_id"],
                         ["manuscript_versions.manuscript_id", "manuscript_versions.id"]),
    Index("ix_manuscript_files_sha256", "sha256"),
)
```

Implement the `(manuscript_id, author_id) → manuscripts(id, owner_author_id)` family constraint, all journal fields, and append-only `operation_logs`. No model relationship may use cascade delete for historical records.

- [ ] **Step 4: Verify migration repeatability and constraints**

Run:

```bash
cd backend
ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test PYTHONPATH=. pytest tests/test_schema_constraints.py -q
```

Expected: the second upgrade is a no-op; all constraint tests pass.

- [ ] **Step 5: Optionally commit**

```bash
git add backend/app/models backend/alembic/versions/0002_manuscripts_files_journals_audit.py backend/tests/test_schema_constraints.py
git commit -m "feat: complete eighteen-table mysql schema"
```

---

### Task 5: Authentication, Session, CSRF, and First-Password Gate

**Files:**
- Create: `backend/app/security/passwords.py`
- Create: `backend/app/security/sessions.py`
- Create: `backend/app/security/csrf.py`
- Create: `backend/app/services/auth.py`
- Create: `backend/app/api/v1/deps.py`
- Create: `backend/app/api/v1/auth.py`
- Create: `scripts/create_admin.py`
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Produces: `SessionService`, `Principal`, `get_principal`, `require_csrf`, and all `/auth/*` endpoints.
- Later tasks consume: `Principal.user`, `Principal.session`, and authentication dependencies.

- [ ] **Step 1: Write failing authentication tests**

```python
# backend/tests/test_auth_api.py
import pytest


def test_session_is_hashed_and_csrf_is_stable(client, admin_with_initial_password):
    first = client.post("/api/v1/auth/login", json=admin_with_initial_password,
                        headers={"Origin": "http://localhost:5173"})
    assert first.status_code == 200
    second = client.get("/api/v1/auth/csrf")
    assert second.json()["csrf_token"] == first.json()["csrf_token"]
    assert "asa_session" in first.headers["set-cookie"]


def test_first_password_gate_blocks_business_api(client, login_initial_admin):
    response = client.get("/api/v1/authors")
    assert response.status_code == 403
    assert response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.parametrize("origin", ["https://attacker.invalid", "null"])
def test_login_rejects_untrusted_origin(client, admin_with_initial_password, origin):
    response = client.post("/api/v1/auth/login", json=admin_with_initial_password,
                           headers={"Origin": origin})
    assert response.status_code == 403
```

- [ ] **Step 2: Run and confirm authentication is missing**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_auth_api.py -q`
Expected: route imports or 404 assertions fail.

- [ ] **Step 3: Implement password, Session, and CSRF primitives**

Use `argon2.PasswordHasher`, 32-byte random Session tokens, and SHA-256 database lookups. Derive the stable CSRF token without storing it:

```python
# backend/app/security/csrf.py
import base64, hashlib, hmac


def csrf_token(session_token_hash: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), b"csrf:" + session_token_hash.encode(),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

`get_principal` checks user status, token hash, revocation, idle expiry, and absolute expiry. It updates idle activity without caching author permissions. Authentication startup rejects an empty or shorter-than-32-byte `CSRF_SECRET_KEY`; health checks remain available for diagnosing that configuration error. The first-password dependency rejects every business route with `PASSWORD_CHANGE_REQUIRED` while allowing only the four approved auth routes.

- [ ] **Step 4: Implement auth routes and administrator initialization**

`create_admin.py` prompts for username and password using hidden input, validates 12–128 characters, seeds the five roles transactionally, and creates one `system_admin` with `must_change_password=true`. Login audits success/failure without recording the username or password. Logout and password change require CSRF; password change revokes all sessions.

Add rate limiting keyed by normalized username and source IP, returning the same `UNAUTHORIZED` response for unknown users and wrong passwords. Never include raw tokens in logs.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_auth_api.py -q`
Expected: all authentication, stable-CSRF, origin, revocation, and first-password tests pass.

```bash
git add backend/app/security backend/app/services/auth.py backend/app/api/v1 scripts/create_admin.py backend/tests/test_auth_api.py
git commit -m "feat: add secure local session authentication"
```

---

### Task 6: Layered Permissions and Transactional Audit

**Files:**
- Create: `backend/app/services/permissions.py`
- Create: `backend/app/services/audit.py`
- Create: `backend/app/repositories/authorizations.py`
- Create: `backend/app/repositories/audit.py`
- Test: `backend/tests/test_permissions.py`
- Test: `backend/tests/test_audit_transactions.py`

**Interfaces:**
- Produces: `Permission`, `require_author_permission()`, `require_roles()`, `has_author_permission()`, and `AuditService.record()`.
- Later tasks consume: one permission service for every author/manuscript/file decision and one audit service for every protected write or sensitive read.

- [ ] **Step 1: Write failing permission-boundary tests**

```python
# backend/tests/test_permissions.py
import pytest
from datetime import timedelta
from app.services.permissions import Permission, has_author_permission


@pytest.mark.parametrize("offset,expected", [(-1, True), (0, True), (1, False)])
def test_valid_from_boundary(db_session, operator, author, grant_factory, frozen_now, offset, expected):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ,
                  valid_from=frozen_now + timedelta(minutes=offset), valid_to=frozen_now + timedelta(hours=1))
    assert has_author_permission(db_session, operator, author.id,
                                 Permission.MANUSCRIPT_READ, frozen_now) is expected


def test_valid_to_boundary_is_exclusive(db_session, operator, author, grant_factory, frozen_now):
    grant_factory(user=operator, author=author, permission=Permission.MANUSCRIPT_READ,
                  valid_from=frozen_now - timedelta(hours=1), valid_to=frozen_now)
    assert not has_author_permission(db_session, operator, author.id,
                                     Permission.MANUSCRIPT_READ, frozen_now)


def test_disabled_admin_is_never_authorized(db_session, disabled_admin, author):
    assert not has_author_permission(db_session, disabled_admin, author.id,
                                     Permission.MANUSCRIPT_READ)
```

- [ ] **Step 2: Run and confirm the permission service is missing**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_permissions.py -q`
Expected: import failure for `Permission`.

- [ ] **Step 3: Implement role aggregation and database-backed grants**

Define the nine V0.1 permission strings as `str, Enum`. Non-admin role capabilities are the union of role sets; `system_admin` takes precedence only after user-active validation. Grant queries use `JSON_CONTAINS`, finite UTC intervals, `revoked_at IS NULL`, and active user/author joins.

```python
# backend/app/services/permissions.py
class Permission(str, Enum):
    MANUSCRIPT_READ = "manuscript:read"
    MANUSCRIPT_CREATE = "manuscript:create"
    MANUSCRIPT_UPDATE = "manuscript:update"
    MANUSCRIPT_FILE_MANAGE = "manuscript:file:manage"
    AUTHOR_PROFILE_READ = "author:profile:read"
    AUTHOR_EMAIL_READ = "author:email:read"
    AUTHOR_PHONE_READ = "author:phone:read"
    AUTHOR_ADDRESS_READ = "author:address:read"
    AUTHOR_PROFILE_UPDATE = "author:profile:update"
```

`require_author_permission` distinguishes no grant (`404`), inactive/expired/revoked grant (`403 AUTHORIZATION_EXPIRED`), and active grant lacking the code (`403 PERMISSION_DENIED`). Role denial occurs before resource lookup.

- [ ] **Step 4: Implement sanitized audit and rollback proof**

`AuditService.record()` accepts explicit allowlisted before/after dictionaries, rejects keys containing password/token/cookie/secret/email/phone/address/storage_path, and writes one append-only log. Add a test that forces `session.add(OperationLog)` to fail and proves the business row is absent after rollback. Add multi-role tests for operator+reviewer, auditor+operator, and disabled admin+reviewer.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_permissions.py tests/test_audit_transactions.py --cov=app.services.permissions --cov-fail-under=95 -q`
Expected: permission coverage is at least 95% and all transaction tests pass.

```bash
git add backend/app/services backend/app/repositories backend/tests/test_permissions.py backend/tests/test_audit_transactions.py
git commit -m "feat: enforce layered authorization and audit"
```

---

### Task 7: Author, Email, Institution, and Authorization APIs

**Files:**
- Create: `backend/app/repositories/authors.py`
- Create: `backend/app/services/authors.py`
- Create: `backend/app/services/authorizations.py`
- Create: `backend/app/api/v1/authors.py`
- Create: `backend/app/api/v1/authorizations.py`
- Test: `backend/tests/test_authors_api.py`
- Test: `backend/tests/test_authorizations_api.py`

**Interfaces:**
- Produces: all author, email, institution, author-institution, and author-authorization routes.
- Later tasks consume: `AuthorService.require_readable_author()` and authorization fixtures for manuscript tests.

- [ ] **Step 1: Write failing normalization and isolation tests**

```python
# backend/tests/test_authors_api.py
import pytest


def test_orcid_and_name_are_normalized(client, admin_context):
    response = client.post("/api/v1/authors", json={
        "display_name": "  张三  ", "orcid": "https://orcid.org/0000-0002-1825-0097",
        "confirm_identity_change": True})
    assert response.status_code == 201
    assert response.json()["display_name"] == "张三"
    assert response.json()["orcid"] == "0000-0002-1825-0097"


def test_email_confirmation_is_not_implicit(client, admin_context, author):
    response = client.post(f"/api/v1/authors/{author.id}/emails",
                           json={"email": "Test@" + "Example.org"})
    assert response.status_code == 422


def test_institution_summary_never_exposes_address(client, operator_context, institution):
    response = client.get(f"/api/v1/institutions/{institution.id}")
    assert response.status_code == 200
    assert "address_line1" not in response.json()
    assert "postal_code" not in response.json()
```

- [ ] **Step 2: Run and confirm domain routes are missing**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_authors_api.py -q`
Expected: 404 or import failures.

- [ ] **Step 3: Implement normalization and transactional author services**

Use NFC for display names, lowercased trimmed comparison fields, ORCID MOD 11-2 and ISSN validation helpers. Create/update authors require the explicit identity confirmation. Author PATCH requires profile read+update. Email writes require profile update+email read; creating and address changes require literal confirmation, and deleting accepts `{"confirm_email_binding":true}` in the request body.

Institution list/detail returns `InstitutionSummaryResponse` for non-admin users. Author-institution writes require profile update+read and an active institution. Sensitive responses create one audit entry per returned author/category without logging values.

- [ ] **Step 4: Implement finite author authorizations**

Only administrators manage authorizations. Reject unknown/empty permission codes, `valid_to <= now`, and `valid_to <= valid_from`. Revocation sets `revoked_at` and takes effect on the next request without Session cache invalidation. Record before/after permission arrays but not evidence contents.

Add integration cases for duplicate normalized email, one generated-column primary email, ORCID check digits, write-without-read rejection, expired grants, and cross-author `404`.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_authors_api.py tests/test_authorizations_api.py -q`
Expected: all author and authorization tests pass.

```bash
git add backend/app/repositories/authors.py backend/app/services/authors.py backend/app/services/authorizations.py backend/app/api/v1/authors.py backend/app/api/v1/authorizations.py backend/tests
git commit -m "feat: add isolated author management apis"
```

---

### Task 8: Manuscript, Authorship, and Immutable Version APIs

**Files:**
- Create: `backend/app/repositories/manuscripts.py`
- Create: `backend/app/services/manuscripts.py`
- Create: `backend/app/schemas/manuscripts.py`
- Create: `backend/app/api/v1/manuscripts.py`
- Test: `backend/tests/test_manuscripts_api.py`
- Test: `backend/tests/test_manuscript_concurrency.py`

**Interfaces:**
- Produces: `ManuscriptService`, manuscript CRUD, ordered authorship, and immutable version routes.
- File tasks consume: `ManuscriptService.get_owned_manuscript()` and `ManuscriptService.lock_current_version()`.

- [ ] **Step 1: Write failing manuscript and minimal-author tests**

```python
# backend/tests/test_manuscripts_api.py
def test_create_builds_initial_version_and_minimal_authors(client, operator_context, owner, coauthor):
    response = client.post("/api/v1/manuscripts", json={
        "owner_author_id": str(owner.id), "title": "A study", "abstract": "Abstract",
        "keywords": ["ai"], "article_type": "research", "language": "en",
        "authors": [{"author_id": str(owner.id), "position": 1, "is_corresponding": True},
                    {"author_id": str(coauthor.id), "position": 2, "is_corresponding": False}]})
    assert response.status_code == 201
    body = response.json()
    assert body["current_version_id"]
    assert body["authors"][1]["display_name"] == coauthor.display_name
    assert "email" not in body["authors"][1]
    assert "phone_number" not in body["authors"][1]


def test_write_without_read_cannot_leak_response(client, write_only_operator_context, manuscript):
    response = client.patch(f"/api/v1/manuscripts/{manuscript.id}", json={"title": "new"})
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert "title" not in response.json()
```

- [ ] **Step 2: Run and confirm manuscript routes are missing**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_manuscripts_api.py -q`
Expected: route or service import failures.

- [ ] **Step 3: Implement manuscript transactions and serializers**

Creating a manuscript locks the owner scope, inserts the working metadata, current authorship, and v1 snapshot, then sets `current_version_id`. The default authorship is owner at position 1 as corresponding. Inputs accept only `author_id`, `position`, and `is_corresponding`; display names come from the database.

PATCH and version creation require update+read. Authorship PUT locks the manuscript, records minimal before/after lists, deletes current links, and inserts the new ordered list in one transaction. Newly linked coauthors require profile read. Metadata/version snapshots never include sensitive coauthor fields.

- [ ] **Step 4: Add real MySQL concurrency tests**

Use committed fixtures and two independent sessions/threads. Concurrent `POST /versions` calls after initial v1 must produce versions 2 and 3 without duplicate numbers. A simultaneous metadata PATCH and version creation must serialize on the manuscript row so the snapshot is either entirely before or entirely after the PATCH.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_manuscripts_api.py tests/test_manuscript_concurrency.py -q`
Expected: manuscript, authorship, snapshot, and concurrency tests pass.

```bash
git add backend/app/repositories/manuscripts.py backend/app/services/manuscripts.py backend/app/api/v1/manuscripts.py backend/app/schemas/manuscripts.py backend/tests
git commit -m "feat: add versioned manuscript management"
```

---

### Task 9: Secure File Families, Upload, Download, and Reconciliation

**Files:**
- Create: `backend/app/services/file_validation.py`
- Create: `backend/app/services/storage.py`
- Create: `backend/app/services/files.py`
- Create: `backend/app/repositories/files.py`
- Create: `backend/app/api/v1/files.py`
- Create: `scripts/reconcile_files.py`
- Test: `backend/tests/test_file_validation.py`
- Test: `backend/tests/test_files_api.py`
- Test: `backend/tests/test_file_failures.py`

**Interfaces:**
- Produces: `FileValidator`, `StorageService`, `FileService.upload()`, `FileService.download()`, and `reconcile_files.py`.
- Later tasks consume: safe file fixtures and the reconciliation manifest at `storage/reconciliation.jsonl`.

- [ ] **Step 1: Write failing validation and path tests**

```python
# backend/tests/test_file_validation.py
import pytest


@pytest.mark.parametrize("filename", ["../../etc/passwd", "bad\r\nContent-Disposition: x", "a/b.pdf"])
def test_download_filename_cannot_inject_headers_or_paths(filename):
    safe = safe_download_filename(filename)
    assert "\r" not in safe and "\n" not in safe
    assert "/" not in safe and "\\" not in safe


def test_mime_spoof_is_rejected(tmp_path):
    payload = tmp_path / "fake.pdf"
    payload.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(UnsupportedFileType):
        FileValidator().inspect(payload, "fake.pdf", "application/pdf")
```

- [ ] **Step 2: Run and confirm file services are missing**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_file_validation.py -q`
Expected: import failures.

- [ ] **Step 3: Implement streaming validation and OOXML limits**

Stream uploads in 1 MiB chunks to `storage/temp/{uuid}.part`, enforcing size while hashing. Use libmagic plus extension allowlists; verify PDF/OOXML/OLE/image structures. For DOCX/XLSX inspect ZIP metadata without extraction: at most 2,000 entries, 500 MiB total expanded size, 100:1 per-entry compression ratio, and no nested ZIP/OOXML. Reject general ZIP, HTML, SVG, scripts, and executables.

`safe_download_filename` removes CR/LF, slashes, NUL, and control characters; use an ASCII fallback plus RFC 5987 UTF-8 encoding for international names.

- [ ] **Step 4: Implement locked upload and outcome-aware compensation**

Generate the file UUID before the transaction. After temporary validation, lock the manuscript, recheck `version_id == current_version_id`, then lock/create the family and increment `file_version`. Store only this relative path:

```python
relative = Path("authors") / str(author_id) / "manuscripts" / str(manuscript_id) \
    / "versions" / str(version_id) / f"{file_uuid}{extension}"
```

Insert file metadata and audit before `os.replace(temp, final)`. If the move fails, roll back. If rollback is certain and the record is absent, clean up. If commit raises or connection state is unknown, retain the file and append JSON containing `file_id`, `relative_path`, `sha256`, and UTC time to `storage/reconciliation.jsonl`; reconcile with a new database connection before any deletion. `reconcile_files.py` reports missing files and orphans without automatically deleting unknown formal files.

- [ ] **Step 5: Add fault/race tests and verify**

Test MIME spoofing, exact size limit and limit+1, OOXML bombs, path traversal, two simultaneous same-family uploads producing versions 1 and 2, upload during current-version change returning `409`, certain rollback cleanup, unknown commit preservation, missing-file download denial, and sensitive-path absence in `FileResponse`.

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_file_validation.py tests/test_files_api.py tests/test_file_failures.py --cov=app.services.files --cov=app.services.storage --cov-fail-under=90 -q`
Expected: all file tests pass with at least 90% core-file coverage.

```bash
git add backend/app/services backend/app/repositories/files.py backend/app/api/v1/files.py scripts/reconcile_files.py backend/tests
git commit -m "feat: add recoverable versioned file storage"
```

---

### Task 10: Journal, Dashboard, and Audit APIs

**Files:**
- Create: `backend/app/repositories/journals.py`
- Create: `backend/app/services/journals.py`
- Create: `backend/app/services/dashboard.py`
- Create: `backend/app/api/v1/journals.py`
- Create: `backend/app/api/v1/dashboard.py`
- Create: `backend/app/api/v1/audit.py`
- Test: `backend/tests/test_journals_api.py`
- Test: `backend/tests/test_dashboard_audit.py`

**Interfaces:**
- Produces: publisher/platform/journal CRUD, permission-filtered dashboard, and read-only audit queries.
- Frontend tasks consume: all remaining API resources.

- [ ] **Step 1: Write failing role and provenance tests**

```python
# backend/tests/test_dashboard_audit.py
def test_auditor_cannot_read_business_dashboard(client, auditor_context):
    assert client.get("/api/v1/dashboard/summary").status_code == 403


def test_journal_requirement_requires_source(client, admin_context, publisher):
    response = client.post("/api/v1/journals", json={
        "publisher_id": str(publisher.id), "name": "Journal",
        "requirements": [{"key": "abstract_words", "value": 250,
                          "scope": "research", "source_url": "https://journal.example/guide",
                          "verified_at": "2026-11-04T00:00:00Z"}]})
    assert response.status_code == 201
    assert response.json()["requirements"][0]["source_url"].endswith("/guide")
```

- [ ] **Step 2: Run and confirm remaining routes are missing**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_journals_api.py tests/test_dashboard_audit.py -q`
Expected: 404 or import failures.

- [ ] **Step 3: Implement resources and permission-filtered aggregates**

Only administrators write journal resources. Only `system_admin`, `submission_operator`, and `reviewer` read them. Validate ISSN/eISSN check digits, HTTPS URLs, and every requirement item's source and verification timestamp.

Dashboard counts use the same permission predicates as list endpoints; auditor receives `403`. Recent operations are limited to the current user and contain no sensitive values.

- [ ] **Step 4: Implement read-only audit filtering**

Only `system_admin` and `auditor` may query audit logs. Filters cover actor, author, category, action, target, result, Request ID, and UTC range. Register no create/update/delete audit routes and add a test that `DELETE /api/v1/audit-logs/{id}` is 405.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_journals_api.py tests/test_dashboard_audit.py -q`
Expected: all resource, role, provenance, and append-only tests pass.

```bash
git add backend/app/repositories/journals.py backend/app/services/journals.py backend/app/services/dashboard.py backend/app/api/v1 backend/tests
git commit -m "feat: add journal dashboard and audit apis"
```

---

### Task 11: OpenAPI Export and Postman/Newman Contract Suite

**Files:**
- Create: `scripts/export_openapi.py`
- Create: `docs/api/v0.1-openapi.json`
- Create: `backend/tests/postman/v0.1.postman_collection.json`
- Create: `backend/tests/postman/local.postman_environment.json`
- Create: `backend/tests/test_openapi_generated.py`
- Create: `scripts/test_api.sh`

**Interfaces:**
- Produces: a reproducible OpenAPI artifact and a Newman command covering positive and negative workflows.
- Final verification consumes: `scripts/test_api.sh` and the checked OpenAPI file.

- [ ] **Step 1: Write failing OpenAPI path/manifest parity test**

```python
# backend/tests/test_openapi_generated.py
from app.api.v1.contract_manifest import CONTRACTS
from app.main import app


def test_fastapi_paths_match_manifest():
    actual = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            actual.add((method.upper(), path.removeprefix("/api/v1")))
    expected = {(item.method, item.path) for item in CONTRACTS}
    assert actual == expected
```

- [ ] **Step 2: Run and correct any route drift**

Run: `cd backend && PYTHONPATH=. pytest tests/test_openapi_generated.py -q`
Expected: any missing or extra route fails with the exact set difference. Correct routers or the intentionally reviewed manifest; do not weaken the assertion.

- [ ] **Step 3: Export and validate OpenAPI**

```python
# scripts/export_openapi.py
import json
from pathlib import Path
from app.main import app

output = Path("docs/api/v0.1-openapi.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

Run `PYTHONPATH=backend python scripts/export_openapi.py` and validate with `openapi-spec-validator docs/api/v0.1-openapi.json`.

- [ ] **Step 4: Build the Postman workflow**

Collection order: health → login → save CSRF → change initial password → login again → create authors A/B → grant only A to a test operator → create manuscript with B as coauthor → create version → upload `backend/tests/fixtures/minimal.pdf` → list manuscript/version/files → verify B has no email/phone/address → test no-session, bad-CSRF, expired grant, cross-author IDs, write-without-read, institution address summary, and audit immutability.

Use this assertion in every coauthor response test:

```javascript
const body = pm.response.json();
const serialized = JSON.stringify(body);
pm.test("no sensitive coauthor fields", function () {
    pm.expect(serialized).not.to.match(/phone_number|phone_country_code|address_line1|postal_code|normalized_email/);
});
```

Store only `base_url`, usernames, and empty secret placeholders in the environment file. Inject `ADMIN_PASSWORD`, `OPERATOR_PASSWORD`, Session cookies, and CSRF at runtime. Install the runner with `npm install --prefix frontend --save-dev newman@6.2.1` and invoke it through `npx --prefix frontend newman`. `scripts/test_api.sh` starts an isolated backend on `127.0.0.1:8001` with the test database and temporary storage, waits for readiness, runs Newman, and stops that process through `trap` on every exit. Do not push the collection to Postman Cloud.

- [ ] **Step 5: Run Newman and optionally commit**

Run: `bash scripts/test_api.sh`
Expected: Newman exits 0 with all positive and negative assertions passing.

```bash
git add scripts/export_openapi.py scripts/test_api.sh docs/api backend/tests/postman backend/tests/test_openapi_generated.py
git commit -m "test: verify openapi and postman api contract"
```

---

### Task 12: Vue Foundation, Authentication, and Typed API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/stores/auth.ts`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/views/auth/LoginView.vue`
- Create: `frontend/src/views/auth/ChangePasswordView.vue`
- Test: `frontend/src/api/client.test.ts`
- Test: `frontend/src/stores/auth.test.ts`

**Interfaces:**
- Produces: `api`, `useAuthStore`, protected router, and working login/change-password/logout.
- Other UI tasks consume: typed `api`, auth store, and route guards.

- [ ] **Step 1: Create Vite scripts and failing auth-store tests**

```json
{
  "name": "academic-submission-agent-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "test": "vitest run",
    "test:coverage": "vitest run --coverage"
  },
  "dependencies": {
    "axios": "^1.7.9",
    "element-plus": "^2.9.3",
    "pinia": "^2.3.0",
    "vue": "^3.5.13",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@types/node": "^22.10.2",
    "@vitejs/plugin-vue": "^5.2.1",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^25.0.1",
    "newman": "^6.2.1",
    "typescript": "~5.7.2",
    "vite": "^6.0.5",
    "vitest": "^2.1.8",
    "vue-tsc": "^2.2.0"
  }
}
```

```typescript
// frontend/src/stores/auth.test.ts
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  it('keeps CSRF only in memory', async () => {
    const store = useAuthStore()
    store.setSession({ id: 'u1', username: 'admin', display_name: 'Admin', roles: ['system_admin'], status: 'active', must_change_password: false, last_login_at: null }, 'csrf')
    expect(store.csrfToken).toBe('csrf')
    expect(localStorage.getItem('asa_session')).toBeNull()
    expect(localStorage.getItem('csrf_token')).toBeNull()
  })
})
```

- [ ] **Step 2: Run and confirm the frontend fails before implementation**

Run: `cd frontend && npm install && npm test -- src/stores/auth.test.ts`
Expected: auth store import fails.

- [ ] **Step 3: Implement Axios and Pinia authentication**

Use `baseURL: '/api/v1'`, `withCredentials: true`, and in-memory CSRF. On mutating requests attach `X-CSRF-Token`. On `SECURITY_CHECK_FAILED`, fetch `/auth/csrf` and retry once; on `401`, clear state and route to login; on `PASSWORD_CHANGE_REQUIRED`, route to change-password. Never persist Session or CSRF tokens.

Vite proxies `/api` to `http://127.0.0.1:8000`; allowed origins remain the explicit local values. Configure Vitest with `environment: 'jsdom'` and `globals: true`, and enable the Vue plugin. Add Element Plus, Vue Router, and Pinia with a single application layout.

- [ ] **Step 4: Implement login and first-password views**

Forms use backend field names, disable double submission, show Request ID for server errors, and never display password hashes or raw server stacks. After password change, clear state and return to login. Router guards wait for `/auth/me` before choosing the destination.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd frontend && npm test && npm run build`
Expected: Vitest, TypeScript, and Vite build pass.

```bash
git add frontend
git commit -m "feat: add vue authentication foundation"
```

---

### Task 13: Author, Institution, Authorization, and Journal UI

**Files:**
- Create: `frontend/src/api/authors.ts`
- Create: `frontend/src/api/journals.ts`
- Create: `frontend/src/components/AuthorForm.vue`
- Create: `frontend/src/components/EmailTable.vue`
- Create: `frontend/src/components/InstitutionLinkForm.vue`
- Create: `frontend/src/views/authors/AuthorListView.vue`
- Create: `frontend/src/views/authors/AuthorDetailView.vue`
- Create: `frontend/src/views/authors/AuthorizationView.vue`
- Create: `frontend/src/views/journals/JournalListView.vue`
- Test: `frontend/src/components/AuthorForm.test.ts`
- Test: `frontend/src/views/authors/AuthorDetailView.test.ts`

**Interfaces:**
- Produces: usable author, email, institution, authorization, publisher, platform, and journal management pages.
- Manuscript UI consumes: author search returning only authorized profiles.

- [ ] **Step 1: Write failing explicit-confirmation and field-absence tests**

```typescript
// frontend/src/components/AuthorForm.test.ts
it('requires identity confirmation before submit', async () => {
  const wrapper = mount(AuthorForm)
  await wrapper.get('[data-test="display-name"]').setValue('张三')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('submit')).toBeUndefined()
  await wrapper.get('[data-test="identity-confirm"]').setValue(true)
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ confirm_identity_change: true })
})
```

- [ ] **Step 2: Run and confirm component failure**

Run: `cd frontend && npm test -- src/components/AuthorForm.test.ts src/views/authors/AuthorDetailView.test.ts`
Expected: component imports fail.

- [ ] **Step 3: Implement typed forms and author detail**

Use separate API types for create/update/response. Author detail requests emails and institutions only when the current permission set allows them and handles `403` without stale cached data. Email creation/address changes and authorship changes use explicit confirmation controls. Institution selectors use summary responses and never expect detailed addresses.

- [ ] **Step 4: Implement authorization and journal pages**

Authorization forms present only the nine defined permissions, require finite start/end times, and provide a separate revoke confirmation. Journal requirement rows require key, value, scope, HTTPS source URL, and verification time. Publisher/platform/journal tables support server pagination, allowlisted sorting, empty states, and soft-delete confirmation.

- [ ] **Step 5: Verify and optionally commit**

Run: `cd frontend && npm test && npm run build`
Expected: all component tests and production build pass.

```bash
git add frontend/src
git commit -m "feat: add author and journal management views"
```

---

### Task 14: Manuscript, Version, File, Dashboard, and Audit UI

**Files:**
- Create: `frontend/src/api/manuscripts.ts`
- Create: `frontend/src/api/files.ts`
- Create: `frontend/src/components/AuthorshipEditor.vue`
- Create: `frontend/src/components/FileFamilyUpload.vue`
- Create: `frontend/src/views/manuscripts/ManuscriptListView.vue`
- Create: `frontend/src/views/manuscripts/ManuscriptDetailView.vue`
- Create: `frontend/src/views/dashboard/DashboardView.vue`
- Create: `frontend/src/views/audit/AuditListView.vue`
- Test: `frontend/src/components/AuthorshipEditor.test.ts`
- Test: `frontend/src/components/FileFamilyUpload.test.ts`

**Interfaces:**
- Produces: the complete V0.1 user workflow from author/manuscript creation through file versioning and audit inspection.

- [ ] **Step 1: Write failing authorship and file tests**

```typescript
// frontend/src/components/AuthorshipEditor.test.ts
it('submits ids and positions but never editable display names', async () => {
  const wrapper = mount(AuthorshipEditor, { props: { modelValue: [{ author_id: 'a', display_name: 'A', position: 1, is_corresponding: true }] } })
  await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
  await wrapper.get('form').trigger('submit')
  const payload = wrapper.emitted('submit')?.[0]?.[0]
  expect(payload.authors[0]).toEqual({ author_id: 'a', position: 1, is_corresponding: true })
  expect(payload.authors[0]).not.toHaveProperty('display_name')
  expect(payload.confirm_authorship_change).toBe(true)
})
```

- [ ] **Step 2: Run and confirm component failure**

Run: `cd frontend && npm test -- src/components/AuthorshipEditor.test.ts src/components/FileFamilyUpload.test.ts`
Expected: component imports fail.

- [ ] **Step 3: Implement manuscript and authorship workflow**

Provide owner selection, metadata editing, ordered author list, corresponding-author selection, and explicit authorship confirmation. Display current version and immutable snapshot history. Do not render fields absent from the minimal-author response or infer sensitive data from other cached views.

- [ ] **Step 4: Implement file versioning and safe errors**

File upload supports new family and existing-family modes, displays client-side size/type hints without treating them as security checks, and uses Axios progress. After upload, refresh both family and current version. Show `409` current-version conflicts with a refresh action rather than automatic retry. Download only through the authorized endpoint and never expose `storage_path`.

Dashboard displays only returned aggregates. Audit pages are admin/auditor routes with filters and no edit/delete buttons.

- [ ] **Step 5: Verify and manually inspect Network**

Run: `cd frontend && npm test && npm run build`
Expected: tests and build pass. With two authors where only the owner is authorized, verify in browser Network that manuscript, version, and file responses contain no coauthor email, phone, address, ORCID, or notes.

```bash
git add frontend/src
git commit -m "feat: complete manuscript and file workspace"
```

---

### Task 15: Security Matrix, Failure Injection, and Coverage Gates

**Files:**
- Create: `backend/tests/test_security_matrix.py`
- Create: `backend/tests/test_authorization_boundaries.py`
- Create: `scripts/check_coverage.py`
- Test: `backend/tests/postman/v0.1.postman_collection.json`

**Interfaces:**
- Produces: one executable release gate for the spec §5.3 matrix and all coverage floors.

- [ ] **Step 1: Encode the remaining negative matrix as parametrized tests**

Cover AUTH-01 through AUTH-05, ROLE-01, AUTHZ-01 through AUTHZ-03, ISO-01 through ISO-06, FILE-01 through FILE-05, TX-01, MIG-01, API-01, and WEB-01. BACKUP-01 is implemented and executed in Task 16. Use explicit expected status and field-absence assertions, not only status checks.

```python
@pytest.mark.parametrize("path", [
    "/api/v1/authors", "/api/v1/manuscripts", "/api/v1/dashboard/summary",
])
def test_initial_password_gate_is_global(client, login_initial_admin, path):
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
```

- [ ] **Step 2: Run the matrix and fix implementation defects rather than expected values**

Run: `cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_security_matrix.py tests/test_authorization_boundaries.py -q`
Expected: initially identifies any unimplemented negative case; after fixes, all pass without removing field assertions.

- [ ] **Step 3: Add per-layer coverage checks**

Run pytest with `--cov=app --cov-report=json:coverage.json`, then evaluate overall and path-specific percentages:

```python
# scripts/check_coverage.py
import json

report = json.load(open("backend/coverage.json", encoding="utf-8"))
overall = report["totals"]["percent_covered"]
assert overall >= 80, f"overall coverage {overall:.2f}% < 80%"
for prefix, threshold in [("app/services/permissions", 95),
                          ("app/services/files", 90),
                          ("app/services/storage", 90),
                          ("app/services/", 85),
                          ("app/api/", 80)]:
    files = [v for k, v in report["files"].items() if k.startswith(prefix)]
    covered = sum(v["summary"]["covered_lines"] for v in files)
    total = sum(v["summary"]["num_statements"] for v in files)
    assert total and covered * 100 / total >= threshold, (prefix, covered, total)
```

- [ ] **Step 4: Verify all backend quality gates**

Run: `cd backend && ruff check app tests && mypy app && ENVIRONMENT=test PYTHONPATH=. pytest --cov=app --cov-report=json:coverage.json && python ../scripts/check_coverage.py`
Expected: lint, typing, tests, and all five coverage floors pass.

- [ ] **Step 5: Optionally commit**

```bash
git add backend scripts/check_coverage.py
git commit -m "test: enforce security and coverage release gates"
```

---

### Task 16: Encrypted Backup and Isolated Restore

**Files:**
- Create: `scripts/backup.py`
- Create: `scripts/restore.py`
- Create: `scripts/test_backup_restore.py`
- Create: `backups/README.md`
- Test: `backend/tests/test_backup_restore.py`

**Interfaces:**
- Produces: encrypted `.tar.age` backups with SHA-256 manifests and a restore command that only accepts an explicit isolated target ending `_test`.

- [ ] **Step 1: Write failing wrong-target and interruption tests**

```python
# backend/tests/test_backup_restore.py
import pytest


def test_restore_refuses_development_target():
    with pytest.raises(ValueError):
        validate_restore_target("academic_submission_agent", "storage")


def test_interrupted_backup_leaves_no_unencrypted_final_artifact(tmp_path, interrupted_dump):
    with pytest.raises(BackupFailed):
        create_backup(tmp_path, dump_command=interrupted_dump)
    assert not list(tmp_path.glob("*.sql"))
    assert not list(tmp_path.glob("*.tar"))
```

- [ ] **Step 2: Run and confirm backup tooling is absent**

Run: `PYTHONPATH=backend pytest backend/tests/test_backup_restore.py -q`
Expected: imports fail.

- [ ] **Step 3: Implement encrypted backup**

Require the application to be stopped before execution. Use `mysqldump --single-transaction --skip-lock-tables` with the password passed through a subprocess environment, include storage files and a SHA-256 manifest, and stream the tar archive directly to `age -r "$AGE_RECIPIENT"`. Write to a temporary `.partial` file and rename only after every command succeeds. Remove unencrypted temporary data on all failure paths; never log command environments or secrets.

- [ ] **Step 4: Implement isolated restore and proof**

`restore.py` requires `--confirm RESTORE`, a target database ending `_test`, and an empty target directory outside live storage. Reject existing non-empty targets and any development database/path. Read the age private key from `AGE_SECRET_KEY_FILE` outside the project, restore into `academic_submission_agent_restore_test`, run Alembic verification, and compare table names, representative row counts, file counts, and every manifest hash.

- [ ] **Step 5: Perform one real isolated backup/restore and optionally commit**

Run: `python scripts/test_backup_restore.py`
Expected: one encrypted backup is created and restored into the isolated test target; all hashes match and the development database/storage are unchanged.

```bash
git add scripts/backup.py scripts/restore.py scripts/test_backup_restore.py backups/README.md backend/tests/test_backup_restore.py
git commit -m "feat: add verified encrypted backup and restore"
```

---

### Task 17: Reconciliation Operations and Repeatable Setup

**Files:**
- Create: `scripts/dev_backend.sh`
- Create: `scripts/dev_frontend.sh`
- Create: `scripts/verify.sh`
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Test: `backend/tests/test_operational_guards.py`

**Interfaces:**
- Produces: reproducible local startup and one-command verification, with optional rather than required Docker MySQL.

- [ ] **Step 1: Write failing operational-guard tests**

```python
def test_test_storage_cannot_equal_live_storage():
    with pytest.raises(RuntimeError):
        validate_test_environment("academic_submission_agent_test", "storage", "storage")


def test_non_test_database_is_rejected():
    with pytest.raises(RuntimeError):
        validate_test_environment("academic_submission_agent", "/tmp/test", "storage")
```

- [ ] **Step 2: Run and fix environment guards**

Run: `cd backend && PYTHONPATH=. pytest tests/test_operational_guards.py -q`
Expected: guards fail until test configuration enforces `_test`, `ENVIRONMENT=test`, and a distinct temporary storage root.

- [ ] **Step 3: Add startup and verification scripts**

`dev_backend.sh` runs `uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`; `dev_frontend.sh` runs Vite on `127.0.0.1:5173`. `verify.sh` runs Ruff, mypy, pytest/coverage, OpenAPI validation/export diff, Newman, frontend tests, and production build, stopping on the first failure with the failing command visible.

The optional Compose file defines only MySQL 8 with a private volume and no public port by default; README must state that the selected installation uses Homebrew MySQL instead.

- [ ] **Step 4: Run the complete verification command**

Run: `bash scripts/verify.sh`
Expected: every backend, contract, frontend, coverage, and build gate exits 0.

- [ ] **Step 5: Optionally commit**

```bash
git add scripts docker-compose.yml .env.example backend/tests/test_operational_guards.py
git commit -m "chore: add repeatable local development workflow"
```

---

### Task 18: Documentation and Final Acceptance

**Files:**
- Create: `README.md`
- Create: `docs/operations.md`
- Create: `docs/security.md`
- Create: `docs/acceptance-v0.1.md`
- Modify: `.env.example`

**Interfaces:**
- Produces: reproducible installation, configuration, testing, backup/restore, security, and acceptance evidence for V0.1.

- [ ] **Step 1: Write the exact operator documentation**

Document Homebrew dependencies, virtualenv setup, MySQL bootstrap, hidden administrator creation, migrations, backend/frontend startup, test execution, OpenAPI/Postman verification, storage reconciliation, age key handling, encrypted backup, isolated restore, and recovery from unknown file commits. Every command must use the actual paths in this plan and must not contain real passwords.

- [ ] **Step 2: Perform clean installation from the documentation**

Use a fresh empty MySQL test schema and fresh temporary storage directory. Run dependency installation, two `upgrade head` commands, administrator initialization, login/change-password, and the complete verification script. Confirm 18 tables and no duplicate migration effects.

- [ ] **Step 3: Perform persistence and safety acceptance**

Create an author, manuscript, version, and file; run `brew services restart mysql@8.0` and restart both web processes; verify all records and the file hash remain. Run the complete security matrix and browser Network inspection. Confirm no secret or personal file is tracked, no audit write route exists, and test/dev storage/database targets remain distinct.

- [ ] **Step 4: Record acceptance evidence**

Create `docs/acceptance-v0.1.md` with the date, commands, test totals, coverage percentages, Newman totals, frontend build result, backup/restore hash result, MySQL restart result, and any explicitly unresolved limitations. Do not mark V0.1 complete if a required gate failed or was skipped.

- [ ] **Step 5: Final review and optional commit**

Run: `bash scripts/verify.sh`
Expected: all gates pass and the acceptance document accurately records the results.

```bash
git add README.md docs .env.example
git commit -m "docs: record v0.1 installation and acceptance"
```

---

## Execution Notes

- If any task exposes a security defect in an earlier task, stop downstream work, add a failing regression test to the owning task, fix it, and rerun all previous affected tests before continuing.
- The MySQL administrative connection, initial administrator password, and age private key are local interactive inputs. Pause only the step that needs them; never substitute hard-coded defaults.
- A successful normal CRUD path does not compensate for a failed isolation, sensitive-field, file-recovery, migration, backup-restore, or coverage gate.
