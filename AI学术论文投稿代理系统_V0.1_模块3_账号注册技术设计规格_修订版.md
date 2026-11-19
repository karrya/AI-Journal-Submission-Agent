# AI 学术论文投稿代理系统 V0.1

# 模块 3：出版社与期刊账号注册技术设计规格

-   **文档版本**：V0.1-R2
-   **文档状态**：修订版设计基线（待评审）
-   **适用系统**：AI 学术论文投稿代理系统
-   **模块名称**：模块 3------出版社与期刊账号注册
-   **技术架构**：Vue 3 + TypeScript + Element Plus；FastAPI +
    Pydantic + SQLAlchemy 2.0；MySQL；Playwright
-   **部署方式**：本地电脑运行
-   **R2 修订范围**：复用现有出版社与投稿入口、强化作者注册授权、补齐 Worker 租约与心跳、一次性确认记录、提交结果核对、账号域唯一性及临时秘密存储。
-   **数据库规范**：MySQL InnoDB、utf8mb4、UUID 主键、UTC
    时间、DATETIME(6)

------------------------------------------------------------------------

## 1. 文档目的

本文档定义 AI 学术论文投稿代理系统 V0.1 的模块
3------出版社与期刊账号注册模块的业务边界、总体架构、业务流程、状态机、数据库设计、API、浏览器自动化、邮箱验证、安全控制、异常恢复、测试验收及实施计划。

本模块承接：

-   **模块 1：稿件与作者资料管理**，提供经授权的作者注册资料。
-   **模块
    2：出版社与期刊识别**，提供出版社、期刊、投稿平台及注册入口信息。
-   **模块
    3：账号注册**，在作者明确授权的前提下，辅助完成投稿平台账号注册、邮箱验证及注册结果归档。

本文档是 V0.1
的设计基线。具体出版社页面可能变化，正式接入前必须在目标平台的使用条款、自动化政策及授权范围内进行验证。

## 2. 设计目标与范围

### 2.1 设计目标

1.  根据模块 2 提供的注册入口打开目标平台。
2.  从模块 1 获取作者资料，自动完成字段识别和表单填写。
3.  根据平台规则生成强密码，并安全保存可供后续登录使用的凭据。
4.  遇到
    CAPTCHA、平台安全挑战或无法可靠识别的页面时暂停自动化，等待人工处理。
5.  通过作者明确授权的邮箱连接方式检索验证邮件。
6.  提取并安全展示验证邮件信息及验证链接，等待授权人员确认后再访问。
7.  准确记录账号创建、邮箱验证及任务执行状态。
8.  支持不同作者之间的数据、邮箱授权和账号凭据隔离。
9.  支持任务审计、失败重试、浏览器中断恢复和后续账号管理。

### 2.2 V0.1 范围

**首期出版社范围（强制白名单）：**

V0.1 账号注册仅支持以下五家出版社旗下、且已完成期刊入口核验及平台适配器验收的期刊：

1. Springer Nature（项目简称：Spring；内部代码建议 `SPRINGER_NATURE`）
2. Elsevier（内部代码 `ELSEVIER`）
3. John Wiley & Sons / Wiley（内部代码 `WILEY`）
4. Taylor & Francis（内部代码 `TAYLOR_FRANCIS`）
5. SAGE Publishing（内部代码 `SAGE`）

出版社在白名单中，不代表其旗下所有期刊或所有投稿入口都自动获得支持。必须逐个核验具体期刊的官方注册/投稿入口、实际平台类型、域名及平台自动化政策。只有出版社、期刊入口和适配器三项检查均通过，任务才可进入自动化流程。

未列入上述名单的出版社在 V0.1 中不创建自动注册任务；如需扩展，必须通过版本升级和正式评审。

**纳入范围：**

-   注册任务创建、查看、取消和状态管理。
-   注册入口打开及页面基本识别。
-   作者资料读取、字段映射、表单填写和填写结果检查。
-   密码生成与凭据安全保存。
-   CAPTCHA 人工介入及浏览器会话暂停/恢复。
-   注册提交前人工确认。
-   授权邮箱的验证邮件检索。
-   验证链接人工确认、访问和结果检查。
-   注册结果入库、审计日志及基础异常恢复。

**暂不纳入范围：**

-   CAPTCHA 自动破解、绕过或第三方代解。
-   绕过登录保护、MFA、多因素认证、访问限制或反机器人措施。
-   未经授权访问作者邮箱或替作者同意平台协议、声明及法律承诺。
-   自动填写需要作者作出实质性学术、伦理、利益冲突或版权判断的内容。
-   自动处理付款、订阅、收费或其他财务授权。
-   未经平台允许的大规模批量注册。
-   保证所有出版社和所有期刊均可自动注册。

### 2.3 关键设计原则

-   **授权先行**：每个注册任务必须关联有效作者授权。
-   **人工控制关键动作**：注册提交、平台协议确认、邮箱验证链接访问等关键节点必须有明确的人工确认。
-   **不绕过安全机制**：CAPTCHA 或其他安全挑战出现时暂停，交由人工处理。
-   **最小权限**：邮箱连接仅申请完成邮件检索所需的最小权限。
-   **凭据隔离**：密码、OAuth
    Token、邮箱访问凭据不以明文形式存入业务表或日志。
-   **可审计**：关键状态变化、人工确认和外部操作均记录审计事件。
-   **可恢复**：任务状态持久化，浏览器中断后先检查外部实际状态，再决定是否继续或重试。
-   **平台适配**：不同投稿系统使用独立适配器，通用适配器不得假定所有网站表单结构相同。

## 3. 角色与权限

  ----------------------------------------------------------------------------------------------
  角色                                权限
  ----------------------------------- ----------------------------------------------------------
  系统管理员                          管理系统配置、适配器、任务运行策略；不得默认查看作者密码

  投稿代理操作员                      在授权范围内创建任务、查看任务、处理人工验证节点

  作者/授权人                         提供并确认个人资料，授权账号注册，确认注册提交及邮箱验证

  系统服务                            执行获准的页面识别、表单填写、邮件检索、状态更新和审计
  ----------------------------------------------------------------------------------------------

### 3.1 授权检查

任务启动前至少检查：

1.  作者授权记录存在且状态有效。
2.  授权范围包含目标出版社/期刊及账号注册行为。
3.  授权未过期、未撤销。
4.  作者资料的使用目的与本次注册一致。
5.  使用的邮箱确属本次授权范围。
6.  执行人员具有对应作者数据访问权限。

注册授权必须使用独立权限代码，例如 `account:register`、`email:verification:read` 和 `credential:use`，不得用普通稿件读取权限替代。操作员的数据访问权限与作者对本次注册行为的同意必须分别校验。即使是系统管理员，也不能仅凭角色绕过作者对注册、凭据使用或邮箱读取的明确授权；系统配置权限不能代替作者授权。

授权撤销后，未开始的任务立即取消；运行中的任务应停止新的外部操作，并进入
`CANCELLED`
或专门的授权撤销状态。不得因任务已创建而继续使用已撤销的授权。

## 4. 上下游模块接口

### 4.1 模块 1 输入

模块 3
通过内部服务接口读取作者资料，不直接接受前端提交的任意作者敏感字段作为权威数据。

建议读取字段：

-   作者 ID
-   姓名及姓名顺序
-   主邮箱及经授权可用于注册的邮箱
-   单位、院系/部门
-   通讯地址、城市、州/省、邮编、国家
-   电话及国家区号
-   ORCID（仅当目标平台注册需要且作者资料已验证）
-   资料更新时间及资料完整性状态

读取时执行字段级授权和必要字段校验。不要将作者全部资料复制到注册任务表。

### 4.2 模块 2 输入

-   出版社 ID、出版社名称及出版社白名单状态
-   期刊 ID、期刊名称（注册任务中必须提供具体期刊）
-   投稿平台名称/类型
-   注册页面 URL
-   平台域名白名单或已验证域名
-   适配器类型及版本
-   平台识别置信度、识别依据及更新时间

注册入口必须来自已识别并经过安全检查的数据。不得直接访问用户输入的任意 URL。注册任务还必须通过 V0.1 五家出版社白名单、具体期刊入口验证状态及适配器启用状态检查。

### 4.3 模块 3 输出

-   出版社账号记录
-   注册任务及最终状态
-   邮箱验证状态和时间
-   注册执行摘要
-   失败原因及可重试建议
-   审计事件

## 5. 总体架构

### 5.1 逻辑架构

``` text
Vue 3 前端
  ├── 注册任务列表
  ├── 注册任务详情
  ├── 人工处理中心
  └── 出版社账号管理
          |
          v
FastAPI /api/v1
  ├── Registration API
  ├── Authorization Guard
  └── Schema Validation
          |
          v
业务服务层
  ├── RegistrationService
  ├── RegistrationWorkflowService
  ├── BrowserService
  ├── FormMappingService
  ├── PasswordService
  ├── CredentialService
  ├── EmailVerificationService
  ├── AdapterRegistry
  └── AuditService
          |
          +--------------------+
          |                    |
          v                    v
Playwright Worker         Mail Provider Adapter
  ├── Browser Context       ├── OAuth/API
  ├── Page Detector         └── IMAP（受控、可选）
  ├── Form Filler
  └── Human Handoff
          |                    |
          +----------+---------+
                     |
          +----------+----------+
          |                     |
          v                     v
        MySQL              本地安全存储
  ├── 账号/任务数据        ├── 密钥链/凭据库
  ├── 状态与审计           ├── 浏览器会话临时数据
  └── 授权关联             └── 临时验证数据
```

### 5.2 组件职责

  组件                       职责
  -------------------------- --------------------------------------------
  Registration API           接收任务请求、查询任务、处理人工确认请求
  Authorization Guard        校验用户身份、作者授权和字段访问范围
  RegistrationService        组织注册业务流程
  WorkflowService            管理状态迁移、步骤执行和恢复
  BrowserService             管理 Playwright 浏览器、页面及会话生命周期
  FormMappingService         将作者字段映射到网页字段
  PasswordService            按平台规则生成密码
  CredentialService          调用操作系统密钥链或加密凭据库
  EmailVerificationService   检索授权邮箱中的验证邮件并解析候选链接
  AdapterRegistry            选择出版社/投稿平台适配器
  AuditService               记录不可抵赖的关键业务审计事件

### 5.3 后台任务执行

浏览器自动化不得在普通 HTTP 请求生命周期内长时间运行。API
只负责创建任务和返回任务 ID；后台 Worker 负责执行任务。

V0.1 可使用独立 Python Worker
进程和数据库任务轮询。若后续并发量增加，再引入 Redis + Celery/RQ
等任务队列。任务领取必须使用数据库事务和行锁，防止同一任务被多个 Worker
同时执行。

## 6. 业务流程

### 6.1 主流程

1.  操作员选择作者、出版社及可选期刊。
2.  系统检查作者授权、作者资料完整性和邮箱授权。
3.  系统从模块 2 获取注册入口及平台适配器信息。
4.  创建注册任务，状态为 `PENDING`。
5.  Worker 领取任务并检查 URL 域名、HTTPS、重定向和适配器策略。
6.  Playwright 打开注册页面。
7.  适配器识别注册表单及字段。
8.  FormMappingService 将作者资料映射至页面字段。
9.  系统填写允许自动填写的字段，并进行格式和完整性检查。
10. PasswordService 生成密码，CredentialService 安全保存。
11. 如遇 CAPTCHA、安全挑战、MFA
    或无法识别的页面，立即暂停并请求人工处理。
12. 页面填写完成后展示提交预览。
13. 授权人员确认注册信息及平台声明后，系统才执行注册提交。
14. 系统检查提交结果，更新为 `SUBMITTED` 或 `WAITING_EMAIL`。
15. EmailVerificationService 在授权范围内检索验证邮件。
16. 系统展示发件人、主题、收件时间、目标域名和脱敏链接信息。
17. 授权人员确认后，系统才打开验证链接。
18. 系统重新检查目标域名和页面状态，确认邮箱验证结果。
19. 更新账号状态、注册时间、邮箱验证时间及任务状态。
20. 写入审计事件并向前端返回执行摘要。

### 6.2 流程图

``` mermaid
flowchart TD
    A[创建注册任务] --> B{作者授权有效?}
    B -- 否 --> X[拒绝执行并审计]
    B -- 是 --> C[读取作者资料和平台信息]
    C --> D[检查注册 URL 和适配器]
    D --> E[打开注册页面]
    E --> F[识别并填写表单]
    F --> G{是否出现安全挑战?}
    G -- 是 --> H[暂停并等待人工处理]
    H --> I{人工处理完成?}
    I -- 否 --> J[保持暂停或取消]
    I -- 是 --> K[重新检查页面]
    G -- 否 --> K
    K --> L[生成并安全保存密码]
    L --> M[展示注册提交预览]
    M --> N{授权人员确认?}
    N -- 否 --> J
    N -- 是 --> O[提交注册]
    O --> P[检索授权邮箱]
    P --> Q{发现有效验证邮件?}
    Q -- 否 --> R[等待邮件或超时]
    R --> P
    Q -- 是 --> S[展示邮件和验证链接信息]
    S --> T{授权人员确认访问?}
    T -- 否 --> J
    T -- 是 --> U[访问验证链接]
    U --> V{验证成功?}
    V -- 是 --> W[更新账号并完成任务]
    V -- 否 --> Y[记录失败或转人工处理]
```

## 7. 注册状态机

### 7.1 状态定义

  状态                       含义                            是否可继续自动执行
  -------------------------- ------------------------------- --------------------
  `PENDING`                  等待执行                        是
  `CHECKING_AUTHORIZATION`   检查授权和资料                  是
  `OPENING_PAGE`             正在打开注册页面                是
  `DETECTING_FORM`           正在识别表单                    是
  `FILLING_FORM`             正在填写表单                    是
  `WAITING_CAPTCHA`          等待人工处理 CAPTCHA/安全挑战   否
  `READY_TO_SUBMIT`          已完成填写，等待人工确认提交    否
  `SUBMITTING`               已获人工确认，正在执行一次注册提交 是，仅执行当前提交动作
  `SUBMITTED`                已提交注册信息                  视平台流程而定
  `SUBMISSION_UNKNOWN`       提交请求已发出但平台结果未知      否，必须先核对平台状态
  `WAITING_EMAIL`            等待验证邮件                    是，按策略轮询
  `WAITING_EMAIL_CONFIRM`    已找到邮件，等待人工确认链接    否
  `VERIFYING_EMAIL`          已获确认，正在验证邮箱          是
  `REGISTERED`               账号注册且要求的验证已完成      否
  `NEEDS_MANUAL_REVIEW`      页面或结果无法可靠判断          否
  `FAILED`                   任务失败                        否，需显式重试
  `CANCELLED`                任务取消或授权撤销              否
  `EXPIRED`                  等待人工处理或邮件验证超时      否

### 7.2 状态迁移规则

-   状态只能通过 WorkflowService 迁移，不允许前端直接指定任意状态。
-   每次迁移必须检查当前状态、目标状态和触发条件。
-   `WAITING_CAPTCHA` 只能由人工处理完成事件恢复，不能由自动识别器绕过。
-   `READY_TO_SUBMIT` 必须收到有效的人工确认令牌才能进入 `SUBMITTING`；只有取得平台接受注册的明确证据后才能进入 `SUBMITTED`。
-   提交超时、连接中断或页面结果不明确时必须进入 `SUBMISSION_UNKNOWN`，不得直接重发或标记成功。
-   `WAITING_EMAIL_CONFIRM` 必须收到人工确认才能进入 `VERIFYING_EMAIL`。
-   `REGISTERED` 必须有平台成功证据，不能仅凭点击提交按钮判定。
-   对结果不确定的提交，不得盲目重复提交；应先检查平台账号或页面状态。
-   取消、授权撤销、超时等终止操作必须写入审计日志。

### 7.3 幂等性

创建任务、确认提交、确认验证链接和任务恢复接口应支持幂等处理。

建议客户端传递
`Idempotency-Key`。数据库对任务关键动作建立唯一约束或动作记录，防止网络重试导致重复注册、重复确认或重复审计业务事件。

## 8. 浏览器自动化设计

### 8.1 Playwright 使用原则

-   使用独立 Worker 管理浏览器。
-   每个注册任务使用隔离的 Browser Context。
-   默认禁止复用其他作者的 Cookie、Local Storage 或浏览器会话。
-   浏览器版本、Playwright 版本及适配器版本应记录。
-   任务结束后关闭页面和
    Context；需要人工处理时，按安全策略短期保留会话。
-   不将浏览器存储状态导出到普通目录或提交到代码仓库。
-   不在日志中记录 Cookie、Authorization Header、密码或完整验证 URL。

### 8.2 页面识别优先级

优先使用稳定、可访问性友好的页面语义：

1.  Label 与关联输入框。
2.  `get_by_label()`。
3.  `get_by_role()` 及可访问名称。
4.  `get_by_placeholder()`。
5.  经适配器验证的稳定属性。
6.  CSS Selector 作为最后手段。

禁止仅依赖容易变化的绝对 XPath、页面坐标或随机生成的 CSS 类名。

### 8.3 表单字段映射

建立统一字段字典：

  内部字段          常见页面字段                        校验
  ----------------- ----------------------------------- ----------------------
  `given_name`      First name / Given name             非空、长度
  `middle_name`     Middle name                         可选
  `family_name`     Last name / Family name / Surname   非空、长度
  `email`           Email / E-mail                      邮箱格式
  `confirm_email`   Confirm email                       与邮箱一致
  `institution`     Institution / Organization          非空或按平台要求
  `department`      Department                          可选
  `address_line1`   Address / Street                    按平台要求
  `city`            City / Town                         按平台要求
  `region`          State / Province / Region           按国家规则
  `postal_code`     ZIP / Postal code                   按国家规则
  `country`         Country / Region                    使用规范国家代码映射
  `phone`           Phone / Telephone                   规范化并保留国家区号
  `orcid`           ORCID iD                            仅在需要时校验格式

字段映射必须保留来源、映射规则、置信度和人工修正记录。低置信度字段不得自动填入，应提示人工选择。

### 8.4 页面变化与未知字段

-   适配器应有版本号和适用平台范围。
-   页面结构与适配器预期不一致时进入 `NEEDS_MANUAL_REVIEW`。
-   不允许 AI 根据页面文本猜测后直接提交敏感字段。
-   识别结果应保存为结构化字段清单，不保存不必要的完整页面内容。
-   截图如用于故障排查，必须脱敏并按短期保留策略管理。

### 8.5 浏览器会话与人工接管

当需要人工处理 CAPTCHA 或安全挑战时：

1.  Worker 将任务置为 `WAITING_CAPTCHA`。
2.  记录当前步骤、页面 URL（脱敏）和会话租约。
3.  前端通知操作人员。
4.  操作人员在受控浏览器窗口中完成平台允许的人工验证。
5.  Worker 重新读取页面状态并验证挑战是否已解除。
6.  验证未解除时继续等待或转人工审查，不尝试绕过。
7.  会话超时后关闭 Context，并按恢复策略重新打开页面或转人工处理。

默认后台自动化使用无头浏览器；需要人工接管时，由 `BrowserHandoffService` 在当前用户的本地桌面打开受控的有头浏览器窗口。任务只保存不可直接恢复会话的 `browser_handoff_id`、当前步骤和租约，不导出 Cookie 或 Storage State。人工会话必须有明确有效期，超时或任务结束后立即关闭 Context。Worker 崩溃后不得假定人工会话仍存在，应重新打开安全入口并先核对平台状态。

## 9. 密码与凭据安全

### 9.1 密码生成

使用 Python `secrets` 生成密码，不使用 `random` 或固定模板。

要求：

-   默认长度建议不少于 16 位，具体以平台要求为准。
-   按平台策略组合大小写字母、数字和允许的特殊字符。
-   避免平台不接受的字符。
-   避免将作者姓名、邮箱、单位等个人信息拼入密码。
-   生成后在提交前检查平台规则。
-   不因重试而无条件更换已成功保存且已提交的密码。

### 9.2 凭据保存

账号密码必须可供后续登录使用，因此不能只保存不可逆哈希。建议：

-   本地单机部署优先使用操作系统 Keychain、Credential Manager 或 Secret
    Service。
-   凭据库只保存随机 `credential_ref`，业务数据库不存密码明文。
-   如果操作系统密钥链不可用，使用经认证加密的本地凭据库；加密密钥应与业务数据库分离。
-   加密算法优先使用成熟 AEAD 实现，例如 AES-256-GCM 或
    ChaCha20-Poly1305。
-   密钥不得硬编码在源码、配置样例或数据库中。
-   读取凭据必须经过用户身份认证、权限校验并记录审计事件。
-   不提供普通管理员批量导出所有作者密码的功能。

### 9.3 邮箱凭据

优先使用邮箱服务商官方 OAuth/API。IMAP
仅在服务商支持、用户明确授权且安全配置满足要求时使用。

-   使用最小权限 Scope。
-   Token 加密存储于安全凭据库。
-   支持撤销授权和重新授权。
-   不把 Token 放入任务表、日志或前端响应。
-   不把邮箱密码作为普通注册表单字段保存。

## 10. CAPTCHA 与人工介入

### 10.1 处理规则

检测到 CAPTCHA、MFA、设备验证、风险挑战或平台明确要求人工操作时：

-   立即停止自动化操作。
-   不调用破解、识别代答或绕过服务。
-   不尝试更换 IP、伪造浏览器指纹或规避访问限制。
-   将任务置为 `WAITING_CAPTCHA` 或 `NEEDS_MANUAL_REVIEW`。
-   在前端显示任务、平台、当前步骤和处理指引。
-   人工处理完成后，Worker 只检查页面状态，不读取或保存 CAPTCHA 答案。

### 10.2 人工介入记录

至少记录：

-   任务 ID
-   介入类型
-   触发时间
-   操作人员 ID
-   处理开始和结束时间
-   处理结果
-   是否恢复自动化
-   失败或取消原因

不得记录 CAPTCHA 内容或答案。

## 11. 邮箱验证设计

### 11.1 邮件检索

检索条件应综合使用：

-   已授权邮箱地址
-   目标出版社/平台的已验证发件人或域名规则
-   任务创建时间及合理时间窗口
-   邮件主题关键词
-   平台账号邮箱
-   邮件唯一标识，防止重复处理

发件人显示名称不能单独作为可信依据。必须检查真实发件地址和邮件中的链接域名。

### 11.2 邮件解析

提取：

-   发件人地址
-   邮件主题
-   收件时间
-   Message-ID
-   纯文本/HTML 内容中的候选验证链接
-   候选链接域名
-   邮件与当前注册任务的匹配依据

邮件正文属于不可信输入。不得执行邮件中的脚本、附件或其他指令。

### 11.3 验证链接安全

-   仅接受 HTTPS 链接。
-   检查目标域名是否与已验证平台域名白名单匹配。
-   拒绝 IP 字面量、异常端口、非预期协议及可疑重定向。
-   对短链接或无法判断最终域名的链接转人工核验。
-   不在日志、普通数据库字段或分析事件中保存完整 Token URL。
-   前端默认展示脱敏链接和目标域名。
-   人工确认必须明确说明访问该链接可能会激活账号。
-   确认后由后端受控访问，并检查最终结果。
-   验证链接过期、已使用或结果不明确时转人工处理，不反复点击。

### 11.4 邮件访问权限

邮箱连接必须绑定到作者授权关系。系统只检索与当前注册任务相关的邮件，不应扫描或保存作者全部邮箱内容。

## 12. 数据库设计

### 12.1 通用规范

-   主键：`CHAR(36)` UUID。
-   存储引擎：InnoDB。
-   字符集：`utf8mb4`。
-   时间：统一 UTC，使用 `DATETIME(6)`。
-   业务表包含 `created_at`、`updated_at`、`created_by`（适用时）。
-   默认软删除；审计和历史记录不可更新或物理删除。
-   外键删除策略不得级联删除注册审计和历史记录。
-   现有 `publishers`、`journals`、`journal_submission_portals`、`author_authorizations` 和 `operation_logs` 不得为模块 3 重复建表；新表只保存模块 3 自有账号、任务、确认和邮箱验证数据。
-   作者、授权、出版社、期刊等外键应按现有项目规范建立。
-   下列 SQL 为逻辑设计示例，落地前需与项目现有基础表和命名规范统一。

### 12.2 `publisher_accounts` 出版社账号表

``` sql
CREATE TABLE publisher_accounts (
    id CHAR(36) NOT NULL PRIMARY KEY,
    author_id CHAR(36) NOT NULL,
    publisher_id CHAR(36) NOT NULL,
    journal_id CHAR(36) NULL,
    platform_code VARCHAR(64) NOT NULL,
    account_namespace VARCHAR(255) NOT NULL,
    account_email VARCHAR(255) NOT NULL,
    normalized_email VARCHAR(255) NOT NULL,
    platform_account_id VARCHAR(255) NULL,
    username VARCHAR(255) NULL,
    credential_ref VARCHAR(255) NULL,
    account_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    email_verified_at DATETIME(6) NULL,
    registered_at DATETIME(6) NULL,
    last_checked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by CHAR(36) NOT NULL,
    deleted_at DATETIME(6) NULL,
    active_account_email VARCHAR(255)
        GENERATED ALWAYS AS (IF(deleted_at IS NULL, normalized_email, NULL)) STORED,
    UNIQUE KEY uk_platform_account (platform_code, account_namespace, active_account_email),
    KEY idx_author_id (author_id),
    KEY idx_publisher_id (publisher_id),
    KEY idx_journal_id (journal_id),
    KEY idx_account_status (account_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

说明：

-   `credential_ref` 仅引用安全凭据库，不保存密码。
-   `account_namespace` 保存经平台核验的账号域或平台实例，不能只凭平台代码合并不同账号体系；`platform_account_id` 在平台返回稳定账号 ID 时保存。
-   `active_account_email` 仅在记录未软删除时取值，使历史账号保留的同时允许按平台规则重新登记。
-   `platform_code`
    区分投稿平台账号体系，避免将同一出版社不同平台错误合并。
-   唯一约束需结合平台实际账号唯一规则评审；若同一邮箱允许多个独立账号，应调整唯一键。
-   `account_status` 与注册任务状态分开管理。

### 12.3 `registration_tasks` 注册任务表

``` sql
CREATE TABLE registration_tasks (
    id CHAR(36) NOT NULL PRIMARY KEY,
    account_id CHAR(36) NULL,
    author_id CHAR(36) NOT NULL,
    publisher_id CHAR(36) NOT NULL,
    journal_id CHAR(36) NULL,
    authorization_id CHAR(36) NOT NULL,
    platform_code VARCHAR(64) NOT NULL,
    registration_url TEXT NOT NULL,
    adapter_code VARCHAR(64) NULL,
    adapter_version VARCHAR(32) NULL,
    task_status VARCHAR(40) NOT NULL DEFAULT 'PENDING',
    current_step VARCHAR(100) NULL,
    retry_count INT NOT NULL DEFAULT 0,
    worker_id VARCHAR(64) NULL,
    lease_expires_at DATETIME(6) NULL,
    available_at DATETIME(6) NULL,
    last_heartbeat_at DATETIME(6) NULL,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    last_external_action VARCHAR(100) NULL,
    external_evidence_ref VARCHAR(255) NULL,
    browser_handoff_id VARCHAR(64) NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    started_at DATETIME(6) NULL,
    last_activity_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by CHAR(36) NOT NULL,
    UNIQUE KEY uk_registration_idempotency (idempotency_key),
    KEY idx_author_status (author_id, task_status),
    KEY idx_account_id (account_id),
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 12.4 `email_verification_records` 邮箱验证记录表

``` sql
CREATE TABLE email_verification_records (
    id CHAR(36) NOT NULL PRIMARY KEY,
    account_id CHAR(36) NOT NULL,
    task_id CHAR(36) NOT NULL,
    email_address VARCHAR(255) NOT NULL,
    email_message_id VARCHAR(255) NULL,
    sender_address VARCHAR(255) NULL,
    subject VARCHAR(500) NULL,
    received_at DATETIME(6) NULL,
    link_domain VARCHAR(255) NULL,
    verification_ref VARCHAR(255) NULL,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    confirmed_by CHAR(36) NULL,
    confirmed_at DATETIME(6) NULL,
    verified_at DATETIME(6) NULL,
    expires_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uk_task_message (task_id, email_message_id),
    KEY idx_account_id (account_id),
    KEY idx_verification_status (verification_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

注意：表中不存完整验证链接或链接中的 Token。`verification_ref` 只引用 `TemporarySecretStore` 中设置了 TTL 的加密临时记录。该存储必须提供 `put`、`get`、`delete` 和过期清理能力，密钥与业务数据库分离；候选链接在使用、过期或任务取消后删除，且不得进入备份、普通日志或审计正文。

### 12.5 注册审计与现有 `operation_logs`

模块 3 复用现有不可变 `operation_logs`，使用 `target_type=registration_task`、`publisher_account` 或 `registration_confirmation`，不再建立一套内容重复的注册审计表。任务时间线如需额外展示，可使用追加式 `registration_task_events`，但不能用时间线替代业务审计。

审计 `after_summary` 仅允许白名单字段，例如适配器版本、状态迁移、错误代码和人工操作 ID。禁止写入密码、Token、Cookie、完整验证链接、邮箱正文及不必要的个人资料。

### 12.6 `registration_confirmations` 一次性人工确认表

注册提交和邮箱验证访问共用以下一次性确认记录；除 `consumed_at` 的单次条件更新外，其他字段不得修改。原始令牌只在创建时返回给授权人员，数据库仅保存哈希；`summary_hash` 必须绑定当前作者、邮箱、入口、表单映射版本和提交摘要，内容变化后旧确认立即失效。

``` sql
CREATE TABLE registration_confirmations (
    id CHAR(36) NOT NULL PRIMARY KEY,
    task_id CHAR(36) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    summary_hash CHAR(64) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    requested_by CHAR(36) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    consumed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    UNIQUE KEY uk_confirmation_token (token_hash),
    KEY idx_confirmation_task (task_id, action_type, created_at),
    CONSTRAINT fk_confirmation_task
        FOREIGN KEY (task_id) REFERENCES registration_tasks(id),
    CONSTRAINT fk_confirmation_user
        FOREIGN KEY (requested_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

确认操作必须同时校验任务当前状态、操作人、CSRF、有效期和 `summary_hash`，并在同一事务内将 `consumed_at` 条件更新为当前时间。`consumed_at` 已存在、已过期或摘要不匹配时一律拒绝，不能重放。

### 12.7 可选：`registration_task_events`

如需更强的状态追踪，可增加事件表，保存每次状态迁移的旧状态、新状态、触发者、触发原因和时间。该表应只追加，不覆盖历史记录。

## 13. API 设计

统一前缀：`/api/v1`

所有接口必须执行认证、CSRF/Origin（适用于 Cookie
会话的修改请求）、作者授权、字段级权限和审计检查。

### 13.1 创建注册任务

`POST /registration/tasks`

请求示例：

``` json
{
  "author_id": "uuid",
  "publisher_id": "uuid",
  "journal_id": "uuid",
  "authorization_id": "uuid",
  "platform_code": "EDITORIAL_MANAGER",
  "idempotency_key": "client-generated-unique-key"
}
```

注册 URL 应优先从模块 2 的已验证记录读取，不允许客户端任意指定未验证
URL。

响应示例：

``` json
{
  "task_id": "uuid",
  "status": "PENDING",
  "message": "Registration task created"
}
```

### 13.2 查询任务列表

`GET /registration/tasks`

支持筛选：

-   `author_id`
-   `publisher_id`
-   `journal_id`
-   `task_status`
-   `created_from`
-   `created_to`
-   分页参数

### 13.3 查询任务详情

`GET /registration/tasks/{task_id}`

返回当前状态、步骤、平台信息、脱敏错误信息、人工处理要求和执行摘要。不得返回密码、Token、Cookie
或完整验证链接。

### 13.4 取消任务

`POST /registration/tasks/{task_id}/cancel`

取消前检查任务状态。若外部提交已经发生，取消仅停止后续动作，不得将外部已创建的账号伪装成未注册。

### 13.5 人工处理完成

`POST /registration/tasks/{task_id}/human-actions/captcha-completed`

仅用于记录人工已完成平台要求的验证并触发页面状态复查。不得接收 CAPTCHA
答案。

### 13.6 确认注册提交

`POST /registration/tasks/{task_id}/confirm-submit`

请求应包含一次性确认令牌或确认记录
ID。后端再次展示/校验提交摘要、作者、邮箱、目标平台和授权状态。确认令牌应短时有效、一次性使用并绑定当前任务和操作人。

### 13.7 确认邮箱验证

`POST /registration/tasks/{task_id}/confirm-email-verification`

请求仅传递验证记录 ID 和一次性确认令牌，不接受任意外部
URL。后端从受控临时存储读取候选链接，重新校验域名后访问。

### 13.8 重试任务

`POST /registration/tasks/{task_id}/retry`

仅允许对可重试错误执行。必须先检查平台端实际账号状态，避免重复注册。

### 13.9 查询账号

`GET /publisher-accounts`

按作者授权范围返回账号列表。凭据引用不应返回给普通前端。

## 14. 前端页面设计

### 14.1 注册任务列表

展示：

-   任务编号
-   作者（按当前用户权限脱敏）
-   出版社/期刊
-   投稿平台
-   创建时间
-   当前步骤
-   注册状态
-   最近活动时间
-   操作入口

支持按作者、出版社、期刊、状态和时间范围筛选。

### 14.2 注册任务详情

建议分为：

1.  任务基本信息
2.  作者资料使用摘要（字段脱敏）
3.  平台识别结果
4.  表单字段映射结果
5.  执行步骤时间线
6.  人工介入记录
7.  异常信息
8.  审计事件摘要

### 14.3 人工处理中心

集中显示：

-   等待 CAPTCHA/安全挑战处理的任务
-   等待注册提交确认的任务
-   等待邮箱验证确认的任务
-   需要人工审查的任务

每项人工操作必须展示明确的操作后果、目标作者、目标平台和授权状态。

### 14.4 出版社账号管理

展示账号邮箱、出版社、投稿平台、期刊关联、账号状态、邮箱验证时间和最近检查时间。不得在列表中显示密码。

### 14.5 界面与交互品质

模块页面采用与现有系统一致的专业工作台风格，并达到以下要求：

1. **任务详情信息层级**：顶部展示作者、期刊、平台和当前状态；使用步骤条呈现授权、表单、人工确认、邮箱验证及完成阶段。
2. **执行时间线**：以时间线卡片展示阶段、耗时、降级警告和人工操作；失败或等待状态同时使用图标、文字和颜色，不只依赖颜色。
3. **人工处理中心**：按“等待验证码、等待提交确认、等待邮箱确认、需要复核”分组，提供清晰的主操作按钮和后果说明。
4. **证据与预览**：来源证据使用侧栏或抽屉展示；注册提交前使用不可编辑摘要卡片逐项核对作者、邮箱、平台和文件，不使用普通文本框冒充确认。
5. **账号管理**：使用简洁表格、状态标签和按需展开详情；敏感字段默认脱敏，不显示密码、完整验证链接或凭据引用。
6. **加载与异常**：列表使用骨架屏，空状态提供下一步操作；网络错误保留当前任务数据并支持安全重试，避免空白或无限等待。
7. **响应式与可访问性**：桌面和窄屏均可用，表单具有关联标签、键盘焦点、错误提示和足够对比度；弹窗支持 Escape 关闭，危险操作不得使用Enter默认提交。
8. **视觉克制**：统一间距、圆角、边框、阴影和状态色，不堆叠大面积渐变、无意义动画或装饰性卡片，保证信息密度和可读性。

## 15. 异常处理与恢复

### 15.1 异常分类

  ---------------------------------------------------------------------------------
  错误代码                        场景                     处理
  ------------------------------- ------------------------ ------------------------
  `AUTHORIZATION_INVALID`         授权不存在、过期或撤销   终止任务

  `AUTHOR_DATA_INCOMPLETE`        作者资料缺失             提示补全资料

  `REGISTRATION_URL_UNTRUSTED`    注册 URL 不在可信范围    拒绝访问

  `PAGE_NOT_RECOGNIZED`           页面结构无法识别         人工审查

  `FORM_FIELD_AMBIGUOUS`          字段映射不确定           人工确认

  `CAPTCHA_REQUIRED`              出现 CAPTCHA             暂停等待人工

  `MFA_REQUIRED`                  出现多因素验证           人工处理

  `SUBMISSION_RESULT_UNKNOWN`     提交结果不明确           先查询平台状态

  `EMAIL_NOT_FOUND`               暂未收到验证邮件         限时轮询后转人工

  `EMAIL_SENDER_UNTRUSTED`        发件人不可信             拒绝处理

  `VERIFICATION_LINK_UNTRUSTED`   验证链接域名不可信       拒绝访问

  `VERIFICATION_EXPIRED`          验证链接过期             请求重新发送

  `BROWSER_DISCONNECTED`          浏览器中断               安全恢复或人工处理

  `PLATFORM_RATE_LIMITED`         平台限流                 遵守
                                                           Retry-After，退避重试

  `PLATFORM_AUTOMATION_BLOCKED`   平台禁止自动化           停止自动操作，人工处理
  ---------------------------------------------------------------------------------

### 15.2 重试策略

-   只对明确可重试的网络错误、暂时服务不可用等场景重试。
-   使用指数退避和随机抖动。
-   遵守平台限流和 `Retry-After`。
-   表单提交超时不能直接重发；先检查账号是否已创建。
-   CAPTCHA、MFA、授权失败、域名不可信等不得自动重试。
-   超过最大重试次数后进入 `NEEDS_MANUAL_REVIEW` 或 `FAILED`。

### 15.3 Worker 崩溃恢复

任务应记录：

-   Worker ID
-   任务租约开始时间
-   最后心跳时间
-   当前步骤
-   最近一次成功的外部操作
-   浏览器 Context 的临时关联信息（不保存明文会话凭据）

Worker 重启后：

1.  扫描租约过期的非终态任务。
2.  获取任务锁。
3.  检查授权是否仍有效。
4.  检查外部平台注册状态。
5.  根据当前步骤决定恢复、等待人工或终止。
6.  记录恢复事件。

不得在无法确认外部状态时重复执行提交动作。

## 16. 安全与隐私要求

### 16.1 URL 与 SSRF 防护

注册入口和验证链接都属于不可信输入。必须：

-   仅允许 HTTPS。
-   使用平台域名白名单。
-   校验 DNS 解析结果，阻止回环、私网、链路本地和保留地址。
-   防止 DNS Rebinding。
-   对每次重定向重新校验协议、主机和解析地址。
-   限制端口。
-   禁止访问本地文件协议、脚本协议及非预期协议。
-   不允许浏览器通过页面请求访问本机管理端口或内部服务。
-   对下载、弹窗、文件上传等行为实施限制。

### 16.2 浏览器隔离

-   不同作者使用不同 Browser Context。
-   不跨任务共享 Cookie、Local Storage、缓存或下载目录。
-   浏览器进程以普通用户权限运行。
-   限制文件系统访问和下载目录。
-   不在截图中暴露密码、完整邮箱内容或验证 Token。
-   人工会话设置超时和自动关闭策略。

### 16.3 日志脱敏

日志禁止记录：

-   密码
-   OAuth Access Token / Refresh Token
-   Cookie / Session ID
-   完整验证链接
-   邮箱正文
-   身份认证密钥
-   不必要的作者家庭/个人地址等资料

可记录字段名、校验结果、状态变化、错误代码和脱敏邮箱。

### 16.4 数据保留

-   注册任务和审计数据按系统数据保留政策管理。
-   邮件正文不长期保存，优先仅保留必要元数据。
-   临时验证链接应在使用、过期或任务取消后删除。
-   浏览器临时数据在任务结束后清理。
-   凭据删除应同时处理安全凭据库中的实际秘密，而不仅是删除数据库引用。
-   作者撤销授权后，按授权协议和数据保留政策处理其资料与凭据。

## 17. 出版社/投稿平台适配器

### 17.1 设计原则

出版社不一定只有一个投稿平台，同一平台也可能被多个出版社或期刊使用。因此适配器应按实际投稿系统或平台类型组织，而不是仅按出版社名称组织。

V0.1 的业务支持范围由五家出版社白名单限定，但技术适配器按实际投稿系统/平台组织。不得因为某出版社已列入白名单，就推断该出版社旗下所有期刊均可自动注册。每个期刊入口都必须独立核验并登记。

建议目录：

``` text
account_registration/
  adapters/
    base_adapter.py
    adapter_registry.py
    generic_adapter.py
    editorial_manager_adapter.py
    manuscript_central_adapter.py
    platform_x_adapter.py
```

具体适配器名称和实现需根据模块 2
的识别结果、平台实际版本及授权测试确定。

### 17.2 基础接口

``` python
from abc import ABC, abstractmethod

class BaseRegistrationAdapter(ABC):

    @abstractmethod
    async def open_registration_page(self, page, platform_info):
        """打开经过验证的注册入口。"""
        raise NotImplementedError

    @abstractmethod
    async def detect_registration_form(self, page):
        """识别注册表单并返回结构化字段。"""
        raise NotImplementedError

    @abstractmethod
    async def fill_author_information(self, page, author_data, mapping):
        """填写经过授权且映射明确的作者字段。"""
        raise NotImplementedError

    @abstractmethod
    async def validate_form(self, page):
        """检查必填项、格式及页面错误。"""
        raise NotImplementedError

    @abstractmethod
    async def get_submission_preview(self, page):
        """生成供人工确认的提交摘要。"""
        raise NotImplementedError

    @abstractmethod
    async def submit_registration(self, page, confirmation):
        """仅在收到有效人工确认后提交。"""
        raise NotImplementedError

    @abstractmethod
    async def check_registration_status(self, page):
        """根据平台证据检查账号注册状态。"""
        raise NotImplementedError
```

### 17.3 适配器注册表

适配器注册表根据模块 2
的平台代码、域名、适配器版本选择实现。无法唯一匹配时不得猜测，必须转人工审查。

### 17.4 适配器验收

每个适配器至少验证：

-   注册入口正确
-   域名白名单有效
-   表单字段映射准确
-   必填项检查正确
-   密码规则符合平台要求
-   CAPTCHA/安全挑战能正确暂停
-   提交前人工确认有效
-   注册结果判断有平台证据
-   页面结构变化能安全失败
-   不会误提交或重复提交

## 18. 测试策略

### 18.1 测试环境

-   后端：pytest。
-   数据库：独立 MySQL 测试数据库，不使用 SQLite 替代。
-   浏览器：Playwright 测试环境。
-   前端：Vue Test Utils / Vitest。
-   邮件：Mock 邮件 Provider 和隔离测试邮箱。
-   凭据：测试专用密钥链或 Mock CredentialService。
-   外部平台：优先使用平台沙箱、测试账号或明确获准的测试环境。

禁止对未经授权的真实作者账号进行自动化测试。

### 18.2 单元测试

-   密码策略生成和字符约束。
-   字段映射及置信度阈值。
-   邮箱地址规范化。
-   国家、电话和 ORCID 格式校验。
-   状态机合法迁移。
-   授权有效期和撤销检查。
-   邮件发件人及链接域名校验。
-   错误分类和重试策略。
-   日志脱敏。

### 18.3 集成测试

-   创建任务并关联作者授权。
-   不同作者的数据隔离。
-   Worker 领取任务的并发安全。
-   浏览器打开页面及表单识别。
-   CAPTCHA 出现后任务暂停。
-   人工完成验证后任务恢复。
-   提交前确认令牌一次性使用。
-   邮箱邮件检索与去重。
-   验证链接域名校验和人工确认。
-   浏览器崩溃后的任务恢复。
-   授权撤销后的任务停止。
-   账号注册成功后的数据库更新。

### 18.4 安全测试

-   未授权用户访问其他作者任务。
-   伪造作者 ID 或授权 ID。
-   重放人工确认令牌。
-   通过注册 URL 发起 SSRF。
-   通过重定向绕过域名白名单。
-   恶意邮件中的钓鱼链接。
-   密码、Token、Cookie 是否进入日志。
-   浏览器 Context 是否跨作者泄露。
-   CSRF、Origin 和会话过期检查。
-   数据库异常时是否出现部分提交或状态不一致。

## 19. 验收标准

  编号     验收项         通过标准
  -------- -------------- ------------------------------------
  M3-001   授权检查       无有效授权时不能启动任务
  M3-002   作者资料读取   只能读取授权范围内字段
  M3-003   注册入口       只访问模块 2 已验证的平台入口
  M3-004   页面识别       可识别已支持平台的注册表单
  M3-005   表单填写       字段映射准确，低置信度字段转人工
  M3-006   密码生成       满足平台策略且使用安全随机数
  M3-007   凭据保存       业务数据库和日志无明文密码
  M3-008   CAPTCHA        能暂停等待人工，不尝试绕过
  M3-009   注册提交       未经人工确认不得提交
  M3-010   邮箱读取       仅检索授权邮箱中与任务相关的邮件
  M3-011   验证链接       域名校验通过且经人工确认后才访问
  M3-012   注册结果       有平台证据才标记成功
  M3-013   异常恢复       Worker 中断后可安全恢复或转人工
  M3-014   幂等控制       重复请求不会导致重复提交
  M3-015   权限隔离       作者之间的任务和凭据严格隔离
  M3-016   审计           关键自动和人工操作均可追踪
  M3-017   数据清理       临时链接、会话和敏感数据按策略清理

## 20. 开发实施计划

### 阶段一：基础数据与任务框架

-   创建注册任务、账号、邮箱验证记录和审计表。
-   实现授权检查和作者资料读取。
-   实现任务状态机、任务列表和任务详情 API。
-   实现后台 Worker 和任务租约机制。

**交付物：** 数据库迁移、Pydantic
Schema、Repository、Service、API、状态机测试。

### 阶段二：浏览器自动化基础能力

-   集成 Playwright。
-   实现 Browser Context 隔离。
-   实现注册入口安全检查。
-   实现页面识别、字段映射和表单校验。
-   建立通用适配器接口。

**交付物：**
BrowserService、FormMappingService、AdapterRegistry、自动化测试。

### 阶段三：密码和人工介入

-   实现密码生成策略。
-   集成操作系统凭据库。
-   实现 CAPTCHA/安全挑战暂停。
-   实现人工接管和任务恢复。
-   实现提交预览及人工确认令牌。

**交付物：**
PasswordService、CredentialService、人工处理中心、确认接口。

### 阶段四：邮箱验证

-   实现邮箱 Provider 接口。
-   优先集成 OAuth/API。
-   实现邮件检索、去重和解析。
-   实现链接安全校验。
-   实现人工确认及验证结果检查。

**交付物：** EmailVerificationService、邮箱授权配置、验证记录页面。

### 阶段五：平台适配和验收

-   选择 1～2 个已获准测试的平台。
-   实现平台适配器。
-   完成端到端测试和安全测试。
-   验证中断恢复、授权撤销和异常流程。
-   整理部署和运维说明。

**交付物：** 平台适配器、测试报告、验收报告、V0.1 发布包。

## 21. 建议的后端目录结构

``` text
backend/
└── app/
    └── modules/
        └── account_registration/
            ├── api/
            │   └── registration.py
            ├── services/
            │   ├── registration_service.py
            │   ├── workflow_service.py
            │   ├── browser_service.py
            │   ├── form_mapping_service.py
            │   ├── password_service.py
            │   ├── credential_service.py
            │   ├── captcha_handoff_service.py
            │   ├── email_verification_service.py
            │   ├── registration_status_service.py
            │   └── audit_service.py
            ├── repositories/
            │   ├── account_repository.py
            │   ├── task_repository.py
            │   ├── email_verification_repository.py
            │   └── audit_repository.py
            ├── models/
            │   ├── publisher_account.py
            │   ├── registration_task.py
            │   ├── email_verification_record.py
            │   └── registration_audit_log.py
            ├── schemas/
            │   ├── registration.py
            │   ├── account.py
            │   └── email_verification.py
            ├── workers/
            │   ├── registration_worker.py
            │   └── task_recovery_worker.py
            ├── adapters/
            │   ├── base_adapter.py
            │   ├── adapter_registry.py
            │   └── generic_adapter.py
            ├── providers/
            │   ├── base_mail_provider.py
            │   └── oauth_mail_provider.py
            └── utils/
                ├── url_security.py
                ├── field_detector.py
                └── data_masking.py
```

## 22. V0.1 最终交付清单

1.  模块 3 数据库迁移脚本。
2.  注册任务、账号及邮箱验证相关 ORM Model。
3.  Pydantic 请求和响应 Schema。
4.  注册任务 API。
5.  授权检查与字段级访问控制。
6.  Playwright 浏览器自动化服务。
7.  通用注册适配器和适配器注册表。
8.  作者表单字段映射服务。
9.  密码生成与安全凭据服务。
10. CAPTCHA 人工介入机制。
11. 注册提交人工确认机制。
12. 邮箱 Provider 和邮件验证服务。
13. 邮箱验证人工确认机制。
14. Vue 3 注册任务列表、详情、人工处理中心和账号管理页面。
15. 状态机、任务恢复和审计功能。
16. pytest 单元测试、集成测试及安全测试。
17. 部署说明、配置说明和验收报告。

## 23. 设计结论

模块 3 应采用"任务状态机 + Playwright 浏览器自动化 + 平台适配器 +
人工关键节点确认 + 授权邮箱验证"的架构。

V0.1
的首要目标不是实现所有出版社的无人值守注册，而是建立安全、可审计、可恢复、可扩展的注册基础能力。对于
CAPTCHA、MFA、平台协议、注册提交和邮箱验证等关键节点，系统必须保留人工控制权。

建议先完成通用任务框架和浏览器自动化基础能力，再选择 1～2
个已获准测试的投稿平台完成端到端适配。后续可在不改变核心任务状态机、权限模型和凭据管理机制的前提下，逐步扩展更多平台。

------------------------------------------------------------------------

**文档结束**


---

## 24. V0.1 出版社白名单与期刊入口接入策略（本次修订新增）

### 24.1 首期支持出版社

V0.1 仅接受以下五家出版社的账号注册任务：

| publisher_code | 标准名称 | 项目显示名称 | V0.1 范围 |
|---|---|---|---|
| `SPRINGER_NATURE` | Springer Nature | Spring / Springer Nature | 纳入白名单 |
| `ELSEVIER` | Elsevier | Elsevier | 纳入白名单 |
| `WILEY` | John Wiley & Sons | Wiley / John Wiley | 纳入白名单 |
| `TAYLOR_FRANCIS` | Taylor & Francis | Taylor and Francis | 纳入白名单 |
| `SAGE` | SAGE Publishing | SAGE | 纳入白名单 |

名称归一化只用于识别和展示。数据库中必须使用稳定的 `publisher_code`，避免因简称、品牌名或拼写差异造成重复记录。

### 24.2 出版社与投稿平台的关系

**必须遵循：出版社决定业务范围，具体期刊入口决定平台类型，平台类型决定适配器。**

| 出版社 | 适配策略 | 注意事项 |
|---|---|---|
| Springer Nature | 按期刊实际入口选择适配器 | 不假定所有期刊共用一个注册系统 |
| Elsevier | 按期刊实际入口选择适配器；对已验证的 Editorial Manager 入口优先接入 | 仅支持已核验的具体期刊入口 |
| Wiley | 根据期刊实际使用的平台选择适配器，例如 ScholarOne、Research Exchange 等 | 不将 Wiley 统一视为单一平台 |
| Taylor & Francis | 根据期刊实际入口选择适配器，例如 Editorial Manager、ScholarOne 或其自有入口 | 不同期刊可能使用不同系统 |
| SAGE | 按期刊实际入口选择适配器；对已验证的 ScholarOne 入口优先接入 | 必须以具体期刊入口核验结果为准 |

上述平台名称是适配器规划方向，不构成对任一出版社全部期刊平台分布的保证。平台接入顺序应由实际目标期刊清单、测试账号、平台规则及验收结果决定。

### 24.3 支持状态枚举

出版社、期刊入口和适配器分别维护状态，不能只用一个出版社级开关代表全部能力。

建议统一支持状态：

| 状态 | 代码 | 行为 |
|---|---|---|
| 已支持 | `SUPPORTED` | 可在授权和其他校验通过后执行已验收的自动化步骤 |
| 测试中 | `TESTING` | 仅允许测试环境或指定测试账号，不允许正式作者账号自动提交 |
| 仅人工 | `MANUAL_ONLY` | 可展示官方入口和资料准备结果，不执行自动填写/提交 |
| 暂不支持 | `UNSUPPORTED` | 不创建自动化注册任务 |
| 已停用 | `DISABLED` | 禁止新任务；运行中的任务按停用策略安全停止 |

状态变更必须记录操作者、原因、变更时间和关联工单/评审记录。

### 24.4 接入准入规则

期刊入口只有同时满足以下条件，才能标记为 `SUPPORTED`：

1. 出版社属于上述五家白名单。
2. 期刊身份和官方归属已核验。
3. 注册入口来自可信来源，且域名、HTTPS 和重定向规则已验证。
4. 已确认该期刊实际使用的投稿平台及注册流程。
5. 对应适配器已实现并通过测试。
6. 已检查目标平台使用条款、自动化政策和访问限制。
7. 已完成测试账号端到端测试；测试不得使用未经许可的真实作者账号。
8. 注册字段映射、必填字段和可能的作者声明已人工复核。
9. CAPTCHA、MFA、平台安全挑战和人工确认流程已验证可暂停与恢复。
10. 入口、平台页面或条款发生重大变化时，支持状态可自动降级为 `TESTING` 或 `MANUAL_ONLY`，等待重新验收。

不得仅凭首页可访问、搜索结果或出版社名称推断某个期刊入口已受支持。

### 24.5 数据库补充设计

在原有 `publisher_accounts`、`registration_tasks` 等表之外，新增以下配置表。所有主键继续采用 `CHAR(36)` UUID；时间字段使用 UTC `DATETIME(6)`；表使用 InnoDB、utf8mb4。

#### 24.5.1 `publisher_registration_support` 出版社注册支持表

白名单只保存注册支持配置，出版社身份仍复用现有 `publishers` 表，不建立第二套出版社主数据。

```sql
CREATE TABLE publisher_registration_support (
    id CHAR(36) NOT NULL PRIMARY KEY,
    publisher_id CHAR(36) NOT NULL,
    publisher_code VARCHAR(64) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    support_status VARCHAR(32) NOT NULL DEFAULT 'SUPPORTED',
    support_level VARCHAR(32) NOT NULL DEFAULT 'V0_1',
    official_domains JSON NULL,
    notes TEXT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by CHAR(36) NOT NULL,
    updated_by CHAR(36) NULL,
    UNIQUE KEY uk_publisher_support_id (publisher_id),
    UNIQUE KEY uk_publisher_code (publisher_code),
    KEY idx_publisher_status (support_status),
    CONSTRAINT fk_publisher_support_publisher
        FOREIGN KEY (publisher_id) REFERENCES publishers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

初始化数据必须且仅包含以下五个启用的出版社代码，并分别关联现有 `publishers.id`；若出版社档案不存在，应先通过现有档案流程建立，再添加支持配置：

- `SPRINGER_NATURE`
- `ELSEVIER`
- `WILEY`
- `TAYLOR_FRANCIS`
- `SAGE`

禁止由普通前端请求直接新增白名单出版社。白名单变更只能由具备系统配置权限的管理员执行，并写入审计日志。

#### 24.5.2 `platform_adapters` 投稿平台适配器表

```sql
CREATE TABLE platform_adapters (
    id CHAR(36) NOT NULL PRIMARY KEY,
    adapter_code VARCHAR(100) NOT NULL,
    adapter_name VARCHAR(255) NOT NULL,
    platform_type VARCHAR(100) NOT NULL,
    adapter_version VARCHAR(64) NOT NULL,
    support_status VARCHAR(32) NOT NULL DEFAULT 'TESTING',
    allowed_domains JSON NOT NULL,
    capability_config JSON NULL,
    last_verified_at DATETIME(6) NULL,
    verification_notes TEXT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by CHAR(36) NOT NULL,
    UNIQUE KEY uk_adapter_version (adapter_code, adapter_version),
    KEY idx_adapter_platform_status (platform_type, support_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

适配器必须绑定版本。适配器升级后应重新执行对应平台的回归测试；不得静默覆盖已验收版本。

#### 24.5.3 复用 `journal_submission_portals` 投稿入口表

模块 2 已提供期刊关联、原始和最终 URL、重定向链、平台代码、入口验证状态、访问状态及证据摘要。模块 3 只增加注册支持配置，不新建 `journal_platform_endpoints`：

```sql
ALTER TABLE journal_submission_portals
    ADD COLUMN normalized_host VARCHAR(255) NULL,
    ADD COLUMN platform_adapter_id CHAR(36) NULL,
    ADD COLUMN support_status VARCHAR(32) NOT NULL DEFAULT 'TESTING',
    ADD COLUMN verified_by CHAR(36) NULL,
    ADD COLUMN verification_evidence_ref VARCHAR(255) NULL,
    ADD COLUMN last_checked_at DATETIME(6) NULL,
    ADD COLUMN disabled_reason VARCHAR(1000) NULL,
    ADD KEY idx_portal_status (support_status, verification_status),
    ADD KEY idx_portal_host (normalized_host),
    ADD CONSTRAINT fk_portal_adapter
        FOREIGN KEY (platform_adapter_id) REFERENCES platform_adapters(id),
    ADD CONSTRAINT fk_portal_verifier
        FOREIGN KEY (verified_by) REFERENCES users(id);
```

说明：

- `journal_id`、`original_url`、`final_url`、`verification_status` 和 `evidence_summary` 均由模块 2 的现有入口记录提供；注册核验使用 `verification_status=VERIFIED`，不另设含义重复的 `PENDING` 身份状态。
- `platform_adapter_id` 关联已验收的具体适配器版本，平台代码仅用于发现，不代表已经支持自动注册。
- `verification_evidence_ref` 保存证据记录引用，不保存账号密码、Cookie 或验证 Token。
- 对入口 URL 的每次访问仍须执行 SSRF、域名和重定向检查。
- 对同一期刊存在多个合法入口的情况，允许多条入口记录，但必须明确入口用途、适用平台和适配器。

### 24.6 注册任务创建校验

创建注册任务时，后端必须在 Service 层按以下顺序校验：

1. 当前操作人身份及角色权限。
2. 作者授权有效且覆盖账号注册行为。
3. 作者与邮箱资料的访问权限。
4. `publisher_id` 对应现有 `publishers` 档案存在，且其 `publisher_registration_support.support_status = SUPPORTED`。
5. `journal_id` 对应具体期刊，且归属出版社与请求中的 `publisher_id` 一致。
6. 期刊入口 `support_status = SUPPORTED`。
7. 期刊入口 `verification_status = VERIFIED`。
8. 关联适配器存在、版本启用且状态为 `SUPPORTED`。
9. 目标域名属于该入口和适配器的允许域名集合。
10. 当前没有需要人工处理或可能重复提交的冲突任务。

任一检查失败，不得创建可执行的自动化任务。可以返回明确的业务错误码，例如：

- `PUBLISHER_NOT_IN_V01_WHITELIST`
- `PUBLISHER_DISABLED`
- `JOURNAL_REQUIRED`
- `JOURNAL_PUBLISHER_MISMATCH`
- `JOURNAL_ENDPOINT_NOT_VERIFIED`
- `JOURNAL_ENDPOINT_NOT_SUPPORTED`
- `PLATFORM_ADAPTER_NOT_SUPPORTED`
- `PLATFORM_DOMAIN_NOT_ALLOWED`

### 24.7 API 补充

统一前缀仍为 `/api/v1`。

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| `GET` | `/registration/publishers` | 查询 V0.1 支持出版社 | 已登录用户，按角色脱敏 |
| `GET` | `/registration/publishers/{publisher_id}/journals` | 查询某出版社已登记期刊及支持状态 | 已登录用户 |
| `GET` | `/registration/platform-adapters` | 查询可用平台适配器 | 管理员/操作员按权限 |
| `POST` | `/admin/registration/publishers` | 新增或配置出版社白名单 | 系统管理员 |
| `PATCH` | `/admin/registration/publishers/{publisher_id}` | 修改出版社支持状态 | 系统管理员 |
| `POST` | `/admin/registration/journal-endpoints` | 登记期刊官方入口 | 系统管理员 |
| `PATCH` | `/admin/registration/journal-endpoints/{endpoint_id}` | 更新入口核验或支持状态 | 系统管理员 |
| `POST` | `/admin/registration/journal-endpoints/{endpoint_id}/verify` | 触发入口核验流程 | 系统管理员 |

管理员接口必须进行二次业务校验并写入不可变审计事件。前端传入的出版社名称、平台代码或 URL 不能覆盖后端白名单和入口核验结果。上述入口管理接口操作的对象是现有 `journal_submission_portals` 记录，`journal-endpoints` 仅是 API 资源名称。

### 24.8 前端页面补充

在“出版社账号注册”模块增加：

1. **出版社选择器**：只展示 V0.1 白名单中的出版社；不支持的出版社显示“暂不支持”，不可创建自动注册任务。
2. **期刊选择器**：选择出版社后，只展示已登记期刊，并显示入口核验状态和支持状态。
3. **平台信息确认区**：展示识别到的平台名称、适配器版本、支持状态和最近核验时间。
4. **管理员接入管理页**：管理出版社白名单、期刊入口、域名、适配器绑定和核验记录。
5. **不支持原因提示**：明确显示是出版社不在白名单、期刊入口未核验、适配器未完成还是平台暂时停用。

### 24.9 测试与验收补充

必须增加以下测试：

- 五家白名单出版社均能被正确识别和查询。
- 任意第六家出版社不能创建 V0.1 自动注册任务。
- 出版社已支持但期刊未登记时，任务创建失败。
- 期刊归属出版社与请求出版社不一致时，任务创建失败。
- 期刊入口未核验或状态为 `TESTING`、`MANUAL_ONLY`、`DISABLED` 时，不得启动自动化。
- 适配器未启用、版本不匹配或域名不匹配时，任务创建失败。
- 同一出版社下不同期刊可绑定不同平台适配器。
- 同一平台适配器可被多个出版社/期刊入口复用，但域名和期刊入口仍分别校验。
- 管理员修改白名单或入口状态后，审计记录完整。
- 任务执行期间入口被停用或授权被撤销时，Worker 在下一安全检查点停止后续外部操作。
- 入口页面发生重大变化时，适配器进入待复核状态，不得继续盲目填写或提交。

### 24.10 V0.1 实施优先级建议

推荐按以下顺序实施，但最终以实际期刊清单和测试环境可用性为准：

1. 完成五家出版社白名单、期刊入口登记和平台识别的通用机制。
2. 优先开发和验收可复用的平台适配器，例如 Editorial Manager、ScholarOne。
3. 根据五家出版社的实际期刊清单，接入对应的其他平台或出版社自有入口。
4. 对暂时无法稳定适配的平台标记为 `MANUAL_ONLY`，保留资料准备、入口展示和任务审计能力。
5. OJS 等其他平台只有在五家出版社的目标期刊确实使用且完成独立验收后，才纳入 V0.1 支持清单；不因预留代码而自动视为已支持。

### 24.11 本次修订结论

本次修订将 V0.1 的业务范围明确限定为 Springer Nature、Elsevier、John Wiley & Sons（Wiley）、Taylor & Francis 和 SAGE 五家出版社。系统采用“出版社白名单 + 期刊官方入口核验 + 投稿平台适配器”的三级准入机制。

这意味着 V0.1 支持的是五家出版社旗下经过逐刊核验的注册入口，而不是无条件支持这五家出版社的全部期刊。未列入白名单的出版社不进入 V0.1 自动注册范围；平台安全挑战、CAPTCHA、MFA 和注册提交等关键环节仍遵循原设计中的人工介入与明确确认原则。

---

## 25. R2 实施前检查清单

1. 出版社、期刊和投稿入口分别复用 `publishers`、`journals` 与 `journal_submission_portals`，不得产生第二套主数据。
2. 注册授权、作者资料访问、邮箱读取和凭据使用分别校验，系统管理员不得绕过作者的明确注册授权。
3. `registration_tasks` 必须包含 Worker 所有权、租约、心跳、取消、重试和最近外部动作字段。
4. 注册提交和验证链接访问必须使用 `registration_confirmations` 的一次性确认记录，并绑定当前摘要哈希。
5. 提交超时或结果未知时进入 `SUBMISSION_UNKNOWN`，先核对平台状态，不得盲目重复提交。
6. 账号唯一性同时考虑平台、账号域和在用状态；不得仅凭平台代码和邮箱错误合并账号。
7. 人工浏览器接管使用本地受控有头窗口和有限租约，不导出会话凭据。
8. 临时验证链接只通过 `TemporarySecretStore` 的引用访问，并在使用、过期或取消后清理。
9. 页面实现遵循第 14.5 节的信息层级、步骤条、时间线、证据抽屉、人工确认和可访问性要求。
10. 未经逐刊核验和适配器验收的入口，不得创建可执行的自动注册任务。

R2 仍需正式评审；评审通过后方可按阶段一开始实施。
