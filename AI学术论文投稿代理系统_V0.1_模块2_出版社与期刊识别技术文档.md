# AI 学术论文投稿代理系统 V0.1
## 模块 2：出版社与期刊识别技术文档

| 项目 | 内容 |
|---|---|
| 文档版本 | V0.2（评审修订版） |
| 文档日期 | 2026-11-17 |
| 文档性质 | 目标技术方案、现状映射与分期实施依据 |
| 模块名称 | 出版社与期刊识别（Publisher & Journal Recognition） |
| 上游模块 | 模块 1：稿件与作者资料管理 |
| 直接下游模块 | 模块 3：投稿账号管理与授权；再下游依次为模块 4 自动化投稿执行、模块 5 投稿状态与进度跟踪 |
| 技术基线 | Vue 3、TypeScript、Element Plus、FastAPI、Pydantic、SQLAlchemy 2.0、MySQL 8 |
| 参考规格 | `AI学术论文投稿代理系统_V0.1_模块2_出版社与期刊识别设计规格.md` |
| V0.2 修订范围 | 正式表结构与隔离模型、网络层 SSRF、双维入口状态、AI 审核、合规规则注册表、适配器能力、幂等及业务验收 |

> 本文区分“已实现”“部分实现”和“规划中”。规划内容不得被理解为当前系统已经具备的能力，也不得直接用于真实期刊自动提交。

---

## 1. 模块定位与目标

### 1.1 模块定位

模块 2 是系统的**投稿目标识别、投稿入口发现、投稿规则提取和稿件合规性检查中心**。

它负责把用户选择的出版社、期刊及其官方资料转换为后续模块可以稳定消费的投稿配置档案，而不是仅提供一个期刊名称搜索页面。

### 1.2 核心目标

1. 识别并确认出版社和期刊身份，避免同名或相似名称导致错误投稿。
2. 使用 ISSN、EISSN、官网域名和出版社关系进行交叉核验。
3. 从期刊官网及作者指南发现并验证正式投稿入口。
4. 识别具体期刊实际使用的投稿系统，而不是按出版社统一推断。
5. 提取官方投稿要求，保存原始证据、解析器信息和审核状态。
6. 对投稿要求执行版本管理，保证历史检查仍能追溯当时使用的规则。
7. 使用模块 1 的稿件和作者资料执行可解释的合规性检查。
8. 输出标准化的 Journal Submission Profile，供投稿账号管理和自动化模块使用。

### 1.3 模块边界

模块 2 负责：

- 出版社和期刊候选发现与身份确认；
- 官网、作者指南和投稿入口定位；
- 投稿平台识别与识别结果核验；
- 投稿规则抓取、结构化、证据关联和版本管理；
- 稿件合规性检查、报告生成及人工复核。

模块 2 不负责：

- 创建作者的真实出版社账号；
- 保存或使用未经授权的登录凭据；
- 自动签署版权协议或学术伦理声明；
- 绕过 CAPTCHA、访问控制或其他安全机制；
- 未经明确授权和人工确认自动提交稿件；
- 判断论文的学术质量或保证录用；
- 将第三方数据库、搜索结果或 AI 推测当作期刊官方政策。

## 2. 当前实现基线与差距

### 2.1 已实现能力

当前系统已经具备出版社、平台和期刊的基础档案管理能力。

| 领域 | 当前实现 |
|---|---|
| 出版社档案 | `publishers` 表保存规范名称、规范化名称、官网、备注和审计字段 |
| 平台档案 | `journal_platforms` 表保存平台代码、名称、描述和状态 |
| 期刊档案 | `journals` 表保存出版社、平台、名称、ISSN、EISSN、官网、投稿入口、作者指南、学科分类、文章类型、投稿要求、来源、核验时间、状态和备注 |
| ISSN | 支持去连字符、转大写、长度校验和加权校验位验证 |
| 投稿要求 | 当前以 JSON 数组保存 `key`、`value`、`scope`、`source_url`、`verified_at` |
| URL 校验 | 仅允许 HTTPS 或经允许的本地 HTTP，并拒绝 URL 中的用户凭据 |
| 权限 | 系统管理员可写；系统管理员、投稿操作员和审稿人可读 |
| 审计 | 创建、更新和软删除写入操作审计，使用脱敏摘要 |
| 前端 | 出版商、平台、期刊三个 Tab，支持新增、编辑、查询、软删除、分页、排序和筛选 |
| 界面 | 中文表单、状态下拉框、错误提示及保存成功提示 |
| 验证 | 后端、前端、OpenAPI 和接口契约测试已覆盖基础档案功能 |

现有基础 API 已支持：

- `/publishers` 的分页、创建、详情、更新和软删除；
- `/journal-platforms` 的分页、创建、详情、更新和软删除；
- `/journals` 的分页、创建、详情、更新和软删除。

### 2.2 部分实现能力

| 能力 | 当前状态 | 与目标差距 |
|---|---|---|
| 期刊身份确认 | 可保存名称、ISSN、EISSN、官网和出版社关系 | 尚无候选识别、冲突检测、身份状态和人工选择流程 |
| 投稿入口 | 可手工保存 `submission_url` | 尚无官网发现、重定向验证、入口状态和验证证据 |
| 平台识别 | 可手工选择平台档案 | 尚无 URL、DOM、登录元素和作者指南联合识别 |
| 投稿规则 | 可保存结构化键值及来源、核验时间 | 尚无网页抓取、AI 提取、逐条证据、置信度和版本化规则 |
| 合规性检查 | 已有稿件、作者、文件和声明数据 | 尚无规则引擎、检查任务、结果报告和审核机制 |
| 数据共享 | 基础档案按角色共享读取 | 是否引入用户工作空间隔离尚需产品决策 |

### 2.3 尚未实现能力

以下均属于规划范围：

- 出版社别名、期刊别名及候选识别；
- 投稿入口自动发现和浏览器验证；
- Editorial Manager、ScholarOne 等平台识别适配器；
- 作者指南抓取、网页快照及 AI 规则提取；
- 规则证据、置信度、审核状态和不可变版本；
- 合规检查任务、检查结果、人工确认和 Journal Submission Profile；
- 正式投稿执行、CAPTCHA 处理和提交回执。

## 3. 目标总体架构

### 3.1 端到端流程

```text
用户输入出版社和期刊信息
        |
        v
出版社候选识别与匹配
        |
        v
期刊候选识别与身份确认
        |
        v
官网和作者指南定位
        |
        v
投稿入口发现与安全验证
        |
        v
投稿平台识别与人工复核（必要时）
        |
        v
官方投稿规则抓取
        |
        v
AI 结构化解析与 Pydantic 校验
        |
        v
证据保存、规则审核和版本确认
        |
        v
读取模块 1 的稿件和作者资料
        |
        v
确定性规则引擎执行合规检查
        |
        v
生成检查报告和 Journal Submission Profile
```

### 3.2 子模块职责

| 子模块 | 职责 | 关键输出 |
|---|---|---|
| 出版社识别 | 名称、别名、官网和机构关系匹配 | 出版社记录、候选及确认状态 |
| 期刊识别 | ISSN、名称、官网和出版社交叉核验 | 期刊记录、候选及身份状态 |
| 投稿入口发现 | 发现、访问和验证正式投稿链接 | 原始 URL、最终 URL、验证状态 |
| 投稿平台识别 | 综合 URL、DOM、标题、登录元素识别平台 | 平台代码、识别证据、置信度 |
| 投稿规则提取 | 抓取作者指南并结构化规则 | 规则、证据、解析版本和审核状态 |
| 合规性检查 | 将稿件资料与已确认规则匹配 | 检查任务、逐项结果和总体状态 |
| 投稿配置输出 | 汇总已确认的身份、入口和规则版本 | Journal Submission Profile |

### 3.3 设计原则

- **身份与执行分离：** 识别成功不代表已经具备该平台的完整自动投稿能力。
- **官方来源优先：** 第三方信息只用于候选发现。
- **规则与稿件分离：** 规则变更不会修改已经完成的检查报告。
- **AI 与确定性逻辑分离：** AI 负责提取，程序负责 Schema 校验和确定性计算，人工负责歧义及高影响规则确认。
- **证据不可变：** 指南版本、来源证据、检查报告和审计记录采用追加式保存。
- **权限复用：** 稿件和作者数据继续沿用模块 1 的授权过滤，不因进入识别任务而扩大访问范围。

### 3.4 模块依赖与职责链

```text
模块 1：稿件与作者资料管理
        |
        v
模块 2：出版社与期刊识别
        |  输出期刊身份、投稿入口、规则版本和合规报告
        v
模块 3：投稿账号管理与授权
        |  输出账号归属、作者授权和登录权限
        v
模块 4：自动化投稿执行
        |  执行表单填写、文件上传、人工审批和受控提交
        v
模块 5：投稿状态与进度跟踪
```

模块 2 只输出标准化的 Journal Submission Profile，不管理真实账号或浏览器执行逻辑。模块 3 根据作者账号和授权确定投稿身份，模块 4 在能力声明允许的范围内执行任务，模块 5 继续跟踪投稿后的状态。

## 4. 出版社与期刊识别设计

### 4.1 出版社识别

#### 输入

- 出版社名称；
- 可选英文名称；
- 可选官网；
- 可选期刊名称，用于交叉确认。

#### 目标字段

| 字段 | 说明 |
|---|---|
| `publisher_name` | 规范名称 |
| `publisher_name_en` | 英文名称，可为空 |
| `website` | 官方网站 |
| `primary_domain` | 规范化主要域名 |
| `country` | 国家或地区，可为空 |
| `publisher_type` | 出版社类型 |
| `parent_organization_id` | 上级机构，可为空 |
| `status` | 管理和识别状态 |
| `source_url` | 信息来源 |
| `verified_at` | 最近核验时间 |

出版社类型包括商业出版社、大学出版社、学术协会、独立出版机构、开放获取出版机构及其他。

#### 匹配规则

1. 名称仅用于候选发现，不能作为最终确认依据。
2. 优先通过官网、规范化域名及期刊关系确认。
3. 区分出版社、出版品牌、母机构和投稿平台。
4. 不因名称相似自动合并出版社。
5. 多候选或信息冲突时进入 `NEEDS_CONFIRMATION`，由用户选择或人工审核。

现有 `publishers.normalized_name` 可继续用于内部唯一性和名称匹配；别名、域名、类型及核验字段通过后续迁移补充。

### 4.2 期刊识别

#### 目标字段

| 字段 | 说明 |
|---|---|
| `journal_name` | 规范名称 |
| `journal_name_en` | 英文名称，可为空 |
| `publisher_id` | 所属出版社 |
| `issn` | 印刷版 ISSN，可为空 |
| `eissn` | 电子版 EISSN，可为空 |
| `journal_website` | 期刊官方网站 |
| `author_guidelines_url` | 作者指南地址 |
| `aims_scope` | 期刊范围和主题 |
| `open_access_status` | 开放获取状态 |
| `journal_status` | 身份状态 |
| `source_url` | 信息来源 |
| `verified_at` | 最近核验时间 |

#### 匹配顺序

1. ISSN / EISSN 规范化后精确匹配；
2. 官方页面和出版社关系匹配；
3. 英文规范名称精确匹配；
4. 别名和历史名称匹配；
5. 模糊匹配仅生成候选，不自动确认。

出现多个高相似候选时，必须展示名称、出版社、ISSN、官网及差异信息，由用户确认。未确认前不得执行可能绑定错误投稿目标的后续操作。

#### 身份状态

- `UNVERIFIED`：尚未核验；
- `VERIFIED`：已核验；
- `NEEDS_CONFIRMATION`：需要用户选择或人工确认；
- `CONFLICT`：来源信息冲突；
- `INACTIVE`：停刊或不可用；
- `UNKNOWN`：无法判断。

现有 `active`、`needs_review`、`disabled` 可继续作为档案管理状态；身份状态应独立保存，避免把“启用的期刊”误解为“身份已核验的期刊”。

### 4.3 ISSN 处理

当前实现已经提供去连字符、转大写、八位格式和加权校验位验证，应复用该逻辑。

目标流程：

1. 去除空格和连字符并转为大写；
2. 校验格式和校验位；
3. 分别保存 ISSN 与 EISSN；
4. 规范化值用于精确匹配和唯一性冲突检测；
5. 前端按 `XXXX-XXXX` 格式显示；
6. 同一标识关联其他期刊时标记 `CONFLICT`，不得静默合并。

后续迁移到 `journal_identifiers` 时，应保留现有 `journals.issn`、`journals.eissn` 的清洗结果及冲突处理记录。

## 5. 投稿入口与平台识别设计

### 5.1 投稿入口发现

#### 发现顺序

1. **期刊官网：** 查找 Submit Your Article、Submit Your Manuscript、Online Submission、Author Login 等链接。
2. **作者指南：** 从 Guide for Authors、Instructions for Authors、Submission Guidelines 中查找投稿入口和平台说明。
3. **浏览器验证：** 在隔离的 Playwright 环境中访问候选链接并记录页面结果。

#### 验证证据

- 原始 URL；
- 完整重定向链；
- 最终 URL 和最终域名；
- 页面标题；
- 是否可访问；
- 是否出现登录、注册或投稿相关元素；
- 验证时间和验证方式；
- 失败原因及必要的脱敏诊断信息。

#### 入口状态模型

入口状态拆分为两个独立维度，不能把“官方入口已验证”和“访问需要登录”当作互斥事实。

**入口验证状态（verification_status）：**

- `UNVERIFIED`：尚未完成官方身份及可达性验证；
- `VERIFIED`：已通过官方链接、页面内容和目标域名核验，确认属于目标期刊；
- `NEEDS_REVIEW`：证据冲突或不足，需要人工复核；
- `BROKEN`：链接失效或目标不可用；
- `UNKNOWN`：无法判断。

**访问状态（access_status）：**

- `PUBLIC_ACCESS`：无需登录即可访问；
- `LOGIN_REQUIRED`：页面有效，但继续操作需要登录；
- `ACCESS_RESTRICTED`：存在机构、地区、权限或其他访问限制；
- `BLOCKED`：被访问控制或安全机制阻止；
- `UNKNOWN`：无法判断。

例如，`verification_status=VERIFIED` 与 `access_status=LOGIN_REQUIRED` 可以同时成立：系统已经确认投稿入口属于期刊官方，但后续登录仍需模块 3 的授权账号和登录流程。`LOGIN_REQUIRED` 不得被解释为入口未验证，也不得被后续模块误解为已经获得登录授权。

现有 `journals.submission_url` 只能视为人工录入的候选入口。只有经过上述流程验证后，才能将入口状态标记为 `VERIFIED`。

### 5.2 投稿平台识别

#### 候选目录

V0.1 候选平台包括：

- `EDITORIAL_MANAGER`；
- `SCHOLARONE`；
- `SNAPP`；
- `WILEY_RESEARCH_EXCHANGE`；
- `IEEE_AUTHOR_PORTAL`；
- `ACS_PARAGON_PLUS`；
- `MDPI_SYSTEM`；
- `FRONTIERS_SYSTEM`；
- `OJS`；
- `CUSTOM`；
- `UNKNOWN`。

候选目录不代表已承诺支持这些平台的完整自动化投稿。

#### 识别依据

按证据强度综合判断：

1. 官方作者指南中的平台说明；
2. 官方链接及重定向关系；
3. URL 域名和路径特征；
4. 页面标题和品牌信息；
5. 页面 DOM 和登录表单特征。

不得仅凭出版社名称推断平台。一个出版社的不同期刊可以使用不同系统。

#### 平台字典、识别结果与适配器边界

三者职责必须分离：

- `journal_platforms` 是平台字典，保存平台代码、名称、描述和管理状态，不证明某期刊实际使用该平台。
- 平台识别结果属于具体期刊入口，保存识别代码、证据、置信度和审核状态。
- 适配器是代码实现，分别声明识别、入口验证、登录、填写、上传和提交能力。

建议统一识别接口，不再把登录执行方法放入识别接口：

```python
from abc import ABC, abstractmethod

class BaseSubmissionPlatform(ABC):
    @abstractmethod
    async def detect(self, url: str):
        """返回平台代码、识别证据和置信度。"""
        raise NotImplementedError

    @abstractmethod
    async def verify_portal(self, url: str):
        """返回投稿入口、验证状态和访问状态。"""
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> set[str]:
        """返回本适配器实际实现的能力代码。"""
        raise NotImplementedError
```

执行接口独立定义：

```python
class BasePortalExecutor(ABC):
    @abstractmethod
    async def get_login_url(self, portal_id: str) -> str:
        """在 LOGIN_SUPPORTED 能力下返回登录入口。"""
        raise NotImplementedError
```

每个适配器必须显式声明能力，不能用“平台识别成功”推断“自动投稿成功”：

| 能力代码 | 含义 |
|---|---|
| `DETECT_SUPPORTED` | 可以识别平台 |
| `PORTAL_VERIFY_SUPPORTED` | 可以验证投稿入口 |
| `LOGIN_SUPPORTED` | 已实现授权登录流程 |
| `FORM_FILL_SUPPORTED` | 已实现表单填写 |
| `FILE_UPLOAD_SUPPORTED` | 已实现文件上传 |
| `SUBMISSION_SUPPORTED` | 已实现提交及回执核验 |

能力状态同时存入适配器注册表并在前端展示。例如，某平台仅具备 `DETECT_SUPPORTED` 和 `PORTAL_VERIFY_SUPPORTED` 时，页面必须显示“可识别、可验证入口，暂不支持自动登录、填写和上传”，后续任务不得创建自动提交动作。

检测到 CAPTCHA 后，唯一允许的处理方式是暂停自动化任务并提示授权人员按平台允许的方式人工处理；不实现、不暗示自动绕过 CAPTCHA。

## 6. 投稿规则提取与版本管理

### 6.1 规则范围

| 类别 | 典型内容 |
|---|---|
| 文章类型 | Research Article、Review、Case Report 及期刊自定义类型 |
| 稿件格式 | 文件格式、模板、单双栏、字数、摘要、关键词、参考文献、图表 |
| 文件要求 | 主稿件、标题页、投稿信、图片、表格、补充材料、亮点、图文摘要、声明文件 |
| 作者与匿名 | 单双盲、独立标题页、身份信息删除、通讯作者和 ORCID |
| 推荐审稿人 | 人数、必填字段、机构邮箱、排除审稿人及原因 |
| Cover Letter | 是否必需、模板、创新性、期刊适配性及投稿声明 |
| 学术伦理 | 基金、利益冲突、作者贡献、伦理审批、知情同意、数据可用性、AI 使用声明 |
| 费用与开放获取 | APC、币种、其他收费、减免政策、适用条件和更新时间 |

文件要求统一支持 `REQUIRED`、`OPTIONAL`、`CONDITIONAL`、`NOT_REQUIRED` 和 `UNKNOWN`，不得把某期刊要求推广为所有期刊的统一要求。

### 6.2 提取流程

```text
隔离环境访问官方页面
        |
        v
HTML 清洗和正文抽取
        |
        v
保存页面标题、URL、抓取时间和内容哈希
        |
        v
AI 按限定 Schema 提取规则
        |
        v
Pydantic 类型和枚举校验
        |
        v
关联原始证据文本和快照
        |
        v
记录置信度及审核状态
        |
        v
生成待确认规则版本
```

AI 输出只能是候选数据。网页正文属于不可信输入，不能作为系统指令，不能触发工具调用、读取本地文件或访问作者账号。

### 6.3 规则结构示例

```json
{
  "rule_code": "ABSTRACT_WORD_LIMIT",
  "rule_category": "MANUSCRIPT_FORMAT",
  "article_type": "RESEARCH_ARTICLE",
  "rule_value": {
    "max_words": 250
  },
  "unit": "words",
  "is_required": true,
  "source_url": "https://example.com/author-guidelines",
  "source_text": "Abstract should not exceed 250 words.",
  "confidence": 0.98,
  "review_status": "PENDING"
}
```

以上仅为结构示例，不代表真实期刊政策。

### 6.4 证据定位要求

每条规则尽可能保存：

- 来源 URL、页面标题和原始证据文本；
- 段落标题、段落序号、页面区域及起止字符位置；
- 抓取时间、内容哈希和快照路径；
- 提取器或模型版本；
- 模型自报置信度和审核状态；
- 适用文章类型和条件；
- 生效及失效时间（仅在来源明确时填写）。

`requirement_sources` 中的 `section_heading`、`paragraph_index`、`evidence_start`、`evidence_end` 用于回到网页中的具体证据位置。证据位置以当次内容哈希和快照为准，页面后续变化不得改写历史定位。

无法确认的费用、限制或声明不得推测补全。

### 6.5 规则冲突处理

同一规则在期刊主页、作者指南和投稿系统中出现不同要求时：

1. 保存全部冲突来源，不覆盖、不静默选择。
2. 优先采用同一官方主体下、明确适用于当前文章类型且生效时间最新的正式政策。
3. 官方页面之间仍不一致，或与投稿系统要求不一致时，将规则标记为 `CONFLICT` 并进入人工审核。
4. 第三方数据库或搜索结果只能作为冲突线索，不能覆盖官方内容。
5. 冲突解决前，该规则不得用于生成确定性的 `FAIL`，只能产生 `WARNING` 或 `UNKNOWN`。

### 6.6 风险分级与人工审核

| 规则级别 | 示例 | 审核要求 |
|---|---|---|
| 普通规则 | 关键词数量、摘要字数 | AI 提取后通过 Schema 校验；根据准确率评估和抽样审核决定是否自动接受 |
| 重要规则 | 文件格式、匿名审稿要求 | 必须核对官方段落和页面位置后才能确认 |
| 高风险规则 | 伦理声明、版权协议、APC 费用 | 必须有明确官方来源，关键操作由授权人员人工确认 |

- 审核通过只锁定一个具体的指南版本，不修改历史版本。
- 人工修改规则值、来源或审核状态时，创建新的指南版本并记录修改前后值和审核人。
- 已锁定版本不得被后续抓取直接覆盖；新内容生成待审核版本。
- 未通过相应级别审核的规则不得用于确定性失败判断或正式提交。

### 6.7 置信度与真实准确率

`confidence: 0.98` 只是模型输出的自报字段，**不等于 98% 的真实准确率**。

上线前必须使用带人工标准答案的期刊样本集，按规则类别评估准确率、精确率、召回率和冲突率，并分别记录普通、重要和高风险规则表现。只有达到经评审确定的阈值后，才可调整自动接受策略；阈值和评估结果必须版本化保存。

### 6.8 版本策略

- 每次重新抓取或人工确认形成新的指南版本，不覆盖旧版本。
- URL 或内容哈希变化时创建待处理版本并生成新旧差异。
- 新提取的规则不得自动成为已确认规则。
- 历史合规检查继续引用当时的规则版本。
- 新规则确认后，后续检查默认使用最新确认版本。
- 页面快照、规则证据和检查报告采用追加式保存，普通业务更新不得修改历史内容。

## 7. 稿件合规性检查设计

### 7.1 输入

来自模块 1：

- 稿件 ID、不可变版本 ID；
- 文件 ID、类型、哈希及实际文件类型；
- 标题、摘要、关键词、文章类型；
- 作者顺序、通讯作者和必要资料；
- Cover Letter、推荐审稿人；
- 基金、伦理、贡献、利益冲突、数据可用性等声明。

来自模块 2：

- `journal_id`；
- 已确认的指南版本 ID；
- 文章类型、文件、格式、匿名、声明和推荐审稿人要求。

### 7.2 检查方式

| 检查项 | 方法 |
|---|---|
| 文章类型 | 检查目标类型是否被接受 |
| 摘要字数 | 确定性分词和上限比较 |
| 关键词数量 | 比较最小和最大数量 |
| 文件格式 | 校验 MIME、扩展名和文件签名 |
| Title Page | 检查所需文件是否存在 |
| 作者资料 | 检查必填字段和通讯作者信息 |
| 匿名要求 | 检测主稿件中的姓名、单位、邮箱及致谢身份信息 |
| Cover Letter | 检查文件和已确认的声明要求 |
| 推荐审稿人 | 检查人数、机构、邮箱及排除原因 |
| 声明材料 | 检查必需声明及对应内容是否存在 |
| 图表和补充材料 | 检查数量、格式和必要元数据 |

### 7.3 规则执行注册表

每类检查由独立、可测试的规则实现，注册表按 `rule_code` 查找执行器，禁止把所有判断集中在单个通用函数中：

```python
from abc import ABC, abstractmethod

class BaseComplianceRule(ABC):
    rule_code: str

    @abstractmethod
    def validate(self, manuscript, requirement):
        """返回实际值、期望值、证据、结果状态和解释。"""
        raise NotImplementedError
```

建议实现目录：

```text
rules/
├── abstract_word_count.py
├── keyword_count.py
├── file_format.py
├── file_size.py
├── author_information.py
├── anonymous_review.py
├── reviewer_requirements.py
└── ethics_declarations.py
```

注册表同时声明 `check_method`：

- `DETERMINISTIC`：程序可以确定的检查；
- `AI_ASSISTED`：需要 AI 辅助语义判断的检查；
- `MANUAL_REQUIRED`：必须由人工确认的检查。

AI 辅助结果只能提供候选证据，不能单独决定最终 `FAIL`。高风险声明、版权、伦理及存在歧义的匿名审稿结果必须进入人工确认。

### 7.4 字数统计与匿名检查语义

摘要和正文字数必须由规则明确统计口径：

- 是否包含标题、关键词和参考文献；
- 是否排除特殊符号、公式、图表文字和空格；
- 英文按单词、中文按字符、其他语言按何种分词器统计；
- 连字符、数字、缩写和 Unicode 文本如何处理；
- 使用哪个版本的文章类型和计数配置。

未指定口径时使用系统公开默认配置并标记假设，不能把不同期刊一律按英文单词数处理。

匿名审稿检查至少区分文件元数据、正文、致谢、引用信息和作者自引：

- 文件属性中的作者、公司和编辑者；
- 正文姓名、单位、邮箱、ORCID 和联系方式；
- 致谢中的身份线索；
- 引用中的作者自引是否违反期刊特定规则。

引用信息或正常学术自引不得一律判为匿名失败。AI 或规则只能标记疑似风险，最终 `FAIL` 需要明确规则或人工确认。

### 7.5 结果生成顺序

1. 执行 `DETERMINISTIC` 规则并保存实际值、期望值和证据。
2. 对 `AI_ASSISTED` 规则生成候选风险，不允许 AI 直接写入最终失败。
3. 对 `MANUAL_REQUIRED` 和歧义结果创建人工复核项。
4. 只有已确认规则、充分证据和确定性逻辑同时满足时才生成 `FAIL`。
5. 汇总时仍显示未执行和未知规则，不能以已知项目全部通过掩盖信息缺口。

### 7.6 状态规则

- `PASS`：证据和规则明确，检查通过；
- `FAIL`：证据和规则明确，检查未通过；
- `WARNING`：存在风险，需要人工注意；
- `UNKNOWN`：规则、证据或输入不足，无法判断；
- `SKIPPED`：不适用或未执行。

只有已确认规则、充分证据和确定性检查逻辑同时满足时，才能产生 `FAIL`。AI 推测、来源不明或歧义规则只能产生 `WARNING` 或 `UNKNOWN`，不得将 `UNKNOWN` 显示为 `PASS`。

### 7.7 报告内容

- 期刊身份和出版社；
- 稿件及不可变版本；
- 使用的规则版本；
- 检查时间；
- 各状态数量；
- 每项实际值、期望值、来源证据和解释；
- 需要用户处理的问题；
- 人工确认记录。

报告只表示对已提取规则的匹配情况，不代表期刊一定接收稿件，也不替代编辑部判断。

## 8. 数据模型、分层隔离与正式表结构

### 8.1 现有表保留与扩展

| 当前表 | 目标用途 | 后续处理 |
|---|---|---|
| `publishers` | 出版社基本档案 | 保留现有记录，补充域名、类型、别名、来源和核验信息 |
| `journal_platforms` | 平台字典 | 可继续作为逻辑平台目录；识别结果和适配器配置另行保存 |
| `journals` | 期刊基本档案 | 保留现有记录，规范官网、入口、指南和身份状态 |

现有 `journals.requirements` JSON 可继续用于简单手工要求，但不能替代版本化规则和逐条证据。迁移时应读取 JSON 并建立初始指南版本，而不是直接删除该字段中的历史信息。

### 8.2 目标新增逻辑表

| 表名 | 用途 |
|---|---|
| `publisher_aliases` | 出版社名称别名及来源 |
| `journal_identifiers` | ISSN、EISSN 等规范标识 |
| `journal_aliases` | 期刊别名和历史名称 |
| `journal_submission_portals` | 投稿入口、跳转链和验证状态 |
| `journal_guidelines` | 不可变作者指南版本 |
| `journal_requirements` | 结构化规则及审核状态 |
| `requirement_sources` | 逐条规则证据 |
| `journal_article_types` | 期刊支持的文章类型及适用条件 |
| `compliance_tasks` | 合规检查任务和总体状态 |
| `compliance_results` | 逐项检查结果和证据 |
| `discovery_tasks` | 识别、抓取和提取后台任务 |
| `journal_discovery_logs` | 识别和发现过程记录 |

规格中的 `submission_platforms` 是逻辑平台目录名称。实施时可沿用现有 `journal_platforms`，不必为了命名一致而破坏性改表。

### 8.3 数据约束总约定

- 所有主键均为 `CHAR(36)` UUID；关联外键均为相同类型。
- 所有表使用 InnoDB、utf8mb4，并沿用当前数据库 collation，不为新模块单独变更字符集规则。
- 时间使用 `DATETIME(6)`，统一保存不带本地偏移的 UTC；API 按现有约定输出 UTC。
- `created_at`、`updated_at` 默认 `CURRENT_TIMESTAMP(6)`，`updated_at` 同时 `ON UPDATE CURRENT_TIMESTAMP(6)`。
- `created_by`、`reviewed_by` 使用 `CHAR(36)` 并关联 `users(id)`，删除策略为 `RESTRICT`。
- 业务外键默认 `ON DELETE RESTRICT`；出版社和期刊使用软删除或状态变更。
- 指南版本、来源、检查报告及审计记录只允许追加，禁止普通 UPDATE/DELETE。
- JSON 字段使用 MySQL 原生 JSON；布尔字段使用 `BOOLEAN`（MySQL 映射为 `TINYINT(1)`）。
- 不对 2048 字符 URL 建立整列唯一索引；需要查重时使用 `url_hash` 或受控前缀索引。
- 下表中的索引名称均为建议名称，正式 Alembic 迁移必须保持模型与数据库一致性测试。

### 8.4 MySQL 分层隔离方案 B

本模块采用“**全局公共基础数据 + 按作者授权隔离的私有业务数据**”。当前系统没有独立 workspace 表，因此逻辑工作空间由 `owner_author_id` 和现有 `author_authorizations` 授权关系确定，不额外虚构 workspace ID。

| 数据类别 | 共享与访问规则 |
|---|---|
| 出版社、平台字典、期刊、别名和标识 | 全局基础数据；系统管理员、投稿操作员、审稿人可读，当前仅系统管理员可写 |
| 已核验投稿入口、指南、公共规则及来源 | 全局共享，可供后续投稿复用；必须经过对应审核级别确认后才进入公共使用 |
| 未确认候选、AI 原始提取结果和冲突内容 | 不作为公共确定规则；仅系统管理员及获独立授权的审核人员可处理 |
| 规则审核和人工修改记录 | 记录审核人、修改前后值和时间，仅系统管理员和审计员查看；审核通过后生成新的全局版本 |
| 稿件、作者资料和文件 | 继续按现有作者授权及稿件读取权限隔离，不因合规任务而扩大权限 |
| 合规任务和报告 | 必须保存 `owner_author_id` 和 `created_by`；仅授权用户可读，系统管理员按现有全局管理员权限处理 |
| 识别任务详情 | 按任务类型限制：公共识别任务仅管理员和审核人员可见；涉及稿件的任务同时校验 `owner_author_id` 授权 |

合规报告的读取必须在服务层执行与稿件读取一致的权限检查，不能仅凭报告 ID 或前端隐藏控制访问。人工修改公共规则虽然会产生全局生效版本，但其审核记录不得向普通用户开放。

### 8.5 `publisher_aliases`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | UUID |
| `publisher_id` | `CHAR(36)` NOT NULL FK → `publishers(id)` RESTRICT | 所属出版社 |
| `alias` | `VARCHAR(500)` NOT NULL | 原始别名 |
| `normalized_alias` | `VARCHAR(500)` NOT NULL | 规范化别名 |
| `source_url` | `VARCHAR(2048)` NULL | 别名来源 |
| `verified_at` | `DATETIME(6)` NULL | 核验时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

约束与索引：`UNIQUE KEY uq_publisher_alias (publisher_id, normalized_alias)`；`INDEX ix_publisher_alias_normalized (normalized_alias)`。

### 8.6 `journal_identifiers` 与 `journal_aliases`

`journal_identifiers` 字段：

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | UUID |
| `journal_id` | `CHAR(36)` NOT NULL FK → `journals(id)` RESTRICT | 所属期刊 |
| `identifier_type` | `VARCHAR(30)` NOT NULL | `ISSN`、`EISSN` 等 |
| `identifier_value` | `VARCHAR(50)` NOT NULL | 规范化标识值 |
| `source_url` | `VARCHAR(2048)` NULL | 标识来源 |
| `verified_at` | `DATETIME(6)` NULL | 核验时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

约束与索引：`UNIQUE KEY uq_journal_identifier (identifier_type, identifier_value)`；`INDEX ix_journal_identifiers_journal (journal_id)`。同一标识关联其他期刊时必须记录冲突，不得直接覆盖。

`journal_aliases` 使用与出版社别名相同的结构：`id`、`journal_id`、`alias`、`normalized_alias`、`source_url`、`verified_at`、`created_at`。`journal_id` 外键指向 `journals(id)`；`UNIQUE KEY uq_journal_alias (journal_id, normalized_alias)`；`INDEX ix_journal_alias_normalized (normalized_alias)`。

### 8.7 `journal_submission_portals`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | UUID |
| `journal_id` | `CHAR(36)` NOT NULL FK → `journals(id)` RESTRICT | 所属期刊 |
| `platform_id` | `CHAR(36)` NULL FK → `journal_platforms(id)` RESTRICT | 识别后的平台，可未确认 |
| `original_url` | `VARCHAR(2048)` NOT NULL | 原始入口 |
| `final_url` | `VARCHAR(2048)` NULL | 最终入口 |
| `url_hash` | `CHAR(64)` NOT NULL | 原始 URL 的 SHA-256，用于查重 |
| `redirect_chain` | `JSON` NOT NULL | 有序跳转记录，含 URL、状态码、目标 IP 和校验结果 |
| `final_domain` | `VARCHAR(255)` NULL | 最终域名 |
| `verification_status` | `VARCHAR(30)` NOT NULL DEFAULT `UNVERIFIED` | 官方入口验证状态 |
| `access_status` | `VARCHAR(30)` NOT NULL DEFAULT `UNKNOWN` | 页面访问状态 |
| `page_title` | `VARCHAR(500)` NULL | 页面标题 |
| `verification_method` | `VARCHAR(50)` NULL | 验证方式 |
| `verified_at` | `DATETIME(6)` NULL | 最近核验时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |
| `updated_at` | `DATETIME(6)` NOT NULL | 更新时间 |
| `created_by` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 创建人 |

约束与索引：`UNIQUE KEY uq_portal_journal_url (journal_id, url_hash)`；`INDEX ix_portals_journal (journal_id)`；`INDEX ix_portals_platform (platform_id)`；`INDEX ix_portals_verification (verification_status, access_status)`。

### 8.8 `journal_guidelines`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 指南版本 ID |
| `journal_id` | `CHAR(36)` NOT NULL FK → `journals(id)` RESTRICT | 所属期刊 |
| `version_no` | `INT UNSIGNED` NOT NULL | 从 1 开始递增的版本号 |
| `source_url` | `VARCHAR(2048)` NOT NULL | 官方指南 URL |
| `page_title` | `VARCHAR(500)` NULL | 页面标题 |
| `content_hash` | `CHAR(64)` NOT NULL | 规范化正文 SHA-256 |
| `snapshot_path` | `VARCHAR(1000)` NULL | 受控相对快照路径 |
| `extractor_version` | `VARCHAR(100)` NOT NULL | 提取器或模型版本 |
| `review_status` | `VARCHAR(30)` NOT NULL DEFAULT `PENDING` | 审核状态 |
| `reviewed_by` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 审核人 |
| `reviewed_at` | `DATETIME(6)` NULL | 审核时间 |
| `fetched_at` | `DATETIME(6)` NOT NULL | 抓取时间 |
| `effective_from` | `DATETIME(6)` NULL | 生效时间 |
| `effective_until` | `DATETIME(6)` NULL | 失效时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |
| `created_by` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 创建人 |

约束与索引：`UNIQUE KEY uq_guideline_version (journal_id, version_no)`；`UNIQUE KEY uq_guideline_hash (journal_id, content_hash)`；`INDEX ix_guidelines_review (journal_id, review_status)`。

### 8.9 `journal_requirements`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 规则 ID |
| `journal_id` | `CHAR(36)` NOT NULL FK → `journals(id)` RESTRICT | 所属期刊 |
| `guideline_id` | `CHAR(36)` NOT NULL FK → `journal_guidelines(id)` RESTRICT | 所属指南版本 |
| `rule_code` | `VARCHAR(100)` NOT NULL | 规则代码 |
| `rule_category` | `VARCHAR(100)` NOT NULL | 规则类别 |
| `article_type` | `VARCHAR(100)` NOT NULL DEFAULT `__ALL__` | 适用文章类型，`__ALL__` 表示默认适用，避免 NULL 导致唯一约束失效 |
| `condition_json` | `JSON` NULL | 适用条件 |
| `condition_hash` | `CHAR(64)` NOT NULL | 规范化条件的 SHA-256，用于区分同代码不同条件 |
| `value_json` | `JSON` NOT NULL | 结构化规则值 |
| `unit` | `VARCHAR(32)` NULL | 单位 |
| `is_required` | `BOOLEAN` NULL | 是否必需，未知时为空 |
| `risk_level` | `VARCHAR(20)` NOT NULL DEFAULT `NORMAL` | `NORMAL`、`IMPORTANT`、`HIGH` |
| `confidence` | `DECIMAL(5,4)` NULL | 模型自报置信度，范围 0–1，不代表真实准确率 |
| `review_status` | `VARCHAR(30)` NOT NULL DEFAULT `PENDING` | 审核状态 |
| `reviewed_by` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 审核人 |
| `reviewed_at` | `DATETIME(6)` NULL | 审核时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |
| `updated_at` | `DATETIME(6)` NOT NULL | 更新时间 |
| `created_by` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 创建人 |

约束与索引：`UNIQUE KEY uq_requirement_version_rule (guideline_id, rule_code, article_type, condition_hash)`；`INDEX ix_requirements_journal (journal_id)`；`INDEX ix_requirements_guideline (guideline_id)`；`INDEX ix_requirements_code (rule_code)`；`CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))`。

### 8.10 `requirement_sources`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 证据 ID |
| `requirement_id` | `CHAR(36)` NOT NULL FK → `journal_requirements(id)` RESTRICT | 对应规则 |
| `source_url` | `VARCHAR(2048)` NOT NULL | 来源 URL |
| `page_title` | `VARCHAR(500)` NULL | 页面标题 |
| `section_heading` | `VARCHAR(500)` NULL | 段落或章节标题 |
| `paragraph_index` | `INT UNSIGNED` NULL | 页面内段落序号 |
| `evidence_start` | `INT UNSIGNED` NULL | 证据在规范化正文中的起始字符位置 |
| `evidence_end` | `INT UNSIGNED` NULL | 证据结束字符位置 |
| `source_text` | `TEXT` NOT NULL | 原始证据文本 |
| `snapshot_path` | `VARCHAR(1000)` NULL | 网页快照受控相对路径 |
| `content_hash` | `CHAR(64)` NOT NULL | 快照或正文内容哈希 |
| `fetched_at` | `DATETIME(6)` NOT NULL | 抓取时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

约束与索引：`INDEX ix_sources_requirement (requirement_id)`；`INDEX ix_sources_fetched (fetched_at)`；`CHECK (evidence_end IS NULL OR evidence_start IS NULL OR evidence_end >= evidence_start)`。

### 8.11 `journal_article_types`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | UUID |
| `guideline_id` | `CHAR(36)` NOT NULL FK → `journal_guidelines(id)` RESTRICT | 所属指南版本 |
| `original_name` | `VARCHAR(255)` NOT NULL | 原始文章类型名称 |
| `normalized_code` | `VARCHAR(100)` NOT NULL | 规范代码 |
| `is_accepted` | `BOOLEAN` NOT NULL DEFAULT TRUE | 是否接受 |
| `condition_json` | `JSON` NULL | 适用条件 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

约束与索引：`UNIQUE KEY uq_article_type_version (guideline_id, normalized_code)`。

### 8.12 `compliance_tasks`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 合规任务 ID |
| `journal_id` | `CHAR(36)` NOT NULL FK → `journals(id)` RESTRICT | 目标期刊 |
| `manuscript_id` | `CHAR(36)` NOT NULL FK → `manuscripts(id)` RESTRICT | 稿件 |
| `manuscript_version_id` | `CHAR(36)` NOT NULL FK → `manuscript_versions(id)` RESTRICT | 不可变稿件版本 |
| `guideline_id` | `CHAR(36)` NOT NULL FK → `journal_guidelines(id)` RESTRICT | 使用的指南版本 |
| `owner_author_id` | `CHAR(36)` NOT NULL FK → `authors(id)` RESTRICT | 授权隔离所属作者 |
| `created_by` | `CHAR(36)` NOT NULL FK → `users(id)` RESTRICT | 发起用户 ID |
| `task_status` | `VARCHAR(30)` NOT NULL DEFAULT `PENDING` | 任务状态 |
| `overall_status` | `VARCHAR(30)` NULL | 总体合规状态 |
| `idempotency_key` | `VARCHAR(128)` NOT NULL | 稿件版本、指南版本及文章类型的确定性幂等键 |
| `started_at` | `DATETIME(6)` NULL | 开始时间 |
| `completed_at` | `DATETIME(6)` NULL | 完成时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

约束与索引：`UNIQUE KEY uq_compliance_idempotency (owner_author_id, idempotency_key)`；`INDEX ix_compliance_owner (owner_author_id, created_at)`；`INDEX ix_compliance_manuscript (manuscript_version_id)`；`INDEX ix_compliance_guideline (guideline_id)`；`INDEX ix_compliance_status (task_status)`。

读取时必须同时验证 `owner_author_id` 的当前授权及稿件版本归属，不能只凭任务 ID 查询。

### 8.13 `compliance_results`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 结果 ID |
| `task_id` | `CHAR(36)` NOT NULL FK → `compliance_tasks(id)` RESTRICT | 所属任务 |
| `requirement_id` | `CHAR(36)` NULL FK → `journal_requirements(id)` RESTRICT | 对应规则，自定义检查可为空 |
| `rule_code` | `VARCHAR(100)` NOT NULL | 检查项代码 |
| `result_key` | `VARCHAR(160)` NOT NULL | 规则代码与条件形成的稳定结果键 |
| `review_round` | `INT UNSIGNED` NOT NULL DEFAULT 1 | 结果或复核轮次，用于追加历史 |
| `check_method` | `VARCHAR(30)` NOT NULL | `DETERMINISTIC`、`AI_ASSISTED`、`MANUAL_REQUIRED` |
| `result_status` | `VARCHAR(30)` NOT NULL | `PASS`、`FAIL`、`WARNING`、`UNKNOWN`、`SKIPPED` |
| `actual_value` | `JSON` NULL | 实际值 |
| `expected_value` | `JSON` NULL | 期望值 |
| `evidence` | `JSON` NULL | 证据及位置 |
| `explanation` | `TEXT` NULL | 结果解释 |
| `reviewed_by` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 人工复核人 |
| `reviewed_at` | `DATETIME(6)` NULL | 人工复核时间 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

约束与索引：`UNIQUE KEY uq_compliance_result_key (task_id, result_key, review_round)`；`INDEX ix_results_task_status (task_id, result_status)`；`INDEX ix_results_requirement (requirement_id)`。结果和证据只允许追加，人工复核通过递增 `review_round` 写入新结果，不覆盖原始判断。

### 8.14 `discovery_tasks`

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 后台任务 ID |
| `task_type` | `VARCHAR(50)` NOT NULL | 识别、入口发现、指南提取等 |
| `journal_id` | `CHAR(36)` NULL FK → `journals(id)` RESTRICT | 相关期刊，可空 |
| `owner_author_id` | `CHAR(36)` NULL FK → `authors(id)` RESTRICT | 涉及作者数据时的隔离字段 |
| `idempotency_key` | `VARCHAR(128)` NOT NULL | 任务类型、目标和输入参数的确定性幂等键 |
| `payload` | `JSON` NOT NULL | 脱敏任务输入 |
| `status` | `VARCHAR(30)` NOT NULL DEFAULT `PENDING` | 任务状态 |
| `progress` | `TINYINT UNSIGNED` NOT NULL DEFAULT 0 | 进度 0–100 |
| `attempt_count` | `INT UNSIGNED` NOT NULL DEFAULT 0 | 已尝试次数 |
| `max_attempts` | `INT UNSIGNED` NOT NULL DEFAULT 3 | 最大尝试次数 |
| `checkpoint` | `JSON` NULL | 最后安全检查点 |
| `last_error_code` | `VARCHAR(64)` NULL | 脱敏错误代码 |
| `last_error_message` | `TEXT` NULL | 脱敏错误说明 |
| `created_by` | `CHAR(36)` NOT NULL FK → `users(id)` RESTRICT | 发起用户 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |
| `started_at` | `DATETIME(6)` NULL | 开始时间 |
| `completed_at` | `DATETIME(6)` NULL | 完成时间 |
| `updated_at` | `DATETIME(6)` NOT NULL | 更新时间 |

约束与索引：`UNIQUE KEY uq_discovery_task_idempotency (task_type, idempotency_key)`；`INDEX ix_discovery_status_updated (status, updated_at)`；`INDEX ix_discovery_owner (owner_author_id, created_at)`；`CHECK (progress BETWEEN 0 AND 100)`。

同一幂等键的并发创建由数据库唯一约束决定：只有一条任务能插入成功，其他请求读取现有任务，不得重复执行。

### 8.15 `journal_discovery_logs` 与审计

`journal_discovery_logs` 保存追加式识别过程记录：

| 字段 | 类型与约束 | 说明 |
|---|---|---|
| `id` | `CHAR(36)` PK | 日志 ID |
| `task_id` | `CHAR(36)` NULL FK → `discovery_tasks(id)` RESTRICT | 相关任务 |
| `journal_id` | `CHAR(36)` NULL FK → `journals(id)` RESTRICT | 相关期刊 |
| `actor_user_id` | `CHAR(36)` NULL FK → `users(id)` RESTRICT | 操作者，系统任务可为空 |
| `event_type` | `VARCHAR(50)` NOT NULL | 事件类型 |
| `message` | `TEXT` NOT NULL | 脱敏说明 |
| `details` | `JSON` NULL | 脱敏上下文 |
| `created_at` | `DATETIME(6)` NOT NULL | 创建时间 |

索引：`INDEX ix_discovery_logs_task (task_id, created_at)`；`INDEX ix_discovery_logs_journal (journal_id, created_at)`。

业务操作继续使用现有 `operation_logs`，不重复建立一套互相不一致的审计表。普通审计仅保存允许的摘要，禁止记录密码、验证码、令牌、完整邮箱正文和敏感路径。

## 9. 后端服务与 API 设计

### 9.1 服务划分

| 服务 | 职责 |
|---|---|
| `publisher_service` | 出版社规范化、候选匹配和冲突处理 |
| `journal_identification_service` | 期刊候选、身份确认和别名管理 |
| `portal_discovery_service` | 投稿入口发现、重定向和验证 |
| `platform_detection_service` | 平台特征识别和适配器选择 |
| `guideline_crawler_service` | 官方指南访问、清洗和快照 |
| `requirement_extraction_service` | AI 提取、Schema 校验和证据关联 |
| `compliance_service` | 规则执行、任务及结果保存 |
| `submission_profile_service` | 汇总标准投稿配置档案 |

建议目录：

```text
backend/app/
├── api/v1/
│   ├── publishers.py
│   ├── journals.py
│   ├── submission_portals.py
│   ├── guidelines.py
│   └── compliance.py
├── services/
│   ├── publisher_service.py
│   ├── journal_identification_service.py
│   ├── portal_discovery_service.py
│   ├── platform_detection_service.py
│   ├── guideline_crawler_service.py
│   ├── requirement_extraction_service.py
│   ├── compliance_service.py
│   └── submission_profile_service.py
├── crawlers/
│   ├── browser.py
│   ├── html_parser.py
│   └── url_security.py
├── submission_platforms/
│   ├── base.py
│   ├── editorial_manager.py
│   ├── scholarone.py
│   └── ojs.py
├── rules/
│   ├── rule_registry.py
│   ├── rule_engine.py
│   └── validators.py
└── tasks/
    ├── discovery_tasks.py
    └── guideline_tasks.py
```

### 9.2 现有 API 与目标 API

| API | 方法 | 当前状态 | 功能 |
|---|---|---|---|
| `/publishers` | POST | 已实现 | 新增出版社 |
| `/publishers/{id}` | GET/PATCH/DELETE | 已实现 | 出版社详情、更新和软删除 |
| `/journal-platforms` | POST | 已实现 | 新增平台档案 |
| `/journals` | GET/POST | 已实现 | 期刊列表和创建 |
| `/journals/{id}` | GET/PATCH/DELETE | 已实现 | 期刊详情、更新和软删除 |
| `/publishers/search` | GET | 规划中 | 搜索出版社候选 |
| `/journals/search` | GET | 规划中 | 搜索期刊候选 |
| `/journals/identify` | POST | 规划中 | 创建期刊识别任务 |
| `/journals/{id}/discover-portal` | POST | 规划中 | 发现并验证投稿入口 |
| `/journals/{id}/detect-platform` | POST | 规划中 | 识别投稿平台 |
| `/journals/{id}/extract-guidelines` | POST | 规划中 | 提取投稿规则 |
| `/journals/{id}/requirements` | GET | 规划中 | 获取指定版本规则 |
| `/compliance/check` | POST | 规划中 | 创建合规检查任务 |
| `/compliance/{id}` | GET | 规划中 | 获取检查报告 |
| `/compliance/{id}/confirm` | POST | 规划中 | 人工确认检查结果 |
| `/tasks/{id}` | GET | 规划中 | 查询后台任务状态 |

新增长耗时操作统一返回任务 ID，前端通过轮询或后续 SSE 获取进度。

### 9.3 识别任务状态

- `PENDING`；
- `PROCESSING`；
- `SUCCEEDED`；
- `FAILED`；
- `CANCELLED`。

V0.1 优先使用数据库任务表和轮询，避免为了简单任务过早引入独立消息队列。任务失败必须记录可重试性、脱敏错误和最后检查点。

### 9.4 接口 Pydantic 模型

规划接口必须分别定义请求和响应模型，禁止在路由中使用无结构的 `dict` 传递业务数据。

```python
from uuid import UUID
from pydantic import Field

from app.schemas.common import InputModel, OutputModel


class JournalIdentifyRequest(InputModel):
    publisher_name: str | None = Field(default=None, max_length=255)
    journal_name: str = Field(min_length=1, max_length=500)
    issn: str | None = Field(default=None, max_length=9)
    eissn: str | None = Field(default=None, max_length=9)
    article_type: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class JournalCandidate(OutputModel):
    journal_id: UUID | None
    journal_name: str
    publisher_name: str | None
    issn: str | None
    website: str | None
    identity_status: str
    conflict_reason: str | None


class JournalIdentifyResponse(OutputModel):
    task_id: UUID
    status: str
    candidates: list[JournalCandidate]


class PortalActionRequest(InputModel):
    candidate_url: str | None = Field(default=None, max_length=2048)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class GuidelineExtractionRequest(InputModel):
    source_url: str | None = Field(default=None, max_length=2048)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class ComplianceCheckRequest(InputModel):
    manuscript_version_id: UUID
    journal_id: UUID
    guideline_id: UUID
    article_type: str = Field(min_length=1, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class ComplianceConfirmRequest(InputModel):
    confirmed: bool
    reason: str | None = Field(default=None, max_length=2000)


class TaskResponse(OutputModel):
    task_id: UUID
    task_type: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str | None
```

- `JournalIdentifyResponse` 在存在多个候选时返回 `NEEDS_CONFIRMATION`，不得自动提交唯一候选。
- `PortalActionRequest` 同时用于投稿入口发现和平台识别，响应统一使用 `TaskResponse`。
- `ComplianceCheckRequest` 在服务端重新校验稿件版本归属、指南版本归属和作者授权，不信任客户端传入的关系。
- 各响应只返回公开或已授权字段，错误响应继续使用现有 `{code, message, request_id, details}` 结构。
- `idempotency_key` 由服务端根据目标和输入生成确定性哈希，客户端键仅作为请求去重辅助，不能由客户端任意指定全局唯一键。

## 10. 前端页面与交互

### 10.1 页面结构

在现有“出版商、平台和期刊”基础上，增加识别与合规工作台：

1. 期刊识别工作台；
2. 出版社和期刊资料库；
3. 投稿入口管理；
4. 投稿规则管理；
5. 合规性检查报告；
6. 识别任务和历史记录。

### 10.2 识别工作台

输入出版社名称、期刊名称、ISSN、EISSN 和目标文章类型，支持：

- 开始识别；
- 查看候选及差异；
- 确认期刊；
- 发现投稿入口；
- 提取投稿规则；
- 执行合规检查。

### 10.3 期刊详情 Tab

| Tab | 内容 |
|---|---|
| 基本信息 | 出版社、名称、ISSN、官网和身份状态 |
| 投稿入口 | 原始 URL、最终 URL、平台、验证状态和核验时间 |
| 投稿要求 | 文章类型、格式、摘要、关键词和文件要求 |
| 规则证据 | 来源文本、页面、快照、置信度和审核状态 |
| 合规检查 | PASS、FAIL、WARNING、UNKNOWN、SKIPPED |
| 历史记录 | 规则版本、差异、抓取和审核历史 |

### 10.4 交互约束

- 多候选必须允许用户选择，不得默认选中第一个候选；
- 未确认规则和身份状态应明显标识；
- 每条规则均可查看来源证据；
- 规则变化展示新旧版本差异；
- 报告可定位到稿件版本和规则版本；
- `UNKNOWN` 不得自动显示为 `PASS`；
- 长耗时任务显示阶段、进度、失败原因和安全重试入口。

## 11. Journal Submission Profile 标准输出

### 11.1 目的

模块 2 的输出不应只有 `journal_id`，而应包含后续模块需要的期刊身份、入口、平台、规则版本和检查状态。

### 11.2 示例

```json
{
  "journal_id": "uuid",
  "publisher_id": "uuid",
  "journal_name": "Journal Example",
  "identity_status": "VERIFIED",
  "submission_portal": {
    "platform_code": "EDITORIAL_MANAGER",
    "original_url": "https://example.com/submit",
    "final_url": "https://example.com/login",
    "verification_status": "VERIFIED",
    "access_status": "LOGIN_REQUIRED",
    "verified_at": "2026-11-17T00:00:00Z"
  },
  "guidelines_version_id": "uuid",
  "article_type": "RESEARCH_ARTICLE",
  "file_requirements": [],
  "author_requirements": [],
  "reviewer_requirements": [],
  "declaration_requirements": [],
  "compliance_status": "READY_FOR_REVIEW"
}
```

以上为接口结构示例，不代表真实期刊数据或当前已经实现的接口。

### 11.3 输出约束

- 必须关联唯一的 `journal_id`；
- 必须记录指南版本；
- 投稿入口必须包含状态和核验时间；
- 规则必须包含来源和审核状态；
- 不得将未确认规则包装成确定要求；
- 后续模块必须能追溯原始证据；
- 不包含任何账号密码、Cookie、会话文件或作者敏感凭据。

## 12. 安全、授权与审计

### 12.1 网页抓取安全

必须防范 SSRF、恶意重定向、恶意脚本、超大页面、非法下载、DNS rebinding 和 Prompt Injection。防护由**应用校验、连接层控制和网络出口控制**共同组成，不能只依赖 Python 中的 URL 字符串检查。

#### 应用层校验
1. 仅允许 HTTP/HTTPS；生产环境默认仅允许 HTTPS。
2. 同时校验 IPv4、IPv6 及 IPv4 映射的 IPv6 地址，拒绝私有、环回、链路本地、组播、保留和云元数据地址。
3. 禁止访问云服务器元数据服务、内网管理接口、本机服务和未经批准的内网域名。
4. 仅允许 80 和 443 端口，禁止通过非标准端口访问内部服务。
5. 每次重定向都重新解析并校验目标 IP，限制跳转次数、连接/读取/总任务超时、页面及下载大小。
6. 对每次实际连接再次校验 IP，而不是只在任务创建时检查一次。
7. 对 DNS rebinding：连接时固定使用已验证 IP，同时保留原始 hostname 用于 HTTP Host、TLS SNI 和证书校验；不得为了固定 IP 而跳过证书验证。IP 集合发生变化时重新评估并按策略拒绝或人工复核。
8. 不执行网页中的系统指令，不允许网页触发工具调用或读取本地文件。
9. 下载文件执行 MIME、扩展名、文件签名和大小检查。
10. 不绕过 CAPTCHA、访问控制或其他安全机制。

#### 浏览器与连接层隔离

- Playwright 使用独立容器或非特权沙箱用户，不挂载用户敏感目录，不共享作者浏览器 profile、Cookie 或登录态。
- 浏览器不直接拥有任意网络访问能力；所有请求通过受控出口代理或防火墙。
- 出口代理同时按目标域名、解析后 IP 和端口实施 allowlist/denylist，实际连接被重定向或 DNS 欺骗时仍能阻断私有目标。
- 容器使用只读根文件系统和独立临时目录，限制进程数、内存、CPU 和任务时长。
- 代理与浏览器日志不得记录账号 Cookie、Authorization 头或完整敏感页面内容。

### 12.2 官方来源优先级

| 优先级 | 来源 | 用途 |
|---|---|---|
| P0 | 期刊官方网站 | 投稿规则首选来源 |
| P1 | 出版社官方网站 | 补充和交叉验证 |
| P2 | 官方投稿系统 | 投稿入口和流程验证 |
| P3 | ISSN 等权威标识来源 | 身份辅助核验 |
| P4 | 第三方学术数据库 | 候选发现和辅助参考 |
| P5 | 搜索引擎结果 | 仅用于发现线索 |

来源冲突时记录差异并进入人工确认，不得静默选择第三方数据覆盖官方政策。

### 12.3 授权边界

模块 2 可以自动：

- 打开公开官网；
- 查找公开投稿入口；
- 提取公开投稿要求；
- 检查已授权访问的稿件文件；
- 生成投稿准备报告。

模块 2 不得自动：

- 创建作者账号；
- 使用未经授权的账号登录；
- 替作者确认伦理声明；
- 签署版权或出版协议；
- 在未获得明确授权和人工确认时提交稿件。

### 12.4 审计内容

至少记录操作者、目标出版社和期刊、原始和最终 URL、任务 ID、规则版本、AI 提取结果、人工修改前后值、审核人、审核时间、检查所用稿件版本、操作结果及脱敏异常信息。

密码、验证码、令牌、完整邮箱正文、敏感个人信息和本地敏感路径不得进入日志或普通审计摘要。

## 13. 任务、错误与性能设计

### 13.1 后台任务与幂等控制

- 识别、抓取和 AI 提取使用独立任务记录；
- 保存任务类型、状态、进度、重试次数、检查点和错误分类；
- 网络错误、限流和临时服务错误可安全重试；
- 数据冲突、权限不足和 Schema 错误不得盲目重试；
- 重试必须保持幂等，不能重复生成已确认规则或合规结果。

#### 幂等键

服务端使用规范化输入计算：

```text
discovery: SHA256(task_type + normalized_target_id + normalized_payload)
compliance: SHA256(manuscript_version_id + guideline_id + article_type)
```

`discovery_tasks` 使用 `UNIQUE(task_type, idempotency_key)`，`compliance_tasks` 使用 `UNIQUE(owner_author_id, idempotency_key)`。同一任务的重复请求读取现有任务；状态为 `FAILED` 且可重试时，在原任务上递增 `attempt_count`，而不是创建并行任务。

#### 并发控制

1. 创建时依赖数据库唯一约束，只有一个请求插入成功。
2. Worker 获取任务时使用 `UPDATE ... WHERE status='PENDING'` 或行锁将状态改为 `PROCESSING`，受影响行数必须为 1，否则放弃执行。
3. 任务状态变化使用条件更新，过期 Worker 不得覆盖较新的检查点或完成状态。
4. 规则确认和合规结果创建依赖各自唯一键，重复执行只能返回已有记录。
5. 网络超时但结果未知时先读取任务和外部结果，不能直接假定失败并重发正式操作。

### 13.2 错误分类

| 类型 | 处理 |
|---|---|
| 身份歧义 | 返回候选，要求用户确认 |
| 来源不可用 | 保存失败状态，允许安全重试 |
| 平台无法识别 | 标记 `UNKNOWN`，不得阻断人工维护 |
| AI 输出不符合 Schema | 保存脱敏诊断并标记提取失败，不入库为正式规则 |
| 规则证据不足 | 标记 `UNKNOWN` 或 `WARNING`，不得生成 `FAIL` |
| 权限不足 | 返回与现有权限模型一致的拒绝响应，不泄露稿件或作者数据 |
| 网页安全校验失败 | 立即终止访问并记录脱敏原因 |

### 13.3 性能要求

- 分页查询出版社、期刊、规则和检查任务；
- 批量读取规则、来源和角色，避免 N+1 查询；
- 限制并发抓取和单域名访问频率；
- 快照使用受控相对路径并设置磁盘配额；
- 不为简单任务引入不必要的前后端服务拆分。

## 14. 测试与验收

### 14.1 单元测试

- 出版社和期刊名称规范化；
- ISSN 格式及校验位；
- 候选匹配和冲突处理；
- URL 规范化、重定向和私有地址拦截；
- 平台特征识别及 `UNKNOWN` 降级；
- 投稿规则 Schema 校验；
- 摘要字数和关键词数量统计；
- 文件类型、大小和签名检查；
- 合规状态计算；
- 规则版本比较。

### 14.2 集成测试

- 出版社与期刊关联；
- 投稿入口与平台关联；
- 指南抓取、快照和版本保存；
- 规则与逐条证据关联；
- 模块 1 稿件和作者数据读取；
- 合规任务创建、结果保存和人工确认；
- 用户授权和数据隔离；
- 后台任务失败、超时、恢复和幂等重试。

默认测试使用本地 fixture 页面或受控 HTTP 服务，不依赖真实期刊网络的稳定性。

### 14.3 安全测试

- SSRF 和私有 IP 拦截；
- 恶意重定向及 DNS 解析变化；
- 超大页面和伪装文件；
- 路径穿越；
- Prompt Injection；
- 未授权访问其他用户的任务或稿件；
- 密码、令牌和敏感信息不进入日志。

### 14.4 真实业务场景验收

以下场景必须进入端到端测试，而不是只做字段存在性检查：

| 场景 | 预期结果 |
|---|---|
| 输入正确 ISSN | 找到对应期刊候选并显示身份证据 |
| 输入错误格式或校验位的 ISSN | 返回 422，拒绝作为有效标识 |
| 两个期刊名称相似 | 返回多个候选并要求用户确认，不默认选择第一个 |
| 投稿链接发生一次或多次跳转 | 保存完整有序跳转链及每次 IP 校验结果 |
| 官网与第三方数据库信息冲突 | 标记冲突，以官方来源为准并保留冲突记录 |
| 作者指南内容更新 | 创建新指南版本并生成新旧规则差异，旧版本仍可查询 |
| AI 无法确定摘要限制 | 返回 `UNKNOWN`，不得自动生成通过或失败 |
| 稿件摘要超过已确认限制 | 确定性检查返回 `FAIL`，同时显示实际值、期望值和来源 |
| 稿件满足全部已知规则 | 已知项目返回 `PASS`，未知和未执行规则仍明确显示 |
| 用户访问其他作者的合规报告 | 按作者授权拒绝访问，不泄露报告是否存在及内容 |
| 普通规则自报高置信度 | 仍需按风险级别和样本集评估结果决定审核路径 |
| CAPTCHA 出现 | 任务暂停并提示人工处理，不自动绕过 |

测试环境固定使用 **pytest + 独立 MySQL 8 测试数据库**。不得使用 SQLite 替代 MySQL 验收 JSON、唯一约束、外键、事务、行锁、检查约束和并发幂等行为。真实网页场景使用可控 fixture 页面和重定向服务，外部网络只用于单独标记的试点验收。

### 14.5 验收清单

- [ ] 能输入出版社和期刊信息并生成候选。
- [ ] 能通过 ISSN、官网和出版社交叉确认期刊。
- [ ] 能处理同名或相似候选并要求人工选择。
- [ ] 能发现并验证投稿入口，保存原始 URL 和最终 URL。
- [ ] 能识别 Editorial Manager、ScholarOne，未知平台可标记为 `UNKNOWN`。
- [ ] 能抓取官方 Guide for Authors 并保存证据和快照。
- [ ] 能提取文章类型、格式、文件、匿名、声明和推荐审稿人要求。
- [ ] 每条规则均有来源证据、置信度和审核状态。
- [ ] 能保存并比较不同规则版本。
- [ ] 能调用模块 1 数据生成可解释的合规报告。
- [ ] 能输出 Journal Submission Profile。
- [ ] 能记录人工确认和修改历史。
- [ ] 抓取具备 SSRF、恶意重定向和 Prompt Injection 防护。
- [ ] 任务失败能记录原因并支持安全重试。

## 15. 分期实施路线

| 阶段 | 内容 | 主要交付与验收 |
|---|---|---|
| 1 | 出版社和期刊身份识别 | 别名、ISSN 匹配、候选冲突和人工确认 |
| 2 | 官网及投稿入口发现 | 原始 URL、重定向链、最终 URL 和验证状态 |
| 3 | 平台识别适配器 | Editorial Manager、ScholarOne 识别及 UNKNOWN 降级 |
| 4 | 作者指南抓取 | 官方页面、内容哈希、快照和失败恢复 |
| 5 | AI 规则提取 | 通过 Schema 校验的结构化候选规则 |
| 6 | 规则证据和版本管理 | 逐条证据、审核、差异和不可变版本 |
| 7 | 合规性检查 | 调用模块 1 数据生成检查报告和投稿配置档案 |
| 8 | 扩展平台 | 根据试点期刊逐步增加适配器，不按出版社批量推断 |

首批试点应覆盖不同出版社和平台，但必须逐刊核验实际入口。识别、抓取和合规流程稳定后，才进入投稿账号管理及浏览器自动化执行阶段。

## 16. 待确认产品决策

1. 出版社和期刊基础档案继续全局共享，还是按用户工作空间隔离。
2. 哪些规则必须人工确认，哪些低风险规则允许自动确认。
3. 指南快照保留期限、磁盘配额和清理策略。
4. V0.1 是否需要 APC 费用定期监测。
5. 后台任务继续使用数据库轮询，还是引入独立 Worker/Celery。
6. 首批试点期刊及其真实投稿入口。
7. AI 服务使用云端模型还是本地模型；使用云端服务时如何最小化作者和稿件数据。

云端与本地 AI 未决策前，默认按以下隐私基线执行：

- 优先发送完成规则提取所必需的公开网页片段，不发送完整作者资料、私有稿件、邮箱、账号或会话信息。
- 必须处理私有稿件内容时，先进行字段级最小化、脱敏和访问审计，并明确处理目的、保留期限和删除方式。
- 云端供应商、模型版本、部署区域和日志保留策略必须经过评审；未确认数据跨境及供应商保留政策前，不得将可识别作者或未公开稿件发送到境外服务。
- 私有内容优先选择本地模型；云端模型只用于经批准的公开资料或明确授权的数据集。
- AI 请求和响应不得包含密码、Cookie、令牌、完整邮箱正文或本地敏感路径。

这些决策不影响基础档案管理，但会影响后续识别任务的数据隔离、成本、安全和部署方式。

## 17. 模块交付边界

模块 2 完成后的核心交付物包括：

- 数据库迁移及 SQLAlchemy 模型；
- Pydantic 请求和响应 Schema；
- 出版社、期刊和投稿入口识别服务；
- 平台识别适配器；
- 作者指南抓取、解析和证据管理；
- 规则版本和审核机制；
- 合规规则引擎和检查报告；
- Journal Submission Profile；
- Vue 3 识别与合规工作台；
- 单元、集成、安全及浏览器测试；
- 模块操作说明和部署配置。

**最终技术标准：目标期刊身份可信、投稿入口可追溯、投稿规则有来源和版本、合规检查结果可解释。**

模块 2 不直接完成正式投稿。正式自动化执行必须继续使用独立模块，并经过账号授权、人工审批和结果核验。
