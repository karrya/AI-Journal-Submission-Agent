# AI 学术论文投稿代理系统 V0.1
## 模块 2：出版社与期刊识别详细设计规格

| 项目 | 内容 |
|---|---|
| 文档版本 | V0.1 |
| 文档状态 | 设计稿 |
| 模块名称 | 出版社与期刊识别（Publisher & Journal Recognition） |
| 上游模块 | 模块 1：稿件与作者资料管理 |
| 下游模块 | 模块 3：投稿账号管理与授权；模块 4：自动化投稿执行 |
| 技术基线 | Vue 3、TypeScript、Element Plus、FastAPI、Pydantic、SQLAlchemy 2.0、MySQL |

---

## 1. 模块概述

### 1.1 建设目标

模块 2 负责识别目标出版社和期刊，定位期刊官方网站及正式投稿入口，识别投稿系统类型，提取期刊当前有效的投稿要求，并将这些要求转换为可供程序执行的结构化规则。

模块 2 不只是期刊搜索工具，而是系统的**投稿目标识别、投稿入口发现、投稿规则提取和稿件合规性检查中心**。

核心目标：

1. 根据用户输入的出版社和期刊名称，识别正确的出版社及期刊。
2. 使用 ISSN、EISSN、官网域名等信息辅助确认期刊身份。
3. 从官方页面发现并验证投稿入口。
4. 识别具体期刊实际使用的投稿平台。
5. 抓取并解析 Guide for Authors、Instructions for Authors 等官方投稿指南。
6. 将自然语言投稿要求转换为结构化、可版本化的规则。
7. 调用模块 1 的稿件和作者资料，执行投稿前合规性检查。
8. 输出标准化的 Journal Submission Profile，供后续模块使用。

### 1.2 技术架构约束

沿用系统已确定的技术方案：

| 层次 | 技术选型 |
|---|---|
| 前端 | Vue 3 + TypeScript + Element Plus |
| 后端 | FastAPI + Pydantic |
| ORM | SQLAlchemy 2.0 |
| 数据库 | MySQL 8.x、InnoDB、utf8mb4 |
| 主键 | CHAR(36) UUID |
| 时间 | DATETIME(6)，统一存储 UTC |
| 网页自动化 | Playwright |
| 网页解析 | BeautifulSoup / HTML Parser |
| 后台任务 | 独立 Worker；V0.1 可先采用数据库任务表 |
| 文件存储 | 本地文件系统，数据库保存受控相对路径和元数据 |
| 测试 | pytest + 独立 MySQL 测试数据库 |
| API 前缀 | `/api/v1` |

整体采用模块化单体和本地 Web 前后端分离架构。

### 1.3 模块边界

模块 2 负责：

- 出版社和期刊识别；
- 期刊官网及作者指南定位；
- 投稿入口发现和验证；
- 投稿平台识别；
- 投稿规则抓取、提取和版本管理；
- 投稿前规则匹配和报告生成。

模块 2 不负责：

- 创建或管理作者的真实出版社账号；
- 保存未经授权的作者登录凭据；
- 自动签署版权协议或学术伦理声明；
- 未经人工确认自动提交稿件；
- 判断论文的学术质量或保证录用；
- 将第三方数据库信息当作期刊官方政策。

## 2. 业务流程与总体架构

### 2.1 端到端业务流程

```text
用户输入出版社和期刊信息
        |
        v
出版社识别与匹配
        |
        v
期刊识别与身份确认
        |
        v
期刊官网和作者指南定位
        |
        v
投稿入口发现
        |
        v
投稿系统类型识别
        |
        v
官方投稿规则抓取
        |
        v
AI 规则解析与 Schema 校验
        |
        v
规则证据保存与人工确认
        |
        v
读取模块 1 稿件和作者资料
        |
        v
规则引擎执行合规性检查
        |
        v
生成检查报告
        |
        v
生成 Journal Submission Profile
```

### 2.2 子模块划分

| 编号 | 子模块 | 主要职责 |
|---|---|---|
| 2.1 | 出版社识别 | 出版社名称、官网、品牌及机构信息 |
| 2.2 | 期刊信息识别 | 期刊名称、ISSN、EISSN、官网和身份确认 |
| 2.3 | 投稿入口发现 | 从期刊官网和作者指南发现投稿入口 |
| 2.4 | 投稿平台识别 | 识别 Editorial Manager、ScholarOne 等平台 |
| 2.5 | 投稿规则提取 | 抓取和结构化解析期刊投稿政策 |
| 2.6 | 稿件合规性检查 | 将期刊规则与模块 1 的资料进行匹配 |

### 2.3 主要数据流

- 模块 1 向模块 2 提供稿件版本、文件元数据、标题、摘要、关键词、作者信息及投稿材料。
- 模块 2 向模块 3、模块 4 提供已确认的期刊身份、投稿入口、平台类型和规则版本。
- 模块 2 的每次抓取、规则变更、人工确认和合规检查均保留审计记录。

## 3. 子模块详细设计

### 3.1 出版社识别（Publisher Recognition）

#### 3.1.1 功能目标

根据用户输入的出版社名称或官网地址，识别真实出版社，建立统一出版社记录。

#### 3.1.2 输入

- 出版社名称；
- 出版社英文名称（可选）；
- 官网地址（可选）；
- 期刊名称（可选，用于交叉确认）。

#### 3.1.3 识别字段

| 字段 | 说明 |
|---|---|
| publisher_name | 出版社规范名称 |
| publisher_name_en | 英文名称 |
| website | 官方网站 |
| primary_domain | 主要官方域名 |
| country | 所在国家或地区 |
| publisher_type | 出版社类型 |
| parent_organization_id | 上级机构或母机构，可为空 |
| status | ACTIVE、INACTIVE、UNKNOWN |
| source_url | 官方信息来源 |
| verified_at | 最近核验时间 |

出版社类型建议包括：

- `COMMERCIAL_PUBLISHER`：商业学术出版社；
- `UNIVERSITY_PRESS`：大学出版社；
- `ACADEMIC_SOCIETY`：学术协会；
- `INDEPENDENT_PUBLISHER`：独立学术出版机构；
- `OPEN_ACCESS_PUBLISHER`：开放获取出版机构；
- `OTHER`：其他。

#### 3.1.4 识别规则

1. 名称匹配只用于候选发现，不作为最终身份确认依据。
2. 优先使用出版社官方网站和官方域名确认。
3. 区分出版社、品牌、期刊平台和母机构。
4. 不将名称相似的出版社自动合并。
5. 存在多个候选时，要求用户确认或进入人工审核。

### 3.2 期刊信息识别（Journal Recognition）

#### 3.2.1 功能目标

识别用户指定的具体期刊，建立可稳定引用的期刊记录。

#### 3.2.2 识别字段

| 字段 | 说明 |
|---|---|
| journal_name | 期刊规范名称 |
| journal_name_en | 英文名称 |
| publisher_id | 所属出版社 |
| issn | 印刷版 ISSN |
| eissn | 电子版 EISSN |
| journal_website | 期刊官方网站 |
| author_guidelines_url | 作者指南地址 |
| aims_scope | 期刊范围和主题 |
| open_access_status | 开放获取状态 |
| journal_status | 期刊状态 |
| source_url | 信息来源 |
| verified_at | 最近核验时间 |

ISSN、EISSN、官网域名和出版社关系应共同用于身份核验。不能仅凭期刊名称自动认定期刊身份。

#### 3.2.3 候选匹配策略

建议采用以下匹配顺序：

1. ISSN / EISSN 精确匹配；
2. 官方期刊页面及出版社关系匹配；
3. 期刊英文名称精确匹配；
4. 名称别名和历史名称匹配；
5. 模糊匹配仅用于生成候选列表。

当出现多个高相似候选时，系统必须展示候选的出版社、ISSN、官网等信息，由用户选择。未经确认不得继续执行可能影响投稿目标的操作。

#### 3.2.4 期刊身份状态

- `UNVERIFIED`：尚未核验；
- `VERIFIED`：已核验；
- `NEEDS_CONFIRMATION`：需要用户确认；
- `CONFLICT`：信息冲突；
- `INACTIVE`：已停刊或不可用；
- `UNKNOWN`：无法判断。

### 3.3 投稿入口发现（Submission Portal Discovery）

#### 3.3.1 功能目标

找到具体期刊当前使用的正式投稿入口，而不只是期刊主页。

#### 3.3.2 发现策略

**第一层：期刊官网**

查找以下常见链接文字：

- Submit Your Article
- Submit Your Manuscript
- Online Submission
- Submit Paper
- Author Login
- Manuscript Submission

**第二层：作者指南**

从 Guide for Authors、Instructions for Authors、Submission Guidelines 等页面查找投稿入口及平台说明。

**第三层：浏览器验证**

使用 Playwright 在受控环境中访问候选链接，记录：

- 原始 URL；
- 重定向链；
- 最终 URL；
- 最终域名；
- 页面标题；
- 页面是否可访问；
- 是否出现登录、注册或投稿相关页面元素；
- 验证时间和验证方式。

#### 3.3.3 入口状态

- `DISCOVERED`：已发现，尚未验证；
- `VERIFIED`：已验证；
- `REDIRECTED`：发生跳转，已记录最终地址；
- `LOGIN_REQUIRED`：需要登录；
- `BLOCKED`：被访问限制阻止；
- `BROKEN`：链接失效；
- `NEEDS_REVIEW`：需要人工确认；
- `UNKNOWN`：无法判断。

#### 3.3.4 安全要求

- 仅允许访问 HTTP/HTTPS。
- 拦截 localhost、私有 IP、链路本地地址及云元数据地址，防止 SSRF。
- 对每次重定向重新执行目标地址校验。
- 限制页面大小、下载大小、请求超时和跳转次数。
- 不执行网页中未经信任的指令。
- 不自动下载或运行网页提供的可执行文件。
- 不绕过验证码、访问控制或其他安全机制。
- 保留原始 URL 和最终 URL，不能只保存跳转后的地址。

### 3.4 投稿平台识别（Submission System Recognition）

#### 3.4.1 功能目标

识别具体期刊投稿入口使用的平台类型，为后续自动化模块提供平台适配器选择依据。

#### 3.4.2 V0.1 优先支持的平台

| 平台代码 | 平台名称 |
|---|---|
| `EDITORIAL_MANAGER` | Editorial Manager |
| `SCHOLARONE` | ScholarOne Manuscripts |
| `SNAPP` | Springer Nature SNAPP |
| `WILEY_RESEARCH_EXCHANGE` | Wiley Research Exchange |
| `IEEE_AUTHOR_PORTAL` | IEEE Author Portal |
| `ACS_PARAGON_PLUS` | ACS Paragon Plus |
| `MDPI_SYSTEM` | MDPI Submission System |
| `FRONTIERS_SYSTEM` | Frontiers Submission System |
| `OJS` | Open Journal Systems |
| `CUSTOM` | 出版社或期刊自建系统 |
| `UNKNOWN` | 未知平台 |

以上是候选平台目录。是否支持某个平台，应以实际期刊入口和页面验证结果为准。

#### 3.4.3 识别方法

平台识别应综合判断：

1. URL 域名和路径特征；
2. 页面标题及品牌信息；
3. 页面 DOM 特征；
4. 登录页面元素；
5. 官方作者指南中的平台说明；
6. 官方链接跳转关系。

不能仅凭出版社名称推断平台。一个出版社可能为不同期刊配置不同投稿系统。

#### 3.4.4 平台适配器

建议采用 Platform Adapter 模式：

```text
submission_platforms/
├── base.py
├── editorial_manager.py
├── scholarone.py
├── snapp.py
├── wiley_research_exchange.py
├── ieee_author_portal.py
├── mdpi.py
└── ojs.py
```

统一接口示例：

```python
from abc import ABC, abstractmethod

class BaseSubmissionPlatform(ABC):

    @abstractmethod
    async def detect(self, url: str):
        """识别平台类型和置信度。"""
        raise NotImplementedError

    @abstractmethod
    async def verify_portal(self, url: str):
        """验证投稿入口。"""
        raise NotImplementedError

    @abstractmethod
    async def get_login_url(self, url: str):
        """获取已验证的登录入口。"""
        raise NotImplementedError

    @abstractmethod
    async def get_platform_features(self):
        """返回平台能力描述。"""
        raise NotImplementedError
```

V0.1 的平台识别与后续登录、填写、上传等自动化执行能力应分离。识别成功不代表已经实现该平台的完整自动投稿适配器。

### 3.5 投稿规则提取（Submission Requirements Extraction）

#### 3.5.1 功能目标

从期刊官方作者指南和投稿页面提取规则，将非结构化网页内容转换为可校验的结构化数据。

#### 3.5.2 规则分类

**A. 文章类型**

- Research Article；
- Review Article；
- Short Communication；
- Editorial；
- Case Report；
- 其他期刊自定义类型。

需要保存文章类型的原始名称、规范代码、是否接受以及适用条件。

**B. 稿件格式**

提取：

- Word、PDF、LaTeX 是否支持；
- 是否提供官方模板；
- 单栏或双栏要求；
- 字体、字号、行距和页边距；
- 正文字数限制；
- 摘要字数限制；
- 关键词数量限制；
- 参考文献格式；
- 图表格式和分辨率要求。

**C. 文件上传要求**

| 文件代码 | 文件类型 | 常见要求 |
|---|---|---|
| `MANUSCRIPT` | 主稿件 | 通常必须 |
| `TITLE_PAGE` | 标题页 | 视期刊要求 |
| `COVER_LETTER` | 投稿信 | 视期刊要求 |
| `FIGURE` | 图片文件 | 视稿件情况 |
| `TABLE` | 表格文件 | 视期刊情况 |
| `SUPPLEMENTARY` | 补充材料 | 可选或条件必需 |
| `HIGHLIGHTS` | 研究亮点 | 视期刊要求 |
| `GRAPHICAL_ABSTRACT` | 图文摘要 | 视期刊要求 |
| `CONFLICT_OF_INTEREST` | 利益冲突声明 | 视期刊要求 |

每项文件要求支持：

- `REQUIRED`：必须；
- `OPTIONAL`：可选；
- `CONDITIONAL`：满足条件时必须；
- `NOT_REQUIRED`：明确不要求；
- `UNKNOWN`：未能确认。

不得将某一出版社或某一期刊的文件要求推广为所有期刊的统一要求。

**D. 作者和匿名审稿要求**

提取：

- Single-blind；
- Double-blind / Double-anonymized；
- 是否需要独立 Title Page；
- 主稿件是否需要删除作者姓名、单位、邮箱和致谢身份信息；
- 通讯作者信息要求；
- 作者顺序要求；
- ORCID 要求。

**E. 推荐审稿人要求**

提取：

- 是否要求推荐审稿人；
- 最少和最多推荐人数；
- 必填字段；
- 是否要求机构和邮箱；
- 是否允许排除审稿人；
- 排除原因要求。

**F. Cover Letter 要求**

提取：

- 是否要求 Cover Letter；
- 是否有模板；
- 是否要求说明创新性、期刊适配性；
- 是否要求声明未重复投稿；
- 是否要求所有作者同意投稿。

**G. 学术伦理和声明**

提取：

- Funding Statement；
- Conflict of Interest；
- Author Contributions；
- Ethics Approval；
- Informed Consent；
- Data Availability Statement；
- Competing Interests；
- Generative AI 使用声明；
- Copyright 和 Publication Agreement。

声明内容应以期刊当前政策为准。系统不得自行替作者作出事实性声明。

**H. 费用与开放获取**

提取：

- 开放获取政策；
- APC 金额和币种；
- 强制出版费用；
- 其他收费项目；
- 费用减免政策；
- 价格适用条件；
- 信息更新时间。

费用信息必须保存来源和抓取时间。未能确认的金额不得推测。

#### 3.5.3 规则提取技术流程

```text
Playwright 获取官方页面
        |
        v
HTML 清洗和正文抽取
        |
        v
页面标题、URL、抓取时间保存
        |
        v
AI 结构化规则解析
        |
        v
Pydantic Schema 校验
        |
        v
规则证据关联
        |
        v
规则置信度与审核状态
        |
        v
MySQL 保存规则版本
```

#### 3.5.4 规则数据示例

```json
{
  "rule_code": "ABSTRACT_WORD_LIMIT",
  "rule_category": "MANUSCRIPT_FORMAT",
  "rule_value": {
    "max_words": 250
  },
  "unit": "words",
  "source_url": "https://example.com/author-guidelines",
  "source_text": "Abstract should not exceed 250 words.",
  "confidence": 0.98,
  "review_status": "PENDING"
}
```

以上 URL 和规则值仅为结构示例，不代表真实期刊政策。

#### 3.5.5 规则证据要求

每条规则尽可能保存：

- 来源 URL；
- 页面标题；
- 原始证据文本；
- 抓取时间；
- 页面内容摘要或快照文件路径；
- 规则提取时间；
- 提取模型或解析器版本；
- 置信度；
- 人工审核状态；
- 生效时间和失效时间（仅在来源明确时填写）。

AI 负责理解和提取，程序负责类型校验和确定性计算，人工负责确认存在歧义或高影响的规则。网页正文必须作为不可信输入，不能被当作系统指令。

### 3.6 稿件合规性检查（Manuscript Compliance Check）

#### 3.6.1 功能目标

将模块 1 中已解析的稿件和作者资料，与模块 2 中已确认的期刊规则进行匹配，输出可解释的投稿准备报告。

#### 3.6.2 输入数据

来自模块 1：

- 稿件 ID 和版本 ID；
- 文件 ID、文件类型、文件哈希；
- 标题；
- 摘要；
- 关键词；
- 作者及通讯作者资料；
- Cover Letter；
- 推荐审稿人；
- 其他声明及补充材料。

来自模块 2：

- journal_id；
- 规则版本 ID；
- 文章类型要求；
- 文件要求；
- 字数和格式限制；
- 作者和匿名要求；
- 声明要求；
- 推荐审稿人要求。

#### 3.6.3 检查项目

| 检查项目 | 检查方式 |
|---|---|
| 文章类型 | 目标文章类型是否被期刊接受 |
| 摘要字数 | 自动统计并比较上限 |
| 关键词数量 | 自动统计并比较范围 |
| 稿件文件格式 | MIME、扩展名和实际文件类型检查 |
| Title Page | 检查是否存在所需文件 |
| 作者资料 | 检查必填字段是否齐全 |
| 匿名要求 | 检测主稿件中的身份信息 |
| Cover Letter | 检查是否存在及是否满足已确认要求 |
| 推荐审稿人 | 检查人数和字段 |
| 声明材料 | 检查所需声明是否存在 |
| 图表和补充材料 | 检查文件数量、格式和必要元数据 |

#### 3.6.4 检查状态

| 状态 | 含义 |
|---|---|
| `PASS` | 满足已确认规则 |
| `FAIL` | 违反已确认规则 |
| `WARNING` | 存在风险，需要注意 |
| `UNKNOWN` | 规则或证据不足，无法判断 |
| `SKIPPED` | 不适用或未执行 |

只有规则已确认、证据充分且检查逻辑确定时，才能生成 FAIL。AI 推测或来源不明确的规则只能产生 WARNING 或 UNKNOWN。

#### 3.6.5 结果示例

```json
{
  "compliance_task_id": "uuid",
  "journal_id": "uuid",
  "manuscript_version_id": "uuid",
  "guideline_version_id": "uuid",
  "summary": {
    "pass": 12,
    "fail": 2,
    "warning": 3,
    "unknown": 1
  },
  "overall_status": "NEEDS_REVISION",
  "results": [
    {
      "rule_code": "ABSTRACT_WORD_LIMIT",
      "status": "PASS",
      "actual_value": 220,
      "expected_value": 250
    },
    {
      "rule_code": "TITLE_PAGE_REQUIRED",
      "status": "FAIL",
      "message": "缺少独立标题页文件"
    }
  ]
}
```

#### 3.6.6 检查报告要求

报告应展示：

- 目标期刊及身份信息；
- 稿件版本；
- 使用的规则版本；
- 检查时间；
- PASS、FAIL、WARNING、UNKNOWN 数量；
- 每项检查的实际值、期望值和来源；
- 需要用户处理的问题；
- 人工确认记录。

合规检查结果只表示对已提取规则的匹配情况，不代表期刊一定会接收稿件，也不替代编辑部的正式判断。

---

## 4. 数据库设计

### 4.1 设计约定

- 主键统一使用 `CHAR(36)` UUID。
- MySQL 使用 InnoDB 和 utf8mb4。
- 时间字段使用 `DATETIME(6)`，统一存储 UTC。
- 业务表包含 `created_at`、`updated_at`、`created_by` 等审计字段。
- 规则版本、来源证据、检查结果和审计记录应保留历史，不得通过覆盖更新破坏历史记录。
- 删除出版社或期刊时应优先使用软删除或状态变更，不得级联删除历史投稿和审计数据。
- 业务查询必须执行用户授权和数据隔离检查。

### 4.2 核心表清单

| 表名 | 用途 |
|---|---|
| `publishers` | 出版社基本信息 |
| `publisher_aliases` | 出版社名称别名 |
| `journals` | 期刊基本信息 |
| `journal_identifiers` | ISSN、EISSN 等标识 |
| `journal_aliases` | 期刊名称别名 |
| `submission_platforms` | 投稿平台字典 |
| `journal_submission_portals` | 期刊投稿入口 |
| `journal_guidelines` | 作者指南及版本 |
| `journal_requirements` | 结构化投稿规则 |
| `requirement_sources` | 规则来源及证据 |
| `journal_article_types` | 期刊支持的文章类型 |
| `compliance_tasks` | 合规检查任务 |
| `compliance_results` | 合规检查结果 |
| `journal_discovery_logs` | 识别和发现日志 |
| `module2_audit_logs` | 模块操作审计 |

### 4.3 publishers 表

```sql
CREATE TABLE publishers (
    id CHAR(36) PRIMARY KEY,
    publisher_name VARCHAR(255) NOT NULL,
    publisher_name_en VARCHAR(255),
    website VARCHAR(1000),
    primary_domain VARCHAR(255),
    country VARCHAR(100),
    publisher_type VARCHAR(50),
    parent_organization_id CHAR(36),
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    verified_at DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by CHAR(36),
    deleted_at DATETIME(6),
    INDEX idx_publishers_name (publisher_name),
    INDEX idx_publishers_domain (primary_domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.4 journals 表

```sql
CREATE TABLE journals (
    id CHAR(36) PRIMARY KEY,
    publisher_id CHAR(36) NOT NULL,
    journal_name VARCHAR(500) NOT NULL,
    journal_name_en VARCHAR(500),
    journal_website VARCHAR(1000),
    author_guidelines_url VARCHAR(2000),
    aims_scope TEXT,
    open_access_status VARCHAR(50),
    journal_status VARCHAR(30) NOT NULL DEFAULT 'UNVERIFIED',
    verified_at DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by CHAR(36),
    deleted_at DATETIME(6),
    INDEX idx_journals_publisher (publisher_id),
    INDEX idx_journals_name (journal_name),
    CONSTRAINT fk_journals_publisher
        FOREIGN KEY (publisher_id) REFERENCES publishers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.5 journal_identifiers 表

```sql
CREATE TABLE journal_identifiers (
    id CHAR(36) PRIMARY KEY,
    journal_id CHAR(36) NOT NULL,
    identifier_type VARCHAR(30) NOT NULL,
    identifier_value VARCHAR(50) NOT NULL,
    source_url VARCHAR(2000),
    verified_at DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_journal_identifier (
        identifier_type,
        identifier_value
    ),
    INDEX idx_journal_identifiers_journal (journal_id),
    CONSTRAINT fk_journal_identifiers_journal
        FOREIGN KEY (journal_id) REFERENCES journals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.6 submission_platforms 表

```sql
CREATE TABLE submission_platforms (
    id CHAR(36) PRIMARY KEY,
    platform_code VARCHAR(80) NOT NULL,
    platform_name VARCHAR(255) NOT NULL,
    vendor_name VARCHAR(255),
    official_website VARCHAR(1000),
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_submission_platform_code (platform_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.7 journal_submission_portals 表

```sql
CREATE TABLE journal_submission_portals (
    id CHAR(36) PRIMARY KEY,
    journal_id CHAR(36) NOT NULL,
    platform_id CHAR(36),
    original_url VARCHAR(2000) NOT NULL,
    final_url VARCHAR(2000),
    domain VARCHAR(255),
    portal_status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
    verification_method VARCHAR(50),
    page_title VARCHAR(500),
    verified_at DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    INDEX idx_portals_journal (journal_id),
    INDEX idx_portals_platform (platform_id),
    CONSTRAINT fk_portals_journal
        FOREIGN KEY (journal_id) REFERENCES journals(id),
    CONSTRAINT fk_portals_platform
        FOREIGN KEY (platform_id) REFERENCES submission_platforms(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.8 journal_guidelines 表

每次抓取或确认作者指南时，生成新的版本记录，不覆盖旧版本。

```sql
CREATE TABLE journal_guidelines (
    id CHAR(36) PRIMARY KEY,
    journal_id CHAR(36) NOT NULL,
    version_no INT NOT NULL,
    source_url VARCHAR(2000) NOT NULL,
    page_title VARCHAR(500),
    content_hash CHAR(64),
    snapshot_path VARCHAR(1000),
    fetched_at DATETIME(6) NOT NULL,
    effective_from DATETIME(6),
    effective_until DATETIME(6),
    review_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at DATETIME(6) NOT NULL,
    created_by CHAR(36),
    UNIQUE KEY uq_guideline_version (journal_id, version_no),
    CONSTRAINT fk_guidelines_journal
        FOREIGN KEY (journal_id) REFERENCES journals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.9 journal_requirements 表

```sql
CREATE TABLE journal_requirements (
    id CHAR(36) PRIMARY KEY,
    journal_id CHAR(36) NOT NULL,
    guideline_id CHAR(36) NOT NULL,
    rule_code VARCHAR(100) NOT NULL,
    rule_category VARCHAR(100) NOT NULL,
    rule_value JSON NOT NULL,
    is_required BOOLEAN,
    confidence DECIMAL(5,4),
    review_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    effective_from DATETIME(6),
    effective_until DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    INDEX idx_requirements_journal (journal_id),
    INDEX idx_requirements_guideline (guideline_id),
    INDEX idx_requirements_code (rule_code),
    CONSTRAINT fk_requirements_journal
        FOREIGN KEY (journal_id) REFERENCES journals(id),
    CONSTRAINT fk_requirements_guideline
        FOREIGN KEY (guideline_id) REFERENCES journal_guidelines(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.10 requirement_sources 表

```sql
CREATE TABLE requirement_sources (
    id CHAR(36) PRIMARY KEY,
    requirement_id CHAR(36) NOT NULL,
    source_url VARCHAR(2000) NOT NULL,
    page_title VARCHAR(500),
    source_text TEXT,
    snapshot_path VARCHAR(1000),
    fetched_at DATETIME(6) NOT NULL,
    content_hash CHAR(64),
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_requirement_sources_requirement
        FOREIGN KEY (requirement_id)
        REFERENCES journal_requirements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.11 compliance_tasks 表

```sql
CREATE TABLE compliance_tasks (
    id CHAR(36) PRIMARY KEY,
    journal_id CHAR(36) NOT NULL,
    manuscript_id CHAR(36) NOT NULL,
    manuscript_version_id CHAR(36) NOT NULL,
    guideline_id CHAR(36) NOT NULL,
    task_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    overall_status VARCHAR(30),
    started_at DATETIME(6),
    completed_at DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    created_by CHAR(36),
    INDEX idx_compliance_journal (journal_id),
    INDEX idx_compliance_manuscript (manuscript_id),
    CONSTRAINT fk_compliance_journal
        FOREIGN KEY (journal_id) REFERENCES journals(id),
    CONSTRAINT fk_compliance_guideline
        FOREIGN KEY (guideline_id) REFERENCES journal_guidelines(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.12 compliance_results 表

```sql
CREATE TABLE compliance_results (
    id CHAR(36) PRIMARY KEY,
    task_id CHAR(36) NOT NULL,
    requirement_id CHAR(36),
    rule_code VARCHAR(100) NOT NULL,
    result_status VARCHAR(30) NOT NULL,
    actual_value JSON,
    expected_value JSON,
    message TEXT,
    evidence JSON,
    reviewed_by CHAR(36),
    reviewed_at DATETIME(6),
    created_at DATETIME(6) NOT NULL,
    INDEX idx_compliance_results_task (task_id),
    CONSTRAINT fk_compliance_results_task
        FOREIGN KEY (task_id) REFERENCES compliance_tasks(id),
    CONSTRAINT fk_compliance_results_requirement
        FOREIGN KEY (requirement_id)
        REFERENCES journal_requirements(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.13 数据库实现注意事项

以上 SQL 是核心表结构示例，正式迁移前还需要：

- 根据现有用户、角色和作者授权模型补充隔离字段；
- 补充所有外键、索引、唯一约束和删除策略；
- 为 `created_by`、`reviewed_by` 等字段建立适当关联；
- 明确 `journal_id` 与 ISSN 的数据清洗和冲突处理规则；
- 根据实际 MySQL 版本验证 JSON、索引及约束行为；
- 通过 Alembic 管理数据库迁移；
- 对不可变的规则版本、证据和审计记录禁止普通更新和删除。

---

## 5. 后端目录结构

建议在现有 FastAPI 项目中增加以下模块：

```text
backend/
└── app/
    ├── api/
    │   └── v1/
    │       ├── publishers.py
    │       ├── journals.py
    │       ├── submission_portals.py
    │       ├── guidelines.py
    │       └── compliance.py
    ├── models/
    │   ├── publisher.py
    │   ├── journal.py
    │   ├── submission_platform.py
    │   ├── submission_portal.py
    │   ├── journal_guideline.py
    │   ├── journal_requirement.py
    │   └── compliance.py
    ├── schemas/
    │   ├── publisher.py
    │   ├── journal.py
    │   ├── submission_portal.py
    │   ├── guideline.py
    │   └── compliance.py
    ├── repositories/
    │   ├── publisher_repository.py
    │   ├── journal_repository.py
    │   ├── portal_repository.py
    │   └── requirement_repository.py
    ├── services/
    │   ├── publisher_service.py
    │   ├── journal_identification_service.py
    │   ├── portal_discovery_service.py
    │   ├── platform_detection_service.py
    │   ├── guideline_crawler_service.py
    │   ├── requirement_extraction_service.py
    │   └── compliance_service.py
    ├── crawlers/
    │   ├── browser.py
    │   ├── html_parser.py
    │   └── url_security.py
    ├── submission_platforms/
    │   ├── base.py
    │   ├── editorial_manager.py
    │   ├── scholarone.py
    │   ├── snapp.py
    │   ├── wiley_research_exchange.py
    │   ├── ieee_author_portal.py
    │   ├── mdpi.py
    │   └── ojs.py
    ├── rules/
    │   ├── rule_registry.py
    │   ├── rule_engine.py
    │   └── validators.py
    └── tasks/
        ├── discovery_tasks.py
        └── guideline_tasks.py
```

职责约定：

- `api`：HTTP 参数校验、认证、响应和状态码。
- `services`：业务流程、授权检查和事务编排。
- `repositories`：SQLAlchemy 数据访问。
- `models`：数据库模型。
- `schemas`：Pydantic 请求和响应模型。
- `crawlers`：网页访问、解析和 URL 安全校验。
- `submission_platforms`：平台识别适配器。
- `rules`：规则注册、执行和校验。
- `tasks`：后台任务入口。

---

## 6. FastAPI 接口设计

统一使用 `/api/v1` 前缀。

| API | 方法 | 功能 |
|---|---|---|
| `/publishers` | POST | 新增出版社 |
| `/publishers/search` | GET | 搜索出版社 |
| `/journals/search` | GET | 搜索期刊 |
| `/journals/identify` | POST | 识别期刊 |
| `/journals/{id}` | GET | 获取期刊详情 |
| `/journals/{id}/discover-portal` | POST | 发现投稿入口 |
| `/journals/{id}/detect-platform` | POST | 识别投稿平台 |
| `/journals/{id}/extract-guidelines` | POST | 提取投稿要求 |
| `/journals/{id}/requirements` | GET | 获取投稿规则 |
| `/compliance/check` | POST | 执行稿件合规检查 |
| `/compliance/{id}` | GET | 获取检查报告 |
| `/compliance/{id}/confirm` | POST | 人工确认检查结果 |
| `/tasks/{id}` | GET | 查询后台任务状态 |

### 6.1 期刊识别请求示例

```json
{
  "publisher_name": "Elsevier",
  "journal_name": "Journal of Cleaner Production",
  "issn": null,
  "eissn": null
}
```

### 6.2 期刊识别响应示例

```json
{
  "task_id": "uuid",
  "status": "NEEDS_CONFIRMATION",
  "candidates": [
    {
      "journal_id": "uuid",
      "journal_name": "Example Journal",
      "publisher_name": "Example Publisher",
      "issn": "0000-0000",
      "website": "https://example.org"
    }
  ]
}
```

以上为接口结构示例，候选期刊内容不是实际识别结果。

### 6.3 后台任务状态

```json
{
  "task_id": "uuid",
  "task_type": "EXTRACT_GUIDELINES",
  "status": "PROCESSING",
  "progress": 35,
  "message": "正在解析作者指南"
}
```

任务状态建议统一为：

- `PENDING`
- `PROCESSING`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`

长耗时抓取和 AI 解析应在后台执行。前端可通过任务查询接口或 SSE 获取进度。

---

## 7. 前端页面设计

### 7.1 页面入口

在系统主导航中增加：**出版社与期刊识别**。

建议包含以下页面：

1. 期刊识别工作台；
2. 出版社列表；
3. 期刊资料库；
4. 投稿入口管理；
5. 投稿规则管理；
6. 合规性检查报告；
7. 识别任务和历史记录。

### 7.2 期刊识别工作台

输入字段：

- 出版社名称；
- 期刊名称；
- ISSN（可选）；
- EISSN（可选）；
- 目标文章类型。

主要操作：

- 开始识别；
- 查看候选期刊；
- 确认期刊；
- 发现投稿入口；
- 提取投稿要求；
- 执行合规检查。

### 7.3 期刊详情 Tab

| Tab | 内容 |
|---|---|
| 基本信息 | 出版社、期刊名称、ISSN、期刊官网 |
| 投稿入口 | 投稿网址、登录网址、平台类型、验证状态 |
| 投稿要求 | 文章类型、文件格式、摘要、关键词等 |
| 投稿材料 | 必需文件、可选文件、声明文件 |
| 合规检查 | PASS、FAIL、WARNING、UNKNOWN |
| 历史记录 | 规则版本、历史抓取、修改记录 |

### 7.4 交互要求

- 识别任务应显示当前阶段和进度。
- 多个候选期刊必须允许用户选择。
- 未确认的规则应明显标识。
- 每条规则应能查看来源证据。
- 规则发生变化时，应展示新旧版本差异。
- 合规报告应允许定位到对应稿件版本和规则版本。
- 页面不得将 UNKNOWN 自动显示为 PASS。

---

## 8. Journal Submission Profile 标准输出

### 8.1 设计目的

模块 2 不应只输出期刊 ID，而应输出完整的期刊投稿配置档案，作为模块 2 与后续模块之间的标准接口。

### 8.2 数据示例

```json
{
  "journal_id": "uuid",
  "publisher_id": "uuid",
  "journal_name": "Journal Example",
  "identity_status": "VERIFIED",
  "submission_platform": "EDITORIAL_MANAGER",
  "submission_url": "https://example.com/submit",
  "guidelines_version_id": "uuid",
  "article_type": "RESEARCH_ARTICLE",
  "file_requirements": [],
  "author_requirements": [],
  "reviewer_requirements": [],
  "declaration_requirements": [],
  "compliance_status": "READY_FOR_REVIEW"
}
```

以上为接口结构示例，不代表真实期刊数据。

### 8.3 输出约束

- 必须关联唯一的 `journal_id`。
- 必须记录所依据的指南版本。
- 投稿入口必须有状态和核验时间。
- 规则应包含来源和审核状态。
- 不得将未确认规则包装成确定要求。
- 后续模块应能通过档案追溯原始证据。

---

## 9. 安全、授权与审计

### 9.1 网页抓取安全

必须防范：

- SSRF；
- 恶意重定向；
- 恶意网页脚本；
- 超大网页和文件；
- 网页 Prompt Injection；
- 非法文件下载；
- 不可信第三方内容。

建议：

1. 只允许访问 HTTP/HTTPS。
2. DNS 解析后校验目标 IP，拒绝私有、环回、链路本地及保留地址。
3. 每次重定向重新校验目标地址。
4. 限制页面大小、下载大小、请求超时、并发数和跳转次数。
5. 浏览器运行在隔离环境中，不挂载用户敏感文件。
6. 抓取网页内容与系统指令严格隔离。
7. 不允许网页内容触发工具调用、读取本地文件或访问作者账号。
8. 对下载文件执行 MIME、扩展名、文件签名和大小检查。

### 9.2 官方来源优先级

| 优先级 | 信息来源 | 使用方式 |
|---|---|---|
| P0 | 期刊官方网站 | 规则确认的首选来源 |
| P1 | 出版社官方网站 | 补充和交叉验证 |
| P2 | 官方投稿系统 | 投稿流程和入口验证 |
| P3 | ISSN 等权威标识来源 | 期刊身份辅助核验 |
| P4 | 第三方学术数据库 | 候选发现和辅助参考 |
| P5 | 搜索引擎结果 | 仅用于发现线索 |

第三方信息不能替代官方投稿要求。出现来源冲突时，应记录冲突并要求人工确认。

### 9.3 授权边界

模块 2 可以自动：

- 打开公开官网；
- 查找公开投稿入口；
- 提取公开投稿要求；
- 检查已授权访问的稿件文件；
- 生成投稿准备报告。

模块 2 不应自动：

- 创建作者账号；
- 使用未经授权的账号登录；
- 替作者确认学术伦理声明；
- 签署版权或出版协议；
- 在未获得明确授权和人工确认时提交稿件。

### 9.4 审计记录

至少记录：

- 操作者；
- 操作时间；
- 目标出版社和期刊；
- 原始 URL 和最终 URL；
- 抓取任务 ID；
- 规则版本；
- AI 提取结果；
- 人工修改前后值；
- 审核人和审核时间；
- 合规检查所用稿件版本；
- 操作结果和异常信息。

---

## 10. 规则版本管理

期刊投稿要求可能随时间变化，因此不得直接覆盖旧规则。

### 10.1 版本策略

每次重新抓取或人工确认形成新的指南版本，不修改历史版本：

```text
Journal
  ├── Guidelines Version 1
  │     ├── Abstract Limit
  │     └── Keyword Range
  │
  ├── Guidelines Version 2
  │     ├── Abstract Limit
  │     └── Keyword Range
  │
  └── Current Confirmed Version
```

### 10.2 版本记录

每个版本应保存：

- 版本号；
- 抓取时间；
- 官方来源 URL；
- 内容哈希；
- 快照路径；
- 提取器版本；
- 审核状态；
- 生效时间（有明确证据时）；
- 失效时间（有明确证据时）。

### 10.3 规则更新策略

- 定期检查官方指南是否变化。
- URL 或内容哈希变化时，创建待处理的新版本。
- 对比新旧规则并生成差异。
- 不自动把新提取规则设为已确认。
- 已完成的合规检查继续引用当时使用的规则版本。
- 新规则确认后，后续检查默认使用最新确认版本。

---

## 11. 测试、验收与交付

### 11.1 单元测试

重点测试：

- 出版社名称规范化；
- 期刊名称匹配；
- ISSN 格式校验；
- 期刊候选冲突；
- 投稿平台特征识别；
- URL 规范化；
- 重定向链处理；
- 投稿规则 Schema 校验；
- 摘要字数统计；
- 关键词数量统计；
- 文件类型和大小检查；
- 合规状态计算；
- 规则版本比较。

### 11.2 集成测试

重点测试：

- 出版社到期刊的关联；
- 期刊到投稿入口的关联；
- 投稿入口到平台类型的关联；
- 作者指南抓取与版本保存；
- 规则和来源证据的关联；
- 模块 1 稿件数据读取；
- 合规任务创建和结果保存；
- 用户授权和数据隔离；
- 后台任务失败、重试和超时处理。

### 11.3 安全测试

重点测试：

- SSRF 和私有 IP 拦截；
- 恶意重定向；
- DNS 解析变化；
- 超大页面和文件；
- 文件伪装；
- 路径穿越；
- Prompt Injection；
- 未授权用户访问其他用户的期刊任务或稿件；
- 敏感信息是否意外写入日志。

### 11.4 验收清单

- [ ] 能输入出版社名称和期刊名称。
- [ ] 能识别并保存出版社官网。
- [ ] 能识别期刊及 ISSN、EISSN。
- [ ] 能处理同名或相似期刊候选。
- [ ] 能发现期刊官方投稿入口。
- [ ] 能记录原始 URL 和最终跳转 URL。
- [ ] 能识别 Editorial Manager。
- [ ] 能识别 ScholarOne。
- [ ] 无法识别的平台可以标记为 UNKNOWN。
- [ ] 能抓取官方 Guide for Authors。
- [ ] 能提取文章类型。
- [ ] 能提取稿件格式要求。
- [ ] 能提取文件上传要求。
- [ ] 能提取匿名审稿要求。
- [ ] 能提取 Cover Letter 和推荐审稿人要求。
- [ ] 能提取学术伦理声明要求。
- [ ] 每条规则都有来源证据。
- [ ] 能保存不同版本的投稿规则。
- [ ] 能调用模块 1 的稿件资料进行合规检查。
- [ ] 能输出合规性报告。
- [ ] 能记录人工确认和修改历史。
- [ ] 抓取服务具备 SSRF 和恶意重定向防护。
- [ ] 任务失败时能记录原因并支持安全重试。

### 11.5 V0.1 交付物

1. 模块 2 数据库迁移脚本；
2. SQLAlchemy 2.0 ORM 模型；
3. Pydantic 请求和响应 Schema；
4. FastAPI 路由和 Service；
5. 出版社、期刊和投稿入口识别服务；
6. Editorial Manager、ScholarOne 的初步识别适配器；
7. 作者指南抓取与解析服务；
8. 投稿规则结构化存储和版本管理；
9. 基础合规规则引擎；
10. Vue 3 模块页面；
11. pytest 单元测试、集成测试和安全测试；
12. 模块操作说明和部署配置。

---

## 12. V0.1 开发顺序

建议按以下顺序实施，避免一开始就开发复杂的全自动投稿：

| 阶段 | 开发内容 | 主要验收结果 |
|---|---|---|
| 1 | 出版社、期刊基础信息管理 | 能创建、搜索和确认期刊 |
| 2 | 期刊官网及投稿入口发现 | 能找到并验证官方入口 |
| 3 | Editorial Manager、ScholarOne 识别 | 能识别常见平台，未知平台可降级 |
| 4 | Guide for Authors 抓取 | 能保存网页来源和内容快照 |
| 5 | AI 投稿规则提取 | 能输出通过 Schema 校验的结构化规则 |
| 6 | 规则证据和版本管理 | 每条规则可追溯、可审核、可回滚查看 |
| 7 | 稿件合规性检查 | 能读取模块 1 数据并生成报告 |
| 8 | 扩展其他投稿平台 | 根据实际业务需要逐步增加适配器 |

### 12.1 首批试点范围

建议先选择少量期刊开展端到端试点，覆盖不同出版社和不同投稿平台。可先测试 Elsevier、Springer Nature 旗下期刊，但必须逐刊核验实际投稿入口和平台，不能按出版社统一推断。

---

## 13. 风险与待确认事项

| 风险 | 影响 | 应对措施 |
|---|---|---|
| 期刊名称重名或相似 | 可能识别错期刊 | ISSN、官网、出版社交叉确认；歧义时人工选择 |
| 投稿入口发生变化 | 自动化进入错误页面 | 定期核验入口，保存验证时间和跳转链 |
| 官方指南动态变化 | 使用过期要求 | 内容哈希、版本管理和变更提醒 |
| AI 规则提取错误 | 错误判断稿件合规性 | 原文证据、Schema 校验、人工确认 |
| 不同文章类型规则不同 | 规则应用错误 | 规则增加 article_type 和适用条件 |
| 网页恶意内容 | SSRF、提示注入或文件风险 | 隔离浏览器、URL 校验、输入内容隔离 |
| 平台页面频繁更新 | 识别适配器失效 | 适配器独立、特征规则版本化、失败降级 |
| 作者资料权限不一致 | 敏感信息泄露 | 复用模块 1 授权模型，Service 层强制校验 |

需要在进入编码前进一步确认：

1. 期刊基础信息是否允许多个用户共享，还是按用户工作空间隔离；
2. 哪些规则需要强制人工确认，哪些低风险规则允许自动确认；
3. 指南网页快照的保留期限和本地磁盘空间上限；
4. V0.1 是否需要 APC 费用的定期监测；
5. 后台任务采用数据库轮询还是引入 Celery 等任务队列。

---

## 14. 与其他模块的衔接

```text
模块 1：稿件与作者资料管理
          |
          v
模块 2：出版社与期刊识别
          |
          | 输出 Journal Submission Profile
          v
模块 3：投稿账号管理与授权
          |
          v
模块 4：自动化投稿执行
          |
          v
模块 5：投稿状态与进度跟踪
```

模块 2 的输出应成为后续模块的稳定输入。模块 3 负责在作者授权范围内管理投稿账号；模块 4 根据已确认的平台适配器执行投稿流程；模块 5 负责投稿后的状态和进度跟踪。

**模块 2 的核心交付标准：目标期刊身份可信、投稿入口可追溯、投稿规则有来源和版本、合规检查结果可解释。**
