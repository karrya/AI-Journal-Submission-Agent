# 模块 2 第一期：出版社与期刊身份识别设计

日期：2026-11-17

## 1. 目标

在现有出版社、平台和期刊 CRUD 基础上，实现本地数据驱动的出版社与期刊身份识别闭环：

- 搜索出版社和期刊候选。
- 使用名称、别名、ISSN、EISSN、官网域名和出版社关系进行匹配。
- 识别唯一匹配、多个候选和信息冲突。
- 由管理员确认身份，保存可审计的确认结果。
- 保留现有档案、API 和历史数据兼容性。

本期不访问外部网站，不调用 AI，不实现投稿入口发现、平台自动识别、指南抓取或合规检查。

## 2. 当前基础与约束

- `publishers` 已有规范名称、规范化名称、官网和备注。
- `journal_platforms` 已有平台代码、名称、描述和状态。
- `journals` 已有出版社、平台、名称、ISSN、EISSN、官网、投稿入口、作者指南、分类、文章类型、要求、来源、核验时间和状态。
- 当前读取角色为系统管理员、投稿操作员和审稿人；写操作仅系统管理员。
- 现有 CRUD、OpenAPI、前端三个 Tab 和测试必须继续工作。
- 档案属于全局基础数据，本期不引入作者或用户工作空间隔离。

## 3. 数据迁移

新增 Alembic 迁移，采用新增字段和新表，不重命名或删除现有字段。

### 3.1 publishers 新增字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `publisher_name_en` | `VARCHAR(255)` | 可空 |
| `primary_domain` | `VARCHAR(255)` | 可空，普通索引 |
| `country` | `VARCHAR(100)` | 可空 |
| `publisher_type` | `VARCHAR(50)` | 可空 |
| `parent_organization_id` | `CHAR(36)` | 可空，自引用 `publishers(id)`，`ON DELETE RESTRICT` |
| `status` | `VARCHAR(30)` | 非空，默认 `ACTIVE` |
| `source_url` | `VARCHAR(2048)` | 可空 |
| `verified_at` | `DATETIME(6)` | 可空 |

### 3.2 journals 新增字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `journal_name_en` | `VARCHAR(500)` | 可空 |
| `aims_scope` | `TEXT` | 可空 |
| `open_access_status` | `VARCHAR(50)` | 可空 |
| `identity_status` | `VARCHAR(30)` | 非空，默认 `UNVERIFIED`，普通索引 |
| `source_url` | `VARCHAR(2048)` | 可空 |
| `verified_at` | `DATETIME(6)` | 可空 |

现有 `status` 继续作为档案管理状态，不与身份状态混用。

### 3.3 publisher_aliases

- `id CHAR(36) PRIMARY KEY`。
- `publisher_id CHAR(36) NOT NULL`，外键到 `publishers(id)`，`ON DELETE RESTRICT`。
- `alias VARCHAR(500) NOT NULL`。
- `normalized_alias VARCHAR(500) NOT NULL`。
- `source_url VARCHAR(2048)` 可空。
- `verified_at DATETIME(6)` 可空。
- `created_at DATETIME(6) NOT NULL`。
- 唯一约束 `(publisher_id, normalized_alias)`，普通索引 `normalized_alias`。

### 3.4 journal_aliases

结构同出版社别名，但 `journal_id` 指向 `journals(id)`：

- 唯一约束 `(journal_id, normalized_alias)`。
- 普通索引 `normalized_alias`。

### 3.5 journal_identifiers

- `id CHAR(36) PRIMARY KEY`。
- `journal_id CHAR(36) NOT NULL`，外键到 `journals(id)`，`ON DELETE RESTRICT`。
- `identifier_type VARCHAR(30) NOT NULL`，仅允许 `ISSN`、`EISSN`。
- `identifier_value VARCHAR(50) NOT NULL`。
- `source_url VARCHAR(2048)` 可空。
- `verified_at DATETIME(6)` 可空。
- `created_at DATETIME(6) NOT NULL`。
- 唯一约束 `(identifier_type, identifier_value)`。
- 普通索引 `journal_id`。

迁移时将现有 `journals.issn`、`journals.eissn` 清洗后写入该表，保留原字段和值。发现异常历史值时停止迁移并报告，不静默丢弃。

### 3.6 discovery_tasks

复用技术文档的任务结构，本期即建立，供后续阶段继续使用：

- `id` UUID 主键。
- `task_type VARCHAR(50)`。
- `journal_id` 可空，外键到 `journals(id)`。
- `owner_author_id` 可空，预留下游隔离字段。
- `idempotency_key VARCHAR(128)`，与 `task_type` 组成唯一约束。
- `payload JSON`。
- `status VARCHAR(30)`。
- `progress TINYINT UNSIGNED`，限制 0–100。
- `attempt_count`、`max_attempts`。
- `checkpoint JSON` 可空。
- `last_error_code`、`last_error_message`。
- `created_by` 非空，外键到 `users(id)`。
- `created_at`、`started_at`、`completed_at`、`updated_at`。

本期识别在请求事务内同步完成，任务记录用于结果查询和幂等，不引入后台 Worker。

## 4. 识别规则

### 4.1 规范化

- 出版社和期刊名称使用现有显示名称规范化及比较规则。
- 域名只解析 HTTPS 或经批准的本地 HTTP URL，转小写并去除协议、末尾点、默认端口和末尾斜杠。
- ISSN 复用现有校验位逻辑；错误格式或校验位返回 422，不进入候选。
- 候选按确定性规则生成，不使用模糊匹配自动确认。

### 4.2 候选顺序

1. ISSN / EISSN 精确匹配。
2. 官网域名和出版社关系匹配。
3. 英文或中文规范名称精确匹配。
4. 别名匹配。

每个候选返回匹配原因、出版社、ISSN、官网和身份状态。多个候选不自动选择。

### 4.3 身份状态

- `UNVERIFIED`：尚未确认。
- `VERIFIED`：唯一精确匹配或管理员确认。
- `NEEDS_CONFIRMATION`：存在候选但需要人工选择。
- `CONFLICT`：同一标识关联多条记录或来源冲突。
- `INACTIVE`：档案不可用。
- `UNKNOWN`：没有候选或无法判断。

唯一 ISSN 精确匹配且其他身份字段不冲突时可自动 `VERIFIED`。其他匹配仅生成 `NEEDS_CONFIRMATION` 候选，确认前不得视为正式目标。

### 4.4 人工确认

- 仅系统管理员可确认。
- 请求必须包含当前候选的 `journal_id`、预期身份状态和 `expected_updated_at`，防止覆盖并发修改。
- 仅允许从 `UNVERIFIED`、`NEEDS_CONFIRMATION` 或 `CONFLICT` 确认到 `VERIFIED`。
- 如果记录已被修改，返回 409 并要求重新读取。
- 确认写入 `identity_status=VERIFIED`、`verified_at` 和安全审计摘要，不覆盖原始识别证据。
- 冲突记录必须先由管理员修正冲突数据，再确认。

### 4.5 新候选创建

- 已存在匹配期刊时复用现有记录，不重复创建。
- 没有匹配期刊时，只有能够确定出版社才能创建候选：精确匹配现有出版社，或根据非空 `publisher_name` 新建出版社档案。
- 未提供 `publisher_name` 且无法从现有记录确定出版社时返回 422，不创建出版社、期刊或任务。
- 新期刊候选使用 `identity_status=UNVERIFIED`、`platform_id=NULL`、手工输入的来源 URL 和空 `verified_at`。
- 新出版社使用默认管理状态、`verified_at=NULL`；名称识别本身不等于出版社已核验。
- 创建出版社、期刊、标识和任务必须在同一事务完成，任一步失败全部回滚。

## 5. API

所有路径使用 `/api/v1`，读取沿用现有角色，创建和确认仅系统管理员并要求 CSRF。静态 `/search` 路由必须注册在 `/{publisher_id}`、`/{journal_id}` 之前。

### `GET /publishers/search`

参数：`name`、`website_url`、`page`、`page_size`。返回出版社候选及匹配原因，不返回备注中的敏感内容。

### `GET /journals/search`

参数：`name`、`issn`、`eissn`、`publisher_id`、`website_url`、`page`、`page_size`。返回候选及匹配原因。

### `POST /journals/identify`

请求：

- `publisher_name` 可选；
- `journal_name` 必填；
- `issn`、`eissn` 可选；
- `website_url` 可选；
- `article_type` 可选；
- `idempotency_key` 可选，仅作客户端关联，服务端另算确定性键。

处理：

1. 在事务内计算输入规范化结果和幂等键。
2. 幂等键冲突时返回已有任务，不重复识别。
3. 生成候选；没有现有匹配时创建一条 `UNVERIFIED` 候选记录。
4. 保存任务、候选摘要和结果，状态为 `SUCCEEDED`。
5. 返回任务 ID、任务状态和候选列表。

### `GET /tasks/{task_id}`

返回任务类型、状态、进度、候选摘要和脱敏错误信息。仅允许有识别读取权限的角色访问；含作者数据的任务还需校验 `owner_author_id`。

### `POST /journals/{journal_id}/confirm-identity`

请求包含 `expected_updated_at` 和 `confirmation_note`（可选）。执行第 4.4 节检查后返回更新后的期刊。

### 现有响应扩展

出版社和期刊响应可以包含新增字段，但旧字段名称、类型和现有 CRUD 行为保持不变。识别响应与现有 CRUD 响应使用独立模型，避免候选字段影响旧客户端。

## 6. 服务与事务

- `PublisherIdentificationService`：出版社规范化、域名和候选匹配。
- `JournalIdentificationService`：标识、名称、别名、候选、确认和任务编排。
- `DiscoveryTaskService`：幂等任务查询和状态更新。
- Repository 负责查询和排序，Service 负责身份规则、授权、事务和审计。
- 创建候选、标识关联、任务和审计在同一事务提交。
- 唯一约束冲突统一转换为安全 409，非唯一数据库异常不得泄露 SQL 参数。

## 7. 前端

在现有“出版商、平台和期刊”页面增加“识别”Tab：

1. 输入出版社、期刊名称、ISSN、EISSN、官网和文章类型。
2. 显示任务状态和候选列表。
3. 每个候选展示匹配原因、出版社、ISSN、官网和身份状态。
4. 多候选必须手工选择后确认；不得默认选中第一项。
5. 冲突显示原因并引导编辑档案。
6. 确认后刷新期刊资料和候选状态，复用 1 秒成功提示。
7. 未确认候选不得显示为“已验证”。

## 8. 安全与审计

- 继续复用现有认证、CSRF 和角色校验。
- 只处理本地数据库和手工输入，不执行外部 URL 请求。
- URL 仅作数据保存和匹配，不视为已核验投稿入口。
- 任务输入及候选不包含作者私有稿件或账号信息。
- 创建候选、确认身份和冲突修改记录安全审计。
- 原始数据库错误不得泄露 SQL、输入 URL 凭据或其他敏感参数。

## 9. 测试与验收

- 出版社和期刊别名、域名和 ISSN 匹配。
- 正确 ISSN 候选与错误 ISSN 422。
- 唯一精确匹配、多个候选、无候选和冲突。
- 人工确认、非管理员拒绝、CSRF 和并发 `expected_updated_at` 冲突。
- 幂等识别不创建重复任务或候选。
- 现有数据迁移、标识唯一约束、外键和完整 CRUD 回归。
- 前端候选展示、人工选择、确认和错误状态。
- 使用独立 MySQL 8 测试数据库，验证 JSON、约束、事务和锁行为。

第一期验收完成后，系统能够创建、搜索、识别冲突并人工确认期刊身份，但仍不具备自动发现投稿入口或自动提交能力。
