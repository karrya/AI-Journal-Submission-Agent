# AI 学术投稿 Agent V0.1 实施计划

> **供代理执行者使用：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，逐任务实施本计划。各步骤使用复选框（`- [ ]`）语法跟踪。

**目标：** 交付经批准的 macOS 本地 V0.1 应用，包含 18 张 MySQL 表、分层授权、作者/稿件/文件管理、Vue UI（用户界面）、契约测试，以及经过验证的加密备份/恢复。

**架构：** 构建模块化 FastAPI 单体应用和 Vue 3 SPA（单页应用）。先建立机器可读的路由/模式契约，再实现 SQLAlchemy 模型和 Alembic 迁移、服务层权限和事务、带补偿机制的本地文件存储，最后实现 UI 和运维验收。使用正在运行的 Homebrew MySQL 8 实例；Docker 可选，并非必需。

**技术栈：** Python 3.13、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、MySQL 8/PyMySQL、Argon2id、Vue 3、TypeScript、Vite、Element Plus、Pinia、Axios、pytest、Postman/Newman、Vitest、age。

**规格：** `docs/superpowers/specs/2026-11-04-v0-1-design.md`

## 全局约束

- 严格实现已批准规格中的 18 张核心表和分层隔离规则；不要添加投稿、邮件同步、AI、Playwright 业务、LangGraph 或调度器模块。
- 使用现有 MySQL 8 服务器。测试要求使用名称以 `_test` 结尾的独立数据库；绝不能用 SQLite 替代。
- 运行时使用仅拥有开发库 DML（数据操作语言）权限的 `asa_app`；Alembic 使用 `asa_migrate`；测试仅对测试库使用 `asa_test`。
- 密钥通过本地隐藏提示或权限为 `0600` 的 `.env` 文件输入。绝不输出或提交密码、原始 Session/CSRF（跨站请求伪造）令牌、age 私钥或类似生产环境的个人文件。
- 每个作者相关查询都经过 Service 授权。写权限绝不隐含读权限；受保护的写响应要求相应读权限。
- Session Cookie 为 `asa_session`，带 HttpOnly、`SameSite=Lax`、`Path=/` 属性；已认证的变更操作要求 Origin 和 `X-CSRF-Token`，登录除外，它仅要求 Origin 和速率限制。
- `must_change_password=true` 时，已认证 API 中仅允许 `/auth/me`、`/auth/csrf`、`/auth/change-password` 和 `/auth/logout`。
- 使用 UTC（协调世界时）`DATETIME(6)`、UUID（通用唯一标识符）`CHAR(36)`、InnoDB、utf8mb4、有限授权区间，并对历史关系使用 `ON DELETE RESTRICT`。
- 默认上传限制为 100 MiB，硬上限为 500 MiB。仅接受批准的扩展名；OOXML 归档要求结构和展开检查。拒绝一般 ZIP 文件。
- 业务变更及其必需的审计记录共享一个事务。数据库提交结果未知时，绝不立即删除已移动文件。
- 覆盖率目标：权限 95%、文件核心 90%、Services 85%、API 80%、后端总体 80%。安全和隔离测试是独立的发布检查项。
- 在执行交接时得到用户明确批准前，不要初始化 Git 或提交。如果获得批准，使用每个任务末尾的提交步骤；否则执行相同测试并请求变更审查，但不要提交。

## 审查重点

1. 精确时间戳的授权边界和多角色组合：`valid_from == now` 时生效，`valid_to == now` 时失效，已禁用用户绝不继承管理员权力。任务 6 负责参数化边界测试。
2. Unicode 和恶意名称：对显示名称进行 NFC 规范化，保留安全的国际文本，拒绝下载标头中的 CR/LF 或路径分隔符，同时不破坏数据库中的原始文件名。任务 9 负责文件名测试；任务 7 负责作者姓名测试。
3. 当前版本变化时并发创建版本和上传：使用真实已提交的 MySQL 夹具、独立连接，以及稿件 → 文件族的锁顺序。任务 8 和 9 负责竞争测试。
4. 提交结果未知和进程中断：保留文件，追加本地核对记录，并在任何清理前按文件 ID 和相对路径核对。任务 9 负责故障注入测试。
5. 备份中断和错误恢复目标：绝不留下看似可用的未加密不完整归档，也绝不覆盖开发数据。任务 16 负责中断和错误目标测试。

## 文件映射

- `backend/app/core/`：配置、数据库、Request ID、错误、日志。
- `backend/app/models/`：按身份、作者、稿件、文件、期刊和审计划分的 18 个 SQLAlchemy 实体。
- `backend/app/schemas/`：请求/响应模型和路由契约清单。
- `backend/app/security/`：Argon2id、Session、CSRF 和主体对象。
- `backend/app/repositories/`：仅负责持久化查询。
- `backend/app/services/`：权限、审计、领域事务、序列化器和存储补偿。
- `backend/app/api/v1/`：HTTP 依赖和资源路由器。
- `backend/alembic/`：两个显式模式迁移和环境配置。
- `backend/tests/`：单元、MySQL 集成、API、并发、故障注入测试和 Postman 资产。
- `frontend/src/`：类型化 API 客户端、认证状态存储、路由器、可复用表单/表格和领域视图。
- `scripts/`：MySQL 初始化、管理员创建、OpenAPI 导出、文件核对、加密备份/恢复和验证。
- `docs/api/v0.1-openapi.json`：根据清单校验的生成 API 契约。

---

### 任务 1：后端基础、配置与健康检查

**文件：**
- 创建：`backend/requirements.txt`
- 创建：`backend/requirements-dev.txt`
- 创建：`backend/pytest.ini`
- 创建：`backend/app/core/config.py`
- 创建：`backend/app/core/errors.py`
- 创建：`backend/app/main.py`
- 创建：`backend/tests/test_health.py`
- 创建：`.env.example`
- 创建：`.gitignore`

**接口：**
- 产出：`Settings`、`get_settings()`、`AppError`、`request_context`、`app`，以及返回 `{"status":"ok"}` 的 `GET /api/v1/health`。
- 后续任务使用：`get_settings()`、全局错误结构和 FastAPI `app`。

- [ ] **步骤 1：创建依赖和测试配置**

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

运行：从项目根目录执行 `../.venv/bin/python -m pip install -r backend/requirements-dev.txt`，然后执行 `brew install node age libmagic`。

- [ ] **步骤 2：编写预期失败的健康检查和错误结构测试**

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

- [ ] **步骤 3：运行测试并确认因应用缺失而失败**

运行：`cd backend && PYTHONPATH=. pytest tests/test_health.py -q`
预期：由于 `app.main` 不存在，测试收集失败。

- [ ] **步骤 4：实现配置、Request ID、错误和健康检查**

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

同时注册 `RequestValidationError`、`StarletteHTTPException` 和未处理异常处理器，使 405、422 和 500 使用相同错误结构。校验详情仅包含字段位置和安全消息；500 处理器在服务端记录异常，并返回不含堆栈的 `INTERNAL_SERVER_ERROR`。

仅为非密钥示例添加 `.env` 条目。忽略 `.env`、`storage/*`、`backups/*`、日志、`.venv`、`node_modules` 和生成的覆盖率输出。

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && PYTHONPATH=. pytest tests/test_health.py -q`
预期：2 个测试通过。

```bash
git add backend .env.example .gitignore
git commit -m "chore: add backend foundation and health contract"
```

---

### 任务 2：机器可读 API 契约与 Pydantic 模式

**文件：**
- 创建：`backend/app/schemas/common.py`
- 创建：`backend/app/schemas/auth.py`
- 创建：`backend/app/schemas/authors.py`
- 创建：`backend/app/schemas/manuscripts.py`
- 创建：`backend/app/schemas/files.py`
- 创建：`backend/app/schemas/journals.py`
- 创建：`backend/app/schemas/audit.py`
- 创建：`backend/app/api/v1/contract_manifest.py`
- 测试：`backend/tests/test_contract_manifest.py`

**接口：**
- 产出：规格 §3 中的所有请求/响应 Schema 名称和 `CONTRACTS: tuple[RouteContract, ...]`。
- 后续任务使用：准确的 Schema 名称和路由路径；任何路由器都不得在没有提示的情况下偏离清单。

- [ ] **步骤 1：编写预期失败的模式和路由覆盖测试**

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

- [ ] **步骤 2：运行契约测试并确认失败**

运行：`cd backend && PYTHONPATH=. pytest tests/test_contract_manifest.py -q`
预期：由于模式和清单不存在，导入失败。

- [ ] **步骤 3：实现严格通用模式和领域模型**

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

为 `AuthorCreate`、`AuthorUpdate`、`AuthorResponse`、邮箱/机构模型、有限期限的 `AuthorizationCreate`、稿件/版本模型、`FileResponse`、期刊模型、`AuditLogResponse` 和 `DashboardSummary` 实现已批准字段。`InstitutionSummaryResponse` 仅包含 `id`、`name`、`institution_type`、`website_url`、`country_code` 和 `city`；`InstitutionResponse` 仅供管理员使用。没有相应特定权限时，绝不填充可选敏感响应字段。

- [ ] **步骤 4：编码完整路由清单**

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

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && PYTHONPATH=. pytest tests/test_contract_manifest.py -q`
预期：3 个测试通过。

```bash
git add backend/app/schemas backend/app/api/v1/contract_manifest.py backend/tests/test_contract_manifest.py
git commit -m "feat: define strict v0.1 API contract"
```

---

### 任务 3：MySQL 初始化与身份/作者迁移

**文件：**
- 创建：`scripts/bootstrap_mysql.py`
- 创建：`backend/app/core/database.py`
- 创建：`backend/app/models/base.py`
- 创建：`backend/app/models/__init__.py`
- 创建：`backend/app/models/auth.py`
- 创建：`backend/app/models/authors.py`
- 创建：`backend/alembic.ini`
- 创建：`backend/alembic/env.py`
- 创建：`backend/alembic/versions/0001_identity_authors.py`
- 创建：`backend/app/api/v1/readiness.py`
- 修改：`backend/app/main.py`
- 创建：`backend/tests/conftest.py`
- 测试：`backend/tests/test_mysql_bootstrap.py`
- 测试：`backend/tests/test_identity_models.py`

**接口：**
- 产出：`Base`、`SessionLocal`、`get_db()`、前 9 张表，以及在不回显密钥的情况下写入权限为 `0600` 的 `.env` 的 `bootstrap_mysql.py`。
- 后续任务使用：`User`、`Role`、`UserRole`、`AuthSession`、`Author`、`AuthorEmail`、`Institution`、`AuthorInstitution`、`AuthorAuthorization`。

- [ ] **步骤 1：编写预期失败的安全和模型测试**

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

- [ ] **步骤 2：运行安全测试并确认失败**

运行：`PYTHONPATH=backend pytest backend/tests/test_mysql_bootstrap.py -q`
预期：`scripts.bootstrap_mysql` 导入失败。

- [ ] **步骤 3：实现隐藏输入的数据库初始化**

使用固定标识符 `academic_submission_agent`、`academic_submission_agent_test`、`asa_app`、`asa_migrate` 和 `asa_test`。通过 `getpass.getpass()` 提示输入 MySQL 管理密码，使用 `secrets.token_urlsafe(32)` 生成三个密码，并通过参数化 PyMySQL 语句创建两个数据库和三个用户。向 `asa_app` 授予仅 DML 的开发库访问权限，向 `asa_migrate` 授予 DDL（数据定义语言）/DML 开发库访问权限，向 `asa_test` 授予仅限测试库的完整访问权限。

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

将 `DATABASE_URL`、`ALEMBIC_DATABASE_URL`、`TEST_DATABASE_URL`、随机 `CSRF_SECRET_KEY` 和 `ENVIRONMENT=development` 写入 `.env`；调用 `os.chmod(".env", 0o600)`，且绝不输出生成的值。

- [ ] **步骤 4：实现模型和迁移，然后在 MySQL 上验证**

定义 `Base`、UUID 默认值、UTC 辅助函数、混入类和九个模型，包含规格 §2.4 中的每个字段和约束。使用 `DATETIME(6)`、JSON 权限数组、ORCID 唯一索引及以下生成的主邮箱列：

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

`alembic/env.py` 只能读取 `ALEMBIC_DATABASE_URL`；运行时 `get_db()` 只能读取 `DATABASE_URL`。在 `readiness.py` 中添加 `GET /api/v1/health/ready`，执行 `SELECT 1`，失败时返回不含连接详情的 `DATABASE_UNAVAILABLE`；在 `main.py` 中包含其路由器。`tests/conftest.py` 加载 `TEST_DATABASE_URL`，拒绝非 `_test` 目标和正式存储，每个测试会话运行一次迁移，并提供独立引擎/会话夹具及临时测试存储根目录。通过本地隐藏输入运行 `python scripts/bootstrap_mysql.py`，然后运行 `cd backend && alembic upgrade head`。

添加一个集成断言：

```python
def test_first_migration_has_nine_tables(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert {"users", "roles", "user_roles", "auth_sessions", "authors",
            "author_emails", "institutions", "author_institutions",
            "author_authorizations"}.issubset(names)
```

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_mysql_bootstrap.py tests/test_identity_models.py -q`
预期：安全测试和首次迁移集成测试在 `academic_submission_agent_test` 上通过。

```bash
git add scripts/bootstrap_mysql.py backend/app/core/database.py backend/app/models backend/alembic backend/tests
git commit -m "feat: add identity and author database schema"
```

---

### 任务 4：稿件、文件、期刊与审计迁移

**文件：**
- 创建：`backend/app/models/manuscripts.py`
- 创建：`backend/app/models/files.py`
- 创建：`backend/app/models/journals.py`
- 创建：`backend/app/models/audit.py`
- 创建：`backend/alembic/versions/0002_manuscripts_files_journals_audit.py`
- 测试：`backend/tests/test_schema_constraints.py`

**接口：**
- 产出：其余 9 张表及其复合外键，总计恰好 18 张表。
- 后续任务使用：所有稿件/文件/期刊/审计模型类和迁移 `head=0002`。

- [ ] **步骤 1：编写预期失败的迁移和跨稿件约束测试**

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

- [ ] **步骤 2：运行并确认第二个迁移不存在**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_schema_constraints.py -q`
预期：表集合断言失败，且稿件模型不可用。

- [ ] **步骤 3：实现九个模型和有序迁移**

先创建不含当前版本外键的 `manuscripts`，再创建 `manuscript_versions`，然后添加 `(id, current_version_id) → (manuscript_id, id)`。使用以下约束创建文件族和文件：

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

实现 `(manuscript_id, author_id) → manuscripts(id, owner_author_id)` 文件族约束、所有期刊字段和仅追加的 `operation_logs`。任何模型关系都不得对历史记录使用级联删除。

- [ ] **步骤 4：验证迁移可重复性和约束**

运行：

```bash
cd backend
ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test PYTHONPATH=. pytest tests/test_schema_constraints.py -q
```

预期：第二次升级不执行任何操作；所有约束测试通过。

- [ ] **步骤 5：可选提交**

```bash
git add backend/app/models backend/alembic/versions/0002_manuscripts_files_journals_audit.py backend/tests/test_schema_constraints.py
git commit -m "feat: complete eighteen-table mysql schema"
```

---

### 任务 5：身份认证、Session、CSRF 与初始密码限制

**文件：**
- 创建：`backend/app/security/passwords.py`
- 创建：`backend/app/security/sessions.py`
- 创建：`backend/app/security/csrf.py`
- 创建：`backend/app/services/auth.py`
- 创建：`backend/app/api/v1/deps.py`
- 创建：`backend/app/api/v1/auth.py`
- 创建：`scripts/create_admin.py`
- 测试：`backend/tests/test_auth_api.py`

**接口：**
- 产出：`SessionService`、`Principal`、`get_principal`、`require_csrf` 和所有 `/auth/*` 端点。
- 后续任务使用：`Principal.user`、`Principal.session` 和身份认证依赖。

- [ ] **步骤 1：编写预期失败的身份认证测试**

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

- [ ] **步骤 2：运行并确认身份认证缺失**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_auth_api.py -q`
预期：路由导入或 404 断言失败。

- [ ] **步骤 3：实现密码、Session 和 CSRF 基础机制**

使用 `argon2.PasswordHasher`、32 字节随机 Session 令牌和 SHA-256（安全哈希算法 256 位）数据库查询。在不存储稳定 CSRF 令牌的情况下派生它：

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

`get_principal` 检查用户状态、令牌哈希、撤销、空闲过期和绝对过期。它更新空闲活动，但不缓存作者权限。身份认证启动时拒绝为空或短于 32 字节的 `CSRF_SECRET_KEY`；健康检查仍可用于诊断该配置错误。初始密码依赖以 `PASSWORD_CHANGE_REQUIRED` 拒绝每个业务路由，仅允许四个批准的认证路由。

- [ ] **步骤 4：实现认证路由和管理员初始化**

`create_admin.py` 使用隐藏输入提示输入用户名和密码，验证长度为 12–128 字符，以事务方式初始化五种角色，并创建一个带 `must_change_password=true` 的 `system_admin`。登录审计成功/失败，但不记录用户名或密码。退出登录和修改密码要求 CSRF；修改密码撤销所有会话。

添加以规范化用户名和源 IP 为键的速率限制，对未知用户和错误密码返回相同的 `UNAUTHORIZED` 响应。绝不在日志中包含原始令牌。

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_auth_api.py -q`
预期：所有身份认证、稳定 CSRF、源、撤销和初始密码测试通过。

```bash
git add backend/app/security backend/app/services/auth.py backend/app/api/v1 scripts/create_admin.py backend/tests/test_auth_api.py
git commit -m "feat: add secure local session authentication"
```

---

### 任务 6：分层权限与事务化审计

**文件：**
- 创建：`backend/app/services/permissions.py`
- 创建：`backend/app/services/audit.py`
- 创建：`backend/app/repositories/authorizations.py`
- 创建：`backend/app/repositories/audit.py`
- 测试：`backend/tests/test_permissions.py`
- 测试：`backend/tests/test_audit_transactions.py`

**接口：**
- 产出：`Permission`、`require_author_permission()`、`require_roles()`、`has_author_permission()` 和 `AuditService.record()`。
- 后续任务使用：一个权限服务处理每个作者/稿件/文件决策，一个审计服务处理每次受保护写入或敏感读取。

- [ ] **步骤 1：编写预期失败的权限边界测试**

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

- [ ] **步骤 2：运行并确认权限服务缺失**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_permissions.py -q`
预期：`Permission` 导入失败。

- [ ] **步骤 3：实现角色聚合和数据库支持的授权**

将九个 V0.1 权限字符串定义为 `str, Enum`。非管理员角色能力取角色集合的并集；`system_admin` 仅在用户活动状态验证通过后优先。授权查询使用 `JSON_CONTAINS`、有限 UTC 区间、`revoked_at IS NULL`，并联接活动用户/作者。

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

`require_author_permission` 区分无授权（`404`）、未生效/过期/已撤销授权（`403 AUTHORIZATION_EXPIRED`）和有效授权缺少权限代码（`403 PERMISSION_DENIED`）。角色拒绝发生在资源查询之前。

- [ ] **步骤 4：实现脱敏审计和回滚证明**

`AuditService.record()` 接受显式白名单中的 before/after 字典，拒绝包含 password/token/cookie/secret/email/phone/address/storage_path 的键，并写入一条仅追加日志。添加一个测试，强制 `session.add(OperationLog)` 失败并证明回滚后业务行不存在。添加 operator+reviewer、auditor+operator 和 disabled admin+reviewer 的多角色测试。

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_permissions.py tests/test_audit_transactions.py --cov=app.services.permissions --cov-fail-under=95 -q`
预期：权限覆盖率至少为 95%，且所有事务测试通过。

```bash
git add backend/app/services backend/app/repositories backend/tests/test_permissions.py backend/tests/test_audit_transactions.py
git commit -m "feat: enforce layered authorization and audit"
```

---

### 任务 7：作者、邮箱、机构与授权 API

**文件：**
- 创建：`backend/app/repositories/authors.py`
- 创建：`backend/app/services/authors.py`
- 创建：`backend/app/services/authorizations.py`
- 创建：`backend/app/api/v1/authors.py`
- 创建：`backend/app/api/v1/authorizations.py`
- 测试：`backend/tests/test_authors_api.py`
- 测试：`backend/tests/test_authorizations_api.py`

**接口：**
- 产出：所有作者、邮箱、机构、作者-机构和作者-授权路由。
- 后续任务使用：`AuthorService.require_readable_author()` 和稿件测试的授权夹具。

- [ ] **步骤 1：编写预期失败的规范化和隔离测试**

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

- [ ] **步骤 2：运行并确认领域路由缺失**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_authors_api.py -q`
预期：404 或导入失败。

- [ ] **步骤 3：实现规范化和事务化作者服务**

显示名称使用 NFC，比较字段去除首尾空白并转为小写，提供 ORCID MOD 11-2 和 ISSN（国际标准连续出版物号）校验辅助函数。创建/更新作者要求显式身份确认。作者 PATCH 要求资料读取+更新权限。邮箱写入要求资料更新+邮箱读取权限；创建和地址变更要求字面确认，删除接受请求正文中的 `{"confirm_email_binding":true}`。

机构列表/详情对非管理员用户返回 `InstitutionSummaryResponse`。作者-机构写入要求资料更新+读取权限及活动机构。敏感响应按返回的每位作者/每个类别创建一条审计条目，但不记录具体值。

- [ ] **步骤 4：实现有限期限的作者授权**

仅管理员可管理授权。拒绝未知/空权限代码、`valid_to <= now` 和 `valid_to <= valid_from`。撤销设置 `revoked_at`，无需使 Session 缓存失效即在下次请求生效。记录 before/after 权限数组，但不记录证据内容。

添加以下集成用例：规范化邮箱重复、生成列唯一主邮箱、ORCID 校验位、无读权限写入拒绝、授权过期和跨作者 `404`。

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_authors_api.py tests/test_authorizations_api.py -q`
预期：所有作者和授权测试通过。

```bash
git add backend/app/repositories/authors.py backend/app/services/authors.py backend/app/services/authorizations.py backend/app/api/v1/authors.py backend/app/api/v1/authorizations.py backend/tests
git commit -m "feat: add isolated author management apis"
```

---

### 任务 8：稿件、署名与不可变版本 API

**文件：**
- 创建：`backend/app/repositories/manuscripts.py`
- 创建：`backend/app/services/manuscripts.py`
- 创建：`backend/app/schemas/manuscripts.py`
- 创建：`backend/app/api/v1/manuscripts.py`
- 测试：`backend/tests/test_manuscripts_api.py`
- 测试：`backend/tests/test_manuscript_concurrency.py`

**接口：**
- 产出：`ManuscriptService`、稿件 CRUD、排序署名和不可变版本路由。
- 文件任务使用：`ManuscriptService.get_owned_manuscript()` 和 `ManuscriptService.lock_current_version()`。

- [ ] **步骤 1：编写预期失败的稿件和最小作者信息测试**

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

- [ ] **步骤 2：运行并确认稿件路由缺失**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_manuscripts_api.py -q`
预期：路由或服务导入失败。

- [ ] **步骤 3：实现稿件事务和序列化器**

创建稿件时锁定所有者范围，插入工作元数据、当前署名和 v1 快照，然后设置 `current_version_id`。默认署名为位置 1 的所有者，并设为通讯作者。输入仅接受 `author_id`、`position` 和 `is_corresponding`；显示名称来自数据库。

PATCH 和版本创建要求更新+读取权限。署名 PUT 锁定稿件，记录最小 before/after 列表，删除当前关联，并在一个事务中插入新的有序列表。新关联的共同作者要求资料读取权限。元数据/版本快照绝不包含共同作者敏感字段。

- [ ] **步骤 4：添加真实 MySQL 并发测试**

使用已提交夹具和两个独立会话/线程。初始 v1 后并发调用 `POST /versions` 必须生成版本 2 和 3，且编号不重复。同时执行元数据 PATCH 和版本创建时，必须在稿件行上串行化，使快照完全位于 PATCH 之前或之后。

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_manuscripts_api.py tests/test_manuscript_concurrency.py -q`
预期：稿件、署名、快照和并发测试通过。

```bash
git add backend/app/repositories/manuscripts.py backend/app/services/manuscripts.py backend/app/api/v1/manuscripts.py backend/app/schemas/manuscripts.py backend/tests
git commit -m "feat: add versioned manuscript management"
```

---

### 任务 9：安全文件族、上传、下载与核对

**文件：**
- 创建：`backend/app/services/file_validation.py`
- 创建：`backend/app/services/storage.py`
- 创建：`backend/app/services/files.py`
- 创建：`backend/app/repositories/files.py`
- 创建：`backend/app/api/v1/files.py`
- 创建：`scripts/reconcile_files.py`
- 测试：`backend/tests/test_file_validation.py`
- 测试：`backend/tests/test_files_api.py`
- 测试：`backend/tests/test_file_failures.py`

**接口：**
- 产出：`FileValidator`、`StorageService`、`FileService.upload()`、`FileService.download()` 和 `reconcile_files.py`。
- 后续任务使用：安全文件夹具和位于 `storage/reconciliation.jsonl` 的核对清单。

- [ ] **步骤 1：编写预期失败的校验和路径测试**

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

- [ ] **步骤 2：运行并确认文件服务缺失**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_file_validation.py -q`
预期：导入失败。

- [ ] **步骤 3：实现流式校验和 OOXML 限制**

以 1 MiB 分块将上传流式写入 `storage/temp/{uuid}.part`，在计算哈希时强制执行大小限制。使用 libmagic 和扩展名白名单；验证 PDF/OOXML/OLE/图像结构。对于 DOCX/XLSX，不解压而检查 ZIP 元数据：最多 2,000 个条目，展开总大小最多 500 MiB，单条目压缩比最多 100:1，且不得嵌套 ZIP/OOXML。拒绝一般 ZIP、HTML、SVG、脚本和可执行文件。

`safe_download_filename` 移除 CR/LF、斜杠、NUL 和控制字符；国际名称使用 ASCII 回退名称加 RFC 5987 UTF-8 编码。

- [ ] **步骤 4：实现锁定上传和感知结果的补偿**

在事务前生成文件 UUID。临时校验后锁定稿件，重新检查 `version_id == current_version_id`，然后锁定/创建文件族并递增 `file_version`。仅存储以下相对路径：

```python
relative = Path("authors") / str(author_id) / "manuscripts" / str(manuscript_id) \
    / "versions" / str(version_id) / f"{file_uuid}{extension}"
```

在 `os.replace(temp, final)` 前插入文件元数据和审计。移动失败则回滚。如果确定已回滚且记录不存在，则清理。如果提交抛出异常或连接状态未知，保留文件，并向 `storage/reconciliation.jsonl` 追加包含 `file_id`、`relative_path`、`sha256` 和 UTC 时间的 JSON；任何删除前使用新数据库连接核对。`reconcile_files.py` 报告缺失文件和孤立文件，不自动删除状态未知的正式文件。

- [ ] **步骤 5：添加故障/竞争测试并验证**

测试 MIME 伪造、恰好达到大小限制和限制+1、OOXML 炸弹、路径穿越、两个同时进行的同族上传生成版本 1 和 2、当前版本变化期间上传返回 `409`、确定回滚清理、未知提交保留、缺失文件下载拒绝，以及 `FileResponse` 不含敏感路径。

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_file_validation.py tests/test_files_api.py tests/test_file_failures.py --cov=app.services.files --cov=app.services.storage --cov-fail-under=90 -q`
预期：所有文件测试通过，文件核心覆盖率至少为 90%。

```bash
git add backend/app/services backend/app/repositories/files.py backend/app/api/v1/files.py scripts/reconcile_files.py backend/tests
git commit -m "feat: add recoverable versioned file storage"
```

---

### 任务 10：期刊、仪表盘与审计 API

**文件：**
- 创建：`backend/app/repositories/journals.py`
- 创建：`backend/app/services/journals.py`
- 创建：`backend/app/services/dashboard.py`
- 创建：`backend/app/api/v1/journals.py`
- 创建：`backend/app/api/v1/dashboard.py`
- 创建：`backend/app/api/v1/audit.py`
- 测试：`backend/tests/test_journals_api.py`
- 测试：`backend/tests/test_dashboard_audit.py`

**接口：**
- 产出：出版商/平台/期刊 CRUD、按权限过滤的仪表盘和只读审计查询。
- 前端任务使用：所有其余 API 资源。

- [ ] **步骤 1：编写预期失败的角色和来源测试**

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

- [ ] **步骤 2：运行并确认其余路由缺失**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_journals_api.py tests/test_dashboard_audit.py -q`
预期：404 或导入失败。

- [ ] **步骤 3：实现资源和按权限过滤的汇总**

仅管理员可写入期刊资源。仅 `system_admin`、`submission_operator` 和 `reviewer` 可读取。校验 ISSN/eISSN 校验位、HTTPS URL，以及每个要求条目的来源和验证时间戳。

仪表盘计数使用与列表端点相同的权限谓词；审计员收到 `403`。最近操作仅限当前用户，且不含敏感值。

- [ ] **步骤 4：实现只读审计过滤**

仅 `system_admin` 和 `auditor` 可查询审计日志。过滤器覆盖操作者、作者、类别、操作、目标、结果、Request ID 和 UTC 范围。不注册创建/更新/删除审计路由，并添加测试验证 `DELETE /api/v1/audit-logs/{id}` 返回 405。

- [ ] **步骤 5：验证并可选提交**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_journals_api.py tests/test_dashboard_audit.py -q`
预期：所有资源、角色、来源和仅追加测试通过。

```bash
git add backend/app/repositories/journals.py backend/app/services/journals.py backend/app/services/dashboard.py backend/app/api/v1 backend/tests
git commit -m "feat: add journal dashboard and audit apis"
```

---

### 任务 11：OpenAPI 导出与 Postman/Newman 契约套件

**文件：**
- 创建：`scripts/export_openapi.py`
- 创建：`docs/api/v0.1-openapi.json`
- 创建：`backend/tests/postman/v0.1.postman_collection.json`
- 创建：`backend/tests/postman/local.postman_environment.json`
- 创建：`backend/tests/test_openapi_generated.py`
- 创建：`scripts/test_api.sh`

**接口：**
- 产出：可复现的 OpenAPI 产物和覆盖正向及负向工作流的 Newman 命令。
- 最终验证使用：`scripts/test_api.sh` 和已检查的 OpenAPI 文件。

- [ ] **步骤 1：编写预期失败的 OpenAPI 路径/清单一致性测试**

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

- [ ] **步骤 2：运行并纠正任何路由偏差**

运行：`cd backend && PYTHONPATH=. pytest tests/test_openapi_generated.py -q`
预期：任何缺失或额外路由都会失败，并显示准确的集合差异。修正路由器或经有意审查的清单；不要削弱断言。

- [ ] **步骤 3：导出并校验 OpenAPI**

```python
# scripts/export_openapi.py
import json
from pathlib import Path
from app.main import app

output = Path("docs/api/v0.1-openapi.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

运行 `PYTHONPATH=backend python scripts/export_openapi.py`，并使用 `openapi-spec-validator docs/api/v0.1-openapi.json` 校验。

- [ ] **步骤 4：构建 Postman 工作流**

集合顺序：健康检查 → 登录 → 保存 CSRF → 修改初始密码 → 再次登录 → 创建作者 A/B → 仅向测试操作员授予 A → 创建以 B 为共同作者的稿件 → 创建版本 → 上传 `backend/tests/fixtures/minimal.pdf` → 列出稿件/版本/文件 → 验证 B 不含邮箱/电话/地址 → 测试无会话、错误 CSRF、授权过期、跨作者 ID、无读权限写入、机构地址摘要和审计不可变性。

在每个共同作者响应测试中使用以下断言：

```javascript
const body = pm.response.json();
const serialized = JSON.stringify(body);
pm.test("no sensitive coauthor fields", function () {
    pm.expect(serialized).not.to.match(/phone_number|phone_country_code|address_line1|postal_code|normalized_email/);
});
```

环境文件中仅存储 `base_url`、用户名和空密钥占位符。运行时注入 `ADMIN_PASSWORD`、`OPERATOR_PASSWORD`、Session Cookie 和 CSRF。使用 `npm install --prefix frontend --save-dev newman@6.2.1` 安装运行器，并通过 `npx --prefix frontend newman` 调用。`scripts/test_api.sh` 使用测试数据库和临时存储在 `127.0.0.1:8001` 启动隔离后端，等待就绪，运行 Newman，并在每次退出时通过 `trap` 停止该进程。不要将集合推送到 Postman Cloud。

- [ ] **步骤 5：运行 Newman 并可选提交**

运行：`bash scripts/test_api.sh`
预期：Newman 以 0 退出，所有正向和负向断言通过。

```bash
git add scripts/export_openapi.py scripts/test_api.sh docs/api backend/tests/postman backend/tests/test_openapi_generated.py
git commit -m "test: verify openapi and postman api contract"
```

---

### 任务 12：Vue 基础、身份认证与类型化 API 客户端

**文件：**
- 创建：`frontend/package.json`
- 创建：`frontend/vite.config.ts`
- 创建：`frontend/tsconfig.json`
- 创建：`frontend/src/main.ts`
- 创建：`frontend/src/api/client.ts`
- 创建：`frontend/src/stores/auth.ts`
- 创建：`frontend/src/router/index.ts`
- 创建：`frontend/src/views/auth/LoginView.vue`
- 创建：`frontend/src/views/auth/ChangePasswordView.vue`
- 测试：`frontend/src/api/client.test.ts`
- 测试：`frontend/src/stores/auth.test.ts`

**接口：**
- 产出：`api`、`useAuthStore`、受保护路由器，以及可用的登录/修改密码/退出登录。
- 其他 UI 任务使用：类型化 `api`、认证状态存储和路由守卫。

- [ ] **步骤 1：创建 Vite 脚本和预期失败的认证状态存储测试**

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

- [ ] **步骤 2：运行并确认前端在实现前失败**

运行：`cd frontend && npm install && npm test -- src/stores/auth.test.ts`
预期：认证状态存储导入失败。

- [ ] **步骤 3：实现 Axios 和 Pinia 身份认证**

使用 `baseURL: '/api/v1'`、`withCredentials: true` 和内存中的 CSRF。变更请求附加 `X-CSRF-Token`。遇到 `SECURITY_CHECK_FAILED` 时，请求 `/auth/csrf` 并重试一次；遇到 `401` 时，清除状态并跳转至登录；遇到 `PASSWORD_CHANGE_REQUIRED` 时，跳转至修改密码。绝不持久化 Session 或 CSRF 令牌。

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`；允许的源仍为显式本地值。使用 `environment: 'jsdom'` 和 `globals: true` 配置 Vitest，并启用 Vue 插件。添加 Element Plus、Vue Router 和 Pinia，采用单一应用布局。

- [ ] **步骤 4：实现登录和初始密码视图**

表单使用后端字段名，防止重复提交，服务器错误显示 Request ID，且绝不显示密码哈希或原始服务器堆栈。修改密码后，清除状态并返回登录。路由守卫等待 `/auth/me` 后再选择目标。

- [ ] **步骤 5：验证并可选提交**

运行：`cd frontend && npm test && npm run build`
预期：Vitest、TypeScript 和 Vite 构建通过。

```bash
git add frontend
git commit -m "feat: add vue authentication foundation"
```

---

### 任务 13：作者、机构、授权与期刊 UI

**文件：**
- 创建：`frontend/src/api/authors.ts`
- 创建：`frontend/src/api/journals.ts`
- 创建：`frontend/src/components/AuthorForm.vue`
- 创建：`frontend/src/components/EmailTable.vue`
- 创建：`frontend/src/components/InstitutionLinkForm.vue`
- 创建：`frontend/src/views/authors/AuthorListView.vue`
- 创建：`frontend/src/views/authors/AuthorDetailView.vue`
- 创建：`frontend/src/views/authors/AuthorizationView.vue`
- 创建：`frontend/src/views/journals/JournalListView.vue`
- 测试：`frontend/src/components/AuthorForm.test.ts`
- 测试：`frontend/src/views/authors/AuthorDetailView.test.ts`

**接口：**
- 产出：可用的作者、邮箱、机构、授权、出版商、平台和期刊管理页面。
- 稿件 UI 使用：仅返回已授权资料的作者搜索。

- [ ] **步骤 1：编写预期失败的显式确认和字段缺失测试**

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

- [ ] **步骤 2：运行并确认组件失败**

运行：`cd frontend && npm test -- src/components/AuthorForm.test.ts src/views/authors/AuthorDetailView.test.ts`
预期：组件导入失败。

- [ ] **步骤 3：实现类型化表单和作者详情**

创建/更新/响应使用独立 API 类型。仅当前权限集合允许时，作者详情才请求邮箱和机构，并处理 `403` 而不保留过期缓存数据。邮箱创建/地址变更和署名变更使用显式确认控件。机构选择器使用摘要响应，绝不期望详细地址。

- [ ] **步骤 4：实现授权和期刊页面**

授权表单仅显示九个已定义权限，要求有限开始/结束时间，并提供独立撤销确认。期刊要求行必须包含键、值、范围、HTTPS 来源 URL 和验证时间。出版商/平台/期刊表格支持服务端分页、白名单排序、空状态和软删除确认。

- [ ] **步骤 5：验证并可选提交**

运行：`cd frontend && npm test && npm run build`
预期：所有组件测试和生产构建通过。

```bash
git add frontend/src
git commit -m "feat: add author and journal management views"
```

---

### 任务 14：稿件、版本、文件、仪表盘与审计 UI

**文件：**
- 创建：`frontend/src/api/manuscripts.ts`
- 创建：`frontend/src/api/files.ts`
- 创建：`frontend/src/components/AuthorshipEditor.vue`
- 创建：`frontend/src/components/FileFamilyUpload.vue`
- 创建：`frontend/src/views/manuscripts/ManuscriptListView.vue`
- 创建：`frontend/src/views/manuscripts/ManuscriptDetailView.vue`
- 创建：`frontend/src/views/dashboard/DashboardView.vue`
- 创建：`frontend/src/views/audit/AuditListView.vue`
- 测试：`frontend/src/components/AuthorshipEditor.test.ts`
- 测试：`frontend/src/components/FileFamilyUpload.test.ts`

**接口：**
- 产出：从作者/稿件创建到文件版本管理和审计检查的完整 V0.1 用户工作流。

- [ ] **步骤 1：编写预期失败的署名和文件测试**

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

- [ ] **步骤 2：运行并确认组件失败**

运行：`cd frontend && npm test -- src/components/AuthorshipEditor.test.ts src/components/FileFamilyUpload.test.ts`
预期：组件导入失败。

- [ ] **步骤 3：实现稿件和署名工作流**

提供所有者选择、元数据编辑、有序作者列表、通讯作者选择和显式署名确认。显示当前版本和不可变快照历史。不渲染最小作者响应中不存在的字段，也不从其他缓存视图推断敏感数据。

- [ ] **步骤 4：实现文件版本管理和安全错误处理**

文件上传支持新文件族和现有文件族模式，显示客户端大小/类型提示但不将其视为安全检查，并使用 Axios 进度。上传后刷新文件族和当前版本。对 `409` 当前版本冲突显示刷新操作，而非自动重试。仅通过授权端点下载，绝不暴露 `storage_path`。

仪表盘仅显示返回的汇总。审计页面为管理员/审计员路由，带过滤器且无编辑/删除按钮。

- [ ] **步骤 5：验证并手动检查 Network**

运行：`cd frontend && npm test && npm run build`
预期：测试和构建通过。使用两名作者且仅所有者获授权，在浏览器 Network 中验证稿件、版本和文件响应不含共同作者邮箱、电话、地址、ORCID（开放研究者与贡献者标识）或备注。

```bash
git add frontend/src
git commit -m "feat: complete manuscript and file workspace"
```

---

### 任务 15：安全矩阵、故障注入与覆盖率检查

**文件：**
- 创建：`backend/tests/test_security_matrix.py`
- 创建：`backend/tests/test_authorization_boundaries.py`
- 创建：`scripts/check_coverage.py`
- 测试：`backend/tests/postman/v0.1.postman_collection.json`

**接口：**
- 产出：针对规格 §5.3 矩阵和全部覆盖率下限的一个可执行发布检查项。

- [ ] **步骤 1：将其余负向矩阵编码为参数化测试**

覆盖 AUTH-01 至 AUTH-05、ROLE-01、AUTHZ-01 至 AUTHZ-03、ISO-01 至 ISO-06、FILE-01 至 FILE-05、TX-01、MIG-01、API-01 和 WEB-01。BACKUP-01 在任务 16 中实现并执行。使用显式预期状态和字段缺失断言，而非仅检查状态。

```python
@pytest.mark.parametrize("path", [
    "/api/v1/authors", "/api/v1/manuscripts", "/api/v1/dashboard/summary",
])
def test_initial_password_gate_is_global(client, login_initial_admin, path):
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
```

- [ ] **步骤 2：运行矩阵并修复实现缺陷，而不是修改预期值**

运行：`cd backend && ENVIRONMENT=test PYTHONPATH=. pytest tests/test_security_matrix.py tests/test_authorization_boundaries.py -q`
预期：初始运行识别出任何未实现的负向用例；修复后全部通过，且不删除字段断言。

- [ ] **步骤 3：添加分层覆盖率检查**

使用 `--cov=app --cov-report=json:coverage.json` 运行 pytest，然后计算总体和按路径划分的覆盖率：

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

- [ ] **步骤 4：验证所有后端质量检查项**

运行：`cd backend && ruff check app tests && mypy app && ENVIRONMENT=test PYTHONPATH=. pytest --cov=app --cov-report=json:coverage.json && python ../scripts/check_coverage.py`
预期：Lint、类型检查、测试和全部五项覆盖率下限均通过。

- [ ] **步骤 5：可选提交**

```bash
git add backend scripts/check_coverage.py
git commit -m "test: enforce security and coverage release gates"
```

---

### 任务 16：加密备份与隔离恢复

**文件：**
- 创建：`scripts/backup.py`
- 创建：`scripts/restore.py`
- 创建：`scripts/test_backup_restore.py`
- 创建：`backups/README.md`
- 测试：`backend/tests/test_backup_restore.py`

**接口：**
- 产出：带 SHA-256 清单的加密 `.tar.age` 备份，以及仅接受以 `_test` 结尾的显式隔离目标的恢复命令。

- [ ] **步骤 1：编写预期失败的错误目标和中断测试**

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

- [ ] **步骤 2：运行并确认备份工具缺失**

运行：`PYTHONPATH=backend pytest backend/tests/test_backup_restore.py -q`
预期：导入失败。

- [ ] **步骤 3：实现加密备份**

执行前要求应用已停止。使用 `mysqldump --single-transaction --skip-lock-tables`，通过子进程环境传递密码，包含存储文件和 SHA-256 清单，并将 tar 归档直接流式传入 `age -r "$AGE_RECIPIENT"`。写入临时 `.partial` 文件，仅在所有命令成功后重命名。所有失败路径均删除未加密临时数据；绝不记录命令环境或密钥。

- [ ] **步骤 4：实现隔离恢复和验证**

`restore.py` 要求 `--confirm RESTORE`、以 `_test` 结尾的目标数据库，以及正式存储之外的空目标目录。拒绝现有非空目标和任何开发数据库/路径。从项目之外的 `AGE_SECRET_KEY_FILE` 读取 age 私钥，恢复到 `academic_submission_agent_restore_test`，运行 Alembic 验证，并比较表名、代表性行数、文件数量和每个清单哈希。

- [ ] **步骤 5：执行一次真实隔离备份/恢复并可选提交**

运行：`python scripts/test_backup_restore.py`
预期：创建一个加密备份并恢复到隔离测试目标；所有哈希匹配，开发数据库/存储保持不变。

```bash
git add scripts/backup.py scripts/restore.py scripts/test_backup_restore.py backups/README.md backend/tests/test_backup_restore.py
git commit -m "feat: add verified encrypted backup and restore"
```

---

### 任务 17：核对运维与可重复配置

**文件：**
- 创建：`scripts/dev_backend.sh`
- 创建：`scripts/dev_frontend.sh`
- 创建：`scripts/verify.sh`
- 创建：`docker-compose.yml`
- 修改：`.env.example`
- 测试：`backend/tests/test_operational_guards.py`

**接口：**
- 产出：可复现的本地启动和单命令验证，Docker MySQL 可选而非必需。

- [ ] **步骤 1：编写预期失败的运维防护测试**

```python
def test_test_storage_cannot_equal_live_storage():
    with pytest.raises(RuntimeError):
        validate_test_environment("academic_submission_agent_test", "storage", "storage")


def test_non_test_database_is_rejected():
    with pytest.raises(RuntimeError):
        validate_test_environment("academic_submission_agent", "/tmp/test", "storage")
```

- [ ] **步骤 2：运行并修复环境防护**

运行：`cd backend && PYTHONPATH=. pytest tests/test_operational_guards.py -q`
预期：在测试配置强制执行 `_test`、`ENVIRONMENT=test` 和独立临时存储根目录之前，防护失败。

- [ ] **步骤 3：添加启动和验证脚本**

`dev_backend.sh` 运行 `uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`；`dev_frontend.sh` 在 `127.0.0.1:5173` 运行 Vite。`verify.sh` 运行 Ruff、mypy、pytest/覆盖率、OpenAPI 校验/导出差异检查、Newman、前端测试和生产构建，首次失败即停止并显示失败命令。

可选 Compose 文件仅定义使用私有卷且默认不公开端口的 MySQL 8；README 必须说明选定安装方案改用 Homebrew MySQL。

- [ ] **步骤 4：运行完整验证命令**

运行：`bash scripts/verify.sh`
预期：每个后端、契约、前端、覆盖率和构建检查项均以 0 退出。

- [ ] **步骤 5：可选提交**

```bash
git add scripts docker-compose.yml .env.example backend/tests/test_operational_guards.py
git commit -m "chore: add repeatable local development workflow"
```

---

### 任务 18：文档与最终验收

**文件：**
- 创建：`README.md`
- 创建：`docs/operations.md`
- 创建：`docs/security.md`
- 创建：`docs/acceptance-v0.1.md`
- 修改：`.env.example`

**接口：**
- 产出：V0.1 可复现的安装、配置、测试、备份/恢复、安全和验收证据。

- [ ] **步骤 1：编写准确的操作员文档**

记录 Homebrew 依赖、virtualenv 配置、MySQL 初始化、隐藏输入创建管理员、迁移、后端/前端启动、测试执行、OpenAPI/Postman 验证、存储核对、age 密钥处理、加密备份、隔离恢复和未知文件提交恢复。每条命令必须使用本计划中的实际路径，且不得包含真实密码。

- [ ] **步骤 2：按文档执行全新安装**

使用全新空 MySQL 测试模式和全新临时存储目录。运行依赖安装、两次 `upgrade head` 命令、管理员初始化、登录/修改密码和完整验证脚本。确认有 18 张表且无重复迁移影响。

- [ ] **步骤 3：执行持久化和安全验收**

创建作者、稿件、版本和文件；运行 `brew services restart mysql@8.0` 并重启两个 Web 进程；验证所有记录和文件哈希仍然保留。运行完整安全矩阵和浏览器 Network 检查。确认未跟踪任何密钥或个人文件、不存在审计写入路由，且测试/开发存储和数据库目标保持分离。

- [ ] **步骤 4：记录验收证据**

创建 `docs/acceptance-v0.1.md`，记录日期、命令、测试总数、覆盖率百分比、Newman 总数、前端构建结果、备份/恢复哈希结果、MySQL 重启结果和任何明确未解决的限制。如果必需检查项失败或被跳过，不要将 V0.1 标记为完成。

- [ ] **步骤 5：最终审查并可选提交**

运行：`bash scripts/verify.sh`
预期：所有检查项通过，且验收文档准确记录结果。

```bash
git add README.md docs .env.example
git commit -m "docs: record v0.1 installation and acceptance"
```

---

## 执行说明

- 如果任何任务暴露先前任务的安全缺陷，停止下游工作，在负责该功能的任务中添加失败的回归测试，修复缺陷，并在继续前重新运行所有受影响的先前测试。
- MySQL 管理连接、初始管理员密码和 age 私钥均为本地交互输入。仅暂停需要它们的步骤；绝不用硬编码默认值替代。
- 正常 CRUD 流程成功不能弥补隔离、敏感字段、文件恢复、迁移、备份恢复或覆盖率检查项的失败。
