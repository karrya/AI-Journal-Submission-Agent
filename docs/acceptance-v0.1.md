# V0.1 最终验收

**验收日期：** 2026-11-06（本轮浏览器证据时间戳 2026-11-05T21:04:57.137Z）
**结果：** **通过——本轮中文化最终验收的完整验证与真实 Chrome 检查均成功执行。** 下述剩余限制不代表跳过或失败的必需检查项。

被测变更基于提交 `8984d61`，包含当前未提交的中文化工作树及最终验收最小修复。本文件保留 2026-11-05 已完成的全新安装、MySQL 重启持久化和隔离备份恢复记录；本轮未重复执行这些破坏性维护步骤，而重新执行了完整 `bash scripts/verify.sh`、真实 Chrome 主验收及路由复用回归。本文不包含真实密码、数据库 URL、会话令牌、age 私钥、个人文档或服务器存储路径。

## 环境

- arm64 架构 macOS；Homebrew `mysql@8.0` 8.0.46（最终运行时）、Python 3.13.3、Node 26.13.0、npm 11.20.0。
- 后端：`/Users/didi/PycharmProjects/AI Journal Submission Agent/.venv/bin/python`。
- 浏览器：实际 Google Chrome 156.0.8078.80，无头模式，由应用依赖之外的临时 `playwright-core` 工具驱动。
- 保存在版本控制目录中的脱敏请求级 Network 证据、可执行浏览器测试工具及合成数据截图位于 [`docs/evidence/v0.1/browser/`](evidence/v0.1/browser/)。本轮发布证据不依赖未提交的原始日志；临时凭据、夹具文件和存储已清理，验收 Web 进程已停止。

## 1. 按文档全新安装

从文档所列项目根目录执行的命令：

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
cd backend
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic check
cd ..
.venv/bin/python scripts/create_admin.py
bash scripts/verify.sh
```

现有已预置的根目录 `.env` 未被读取到证据中，也未被修改、暂存或输出。因此，没有重新运行会轮换凭据的管理初始化。相反，内部使用现有最小权限 `asa_test` 连接（未输出其 URL），仅删除并重建 `academic_submission_agent_test`，使其成为采用文档所列 utf8mb4 排序规则的全新空模式。未将任何其他数据库作为目标。存储使用新建的 `/tmp` 目录。

观察结果：

- 锁定版本的后端/前端依赖安装通过（`dependency-install.log`）。
- 模式初始为空。两次 `upgrade head` 调用到达同一 head；第二次日志中没有 `Running upgrade` 操作。`alembic check` 通过。
- 迁移后检查到恰好 **18 张应用表加 `alembic_version`**（共 19 张）。
- 实际 `create_admin.py` CLI 收到生成的用户名和隐藏输入的初始密码。首次登录返回 `must_change_password=true`；`POST /api/v1/auth/change-password` 返回 204；使用替换后的新密码重新登录返回 200 和 `must_change_password=false`。生成的密码既未写入证据，也未输出。
- 全新的临时后端使用端口 8002，随后被终止；临时存储已删除。
- 一次测试工具尝试错误地包含了仅供前端使用的 `confirm_password` 字段。API 正确拒绝了该额外字段；测试工具修正为文档所列 `current_password`/`new_password` API 模式后，从另一个全新模式重新运行了完整的全新安装序列。这不是产品故障。

## 2. 完整验证、覆盖率与接口契约

2026-11-06 中文化最终验收重新执行 `bash scripts/verify.sh`，全部检查通过。由于 OpenAPI 中文化本身就是当前未提交变更，验证脚本使用导出前后快照的逐字节 `cmp` 检查生成漂移；这与原 `git diff --exit-code` 一样会在源定义和快照不一致时失败，但不要求先提交中文化变更。

| 检查项 | 本轮实际结果 |
|---|---|
| Ruff 和 mypy | 通过；Ruff 无问题，mypy 检查 54 个源文件无问题 |
| 后端 pytest | **476 passed**，0 failed（最终复验 32.28 s） |
| 专项可执行安全矩阵 | **37 项**包含在上述完整套件中 |
| 后端总体覆盖率 | **95.74%**（下限 80%） |
| 权限覆盖率 | **98.78%**（下限 95%） |
| 文件服务覆盖率 | **91.83%**（下限 90%） |
| 文件校验覆盖率 | **90.23%**（下限 90%） |
| 存储覆盖率 | **94.83%**（下限 90%） |
| 服务合并覆盖率 | **93.54%**（下限 85%） |
| API 覆盖率 | **96.91%**（下限 80%） |
| OpenAPI | 已生成，经 `openapi-spec-validator` 校验，导出前后快照逐字节一致 |
| Newman | **40/40 个请求、97/97 个断言**，0 个失败；隔离后端端口 8001 和临时存储 |
| 前端单元测试 | **22 个文件、126 个测试通过**，覆盖率运行时重复执行且同样通过 |
| 前端语句覆盖率 | **83.12%**（1690/2033） |
| 前端分支覆盖率 | **85.99%**（1959/2278） |
| 前端函数覆盖率 | **77.85%**（443/569） |
| 前端行覆盖率 | **86.84%**（1558/1794） |
| 前端生产构建 | `vue-tsc --noEmit && vite build` 通过；最终复验 Vite 构建耗时 2.59 s，1718 个模块完成转换 |

本轮重新执行生产 `npm audit --omit=dev`，返回零个漏洞。完整开发 `npm audit` 仍返回五个高危条目，详见限制部分。

## 3. 持久化与 MySQL/Web 重启验收

通过真实 API，在全新 `_test` 模式和临时存储中创建了一个合成所有者、带恶意标记的共同作者、稿件、不可变版本 2 和 PDF 文件。为角色检查添加了一次性操作员和审计员账号，以及仅针对所有者的操作员授权。重启前，通过直接 ORM（对象关系映射）和文件系统检查确认全部四条记录、当前版本关联、字节数和 SHA-256（安全哈希算法 256 位）。

执行了经授权的维护命令及两个已纳入版本控制的启动脚本：

```bash
brew services restart mysql@8.0
bash scripts/dev_backend.sh
bash scripts/dev_frontend.sh
```

MySQL 重启前后端和前端均在运行，随后仅使用其验收 PID/监听器停止并重启。重启后检查包括全新 API 登录、稿件/版本/文件读取和授权下载。

| 持久化检查 | 重启前 | 重启后 |
|---|---|---|
| 作者、稿件、版本、文件记录 | 存在 | 存在 |
| 稿件当前版本为已接受的 v2 | True | True |
| 文件字节数 | 69 | 69 |
| 文件 SHA-256 | `cfa3181c1ee36e8bce5e39f84959f4558ea7ba32c0e4539a8ab3c8ce8c716ec6` | 完全相同 |
| 授权下载 SHA-256 | 与测试夹具哈希相同 | 重启后完全相同 |

`persistence-before.json` 和 `persistence-after.json` 逐字节相同。最终 MySQL 服务保持启动；验收 Web 进程已停止。

### 已解决的环境事故

首次经授权的重启暴露了 Homebrew 运行时缺陷：`mysqld` 8.0.42 无法加载已移除的 Abseil `2407.0.0` 动态库。因此服务未能恢复，且未声称该次尝试通过持久化/浏览器验收。`mysql-homebrew-repair.log` 和 `mysql-homebrew-repair-mirror.log` 记录了修复过程。升级软件包时未删除或初始化任何数据目录；默认下载停滞后使用了可访问的清华 bottle 镜像。随后 MySQL 8.0.46 成功启动。从全新测试模式重新运行完整持久化序列之前，检查了开发模式和测试模式。最终重启及后续所有检查均通过。

## 4. 实际浏览器 Network 与视觉验收（WEB-01）

浏览器测试工具使用临时 `playwright-core`，未将 Playwright 添加到应用依赖。Axios 适配器/Vitest 模拟**未**用作浏览器证据。本轮向固定 `academic_submission_agent_test` 模式添加合成夹具，未删除或重置任何数据库，也未重复 MySQL 重启或 BACKUP-01。路由复用证据捕获于 **2026-11-05T21:04:52.211Z**，主验收 Network 捕获于 **2026-11-05T21:04:57.137Z**。随后删除了临时存储和夹具文件并停止 Web 进程；后续完整测试按既有隔离策略清理了测试模式。

本轮重新生成的产物：

- [`browser-network.json`](evidence/v0.1/browser/browser-network.json)：99 个有序请求/响应事件，含方法、路径、状态和请求/响应关联；检查作者字段白名单；19 个响应的业务扫描；过期上传时间线；以及零个操作员审计请求。仅保留合成资源 ID 和 API 路径。源、查询字符串、标头、Cookie、CSRF（跨站请求伪造）/会话令牌、凭据及请求/响应正文均被排除。
- [`browser-result.json`](evidence/v0.1/browser/browser-result.json) 和 [`browser-run.log`](evidence/v0.1/browser/browser-run.log)：通过的断言摘要，包含 `chinese_ui=true`，并以 `chinese_ui_scopes` 明确记录主导航、稿件工作区、操作员工作台、管理员审计表格和审计员审计表格五类中文检查范围。
- [`acceptance.cjs`](evidence/v0.1/browser/acceptance.cjs)：主验收测试工具的准确源代码（SHA-256 `f059ecd13e94e6b156516b04d598a6358ee42df8eeb4e262ee5c51bb140c4ad0`）。
- [`browser-authorized-download.pdf`](evidence/v0.1/browser/browser-authorized-download.pdf)：用于独立下载哈希检查的 69 字节合成 PDF。
- [`final-fix-route-reuse.cjs`](evidence/v0.1/browser/final-fix-route-reuse.cjs) 和 [`browser-route-reuse-result.json`](evidence/v0.1/browser/browser-route-reuse-result.json)：中文界面下的路由复用回归工具及请求级结果。

验收 Shell 中已导出生成的凭据和夹具变量时，实际浏览器调用命令为：

```bash
NODE_PATH=/tmp/asa-v01-browser-tool/node_modules node "$ROOT/docs/evidence/v0.1/browser/acceptance.cjs" > "$EVIDENCE/browser-run.log" 2>&1
```

其中，`ROOT` 为文档所列项目根目录，`EVIDENCE` 为 `$ROOT/docs/evidence/v0.1/browser`，`EVIDENCE_DIR` 导出为相同值，`FIXTURE_FILE=/tmp/asa-v01-browser-tool/evidence-fixture.json`，`PDF_FIXTURE=$ROOT/backend/tests/fixtures/minimal.pdf`。密码仅保留在进程环境变量中，不存在于任何发布证据。

仅获授权访问合成所有者的操作员加载了一篇稿件，其中的共同作者带有合成私人邮箱、电话和备注标记。中文选择器和显式界面文本断言均通过；除稿件工作区外，还逐一断言了三种角色的主导航、操作员工作台汇总与导航、管理员和审计员审计表格的八个中文表头及筛选/分页文案，不将四个稿件页标签当作全项目中文证明。关联的请求级证据证明：

- 响应序列 **11** 和 **17** 中的稿件及不可变快照作者对象恰好包含 `author_id`、`display_name`、`position` 和 `is_corresponding`；明确记录了观察到的键集合和白名单。
- 操作员的 **19** 个业务响应（序列列于 `network_scan.response_sequences`）不含合成私人标记或 `storage_path`/`stored_filename`：扫描了 18 个 JSON 正文，响应 **37** 是单独验证哈希的 PDF。渲染后的 DOM（文档对象模型）同样不含这些标记或路径字段。
- 新文件族上传响应 **21** 返回 **201**，文件版本为 1。现有文件族上传响应 **29** 返回 **201**，在原文件族中生成文件版本 2。
- 授权下载响应 **37** 返回 **200**；保存文件的 SHA-256 `453c8ccf889936826ae6e01dbda5cd2038f4a5b0c0aea9b3cb659efcd0e628cf` 与上传的第二个 PDF 匹配。
- 第二个标签页保留版本 2 时，竞争版本创建响应 **53** 返回 **201**。过期上传请求 **64** 恰好产生一个响应 **65**，状态为 **409 `INVALID_MANUSCRIPT_STATE`**。记录的时间线显示：请求发生于 605 ms，冲突发生于 624 ms，非重试警告和刷新操作发生于 630 ms；显式观察在 1631 ms 结束时仍恰好只有一个上传 POST（冲突后观察 1000 ms）。
- 操作员仪表盘响应 **71** 返回 **200**，显示一个获授权作者。导航该操作员至 `/audit` 并重定向至仪表盘后，`operator_audit_request_sequences` 为空。
- 管理员审计响应 **82** 返回 **200**，有可见记录。审计员仪表盘响应 **93** 返回 **403**，而审计员审计响应 **99** 返回 **200**，有可见记录。

以下实际截图均已重新生成、打开并进行视觉检查：[`browser-manuscript.png`](evidence/v0.1/browser/browser-manuscript.png)、[`browser-stale-409.png`](evidence/v0.1/browser/browser-stale-409.png)、[`browser-dashboard-operator.png`](evidence/v0.1/browser/browser-dashboard-operator.png)、[`browser-audit-admin.png`](evidence/v0.1/browser/browser-audit-admin.png)、[`browser-audit-auditor.png`](evidence/v0.1/browser/browser-audit-auditor.png)、[`browser-route-reuse-loading.png`](evidence/v0.1/browser/browser-route-reuse-loading.png) 和 [`browser-route-reuse-second.png`](evidence/v0.1/browser/browser-route-reuse-second.png)。导航、页面、表单、文件、冲突消息、仪表盘汇总和审计表格均以中文正常渲染；合成业务标题和审计操作代码不属于未翻译的界面控件。未见敏感标记或存储路径。稿件截图还确认，固定快照署名列表每位作者仅显示一个位置标记。没有浏览器执行阻塞项需要报告。

## 5. 加密备份与隔离恢复（BACKUP-01）

应用写入方停止后，验证使用其受保护的 `RESTORE_ADMIN_URL` 预置路径：未使用 `RESTORE_DATABASE_URL`；固定空 `academic_submission_agent_restore_test` 模式在不存在时创建，非空时拒绝；现有 `asa_test` 身份仅在导入时获得该恢复模式的 `ALL PRIVILEGES`。这并未假定或要求 `asa_test` 预先拥有恢复模式权限。[运维手册](operations.md#8-age-密钥加密备份与隔离恢复)现在记录了此受保护路径和专用 `asa_restore` 替代路径，两者均采用模式范围最小权限预置。实际执行了验证：

```bash
.venv/bin/python scripts/test_backup_restore.py
```

观察输出（`backup-restore.log`）：

- **Alembic 后共 19 张表**（18 张应用表加迁移簿记表）。
- **9 项源表行数比较**，转储比较中有意排除会话。
- **1 个恢复文件**和 **3/3 个已验证清单哈希**（转储、配置示例和存储文件）。
- `development_unchanged=true`，覆盖源行数、表校验和、模式 DDL（数据定义语言）哈希和存储哈希。
- age 封装验证通过；未残留明文 SQL/tar 或 `.partial` 产物；临时验证文件和解密恢复目录已删除。

加密产物：`academic-submission-agent-20261105T132015Z-168d47ff.tar.age`
加密产物 SHA-256：`03fe435da3c0c223d3f76cbcd7f54e0fbccae8451f81520b2b7a9fa29540e376`

加密备份保留在由 Git 忽略的 `backups/` 中；其 age 私钥仅供已纳入版本控制的验证使用，未读取到证据中。

## 6. 安全与恢复检查

- `git ls-files` 检查未发现已跟踪的真实 `.env`、存储对象、加密/明文备份、SQL 转储、tar 或不完整产物。未添加个人文档。
- OpenAPI 对 `/api/v1/audit-logs` 和 `/api/v1/audit-logs/{log_id}` 仅暴露 GET。自动 POST/PATCH/DELETE 405 和不可变快照断言同样通过。
- 开发数据库与固定测试数据库名称不同，测试主机为回环地址，所有破坏性测试/API 命令均使用临时非正式存储。防护测试要求显式环境和主机参数。
- 未知提交保留、核对、孤立/缺失处理、确定回滚补偿、过期版本竞争和下载完整性阻断均在可执行安全矩阵及完整套件中通过。
- 快照署名现在使用 `authorship-position-list` 隐藏原生有序列表标记，同时保留存储的位置。专项组件/CSS 回归通过，本轮稿件截图显示 `1. Synthetic Evidence Owner`，而非 `1. 1. ...`。
- `git diff --check` 通过。无关的 `.idea/AI Journal Submission Agent.iml` 修改保持未触碰且未暂存。

## 7. 剩余限制（非跳过的检查项）

1. **开发依赖审计并非无问题。** 完整 `npm audit` 在 Postman/Newman 开发依赖链中报告与 CVE-2026-73231 相关的五个高危条目。移除冗余 Faker override 并未移除必需的传递依赖，也未破坏 Newman。锁定的工具链中没有受支持的 Postman 兼容修复版本。生产审计无问题，为 **0 个漏洞**。
2. V0.1 仍为回环本地部署：不声称提供生产 TLS/反向代理、分布式登录限流、恶意软件扫描器集成、数据库触发器不可变性或异地 age 密钥托管。`scan_status=not_scanned` 不是恶意软件安全断言。
3. Homebrew 警告 `mysql@8.0` formula 已弃用，计划于 2027-04-30 禁用。V0.1 有意以 MySQL 8.0 为目标；在该支持边界之前，规划经审查的数据库升级。

历史全新安装、迁移、持久化、隔离和 BACKUP-01 检查均有成功记录；本轮中文化验收要求的浏览器、完整测试、覆盖率、OpenAPI/Newman 和前端构建检查均未跳过，也未遗留失败。

## 8. 最终审查修复批次验证

本节记录实施者对六项最终审查发现的验证。它**不是**最终审查通过的结论；仍需进行限定范围的复审。

- 稿件路由复用现在会在 `manuscriptId` 变化时立即重新加载，使过期序列失效，清除先前稿件/版本/文件表示，并将变更绑定到已加载的稿件身份。除组件回归外，实际 Google Chrome 证据延迟了 m2 响应，尝试提交已分离的 m1 署名，并观察到**零个署名 PUT 请求**。见 [`final-fix-route-reuse.cjs`](evidence/v0.1/browser/final-fix-route-reuse.cjs)、[`browser-route-reuse-result.json`](evidence/v0.1/browser/browser-route-reuse-result.json)、[`browser-route-reuse-loading.png`](evidence/v0.1/browser/browser-route-reuse-loading.png) 和 [`browser-route-reuse-second.png`](evidence/v0.1/browser/browser-route-reuse-second.png)。截图已经视觉检查，仅含合成数据。
- 权限和失效授权拒绝现在会提交一条脱敏授权失败审计，包含操作者、目标作者、所请求权限、请求 ID 和固定错误码。已覆盖过期、已撤销、尚未生效、角色拒绝及有效授权但无权限的情况；404 行为和敏感值排除仍有覆盖。reviewer+auditor 回归证明，在无授权时，已知和未知 UUID 产生完全相同的脱敏拒绝表示，两者均省略 `author_id`；而已建立授权的拒绝路径保留有意义的作者 ID。
- 正式发布使用同一文件系统硬链接，随后解除临时名称链接。确定性的目标创建竞争证明，回滚补偿既不会覆盖也不会删除现有字节；确定和未知结果恢复测试仍全部通过。
- 测试客户端将全局恢复引擎绑定到隔离测试引擎。金丝雀检查在发出 SQL 前检查绑定，然后证明实际恢复会话报告 `academic_submission_agent_test`。
- 运行时请求 ID 在去除首尾空白前要求值为字符串，已覆盖数字、对象和 null 情况。
- 期刊要求验证时间戳要求包含时区信息，并在 JSON 存储和 API 响应前归一化为 UTC；已覆盖无时区输入和非 UTC 偏移。

这些变更及本轮中文化最终修复后，完整 `bash scripts/verify.sh` 检查通过：**476 个后端测试**、**126 个前端测试**（覆盖率运行中同样重复执行）、**40/40 个 Newman 请求和 97/97 个断言**，以及 Ruff、mypy、OpenAPI 生成/校验/快照比较和生产构建。后端总体覆盖率为 **95.74%**，权限 **98.78%**，文件服务 **91.83%**，文件校验 **90.23%**，存储 **94.83%**，服务 **93.54%**，API **96.91%**。前端语句/分支/函数/行覆盖率为 **83.12% / 85.99% / 77.85% / 86.84%**。

中文化终验及本次独立审查修复包括期刊布尔要求值和审计目标类型的中文显示、OpenAPI 参数/组件属性/组件及内联响应标题中文化、保留约束上下文的通用校验消息、Alembic 与 Compose 错误提示、期刊布尔解析错误文案、根目录 PyCharm 示例，以及浏览器多页面中文显式断言。最终 OpenAPI 共检查 **677 个 `title`，纯英文标题为 0**；递归去除 `title` 后，修复前后文档结构完全一致，属性名、组件键、`operationId`、schema 结构和枚举均未改变。新增 11 个上下文消息精确断言和 1 个全文档标题回归，底层 API 枚举、权限判断、安全断言及期刊要求值解析行为均未改变。

生产 `npm audit --omit=dev` 仍无问题，为零个漏洞。完整开发 `npm audit` 仍报告第 7 节记录的五个 Faker/Postman 高危公告条目；本修复批次未隐藏或声称解决这些问题。浏览器运行仅使用固定 `academic_submission_agent_test` 模式和临时存储，清理了合成记录，并停止两个 Web 进程。未触碰开发数据、根目录 `.env`、现有 age 密钥及无关 `.idea` 变更。
