# Module 3 Phase 1: Registration Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不访问真实作者账号、不执行外部注册提交的前提下，建立可授权、可审计、可恢复的出版社账号注册任务基础能力。

**Architecture:** 复用现有 `publishers`、`journals`、`journal_submission_portals`、作者授权和 `operation_logs`。新增模块 3 自有账号、任务、确认及邮箱验证表，以独立 Worker 执行持久化任务；前端提供专业任务工作台，但本阶段不打开真实注册页面。

**Tech Stack:** FastAPI 0.115.12、Pydantic 2.11.4、SQLAlchemy 2.0.41、MySQL 8、Alembic、pytest、Vue 3、TypeScript、Vitest、Element Plus。

**Spec:** `AI学术论文投稿代理系统_V0.1_模块3_账号注册技术设计规格_修订版.md`（V0.1-R2，含第 25 节实施前检查清单）。

## Global Constraints

- 主键使用 `CHAR(36)` UUID；MySQL InnoDB、utf8mb4；UTC 时间使用 `DATETIME(6)`。
- 出版社、期刊和投稿入口分别复用 `publishers`、`journals`、`journal_submission_portals`，不得创建第二套主数据。
- V0.1 出版社代码只能为 `SPRINGER_NATURE`、`ELSEVIER`、`WILEY`、`TAYLOR_FRANCIS`、`SAGE`。
- 作者注册授权、作者资料访问、邮箱读取和凭据使用分别校验；系统管理员不得绕过作者明确注册授权。
- 不保存明文密码、OAuth Token、Cookie 或完整验证链接；日志只记录白名单摘要。
- 不绕过 CAPTCHA、MFA 或访问限制；本阶段不执行真实注册、表单提交或邮箱访问。
- 任务状态迁移只能通过 Workflow Service；结果不确定的外部提交不得重试。
- 所有任务步骤先写失败测试，再做最小实现；每个任务结束后独立提交。
- 当前分支已有模块 2 未提交修改；开始 Task 1 前必须先将模块 2 审核并提交到当前功能分支，或使用包含这些修改的专用 worktree，不能把模块 2 和用户文件混入模块 3 提交。

## Review Focus

- **管理员无作者授权**：应拒绝注册，Task 2 用管理员无授权测试固定。
- **错误期刊/出版社/入口组合**：应拒绝创建任务，Task 4 用归属错误、未验证入口和域名不匹配测试固定。
- **重复任务与并发领取**：相同幂等键只返回一个任务，Worker 只能有一个所有者，Task 5 和 Task 7 用 MySQL 并发测试固定。
- **授权撤销或入口停用发生在执行中**：下一安全检查点必须停止，Task 7 用执行中撤销测试固定。
- **确认令牌重放或摘要变化**：应拒绝且不得产生外部动作，Task 6 用已消费和摘要不匹配测试固定。

---

### Task 1: 创建 R2 数据库结构与 ORM 基线

**Files:**
- Create: `backend/alembic/versions/0007_registration_foundation.py`
- Create: `backend/app/models/registration.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/discovery.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_schema_constraints.py`
- Create: `backend/tests/test_registration_schema.py`

**Interfaces:**
- Consumes: 现有 `Base`、`UUIDPrimaryKeyMixin`、`CreatedUpdatedByMixin`、`SoftDeleteMixin`、`publishers.id`、`journals.id`、`journal_submission_portals.id`。
- Produces: `PublisherRegistrationSupport`、`PlatformAdapter`、`PublisherAccount`、`RegistrationTask`、`EmailVerificationRecord`、`RegistrationConfirmation`；迁移头为 `0007`。

- [ ] **Step 1: 写迁移和模型的失败测试**

```python
def test_registration_schema_is_at_0007(db_engine):
    from sqlalchemy import inspect, text
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
    expected = {
        "publisher_registration_support", "platform_adapters", "publisher_accounts",
        "registration_tasks", "email_verification_records", "registration_confirmations",
    }
    assert expected <= set(inspect(db_engine).get_table_names())


def test_completed_registration_preserves_account_namespace_and_active_email():
    from app.models import PublisherAccount
    columns = PublisherAccount.__table__.c
    assert columns.account_namespace.nullable is False
    assert columns.normalized_email.nullable is False
    assert columns.active_account_email.computed is not None
```

- [ ] **Step 2: 运行测试并确认因迁移/模型不存在而失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_schema.py -q`
Expected: FAIL，迁移头不是 `0007`，且模型不存在。

- [ ] **Step 3: 实现迁移和 ORM**

迁移必须：
1. 创建 `publisher_registration_support`，用唯一 `publisher_id` 外键关联 `publishers.id`，五个代码各有唯一 `publisher_code`。
2. 创建 `platform_adapters`，唯一键为 `(adapter_code, adapter_version)`。
3. 扩展 `journal_submission_portals`：`normalized_host`、`platform_adapter_id`、`support_status`、`verified_by`、`verification_evidence_ref`、`last_checked_at`、`disabled_reason`，不新增期刊或 URL 副本。
4. 创建 `publisher_accounts`，唯一键为 `(platform_code, account_namespace, active_account_email)`；`active_account_email` 在未删除时为 `normalized_email`，否则为 `NULL`。
5. 创建 `registration_tasks`，包含授权、作者、出版社、期刊、账号、平台、幂等键、状态、Worker、租约、心跳、重试、取消和最近外部动作字段。
6. 创建 `email_verification_records`，只允许 `verification_ref` 引用临时秘密存储，不保存完整链接。
7. 创建 `registration_confirmations`，保存 `summary_hash`、`token_hash`、有效期和单次消费时间。
8. 复用 `operation_logs`，不创建 `registration_audit_logs`。

```python
class RegistrationTask(UUIDPrimaryKeyMixin, CreatedUpdatedByMixin, Base):
    __tablename__ = "registration_tasks"

    task_status: Mapped[str] = mapped_column(VARCHAR(40), default="PENDING", nullable=False)
    worker_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), default=utc_now)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

同步更新模式测试：应用表总数从 25 变为 31，清理顺序先删除模块 3 外键子表，再删除入口、期刊、出版社和用户。

- [ ] **Step 4: 验证迁移、重复升级、降级和模型一致性**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_schema.py tests/test_schema_constraints.py -q`
Expected: PASS；开发库迁移另行使用 `ALEMBIC_DATABASE_URL` 专用迁移账号，不使用应用 CRUD 账号。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/alembic/versions/0007_registration_foundation.py backend/app/models/registration.py backend/app/models/__init__.py backend/app/models/discovery.py backend/tests/conftest.py backend/tests/test_schema_constraints.py backend/tests/test_registration_schema.py
git commit -m "feat: add module 3 registration schema"
```

---

### Task 2: 实现注册权限与作者同意检查

**Files:**
- Modify: `backend/app/services/permissions.py`
- Create: `backend/app/services/registration_authorization.py`
- Create: `backend/tests/test_registration_authorization.py`

**Interfaces:**
- Consumes: `AuthorizationRepository.any_active(user_id, author_id, permission, now_utc)` 和现有字段读取权限。
- Produces: `require_registration_consent(db, user, author_id, authorization_id, permissions, request_id) -> Author`。

- [ ] **Step 1: 写失败测试**

```python
def create_grant(db, user, author, permissions):
    grant = AuthorAuthorization(
        author_id=author.id,
        user_id=user.id,
        permissions=permissions,
        valid_from=utc_now() - timedelta(minutes=1),
        valid_to=utc_now() + timedelta(hours=1),
    )
    db.add(grant)
    db.commit()
    return grant


def test_admin_without_author_registration_grant_is_denied(db_session, admin, author):
    with pytest.raises(AppError) as caught:
        require_registration_consent(
            db_session, admin, author.id, str(uuid4()), {"account:register"}, "request-id"
        )
    assert caught.value.status_code == 403


def test_explicit_grant_allows_operator(db_session, operator, author):
    grant = create_grant(db_session, operator, author, ["account:register", "author:profile:read"])
    result = require_registration_consent(
        db_session, operator, author.id, grant.id,
        {"account:register", "author:profile:read"}, "request-id"
    )
    assert result.id == author.id
```

- [ ] **Step 2: 运行权限测试**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_authorization.py -q`
Expected: FAIL，函数不存在。

- [ ] **Step 3: 实现独立授权检查**

```python
REGISTRATION_PERMISSIONS = frozenset({
    "account:register", "email:verification:read", "credential:use"
})


def require_registration_consent(db, user, author_id, authorization_id, permissions, request_id):
    repository = AuthorizationRepository(db)
    for permission in permissions:
        if not has_author_permission(db, user, author_id, Permission(permission)):
            raise AppError(403, "PERMISSION_DENIED", "当前角色无权执行注册相关操作")
        if not repository.any_active(
            user_id=user.id,
            author_id=author_id,
            permission=permission,
            now_utc=utc_now(),
            authorization_id=authorization_id,
        ):
            raise AppError(403, "AUTHORIZATION_INVALID", "作者注册授权未生效、已过期或已撤销")
    author = db.get(Author, author_id)
    if author is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
    return author
```

先给 `AuthorizationRepository` 增加可选 `authorization_id` 过滤并保留既有调用兼容性。该函数不得调用现有管理员绕过路径；角色能力检查与作者授权记录分别执行。

- [ ] **Step 4: 验证角色、过期、撤销、跨作者和错误授权 ID**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_authorization.py tests/test_authorization_boundaries.py -q`
Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/services/permissions.py backend/app/repositories/authorizations.py backend/app/services/registration_authorization.py backend/tests/test_registration_authorization.py
git commit -m "feat: enforce explicit registration consent"
```

---

### Task 3: 建立注册 Pydantic Schema 与 Repository

**Files:**
- Create: `backend/app/schemas/registration.py`
- Create: `backend/app/repositories/registration.py`
- Create: `backend/tests/test_registration_repository.py`

**Interfaces:**
- Consumes: Task 1 ORM 和 Task 2 权限函数。
- Produces: `RegistrationTaskCreate`、`RegistrationTaskResponse`、`RegistrationTaskPage`、`PublisherSupportResponse`、`PlatformAdapterResponse`、`PublisherAccountResponse`、`RegistrationRepository`。

- [ ] **Step 1: 写 Schema 和查询失败测试**

```python
def test_task_response_has_no_credential_or_full_verification_link():
    assert "credential_ref" not in RegistrationTaskResponse.model_fields
    assert "verification_url" not in RegistrationTaskResponse.model_fields
    assert RegistrationTaskPage.model_fields["items"].annotation is not None


def test_repository_finds_supported_portal(db_session, supported_portal):
    repository = RegistrationRepository(db_session)
    result = repository.supported_portal(supported_portal.id)
    assert result.platform_adapter_id == supported_portal.platform_adapter_id
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_repository.py -q`
Expected: FAIL，Schema 或 Repository 不存在。

- [ ] **Step 3: 实现最小 Schema 与查询方法**

```python
class RegistrationTaskCreate(InputModel):
    author_id: UUID
    publisher_id: UUID
    journal_id: UUID
    authorization_id: UUID
    platform_code: str = Field(max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=128)


class RegistrationTaskResponse(OutputModel):
    id: UUID
    author_id: UUID
    publisher_id: UUID
    journal_id: UUID
    platform_code: str
    task_status: str
    current_step: str | None
    retryable: bool
    created_at: datetime
```

Repository 方法：`publisher_support(publisher_id)`、`supported_portal(portal_id)`、`adapter(adapter_id)`、`task_by_idempotency(key)`、`task_page(filters, page, page_size)`、`account_page(user_id, page, page_size)`。所有列表查询限制 `page_size <= 100`，并排除软删除档案。

- [ ] **Step 4: 验证 Schema 拒绝额外字段及 Repository 过滤**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_repository.py -q`
Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/schemas/registration.py backend/app/repositories/registration.py backend/tests/test_registration_repository.py
git commit -m "feat: add registration schemas and repository"
```

---

### Task 4: 实现出版社、入口和适配器准入检查

**Files:**
- Create: `backend/app/services/registration_admission.py`
- Create: `backend/tests/test_registration_admission.py`

**Interfaces:**
- Consumes: `RegistrationRepository.publisher_support()`、`supported_portal()`、`adapter()`。
- Produces: `require_supported_registration_target(db, publisher_id, journal_id, portal_id, platform_code) -> AdmissionResult`。

- [ ] **Step 1: 写准入失败测试**

```python
def test_unverified_or_wrong_domain_portal_is_rejected(db_session, portal, adapter):
    portal.verification_status = "NEEDS_REVIEW"
    db_session.commit()
    publisher_id = db_session.get(Journal, portal.journal_id).publisher_id
    with pytest.raises(AppError) as caught:
        require_supported_registration_target(
            db_session, publisher_id, portal.journal_id, portal.id,
            portal.platform_code,
        )
    assert caught.value.code == "JOURNAL_ENDPOINT_NOT_VERIFIED"


def test_publisher_journal_mismatch_is_rejected(db_session, publisher, other_journal, portal):
    with pytest.raises(AppError) as caught:
        require_supported_registration_target(
            db_session, publisher.id, other_journal.id, portal.id, portal.platform_code
        )
    assert caught.value.code == "JOURNAL_PUBLISHER_MISMATCH"
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_admission.py -q`
Expected: FAIL，准入函数不存在。

- [ ] **Step 3: 实现顺序校验**

按规格顺序检查：出版社支持状态、期刊归属、入口 `support_status=SUPPORTED`、入口 `verification_status=VERIFIED`、适配器 `SUPPORTED`、平台和版本、规范化域名。域名使用 `urlsplit(final_url).hostname` 并转小写去尾点，禁止后缀拼接匹配。

```python
@dataclass(frozen=True)
class AdmissionResult:
    publisher: Publisher
    journal: Journal
    portal: JournalSubmissionPortal
    adapter: PlatformAdapter


def require_supported_registration_target(db, publisher_id, journal_id, portal_id, platform_code):
    repository = RegistrationRepository(db)
    support = repository.publisher_support(publisher_id)
    if support is None or support.support_status != "SUPPORTED":
        raise AppError(403, "PUBLISHER_NOT_IN_V01_WHITELIST", "出版社不在 V0.1 支持范围")
    journal = db.get(Journal, journal_id)
    if journal is None or journal.deleted_at is not None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "期刊不存在")
    if journal.publisher_id != publisher_id:
        raise AppError(409, "JOURNAL_PUBLISHER_MISMATCH", "期刊与出版社归属不一致")
    portal = repository.supported_portal(portal_id)
    if portal is None or portal.journal_id != journal_id:
        raise AppError(404, "JOURNAL_ENDPOINT_NOT_FOUND", "期刊入口不存在")
    if portal.support_status != "SUPPORTED":
        raise AppError(409, "JOURNAL_ENDPOINT_NOT_SUPPORTED", "期刊入口尚未开放")
    if portal.verification_status != "VERIFIED":
        raise AppError(409, "JOURNAL_ENDPOINT_NOT_VERIFIED", "期刊入口尚未核验")
    adapter = repository.adapter(portal.platform_adapter_id)
    if adapter is None or adapter.support_status != "SUPPORTED":
        raise AppError(409, "PLATFORM_ADAPTER_NOT_SUPPORTED", "平台适配器尚未验收")
    if portal.platform_code != platform_code:
        raise AppError(409, "PLATFORM_ADAPTER_NOT_SUPPORTED", "平台代码与入口不一致")
    host = (urlsplit(portal.final_url).hostname or "").lower().rstrip(".")
    if host not in set(adapter.allowed_domains or []):
        raise AppError(403, "PLATFORM_DOMAIN_NOT_ALLOWED", "目标域名不在适配器白名单")
    publisher = db.get(Publisher, publisher_id)
    assert publisher is not None
    return AdmissionResult(publisher=publisher, journal=journal, portal=portal, adapter=adapter)
```

- [ ] **Step 4: 验证白名单、逐刊归属、适配器状态和域名**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_admission.py -q`
Expected: PASS，包括第六家出版社、停用适配器和 `example.com.evil.test` 拒绝。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/services/registration_admission.py backend/tests/test_registration_admission.py
git commit -m "feat: validate registration targets and adapters"
```

---

### Task 5: 实现注册任务状态机与任务服务

**Files:**
- Create: `backend/app/services/registration_workflow.py`
- Create: `backend/app/services/registration.py`
- Create: `backend/tests/test_registration_service.py`

**Interfaces:**
- Consumes: Task 2 授权函数、Task 3 Repository、Task 4 准入结果。
- Produces: `RegistrationWorkflowService.transition()`；`RegistrationService.create_task()`、`get_task()`、`list_tasks()`、`cancel_task()`、`retry_task()`。

- [ ] **Step 1: 写任务创建、幂等和状态失败测试**

```python
def test_create_and_reuse_registration_task(db_session, operator, approved_input):
    service = RegistrationService(db_session, operator, "request-create")
    first = service.create_task(approved_input)
    second = service.create_task(approved_input)
    assert first.id == second.id
    assert first.task_status == "PENDING"
    assert db_session.scalar(select(func.count(RegistrationTask.id))) == 1


def test_cancelled_or_completed_task_can_be_restarted(db_session, operator, task):
    service = RegistrationService(db_session, operator, "request-retry")
    task.task_status = "CANCELLED"
    db_session.commit()
    assert service.retry_task(task.id).task_status == "PENDING"
```

- [ ] **Step 2: 运行服务测试**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_service.py -q`
Expected: FAIL，服务不存在。

- [ ] **Step 3: 实现状态机与任务服务**

```python
TERMINAL_STATUSES = {"REGISTERED", "FAILED", "CANCELLED", "EXPIRED"}


class RegistrationWorkflowService:
    def transition(self, task, target, *, actor_id, reason):
        if task.task_status == target:
            return task
        if task.task_status in TERMINAL_STATUSES:
            raise AppError(409, "INVALID_TASK_STATE", "当前任务状态不允许迁移")
        task.task_status = target
        task.current_step = reason
        task.last_activity_at = utc_now()
        return task

    def cancel(self, task, *, actor_id, reason="用户取消"):
        task.task_status = "CANCELLED"
        task.cancel_requested = True
        task.current_step = reason
        task.last_activity_at = utc_now()
        return task

    def restart(self, task, *, actor_id, reason="重新执行"):
        task.task_status = "PENDING"
        task.cancel_requested = False
        task.retryable = False
        task.worker_id = None
        task.lease_expires_at = None
        task.available_at = utc_now()
        task.current_step = reason
        task.last_activity_at = utc_now()
        return task
```

创建任务时校验授权和准入，保存 `created_by`、脱敏 `registration_url` 来源引用、平台和适配器版本，返回 `PENDING`。`SUBMITTING`、`SUBMISSION_UNKNOWN` 和 `READY_TO_SUBMIT` 的状态迁移由独立方法控制，不能让前端直接指定状态。取消与重试必须分别调用 `WorkflowService.cancel()` 和 `WorkflowService.restart()`，不得在任务 Service 中直接修改状态。取消只停止后续动作，不能删除外部已创建账号。

- [ ] **Step 4: 验证权限、幂等、取消、重试和非法迁移**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_service.py -q`
Expected: PASS；相同幂等键并发只创建一条任务。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/services/registration_workflow.py backend/app/services/registration.py backend/tests/test_registration_service.py
git commit -m "feat: add registration task workflow"
```

---

### Task 6: 实现一次性确认与提交摘要绑定

**Files:**
- Create: `backend/app/schemas/confirmation.py`
- Create: `backend/app/services/registration_confirmation.py`
- Create: `backend/tests/test_registration_confirmation.py`

**Interfaces:**
- Consumes: Task 1 `RegistrationConfirmation` 和 Task 5 任务状态机。
- Produces: `ConfirmationService.create_challenge()` 与 `ConfirmationService.consume()`。

- [ ] **Step 1: 写重放、过期和摘要变化失败测试**

```python
def test_confirmation_cannot_be_replayed_or_used_after_summary_change(db_session, admin, task):
    service = ConfirmationService(db_session)
    challenge = service.create_challenge(
        task=task,
        action_type="SUBMIT_REGISTRATION",
        summary={"author_id": task.author_id, "email": "author@example.com"},
        user=admin,
        ttl_seconds=600,
    )
    consumed = service.consume(task, challenge.id, challenge.token, challenge.summary_hash, admin)
    assert consumed.consumed_at is not None
    with pytest.raises(AppError):
        service.consume(task, challenge.id, challenge.token, challenge.summary_hash, admin)
    with pytest.raises(AppError):
        service.consume(task, challenge.id, challenge.token, "0" * 64, admin)


def test_expired_confirmation_is_rejected(db_session, admin, task):
    service = ConfirmationService(db_session)
    challenge = service.create_challenge(
        task=task,
        action_type="SUBMIT_REGISTRATION",
        summary={"author_id": task.author_id},
        user=admin,
        ttl_seconds=-1,
    )
    with pytest.raises(AppError) as caught:
        service.consume(task, challenge.id, challenge.token, challenge.summary_hash, admin)
    assert caught.value.code == "CONFIRMATION_EXPIRED"
```

- [ ] **Step 2: 运行确认测试**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_confirmation.py -q`
Expected: FAIL，确认服务不存在。

- [ ] **Step 3: 实现哈希、TTL 和原子单次消费**

```python
@dataclass(frozen=True)
class ConfirmationChallenge:
    id: str
    token: str
    summary_hash: str


class ConfirmationService:
    def create_challenge(self, *, task, action_type, summary, user, ttl_seconds=600):
        token = secrets.token_urlsafe(32)
        canonical = json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        summary_hash = hashlib.sha256(canonical.encode()).hexdigest()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        record = RegistrationConfirmation(
            task_id=task.id,
            action_type=action_type,
            summary_hash=summary_hash,
            token_hash=token_hash,
            requested_by=user.id,
            expires_at=utc_now() + timedelta(seconds=ttl_seconds),
        )
        self.db.add(record)
        self.db.flush()
        return ConfirmationChallenge(id=record.id, token=token, summary_hash=summary_hash)
```

`consume()` 使用 `UPDATE registration_confirmations SET consumed_at = CURRENT_TIMESTAMP(6) WHERE id=? AND consumed_at IS NULL AND expires_at > now AND token_hash=? AND summary_hash=?`，受影响行数必须为 1。原始令牌不进入日志或任务表。

- [ ] **Step 4: 验证确认服务和现有权限回归**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_confirmation.py tests/test_registration_authorization.py -q`
Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/schemas/confirmation.py backend/app/services/registration_confirmation.py backend/tests/test_registration_confirmation.py
git commit -m "feat: add one-time registration confirmations"
```

---

### Task 7: 实现注册 Worker 的租约、取消和恢复

**Files:**
- Create: `backend/app/workers/registration_worker.py`
- Create: `backend/app/workers/run_registration_worker.py`
- Create: `scripts/dev_registration_worker.sh`
- Modify: `scripts/dev_services.sh`
- Create: `backend/tests/test_registration_worker.py`

**Interfaces:**
- Consumes: `RegistrationTask`、Workflow Service 和模块 2 `DiscoveryWorker` 的原子所有权模式。
- Produces: `RegistrationWorker(engine, worker_id, executor=None).run_once() -> bool` 和 `execute_claimed(task_id) -> None`。

- [ ] **Step 1: 写并发、租约丢失和撤销失败测试**

```python
def test_only_one_worker_claims_registration_task(db_engine, task):
    first = RegistrationWorker(db_engine, worker_id="worker-1", executor=lambda task, db: None)
    second = RegistrationWorker(db_engine, worker_id="worker-2", executor=lambda task, db: None)
    assert first.claim_next() == task.id
    assert second.claim_next() is None


def test_lost_lease_cannot_overwrite_new_owner(db_engine, task):
    first = RegistrationWorker(
        db_engine, worker_id="worker-a", executor=lambda task, db: RegistrationExecutionResult("SUCCEEDED")
    )
    second = RegistrationWorker(
        db_engine, worker_id="worker-b", executor=lambda task, db: RegistrationExecutionResult("SUCCEEDED")
    )
    assert first.claim_next() == task.id
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    task._sa_instance_state.session.commit()
    assert second.claim_next() == task.id
    first.execute_claimed(task.id)
    task._sa_instance_state.session.refresh(task)
    assert task.worker_id == "worker-b"
```

实际测试必须分别覆盖：正常完成、租约丢失、执行中授权撤销、入口停用、用户取消和可重试错误退避。

- [ ] **Step 2: 运行 Worker 测试**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_worker.py -q`
Expected: FAIL，Worker 不存在。

- [ ] **Step 3: 实现原子领取与所有权提交**

Worker 使用与当前 `DiscoveryWorker` 相同的数据库条件更新：只有 `PENDING` 且可执行，或 `PROCESSING` 且租约过期的任务可领取。检查点和最终状态必须同时匹配 `worker_id`；取消或授权撤销在下一检查点停止。

```python
@dataclass
class RegistrationExecutionResult:
    status: str
    checkpoint: dict = field(default_factory=dict)


updated = db.execute(
    update(RegistrationTask)
    .where(
        RegistrationTask.id == task.id,
        RegistrationTask.worker_id == self.worker_id,
        RegistrationTask.task_status == "PROCESSING",
        RegistrationTask.cancel_requested.is_(False),
    )
    .values(
        task_status=result.status,
        last_heartbeat_at=utc_now(),
        worker_id=None,
        lease_expires_at=None,
    )
)
if updated.rowcount != 1:
    db.rollback()
    raise TaskLeaseLost()
db.commit()
```

本阶段默认执行器只验证授权和准入；未实现浏览器能力时转入 `NEEDS_MANUAL_REVIEW`，不得打开真实注册页面。新增 `scripts/dev_registration_worker.sh`，并在 `scripts/dev_services.sh` 注册第三个 launchd 服务 `com.academic-submission-agent.registration-worker`；现有 Discovery Worker 保持不变。

- [ ] **Step 4: 验证 Worker 和现有 Discovery Worker**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_worker.py tests/test_discovery_worker.py -q`
Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/workers/registration_worker.py backend/app/workers/run_registration_worker.py scripts/dev_registration_worker.sh scripts/dev_services.sh backend/tests/test_registration_worker.py
git commit -m "feat: add recoverable registration worker"
```

---

### Task 8: 发布注册任务、配置和账号 API

**Files:**
- Create: `backend/app/api/v1/registration.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/contract_manifest.py`
- Modify: `backend/tests/test_contract_manifest.py`
- Create: `backend/tests/test_registration_api.py`

**Interfaces:**
- Consumes: Tasks 2–7 的服务和 Schema。
- Produces: `/registration/publishers`、`/registration/platform-adapters`、`/registration/tasks`、`/publisher-accounts` 及任务取消/重试 API。

- [ ] **Step 1: 写 API 权限与响应失败测试**

```python
def test_registration_task_api_hides_secrets_and_enforces_csrf(client, operator_context, approved_input):
    denied = client.post("/api/v1/registration/tasks", json=approved_input, headers={"X-CSRF-Token": "wrong"})
    assert denied.status_code == 403
    created = client.post("/api/v1/registration/tasks", json=approved_input)
    assert created.status_code == 202
    assert "credential_ref" not in created.text
    assert "verification_url" not in created.text
```

- [ ] **Step 2: 运行 API 测试**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_api.py -q`
Expected: FAIL，路由不存在。

- [ ] **Step 3: 实现路由和 OpenAPI 合约**

实现：
- `GET /registration/publishers`
- `GET /registration/publishers/{publisher_id}/journals`
- `GET /registration/platform-adapters`
- `POST /registration/tasks`（202）
- `GET /registration/tasks`
- `GET /registration/tasks/{task_id}`
- `POST /registration/tasks/{task_id}/cancel`
- `POST /registration/tasks/{task_id}/retry`
- `GET /publisher-accounts`
- 管理员出版社支持配置、入口适配器绑定与状态修改接口。

写操作要求 CSRF；作者数据按授权过滤；普通用户不得修改白名单。统一使用 `ErrorResponse` 文档模型，中文 operation summary 和字段标题，并重新生成 `docs/api/v0.1-openapi.json`。

- [ ] **Step 4: 验证 API、OpenAPI 和权限矩阵**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_api.py tests/test_openapi_generated.py tests/test_security_matrix.py -q`
Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/app/api/v1/registration.py backend/app/main.py backend/app/api/v1/contract_manifest.py backend/tests/test_contract_manifest.py backend/tests/test_registration_api.py docs/api/v0.1-openapi.json
git commit -m "feat: expose registration task APIs"
```

---

### Task 9: 实现专业注册任务工作台前端

**Files:**
- Create: `frontend/src/api/registration.ts`
- Create: `frontend/src/views/registration/RegistrationView.vue`
- Create: `frontend/src/views/registration/RegistrationView.test.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: Task 8 API。
- Produces: `getRegistrationPublishers()`、`getRegistrationTasks()`、`createRegistrationTask()`、`cancelRegistrationTask()`、`retryRegistrationTask()`；路由 `/registration`。

- [ ] **Step 1: 写前端交互失败测试**

```typescript
it('shows workflow steps and disables unsupported targets', async () => {
  const wrapper = mount(RegistrationView)
  await flushPromises()
  expect(wrapper.get('[data-test="registration-workflow"]').exists()).toBe(true)
  expect(wrapper.get('[data-test="unsupported-target"]').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).not.toContain('credential_ref')
})
```

另写测试覆盖：出版社选择后加载期刊、任务筛选、取消、重新识别/重试、人工确认摘要、加载骨架屏、空状态、错误保留当前数据，以及窄屏可访问性。

- [ ] **Step 2: 运行前端测试**

Run: `cd frontend && npm test -- --run src/views/registration/RegistrationView.test.ts`
Expected: FAIL，页面不存在。

- [ ] **Step 3: 实现工作台**

页面使用现有设计系统和 R2 第 14.5 节：
1. 顶部为作者、出版社、期刊和平台选择卡片。
2. 任务详情使用步骤条、状态卡片和执行时间线。
3. 人工处理按验证码、提交确认、邮箱确认和复核分组。
4. 证据使用抽屉，确认摘要使用只读卡片。
5. 账号表格不显示密码、凭据引用或完整验证链接。
6. 列表有骨架屏、空状态、键盘焦点、明确错误和安全重试。

```typescript
export async function createRegistrationTask(payload: RegistrationTaskCreate): Promise<RegistrationTask> {
  const response = await api.post<RegistrationTask>('/registration/tasks', payload)
  return response.data
}
```

不得添加大面积装饰渐变、无意义动画或仅依赖颜色的状态表达。

- [ ] **Step 4: 验证组件、完整前端测试和构建**

Run: `cd frontend && npm test && npm run build`
Expected: PASS。

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/src/api/registration.ts frontend/src/views/registration/RegistrationView.vue frontend/src/views/registration/RegistrationView.test.ts frontend/src/router/index.ts frontend/src/App.vue
git commit -m "feat: add registration task workspace"
```

---

### Task 10: 文档、全量验证与阶段一验收

**Files:**
- Modify: `README.md`
- Modify: `docs/operations.md`
- Create: `docs/registration-foundation.md`
- Modify: `docs/api/v0.1-openapi.json`

**Interfaces:**
- Consumes: Tasks 1–9 的全部交付物。
- Produces: 可重复的阶段一启动、迁移、测试和验收说明。

- [ ] **Step 1: 写文档检查并验证验收命令可用**

Run: `bash -n scripts/dev_services.sh scripts/dev_backend.sh scripts/dev_worker.sh scripts/dev_registration_worker.sh`
Expected: PASS。

- [ ] **Step 2: 编写运维与验收文档**

文档必须包含：
- 模块 2 与模块 3 的表和权限关系；
- 专用迁移账号运行 `alembic upgrade head`；
- `bash scripts/dev_services.sh start` 启动后端与 Worker；
- `bash scripts/dev_frontend.sh` 启动前端；
- 独立 MySQL 测试库及不得指向开发库的警告；
- 本阶段不执行真实注册、邮箱读取或外部提交；
- 如何验证无授权拒绝、入口未核验拒绝、Worker 恢复和确认重放拒绝。

- [ ] **Step 3: 运行完整验证**

Run: `bash scripts/verify.sh`
Expected: 后端、前端、Postman、覆盖率、OpenAPI、`ruff`、`mypy` 和生产构建全部通过；不得出现未处理警告或跳过的新测试。

- [ ] **Step 4: 检查差异和敏感信息**

Run: `git diff --check && git status --short`
Expected: 无空白错误；没有 `.env`、密码、Token、Cookie、完整验证链接或用户文件被加入提交。

- [ ] **Step 5: 提交阶段一验收**

```bash
git add README.md docs/operations.md docs/registration-foundation.md docs/api/v0.1-openapi.json
git commit -m "docs: verify module 3 registration foundation"
```

---

## 本计划不包含

- 真实平台注册、自动登录、表单提交、文件上传或正式投稿。
- 读取真实邮箱或访问真实验证链接。
- CAPTCHA/MFA 绕过、自动同意平台条款、版权或伦理声明。
- 自动处理费用、付款或订阅。
- 平台适配器的真实账号验收；这些需要独立规格、授权测试账号和沙箱验收计划。
