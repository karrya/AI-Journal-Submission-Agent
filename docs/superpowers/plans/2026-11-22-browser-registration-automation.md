# 浏览器自动注册与人工接管实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户只选期刊和作者，系统从数据库取数，在可见浏览器中自动注册，并只在卡点弹窗请求人工接管。

**Architecture:** 预检决定自动执行或人工打开官方页面。注册 Worker 调用带检查点的浏览器执行器；适配器负责确定性点击，原生浏览器展示过程，前端只负责人工接管与恢复。

**Tech Stack:** FastAPI、SQLAlchemy、现有 RegistrationWorker、Playwright、Keychain、Vue 3、Vitest、pytest。

**Spec:** `docs/superpowers/specs/2026-11-22-browser-registration-automation-design.md`

## Global Constraints

- 用户无需填写适配器代码、名称、版本或重复业务资料。
- 不绕过 robots、平台条款、CAPTCHA、MFA、登录限制或邮箱授权。
- APEC 的 robots 为 `Disallow: /`，禁止自动点击，只打开 `https://wiley.atyponrex.com/journal/APEC`。
- 密码、Token、Cookie 和完整验证链接不得进入任务表、日志、截图、API 响应或审计摘要。
- 未知最终提交结果不得自动重放；人工接管不得重复创建任务或清空已填数据。

## Review Focus

- robots 禁止：不得打开目标注册页，Task 1 测试 `assert_allowed` 拒绝后的结果。
- 适配器缺失：不得伪造代码或版本，Task 1 测试注册表未命中。
- 秘密泄露：Task 2 和 Task 4 测试检查点、结果及审计不含秘密。
- 人工接管：Task 3 和 Task 5 测试保留 handoff ID、恢复后不新建任务。
- 重复提交：Task 4 测试未知结果只转人工，不重试最终动作。

---

### Task 1: 自动注册预检与适配器注册表

**Files:**
- Create: `backend/app/automation/registration_contracts.py`
- Create: `backend/app/automation/registration_preflight.py`
- Test: `backend/tests/test_registration_automation_preflight.py`

**Interfaces:**
- Consumes: 现有 `JournalSubmissionPortal` 与 `SafeHttpClient.assert_allowed`。
- Produces: `RegistrationData`、`RegistrationReceipt`、`RegistrationAutomationError.code`、`RegistrationAdapterRegistry.get(code, version)`、`RegistrationPreflight.evaluate(portal)`。

- [ ] **Step 1: 写失败测试**

```python
def test_apec_returns_manual_handoff_without_opening_browser(apec_portal):
    preflight = RegistrationPreflight(
        adapters=RegistrationAdapterRegistry(),
        url_checker=FakeUrlChecker(allowed=False),
    )
    result = preflight.evaluate(apec_portal)
    assert result.checkpoint["current_step"] == "HANDOFF_ROBOTS"
    assert result.checkpoint["manual_url"] == apec_portal.final_url


def test_missing_adapter_cannot_be_fabricated(portal):
    with pytest.raises(RegistrationAutomationError) as error:
        RegistrationAdapterRegistry().get("WILEY_RESEARCH_EXCHANGE", "1.0.0")
    assert error.value.code == "ADAPTER_NOT_REGISTERED"
```

- [ ] **Step 2: 运行并确认失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_automation_preflight.py -q`
Expected: `RegistrationPreflight` 和 `RegistrationAdapterRegistry` 尚不存在。

- [ ] **Step 3: 实现最小契约与预检**

```python
@dataclass(frozen=True)
class RegistrationAdapter:
    execute: Callable[[RegistrationData, VisibleRegistrationBrowser, CheckpointCallback], RegistrationReceipt]


class RegistrationAdapterRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, code: str, version: str, adapter: RegistrationAdapter) -> None:
        self._adapters[(code, version)] = adapter

    def get(self, code: str, version: str) -> RegistrationAdapter:
        try:
            return self._adapters[(code, version)]
        except KeyError:
            raise RegistrationAutomationError("ADAPTER_NOT_REGISTERED", "平台适配器尚未注册")
```

在 `registration_contracts.py` 同时定义统一数据类型：

```python
@dataclass(frozen=True)
class RegistrationData:
    task_id: str
    login_name: str
    secret: str
    profile: dict[str, Any]
    portal_url: str
    allowed_hosts: tuple[str, ...]
    adapter_code: str
    adapter_version: str
    checkpoint: dict[str, str]


@dataclass(frozen=True)
class RegistrationReceipt:
    status: str
    checkpoint: dict[str, Any]
    retryable: bool = False
```

`RegistrationAutomationError` 必须暴露机器可断言的 `code`，浏览器恢复使用 `RegistrationReceipt`，Worker 最终只接收现有 `RegistrationExecutionResult`。

预检依次检查适配器存在、HTTPS 精确域名、`assert_allowed`。robots 拒绝只返回 `NEEDS_MANUAL_REVIEW` 和 `HANDOFF_ROBOTS`，不得实例化浏览器。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_automation_preflight.py -q`
Expected: robots 拒绝、适配器缺失和允许路径全部通过。

- [ ] **Step 5: 提交**

```bash
git add backend/app/automation/registration_contracts.py backend/app/automation/registration_preflight.py backend/tests/test_registration_automation_preflight.py
git commit -m "feat: add registration automation preflight"
```

### Task 2: 数据库资料与安全凭据提供层

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/automation/registration_data.py`
- Create: `backend/tests/test_registration_data.py`

**Interfaces:**
- Consumes: `Author`、`AuthorEmail`、`RegistrationTask`、Keychain。
- Produces: `RegistrationDataProvider.load(task, session) -> RegistrationData`。

- [ ] **Step 1: 写失败测试**

```python
def test_loads_author_data_and_keeps_secret_out_of_checkpoint(db_session, task):
    provider = RegistrationDataProvider(store=FakeCredentialStore())
    data = provider.load(task, db_session)
    assert data.login_name == "synthetic-login"
    assert data.profile["given_name"] == "Ada"
    assert data.secret
    assert "secret" not in data.checkpoint
    assert "password" not in data.checkpoint
```

- [ ] **Step 2: 运行并确认失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_data.py -q`
Expected: `RegistrationDataProvider` 尚不存在。

- [ ] **Step 3: 添加依赖并实现数据提供层**

在 `backend/requirements.txt` 固定 `keyring==25.7.0`。`RegistrationData` 包含 `login_name`、`secret`、`profile`、`portal_url`、`allowed_hosts`、`adapter_code`、`adapter_version`；`checkpoint` 只含非秘密步骤。

首次生成 `secrets.token_urlsafe(24)`，通过 `CredentialStore.put(login_name=f"registration:{task.id}", secret=...)` 保存；重试先用 `get` 读取同一凭据，避免重复改密。缺注册邮箱或作者姓名时返回人工原因，不生成凭据。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_data.py -q`
Expected: 数据映射、凭据复用、缺资料和秘密排除检查通过。

- [ ] **Step 5: 提交**

```bash
git add backend/requirements.txt backend/app/automation/registration_data.py backend/tests/test_registration_data.py
git commit -m "feat: load registration data and credentials securely"
```

### Task 3: 可见浏览器与确定性表单执行器

**Files:**
- Create: `backend/app/automation/registration_browser.py`
- Create: `backend/app/automation/registration_adapters.py`
- Create: `backend/tests/test_registration_browser_adapter.py`

**Interfaces:**
- Consumes: Task 2 的 `RegistrationData`、Playwright。
- Produces: `VisibleRegistrationBrowser.open/fill/click/intervene/close`、`LabelFormRegistrationAdapter.execute`。

- [ ] **Step 1: 写失败测试**

```python
def test_visible_steps_and_intervention_keep_handoff(data):
    browser = FakeVisibleBrowser(intervene_on="CAPTCHA")
    adapter = LabelFormRegistrationAdapter()
    result = adapter.execute(data, browser, checkpoint=lambda value: None)
    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_CAPTCHA"
    assert result.checkpoint["browser_handoff_id"]
    assert browser.stopped_at == "CAPTCHA"
    assert "secret" not in result.checkpoint
```

- [ ] **Step 2: 运行并确认失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_browser_adapter.py -q`
Expected: 浏览器与适配器类尚不存在。

- [ ] **Step 3: 实现可见浏览器与标签表单适配器**

`VisibleRegistrationBrowser` 在生产环境使用 `sync_playwright().chromium.launch(headless=False)`；测试注入 fake。`fill(labels, value)` 按候选 label 填写，`click(labels)` 点击，`intervene(kind, checkpoint)` 生成 UUID handoff 并保留页面。

首个 `LabelFormRegistrationAdapter` 只支持明确标签：First/Given Name、Last/Family Name、Email、Password、Confirm Password、Register/Create Account。缺标签或出现 CAPTCHA 时只调用 `intervene`，不得猜测或强行提交。最终提交后读取账户标识，成功返回 `REGISTERED`，结果未知返回 `NEEDS_MANUAL_REVIEW`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_browser_adapter.py -q`
Expected: 自动步骤、缺标签、CAPTCHA、未知结果和秘密排除检查通过。

- [ ] **Step 5: 提交**

```bash
git add backend/app/automation/registration_browser.py backend/app/automation/registration_adapters.py backend/tests/test_registration_browser_adapter.py
git commit -m "feat: add visible browser registration adapter"
```

### Task 4: Worker 执行器与检查点恢复

**Files:**
- Create: `backend/app/automation/registration_executor.py`
- Modify: `backend/app/workers/run_registration_worker.py`
- Modify: `backend/tests/test_registration_worker.py`

**Interfaces:**
- Consumes: Task 1–3 的 preflight、provider、adapter registry、`RegistrationWorker.save_checkpoint`。
- Produces: `RegistrationAutomationExecutor.execute(task, session, checkpoint_callback)`。

- [ ] **Step 1: 写失败测试**

```python
def test_executor_saves_steps_and_never_replays_unknown_result(task, session):
    checkpoints = []
    executor = RegistrationAutomationExecutor(
        preflight=allow_preflight,
        provider=FakeProvider(),
        adapters=registry_with_unknown_receipt,
    )
    result = executor.execute(task, session, checkpoints.append)
    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "SUBMISSION_UNKNOWN"
    assert registry_with_unknown_receipt.submit_calls == 1
    assert "secret" not in result.checkpoint
```

- [ ] **Step 2: 运行并确认失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_worker.py -q`
Expected: `RegistrationAutomationExecutor` 尚不存在。

- [ ] **Step 3: 实现执行器并接入 Worker**

执行器只在预检通过后创建浏览器。每个步骤调用 `checkpoint_callback({"current_step": code})`；人工接管保存 `browser_handoff_id` 和 `HANDOFF_*`。成功返回 `REGISTERED` 与脱敏凭据引用；异常返回人工结果。最终提交未知不得设置 `retryable=True`。

Worker 构造后注入：

```python
worker.executor = lambda task, session: automation_executor.execute(
    task, session, worker.save_checkpoint
)
```

保留现有 `_default_executor` 作为未配置浏览器执行器时的回退。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_worker.py -q`
Expected: 检查点、恢复、取消、幂等和未知结果测试通过。

- [ ] **Step 5: 提交**

```bash
git add backend/app/automation/registration_executor.py backend/app/workers/run_registration_worker.py backend/tests/test_registration_worker.py
git commit -m "feat: run visible registration automation from worker"
```

### Task 5: 人工接管查询与恢复 API

**Files:**
- Modify: `backend/app/schemas/registration.py`
- Modify: `backend/app/api/v1/registration.py`
- Modify: `backend/app/services/registration.py`
- Modify: `backend/app/services/registration_workflow.py`
- Modify: `backend/app/api/v1/contract_manifest.py`
- Create: `backend/tests/test_registration_handoff_api.py`

**Interfaces:**
- Produces: `GET /registration/tasks/{task_id}/handoff -> RegistrationHandoffResponse`、`POST /registration/tasks/{task_id}/resume -> RegistrationTaskResponse`。

- [ ] **Step 1: 写失败测试**

```python
def test_handoff_and_resume_keep_task_identity(client, admin_context, handoff_task):
    shown = client.get(f"/api/v1/registration/tasks/{handoff_task.id}/handoff")
    assert shown.status_code == 200
    assert shown.json()["manual_url"] == "https://register.example/start"
    resumed = client.post(f"/api/v1/registration/tasks/{handoff_task.id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["id"] == handoff_task.id
    assert resumed.json()["task_status"] == "PENDING"
    assert "secret" not in resumed.text
```

- [ ] **Step 2: 运行并确认失败**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_handoff_api.py -q`
Expected: 两个路由均为 404 或 405。

- [ ] **Step 3: 实现查询与恢复**

`RegistrationHandoffResponse` 仅含 `task_id`、`reason`、`manual_url`、`browser_handoff_id`、`current_step`。handoff 路由必须声明在动态 `/registration/tasks/{task_id}` 详情路由之前，避免被当成 UUID 参数。resume 要求 CSRF 和注册授权，状态只能由 `NEEDS_MANUAL_REVIEW` 转 `PENDING`；保留任务 ID、幂等键和 handoff ID，清除错误消息并写审计。禁止对已 `REGISTERED`、已有未知最终动作或不存在的任务恢复。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && ENVIRONMENT=test ../.venv/bin/python -m pytest tests/test_registration_handoff_api.py tests/test_registration_api.py -q`
Expected: 权限、CSRF、状态限制、任务身份和秘密排除检查通过。

- [ ] **Step 5: 提交**

```bash
git add backend/app/schemas/registration.py backend/app/api/v1/registration.py backend/app/services/registration.py backend/app/services/registration_workflow.py backend/app/api/v1/contract_manifest.py backend/tests/test_registration_handoff_api.py
git commit -m "feat: add registration handoff resume APIs"
```

### Task 6: 前端人工接管弹窗与状态刷新

**Files:**
- Modify: `frontend/src/api/registration.ts`
- Create: `frontend/src/components/RegistrationHandoffDialog.vue`
- Create: `frontend/src/components/RegistrationHandoffDialog.test.ts`
- Modify: `frontend/src/views/registration/RegistrationView.vue`
- Create: `frontend/src/views/registration/RegistrationHandoffFlow.test.ts`

**Interfaces:**
- Consumes: Task 5 的 handoff/resume API、`AppModal`。
- Produces: `getRegistrationHandoff(taskId)`、`resumeRegistrationTask(taskId)`、`RegistrationHandoffDialog`。

- [ ] **Step 1: 写失败测试**

```typescript
it('opens the official page and resumes the same task', async () => {
  vi.stubGlobal('open', vi.fn())
  const wrapper = mount(RegistrationHandoffDialog, { props: { handoff } })
  await wrapper.get('[data-test="open-manual-page"]').trigger('click')
  expect(window.open).toHaveBeenCalledWith(handoff.manual_url, '_blank', 'noopener,noreferrer')
  await wrapper.get('[data-test="resume-registration"]').trigger('click')
  expect(wrapper.emitted('resume')).toEqual([[handoff.task_id]])
})
```

- [ ] **Step 2: 运行并确认失败**

Run: `npm --prefix frontend test -- src/components/RegistrationHandoffDialog.test.ts src/views/registration/RegistrationHandoffFlow.test.ts`
Expected: 组件和流程方法尚不存在。

- [ ] **Step 3: 实现弹窗与页面集成**

弹窗只显示人工原因和官方 URL，提供“打开人工处理页面”和“处理完毕，继续执行”。`window.open` 必须使用 `noopener,noreferrer`。

注册页对活动任务每 2 秒查询 handoff；收到 `HANDOFF_*` 时打开弹窗，不在页面卸载后继续轮询。resume 成功后关闭弹窗、刷新同一任务，不重新打开创建表单。APEC 只显示官方人工入口，不出现适配器字段。

- [ ] **Step 4: 运行测试确认通过**

Run: `npm --prefix frontend test -- src/components/RegistrationHandoffDialog.test.ts src/views/registration/RegistrationHandoffFlow.test.ts`
Expected: 弹窗、官方链接、恢复、轮询清理和秘密排除检查通过。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/registration.ts frontend/src/components/RegistrationHandoffDialog.vue frontend/src/components/RegistrationHandoffDialog.test.ts frontend/src/views/registration/RegistrationView.vue frontend/src/views/registration/RegistrationHandoffFlow.test.ts
git commit -m "feat: add registration handoff dialog"
```

### Task 7: 契约、文档与端到端验收

**Files:**
- Modify: `backend/app/main.py`
- Modify: `docs/registration-foundation.md`
- Modify: `docs/api/v0.1-openapi.json`（仅由 `scripts/export_openapi.py` 生成）
- Modify: `.claude/skills/run-ai-journal-submission-agent/SKILL.md`
- Modify: `.claude/skills/run-ai-journal-submission-agent/driver.mjs`

**Interfaces:**
- Consumes: Task 1–6 的全部接口。

- [ ] **Step 1: 更新契约并运行检查**

```bash
PYTHONPATH=backend .venv/bin/python scripts/export_openapi.py
.venv/bin/python -c 'import json, sys; from pathlib import Path; from openapi_spec_validator import validate_spec; validate_spec(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))' docs/api/v0.1-openapi.json
```

为 handoff/resume 增加中文 summary、组件标题和 `RouteContract`。文档明确可见浏览器、人工接管、APEC 禁止自动点击及秘密边界。

- [ ] **Step 2: 运行后端与前端测试**

```bash
cd backend && ../.venv/bin/ruff check app tests && ../.venv/bin/mypy app
cd .. && npm --prefix frontend test && npm --prefix frontend run build
```

Expected: 静态检查、所有新增及既有测试、类型检查和构建通过。若其他工作区迁移仍造成历史测试冲突，单独列出，不能宣称完整后端门禁通过。

- [ ] **Step 3: 扩展浏览器验收并检查截图**

驱动新增允许自动化的本地模拟注册站，验证数据库字段自动填写、可见步骤、CAPTCHA 弹窗、打开人工页面和 resume；APEC 断言只打开官方人工页且不启动自动点击。结果和截图保存到 `/tmp/ai-journal-submission-agent-run/`，必须人工查看。

- [ ] **Step 4: 最终差异检查**

```bash
git diff --check
git status --short
```

确认无秘密、临时浏览器 profile、数据库文件、截图或临时测试插件进入提交范围。

- [ ] **Step 5: 提交**

```bash
git add backend/app/main.py docs/registration-foundation.md docs/api/v0.1-openapi.json .claude/skills/run-ai-journal-submission-agent/SKILL.md .claude/skills/run-ai-journal-submission-agent/driver.mjs
git commit -m "docs: verify browser registration automation"
```
