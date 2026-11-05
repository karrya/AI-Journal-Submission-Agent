# 安全说明与验证

## 本地信任边界

V0.1 是仅绑定回环地址的本地应用，并非针对互联网加固的部署。后端和 Vite 监听器绑定 `127.0.0.1`；默认信任的浏览器源为 `http://127.0.0.1:5173` 和 `http://localhost:5173`，与文档中的快速入门一致。MySQL 账号固定为 `127.0.0.1`，权限仅限各自数据库。不要公开开发服务器或 MySQL，也不要在其他位置复用本地凭据。

实际 `.env`、存储、加密备份、Python/Node 依赖、覆盖率输出和 IDE 状态均由 Git 忽略。`.env.example` 仅含占位符。不要将数据库 URL、密码、CSRF（跨站请求伪造）密钥、可复用 Cookie、age 私钥、个人文件或服务器存储路径放入源代码、测试、截图、日志、问题单或验收证据。

## 身份认证、授权与数据暴露

- 密码采用 Argon2 密码哈希算法。隐藏输入的管理员初始化工具没有默认凭据，并强制首次修改密码。
- 会话使用随机令牌，由服务端保存，同时受空闲时限和绝对时限约束；MySQL 中仅存储其哈希，并通过带 `HttpOnly`、`SameSite=Lax` 属性的 Cookie 传输。除非显式覆盖，否则在 HTTPS/非开发环境中 Cookie 带 `Secure` 属性；示例中的 `SESSION_COOKIE_SECURE=false` 仅供本地 HTTP 使用。
- 修改密码和退出登录会撤销会话。登录速率限制仅在单个进程内生效，因此不是分布式限流方案。
- 变更操作要求可信 Origin 和绑定会话的 CSRF 令牌。前端将 CSRF 保存在内存中，而非浏览器持久化存储。
- 初始密码限制全局适用于业务 API。多个标签页共享稳定的会话 CSRF 令牌。
- `system_admin` 拥有管理和审计访问权限。`submission_operator` 仍需有效的逐作者授权。即使授予写权限，`reviewer` 仍为只读。`auditor` 可读取审计日志，但不能读取业务仪表盘或期刊数据。混合角色的能力取并集，但系统管理员优先规则和显式角色排除仍然执行。
- 授权具有生效起止时间和撤销状态。写操作还独立要求读取权限；仅有写权限的授权无法通过变更响应窃取数据。
- 稿件署名和不可变快照作者仅包含 `author_id`、`display_name`、`position` 和 `is_corresponding`。共同作者邮箱、电话、地址、ORCID（开放研究者与贡献者标识）、备注及服务器存储路径均不包含在稿件/版本/文件/仪表盘响应中。
- 署名更新仅提交 ID、位置、通讯作者标记和显式确认。关联新共同作者需要资料读取权限，且不会泄露未授权作者 ID 是否存在。
- 审计响应采用显式摘要字段白名单。系统没有审计创建/更新/删除 API；不支持的变更方法返回标准错误结构。业务写入与其审计记录在同一事务中提交。

仅追加稿件快照、不可变审计行为和文件族历史通过服务/API 边界强制执行。**不声称**使用 MySQL 触发器或数据库级不可变规则。

## 文件与恢复

上传受大小限制，并按内容校验，包括结构化 Office/ZIP/XML 检查以及拒绝格式错误或被截断的输入。不信任客户端文件名和 MIME（多用途互联网邮件扩展）提示。生成的 UUID（通用唯一标识符）路径可防止客户端路径穿越；下载使用经授权的文件 ID、绑定文件描述符的流式传输、安全的 Content-Disposition 和 `X-Content-Type-Options: nosniff`。文件 API 不返回 `storage_path` 和 `stored_filename`。

上传期间会在锁内重新检查稿件/版本状态。同一文件族的上传会串行分配文件版本；过期版本上传返回 `409`，浏览器不会自动重发 POST。确定回滚时会补偿清理新移动的文件。提交/回滚结果未知时，会保留正式文件并写入核对清单条目，而不是猜测结果或删除文件。核对会报告缺失、损坏和孤立文件，不暴露存储路径，也绝不会自动删除状态不确定的正式文件。

## 备份边界

备份将 tar 字节流直接传入 age，并且只发布完整的 `.tar.age` 文件。备份包含 MySQL 转储、存储、`.env.example` 和 SHA-256（安全哈希算法 256 位）/大小清单条目；排除实际 `.env`、明文凭据、可复用 Cookie 和 `auth_sessions`。恢复要求显式输入 `RESTORE`、空的隔离 `_test` 模式，以及正式存储之外的空存储目录。恢复会验证归档路径、哈希、受限 mysqldump SQL、非限定表引用、行数、迁移和恢复文件。

age 私钥必须位于项目之外，不得为符号链接，并且用户组和其他用户均不可访问。唯一密钥丢失意味着备份无法恢复。独立恢复可证明源表和行数稳定；更强的 BACKUP-01 验证还会证明开发库校验和、模式 DDL（数据定义语言）哈希及存储哈希均未改变。

## 可执行矩阵与发布检查

在项目根目录运行完整检查：

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/verify.sh
```

专项矩阵命令为：

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent/backend"
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_security_matrix.py tests/test_authorization_boundaries.py -q
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_schema_constraints.py::test_mig_01_empty_upgrade_head_is_cleanly_repeatable -q
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
.venv/bin/python scripts/test_backup_restore.py
```

可执行覆盖范围如下：

| 矩阵范围 | 执行内容 |
|---|---|
| AUTH-01–AUTH-05 | 缺失/过期/已撤销会话、CSRF/Origin 失败、全局初始密码限制、稳定的多标签页 CSRF |
| ROLE-01, AUTHZ-01–AUTHZ-03 | 角色并集/排除、资源不存在与未授权不可区分、失效授权、只读拒绝及安全的审计失败 |
| ISO-01–ISO-06 | 最小共同作者署名、使用带恶意共同作者源数据的真实 API 创建快照、跨文件族替换、不可枚举、仅写权限响应、机构摘要 |
| FILE-01–FILE-05 | 伪造内容、恶意文件名、并发文件族版本、回滚/未知提交恢复、过期版本竞争 |
| TX-01 | 业务/审计回滚原子性 |
| MIG-01 | 空库升级至 head，并重复升级而不产生重复影响 |
| API-01 | 生成的 OpenAPI 校验及真实 Newman 请求/断言集合 |
| WEB-01 | 实际本地浏览器 DOM（文档对象模型）/视觉检查及捕获的 Network 响应；前端模拟适配器测试仅是单元测试证据，不是浏览器端到端测试 |
| BACKUP-01 | 真实加密备份和隔离恢复，并检查源/目标记录及哈希 |

后端覆盖率下限为：总体 80%、权限 95%、文件服务 90%、文件校验 90%、存储 90%、全部服务 85%、API 80%。`scripts/check_coverage.py` 会逐项执行这些下限检查。测试/开发数据库和存储目标必须分离；迁移或删除前，破坏性防护要求显式设置 `ENVIRONMENT=test`、显式回环数据库主机、固定 `_test` 数据库及非正式存储。

## 剩余限制与依赖公告

- V0.1 不提供分布式登录限流、恶意软件扫描器集成、数据库触发器不可变性、异地密钥托管或生产 TLS/反向代理部署。`scan_status=not_scanned` 是如实状态，并不表示内容不含恶意软件。
- 冗余的直接 `@faker-js/faker` npm override 已移除；Newman 仍使用其 Postman 依赖树所要求的传递 Faker 版本。完整的**开发** `npm audit` 并非无问题：在该仅开发依赖链中报告了与 CVE-2026-73231 相关的五个高危软件包条目。当前锁定的工具链中没有受支持的 Postman 兼容修复版本。生产依赖审计使用 `npm audit --omit=dev` 单独评估；不要将完整开发审计描述为无问题。
- 使用 Axios 适配器或自行填充响应的前端测试仅验证组件行为，不作为浏览器 Network 或视觉验收证据。实际浏览器证据及任何阻塞项单独记录在 `docs/acceptance-v0.1.md`。
- 验收证据记录准确命令和未解决的检查项。CRUD（增删改查）流程成功绝不能替代隔离、迁移、文件恢复、备份/恢复、覆盖率或浏览器检查失败项。
