---
name: run-ai-journal-submission-agent
description: Use when asked to run, start, build, test, screenshot, or interact with the AI Journal Submission Agent frontend, including the manuscript creation dialog.
---

# Run AI Journal Submission Agent

这是 Vue 3 前端的可重复浏览器验收入口。使用 `.claude/skills/run-ai-journal-submission-agent/driver.mjs` 启动或复用 Vite，并驱动本机 Chrome；所有 API 响应均为合成数据，不需要后端、MySQL、`.env` 或真实账号。以下命令均从仓库根目录执行。

## Prerequisites

已验证环境：macOS、Node 26.13.0、npm 11.20.0、Google Chrome 157。驱动依赖 Node 20+，默认 Chrome 路径为 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。

## Setup

```bash
npm --prefix frontend ci --no-audit --no-fund
npm --prefix .claude/skills/run-ai-journal-submission-agent ci --no-audit --no-fund
```

## Run (agent path)

```bash
node .claude/skills/run-ai-journal-submission-agent/driver.mjs
```

驱动复用 `127.0.0.1:5173` 的现有服务；无服务时自行启动，并在结束后仅清理自己启动的进程。要在独立端口验证冷启动：

```bash
ASA_RUN_URL=http://127.0.0.1:5174 ASA_RUN_OUTPUT=/tmp/ai-journal-submission-agent-run-self-start node .claude/skills/run-ai-journal-submission-agent/driver.mjs
```

驱动打开“创建稿件”，验证遮罩挂载与视口边界、正文滚动、步骤 `1 → 2 → 3 → 2 → 1 → 3`、输入保留及 390px 移动端布局；随后在 1000px 高视口检查“添加作者”“添加期刊”“创建注册任务”按内容确定高度并垂直居中，再验证管理员人工核验添加入口后自动选中新平台、APEC robots 人工接管与原任务恢复，最后复现“编辑授权”过期时间错误并用真实滚轮确认保存按钮可达。默认截图和 `result.json` 写入 `/tmp/ai-journal-submission-agent-run/`；独立端口示例写入 `/tmp/ai-journal-submission-agent-run-self-start/`。必须查看截图，不能只依赖退出码。

## Build and test

```bash
npm --prefix frontend run build
npm --prefix frontend test
```

## Gotchas

- 此入口验证真实前端交互，但拦截 API，不验证 FastAPI、数据库或真实保存。
- 打开动画作用于 `.el-overlay-dialog`，不是 `.el-dialog`；测量几何尺寸前必须等待该元素的动画结束，否则可能读到约 `-19px` 的中间位置。
- 本机 Chrome 无 `--no-sandbox` 即可运行，不要添加该参数。
- 不要从根目录直接运行 `npm test`：根目录没有 `package.json`，会出现 `ENOENT`；使用上述 `npm --prefix frontend ...` 命令。
- 环境没有 `chromium-cli` 时使用随技能提交的 Playwright 驱动，无需另行安装浏览器自动化工具。
