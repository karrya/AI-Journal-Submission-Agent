# 注册基础与阶段一验收

本文给出模块 3 注册基础的可重复启动、迁移、测试和阶段一验收步骤，并说明它与模块 2 期刊身份/网络识别的表及权限关系。除非另有说明，命令均从项目根目录执行。

## 1. 阶段一范围与安全边界

阶段一交付出版社支持配置、平台适配器元数据、投稿入口准入、作者显式授权、注册任务工作区、可恢复 Worker，以及哈希绑定的一次性确认。默认注册执行器只复核授权与目标准入，然后将任务置为 `NEEDS_MANUAL_REVIEW`。

**本阶段不执行真实平台注册、自动登录、真实邮箱读取、真实验证链接访问、表单提交、文件上传或外部投稿。** 不绕过 CAPTCHA/MFA，不自动同意平台条款，不处理费用、付款或订阅。测试中的注册执行器和外部结果均为本地模拟；平台适配器的真实账号验收需要独立规格、明确授权、测试账号和沙箱计划。

不得将真实密码、Token、Cookie、凭据引用内容、完整验证链接或用户文件写入文档、测试集合、日志或 Git。

## 2. 可重复启动与迁移

### 2.1 一次性准备

按[运维手册](operations.md)安装依赖并运行一次 `scripts/bootstrap_mysql.py`。初始化创建相互隔离的开发库、固定测试库和三个专用 MySQL 账号，并将凭据写入权限为 `0600` 的 `.env`。不要在日常启动或测试时重复初始化，不要提交 `.env`。

```bash
export PROJECT_ROOT="/Users/didi/PycharmProjects/AI Journal Submission Agent"
cd "$PROJECT_ROOT"
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
.venv/bin/python scripts/bootstrap_mysql.py
```

### 2.2 使用专用迁移账号

开发库迁移使用 `.env` 中的 `ALEMBIC_DATABASE_URL`，其身份必须是仅拥有开发库迁移权限的 `asa_migrate@127.0.0.1`。不要使用 `DATABASE_URL` 的应用账号，也不要使用 `TEST_DATABASE_URL` 的测试账号。连续执行两次 `upgrade head`，第二次应无模式或数据变更，再执行模型一致性检查：

```bash
cd "$PROJECT_ROOT/backend"
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic check
```

完全迁移后的模式包含 23 张应用表和 1 张 `alembic_version` 表。`0010_domain_wide_tables` 将出版社注册支持、出版社/期刊别名和平台适配器配置合并到对应领域宽表，ISSN/EISSN 直接读取 `journals` 自有字段，并删除未投入使用的出版社账号、邮箱验证记录和平台目录。迁移先校验旧数据，再复制和核对，最后才删除 8 张旧表；升级前如已有相同作用域的未决任务，必须先人工核查并整理这些任务，不能靠删除或覆盖历史记录绕过冲突。

### 2.3 启动后端、两个 Worker 和前端

使用 launchd 脚本同时启动后端、期刊识别 Worker 和注册 Worker，再在一个独立终端启动前端：

```bash
cd "$PROJECT_ROOT"
bash scripts/dev_services.sh start
bash scripts/dev_services.sh status
```

```bash
cd "$PROJECT_ROOT"
bash scripts/dev_frontend.sh
```

检查本地健康状态：

```bash
curl --fail --silent http://127.0.0.1:8000/api/v1/health
curl --fail --silent http://127.0.0.1:5173/ >/dev/null
```

前端为 `http://127.0.0.1:5173`，后端仅监听 `127.0.0.1:8000`。三个长期服务的日志分别位于 `storage/logs/backend.*.log`、`storage/logs/worker.*.log` 和 `storage/logs/registration-worker.*.log`。需要停止时使用 `bash scripts/dev_services.sh stop`；该命令不停止前端终端。

## 3. 模块 2 与模块 3 的表关系

| 归属 | 表 | 关系与用途 |
| --- | --- | --- |
| 模块 2 出版社宽表 | `publishers` | 保存出版社身份、JSON 别名及 `registration_code`、`registration_support_status`、`registration_support_level` 等注册支持字段。 |
| 模块 2 期刊宽表 | `journals` | 通过 `publisher_id` 归属出版社；直接保存 ISSN/EISSN、`platform_code` 和 JSON 别名，不再有重复标识子表。 |
| 模块 2 识别任务 | `discovery_tasks` | 保存网络识别任务、幂等键、检查点、租约和重试状态，可关联期刊及作者。 |
| 模块 2 识别证据 | `journal_source_snapshots`、`journal_discovery_logs` | 通过 `task_id` 关联识别任务，并可关联期刊；保存页面快照元数据和追加式发现日志。 |
| 模块 2/3 共享边界 | `journal_submission_portals` | 必须关联 `journals`，可回溯 `discovery_tasks`；直接保存规范化主机、入口支持状态、核验信息及 `adapter_*` 适配器配置。 |
| 模块 3 注册任务 | `registration_tasks` | 关联作者、出版社、期刊、投稿入口和 `author_authorizations`；保存授权 ID、幂等键、状态、检查点、租约及重试信息，不再关联出版社账号目录。 |
| 模块 3 一次性确认 | `registration_confirmations` | 关联注册任务和请求用户，只保存摘要哈希、Token 哈希、到期时间和消费时间；保留多次挑战历史以防重放。 |

注册授权还依赖既有身份表 `users`、`roles`、`user_roles`、`authors` 和 `author_authorizations`。外键均使用受控关联和 `RESTRICT` 删除策略；授权记录是注册任务不可缺少的一部分，而不是可由期刊或稿件读取权限替代的关系。`publisher_accounts`、`email_verification_records`、`publisher_registration_support`、`platform_adapters`、`journal_platforms`、`publisher_aliases`、`journal_aliases` 和 `journal_identifiers` 已在 `0010` 中删除，不再被当前代码使用。

## 4. 权限与准入规则

### 4.1 角色能力和作者授权必须同时成立

- 注册相关操作要求登录会话；创建、取消和重试任务还要求 CSRF。出版社支持字段及投稿入口/内联适配器配置仅系统管理员可修改，并要求 CSRF。入口响应不包含适配器能力配置或内部验收说明。
- `account:register`、`email:verification:read` 和 `credential:use` 是三个独立权限，任何一个都不能由其他权限或 `manuscript:read` 替代。
- 注册任务要求当前角色具备 `account:register` 能力，并且请求中的 `authorization_id` 对应当前用户、当前作者的有效 `author_authorizations` 记录。授权必须已生效、未到期、未撤销，且包含该权限。
- 系统管理员也不能省略作者显式授权；只读角色即使持有授权记录也仍被角色能力拒绝。
- 任务查询、取消和重试沿用同一作者及授权边界。Worker 在执行前、检查点和完成写入前重新校验授权及目标，执行中撤销授权或禁用入口会阻止后续动作。

### 4.2 目标准入必须全部通过

1. 出版社属于 Springer Nature、Elsevier、Wiley、Taylor & Francis 或 SAGE 的 V0.1 支持集合，支持级别为 `V0_1` 且状态为 `SUPPORTED`。
2. 期刊存在、未删除且确实属于该出版社。
3. 投稿入口属于该期刊，`support_status=SUPPORTED` 且 `verification_status=VERIFIED`。
4. 入口的 `adapter_support_status` 为 `SUPPORTED`，适配器代码和版本完整，入口平台代码与请求平台代码一致。
5. 入口最终 URL 必须使用 HTTPS 和标准 TLS 端口（缺省或 443），其精确主机名与入口 `normalized_host` 一致，并位于入口 `adapter_allowed_domains` 集合中；大小写和末尾点规范化不放宽主机匹配。

## 5. 任务、Worker 恢复与确认防重放

注册任务创建使用唯一幂等键；相同输入返回既有任务，相同幂等键用于不同输入会被拒绝。入口行锁内的冲突检查与数据库生成列唯一约束共同保证：同一作者和投稿入口不能由不同幂等键并发创建多个活跃、结果不确定或已完成注册的任务。创建 API 返回 `202`，任务 API 不返回原始凭据、Cookie 或确认 Token。

任务状态只能按 Workflow Service 的显式源/目标图迁移。提交确认、平台接受证据和注册完成证据分别由专用方法校验；`REGISTERED` 是终态，不能重试。`CANCELLED` 或明确可重试的 `FAILED` 只有在没有外部动作标记时才可重新排队，否则返回 `PLATFORM_RECONCILIATION_REQUIRED`，等待人工核查平台实际状态。

注册 Worker 原子认领待执行任务，并记录 Worker ID、心跳和租约。过期租约可由存活 Worker 重新认领；失去租约的旧 Worker 不能覆盖新所有者的检查点或结果。可重试失败使用带配置上限、最大次数和有界随机抖动的指数退避，耗尽后进入 `NEEDS_MANUAL_REVIEW`。如果过期任务已记录提交标记，Worker 会在同一事务中将其恢复为 `SUBMISSION_UNKNOWN`、清除所有权并审计，不会调用执行器。任务创建、配置、取消、重试、Worker 认领、结果、取消、失败和恢复均复用 `operation_logs`，只写显式白名单摘要。

确认挑战与任务、动作、请求用户和规范化摘要哈希绑定，默认十分钟到期。数据库只保存 Token 哈希和摘要哈希。消费时锁定任务并同时校验预期动作与合法当前状态，再使用带全部绑定条件的原子更新；只有一个并发请求能成功。重放返回 `CONFIRMATION_CONSUMED`，过期返回 `CONFIRMATION_EXPIRED`，跨动作、任务、用户、Token 或摘要不匹配返回 `CONFIRMATION_INVALID`，已取消或其他非法状态返回 `INVALID_TASK_STATE`。拒绝路径显式回滚，不保留部分消费。

## 6. 阶段一自动化验收

### 6.1 固定独立测试库

所有后端测试都要求 `ENVIRONMENT=test`，且回环地址 `TEST_DATABASE_URL` 的数据库名必须恰好为 `academic_submission_agent_test`。测试会删除并重建该测试库的数据，使用临时文件存储。**绝不能把 `TEST_DATABASE_URL` 指向开发库或其他真实数据。** 防护同时拒绝非测试数据库、非回环目标和正式存储。

### 6.2 四项安全行为专项验证

先运行脚本语法检查：

```bash
cd "$PROJECT_ROOT"
bash -n scripts/dev_services.sh scripts/dev_backend.sh scripts/dev_worker.sh scripts/dev_registration_worker.sh
```

再运行注册专项测试：

```bash
cd "$PROJECT_ROOT/backend"
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_registration_authorization.py \
  tests/test_registration_service.py \
  tests/test_registration_admission.py \
  tests/test_registration_worker.py \
  tests/test_registration_confirmation.py \
  tests/test_registration_api.py \
  tests/test_registration_hardening.py -q
```

按下表核对覆盖的安全行为；这些测试全部使用固定测试库和模拟执行器：

| 验收行为 | 代表测试 | 预期结果 |
| --- | --- | --- |
| 无授权拒绝 | `test_admin_without_author_registration_grant_is_denied`、`test_inactive_registration_grant_is_denied` | 缺失、未生效、过期或撤销授权均返回 `403 AUTHORIZATION_INVALID`；角色不允许时为 `403 PERMISSION_DENIED`。 |
| 入口未核验拒绝 | `test_unverified_portal_is_rejected` | 非 `VERIFIED` 入口返回 `409 JOURNAL_ENDPOINT_NOT_VERIFIED`，不会创建可执行任务。 |
| Worker 恢复 | `test_expired_lease_can_be_reclaimed`、`test_lost_lease_cannot_overwrite_new_owner`、`test_recovered_task_with_submission_action_is_not_executed` | 过期租约可恢复；旧 Worker 无法覆盖新所有者；存在未知提交动作时不执行或重放。 |
| 确认重放拒绝 | `test_confirmation_cannot_be_replayed_or_used_after_summary_change`、`test_concurrent_consume_has_exactly_one_winner` | 第二次消费返回 `409 CONFIRMATION_CONSUMED`，并发消费只有一个成功，摘要不匹配返回 `CONFIRMATION_INVALID`。 |

### 6.3 完整验证与差异检查

从项目根目录运行完整门禁：

```bash
cd "$PROJECT_ROOT"
bash scripts/verify.sh
```

该命令依次检查 Ruff、mypy、完整 MySQL 后端测试及覆盖率、确定性 OpenAPI 生成与校验、隔离 Postman/Newman 集合、前端测试及覆盖率和生产构建。只有全部命令成功且没有未处理警告或新增测试被跳过，阶段一自动化验收才通过。

最后检查空白错误和提交范围：

```bash
cd "$PROJECT_ROOT"
git diff --check
git status --short
```

暂存和提交只能包含本阶段计划内文档及确定性 OpenAPI 契约；不得包含 `.env`、密码、Token、Cookie、完整验证链接、覆盖率/测试产物或用户文件。

## 7. 主要 API 契约

已提交的 `docs/api/v0.1-openapi.json` 是以下路由的权威请求/响应契约：

- `GET /api/v1/registration/publishers` 与 `GET /api/v1/registration/publishers/{publisher_id}/journals`：读取安全目录元数据；
- `PUT /api/v1/registration/publishers/{publisher_id}/support`：管理员配置出版社宽表中的注册支持字段；
- `PATCH /api/v1/registration/submission-portals/{portal_id}`：管理员配置入口支持状态及内联 `adapter_*` 字段；
- `POST/GET /api/v1/registration/tasks`、`GET /api/v1/registration/tasks/{task_id}`：创建和查询授权范围内任务；
- `POST /api/v1/registration/tasks/{task_id}/cancel` 与 `/retry`：按状态机取消或重试。
