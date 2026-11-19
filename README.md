# AI-Journal-Submission-Agent

本地 V0.1 学术投稿工作区，采用 FastAPI、Vue 3、MySQL 8、服务端会话、作者范围授权、不可变稿件快照、经校验的文件存储、操作审计和加密备份。当前阶段一还提供注册基础：显式作者授权、受支持且已核验的入口准入、可恢复注册任务和一次性确认；不执行真实平台注册或外部提交。

## 本地开发

选定的本地安装方案使用 **Homebrew MySQL**，而非 Docker。将 `.env.example` 复制为 `.env`，填写仅供本地使用的值，并在执行迁移和创建管理员之前运行一次 MySQL 初始化。初始化过程会提示输入 MySQL 管理密码，并生成应用、迁移、测试账号及 CSRF（跨站请求伪造）密钥；绝不要求使用默认管理员密码。

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
.venv/bin/python scripts/bootstrap_mysql.py
```

完成受保护的 `.env` 配置后，使用专用迁移账号 `asa_migrate@127.0.0.1` 对应的 `ALEMBIC_DATABASE_URL` 连续运行两次迁移，以证明第二次调用不会执行任何操作。不要使用应用账号或测试账号迁移开发库：

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent/backend"
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
cd ..
.venv/bin/python scripts/create_admin.py
```

`create_admin.py` 读取初始密码时不会回显，并要求首次登录时修改密码。不要将初始化或管理员创建纳入日常启动流程。

使用 macOS launchd 启动后端、期刊识别 Worker 和注册 Worker，再在独立终端启动前端：

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/dev_services.sh start
bash scripts/dev_services.sh status
```

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/dev_frontend.sh
```

网络识别的 Provider、Kimi、Chromium 和证据配置见[自动化期刊网络识别](docs/network-discovery.md)。注册阶段一的表、权限、任务恢复和验收边界见[注册基础与阶段一验收](docs/registration-foundation.md)。注册 Worker 的默认执行器只进行准入复核并转入人工复核，不执行真实注册、邮箱读取或外部提交。

后端监听 `127.0.0.1:8000`；前端地址为 `http://127.0.0.1:5173`。默认 `ALLOWED_ORIGINS` 同时信任该地址和 `http://localhost:5173`，因此可在文档所列地址正常登录并执行受 CSRF 保护的密码修改。Vite 的 `/api` 代理保留浏览器源，并将请求转发至后端。健康检查地址为 `http://127.0.0.1:8000/api/v1/health`。

使用以下命令运行全部后端、接口契约、前端、覆盖率、OpenAPI/Newman 和生产构建检查：

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/verify.sh
```

验证仅会对预置的独立 `academic_submission_agent_test` MySQL 数据库执行破坏性操作，并使用隔离的临时文件存储。对于非测试数据库、非回环数据库目标及正式存储，验证会拒绝执行。**切勿让 `TEST_DATABASE_URL` 指向开发库或任何真实用户数据。** 本阶段测试使用模拟执行器，不进行真实注册、邮箱访问、验证链接访问或外部提交。

## 运维与发布证据

- [注册基础与阶段一验收](docs/registration-foundation.md)：模块 2/3 表关系、显式授权、入口准入、Worker 恢复、确认防重放、启动和完整验收。
- [自动化期刊网络识别](docs/network-discovery.md)：独立 Worker、开放数据、Kimi 搜索、官网与投稿入口证据、浏览器降级及安全边界。
- [运维手册](docs/operations.md)：准确的 Homebrew 配置、初始化及凭据失步恢复、迁移、启动、测试、OpenAPI/Postman、存储核对、age 密钥、加密备份、隔离恢复和未知提交恢复。
- [安全说明与矩阵](docs/security.md)：信任边界、角色行为、密钥处理、可执行安全检查及剩余限制。
- [V0.1 验收记录](docs/acceptance-v0.1.md)：注明日期的全新安装、持久化/重启、真实浏览器、备份/恢复、测试/覆盖率及未解决限制的证据。
- [备份格式与恢复防护](backups/README.md)：归档内容、排除的会话、SQL 校验及可重复的 BACKUP-01 验证。

`docker-compose.yml` 为可选配置，仅定义使用私有命名卷且不发布端口的 MySQL 8，因此不会与 Homebrew MySQL 冲突。如选择使用该配置，须显式设置 `MYSQL_ROOT_PASSWORD`；不要让两套安装使用同一数据目录。文档所述且经过验收测试的运行时为 Homebrew `mysql@8.0`。
