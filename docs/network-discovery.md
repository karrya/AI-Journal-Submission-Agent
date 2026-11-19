# 自动化期刊网络识别

## 已实现流程

`POST /api/v1/journals/identify` 创建持久化任务并返回 `202` 和 `task_id`。独立 Worker 依次执行：

1. OpenAlex、Crossref、DOAJ 元数据发现；
2. 已配置时的 Kimi Web Search Pro 候选发现；
3. 官网身份、ISSN/EISSN 和名称交叉核验；
4. 作者指南与投稿入口发现；
5. 投稿平台特征识别；
6. 保存期刊、投稿入口、页面文本快照和追加式发现日志。

只有单一候选具备充分证据时才自动建档并标记 `VERIFIED`。多候选或证据不足时保留在任务结果中，由管理员通过 `confirm-candidate` 选择。单个 Provider 失败会记录降级警告，不会直接抹掉其他来源的结果。

## Kimi 配置

在本地 `.env` 中配置，不要提交真实密钥：

```dotenv
KIMI_API_KEY=替换为本地密钥
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_MODEL=kimi-k3.1-pro
```

当前实现优先使用 Moonshot 官方独立接口 `POST /v1/tools/search_pro`。如果该公共 API 返回 401，则自动回退到 Claude Code 同款 `POST https://api.kimi.com/coding/v1/messages` 通道生成候选。Messages 通道只用于提供候选线索，实际官网、ISSN 和投稿入口仍由 Worker 独立访问并验证，不把模型生成的 URL 当作已确认事实。密钥只用于相应官方 HTTPS 端点，不进入前端或日志。未配置 `KIMI_API_KEY` 时仍使用 OpenAlex、Crossref、DOAJ 和用户提供的官网。

`KIMI_MODEL` 预留给后续模型辅助提取；当前首版的搜索与平台识别不依赖模型生成结论。

## 启动

先安装依赖。浏览器优先使用系统 Google Chrome；没有系统 Chrome 时，再安装 Playwright 内置 Chromium：

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
.venv/bin/python -m pip install -r backend/requirements-dev.txt
# 仅在没有可用系统 Chrome 时执行：
.venv/bin/python -m playwright install chromium
```

可通过 `PLAYWRIGHT_CHROMIUM_CHANNEL` 指定其他 Playwright 浏览器通道。

迁移开发数据库后，分别启动后端、前端和 Worker：

```bash
bash scripts/dev_backend.sh
bash scripts/dev_frontend.sh
bash scripts/dev_worker.sh
```

长期运行时，推荐使用 macOS launchd 托管后端和 Worker，避免开发工具的后台运行时限：

```bash
bash scripts/dev_services.sh start    # 安装并启动
bash scripts/dev_services.sh status   # 查看状态
bash scripts/dev_services.sh stop     # 停止服务
```

launchd 配置写入当前用户的 `~/Library/LaunchAgents`，日志保存在 `storage/logs/`。只有用户登录后服务才会运行。

Worker 使用 `DATABASE_URL` 连接开发库，以 `主机名:进程 ID` 作为默认 Worker 标识。可通过 `DISCOVERY_WORKER_ID` 和 `DISCOVERY_POLL_INTERVAL` 覆盖默认值。生产部署应单独设置 Worker 副本数和停止信号，不需要启动第二个 Web 后端。

## 任务与证据 API

- `GET /api/v1/tasks/{id}`：阶段、进度、候选、警告和最终状态；
- `POST /api/v1/tasks/{id}/cancel`：取消待执行或执行中的任务；
- `POST /api/v1/tasks/{id}/retry`：重试允许重试的失败任务；
- `POST /api/v1/tasks/{id}/confirm-candidate`：确认歧义候选；
- `GET /api/v1/journals/{id}/submission-portals`：查看入口、平台和证据摘要。

文本快照保存在 `STORAGE_ROOT/discovery/{task_id}/` 下，数据库只保存受控相对路径。外部访问统一执行 HTTPS、DNS/IP、重定向、内容大小和 robots.txt 校验；JavaScript 页面通过隔离 Chromium 降级访问，不加载用户 Cookie，也不绕过验证码或登录限制。

## 测试

默认测试使用固定 Provider 响应、可控本地网站和模拟浏览器，不访问公网，也不需要 Kimi 密钥：

```bash
cd backend
ENVIRONMENT=test ../.venv/bin/python -m pytest \
  tests/test_url_security.py \
  tests/test_discovery_providers.py \
  tests/test_network_identification_pipeline.py \
  tests/test_discovery_worker.py \
  tests/test_network_identification_api.py
cd ..
bash scripts/verify.sh
```

真实公网验收应使用允许的公开期刊，并核对官网、入口、证据和任务日志。不得把测试数据库 URL 指向开发库。

## 首版边界

- 不执行 AI 投稿规则提取、自动登录或稿件提交。
- 平台识别目前基于 URL 和页面特征；`UNKNOWN` 不代表网站无效。
- 开放数据缺失或官网证据冲突时仍需要人工选择，不能保证所有期刊自动核验成功。
- 浏览器访问需要额外的 Chromium 运行资源；纯静态页面不启动浏览器。
