# 运维手册

除非另有目录说明，以下命令均从实际项目根目录开始执行。仅替换明确标记的占位值；切勿将真实密码、会话令牌、数据库 URL、age 私钥或个人文件路径粘贴到文档、问题单、Shell 历史或 Git 中。

```bash
export PROJECT_ROOT="/Users/didi/PycharmProjects/AI Journal Submission Agent"
cd "$PROJECT_ROOT"
```

## 1. Homebrew 依赖与隔离运行环境

V0.1 使用 Homebrew MySQL 8.0。Docker 为可选项，不是经过测试的运行时。

```bash
brew install python@3.13 node mysql@8.0 age libmagic
export PATH="$(brew --prefix mysql@8.0)/bin:$PATH"
brew services start mysql@8.0
mysql --version
mysqldump --version
age --version
node --version
npm --version
```

确保 MySQL 软件包及其 Homebrew 依赖的 ABI（应用二进制接口）兼容。如果重启时报告缺少带版本号的 `dylib`，停止所有应用写入方并运行 `HOMEBREW_NO_AUTO_UPDATE=1 brew upgrade mysql@8.0`，然后运行 `brew services start mysql@8.0`；不要删除或重新初始化 `/opt/homebrew/var/mysql`。修复软件包后，验证开发库和测试库的连通性。验收日志记录了一次在成功重启检查前从 8.0.42 到 8.0.46 的此类修复。

安装锁定版本的后端和前端依赖。本手册中的后端命令始终使用项目 virtualenv，而非系统 Python。

```bash
cd "$PROJECT_ROOT"
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

`backend/requirements-dev.txt` 包含运行时依赖以及 pytest、coverage、Ruff、mypy、HTTPX 和 OpenAPI 校验。`npm ci` 按锁文件安装精确版本，包括 Newman、Vitest、Vite、TypeScript 和生产依赖。

## 2. 配置与一次性 MySQL 初始化

检查不含密钥的模板，然后保护本地配置：

```bash
cd "$PROJECT_ROOT"
cp -n .env.example .env
chmod 600 .env
```

仅在首次预置或有意轮换凭据时运行初始化：

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/bootstrap_mysql.py
```

脚本通过隐藏输入提示输入 MySQL 管理密码。`MYSQL_ADMIN_USER`、`MYSQL_ADMIN_HOST` 和 `MYSQL_ADMIN_PORT` 可选择管理端点，默认值分别为 `root`、`localhost` 和 `3306`。脚本会创建：

- 用于开发的 `academic_submission_agent`；
- 用于破坏性自动化测试的 `academic_submission_agent_test`；
- 仅拥有开发库 CRUD（增删改查）权限的 `asa_app@127.0.0.1`；
- 仅拥有开发库迁移权限的 `asa_migrate@127.0.0.1`；
- 仅拥有固定测试库权限的 `asa_test@127.0.0.1`。

脚本生成新的账号密码和 CSRF（跨站请求伪造）密钥，并且仅在 MySQL 步骤成功后，才以 `0600` 权限原子写入 `.env`。随后完成其他本地配置，尤其是 `STORAGE_ROOT`、`ALLOWED_ORIGINS`，以及备份所需的 age/恢复配置。不要提交 `.env`。

**初始化不会幂等保留凭据。** 每次成功运行都会轮换全部三个 MySQL 账号密码并重写 `.env`；不要在日常启动或测试期间运行。

### 初始化密码轮换失步恢复

MySQL 用户变更无法参与随后的文件系统重命名。如果运行过程已轮换一个或多个 MySQL 密码，却在替换 `.env` 之前失败，旧 `.env` 与新 MySQL 凭据就会失步。按以下步骤恢复：

1. 停止后端及所有其他应用写入方。不要持续重试登录，也不要覆盖任一数据库。
2. 检查管理连接，并修复环境写入失败的原因（例如目录权限或磁盘空间耗尽）。不要将凭据复制到所有用户可读的临时文件。
3. 修复写入问题后，以交互方式再次运行 `.venv/bin/python scripts/bootstrap_mysql.py`。这会生成另一套完整凭据，并且仅在 MySQL 操作和 `.env` 原子替换均成功后完成。失败尝试所生成的密码无法恢复，也绝不会记录到日志。
4. 恢复重写后的 `.env` 所需的本地非密钥配置，然后运行迁移/就绪检查及管理员登录检查。只有另有证据表明管理员密码已暴露时，才通过应用轮换该密码；初始化不会更改应用用户密码。

如果管理连接在任何 `ALTER USER` 之前失败，现有 `.env` 仍为有效依据。如果后续初始化也失败，保持服务停止并重复修复，不要猜测密码。

## 3. 迁移与模式验证

连续运行两次迁移命令。第一次到达 head；第二次不得产生重复数据或模式变更。`alembic check` 验证模型与已迁移的 head 一致。

```bash
cd "$PROJECT_ROOT/backend"
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic check
../.venv/bin/python - <<'PY'
from sqlalchemy import inspect
from app.core.database import SessionLocal

session = SessionLocal()
try:
    names = set(inspect(session.bind).get_table_names())
    application_tables = names - {"alembic_version"}
    assert len(application_tables) == 18, sorted(application_tables)
    assert "alembic_version" in names
    print("18 application tables plus alembic_version; migration head verified")
finally:
    session.close()
PY
```

模式包含 18 张应用表；`alembic_version` 用于迁移簿记，因此完全迁移的 MySQL 模式共含 19 张表。

## 4. 隐藏输入创建管理员与首次登录

迁移完成后，且仅在不存在任何应用用户时运行：

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/create_admin.py
```

在隐藏提示中输入唯一的管理员用户名和 6–128 字符的初始密码。系统没有默认密码。该命令创建固定角色目录和一个 `system_admin`，设置 `must_change_password=true`，并在任何用户已存在时拒绝初始化。

启动应用，在前端登录并完成强制修改密码表单。修改密码会撤销现有会话；使用新密码重新登录。在完成此步骤前，业务 API 返回 `403 PASSWORD_CHANGE_REQUIRED`；仅会话身份、CSRF、退出登录和修改密码路由保持可用。

## 5. 后端与前端启动

使用两个终端，使完整参数列表均来自已纳入版本控制的脚本：

```bash
cd "$PROJECT_ROOT"
bash scripts/dev_backend.sh
# .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```bash
cd "$PROJECT_ROOT"
bash scripts/dev_frontend.sh
# npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

验证：

```bash
curl --fail --silent http://127.0.0.1:8000/api/v1/health
curl --fail --silent http://127.0.0.1:5173/ >/dev/null
```

打开 `http://127.0.0.1:5173`。不要将任一开发监听器暴露到非回环接口。计划内持久化维护时，停止写入，运行经授权的 `brew services restart mysql@8.0`，重启两个脚本，然后在恢复工作前验证数据库记录及存储文件的 SHA-256（安全哈希算法 256 位）值。

## 6. 测试、覆盖率、OpenAPI 与 Postman/Newman

完整发布检查为：

```bash
cd "$PROJECT_ROOT"
bash scripts/verify.sh
```

该命令运行 Ruff、mypy、完整 MySQL 后端 pytest 套件、后端总体及分层覆盖率下限、确定性 OpenAPI 生成与校验、隔离的 Newman 集合、前端单元测试与覆盖率，以及前端生产构建。它在首次失败时停止，并输出失败命令。

测试要求 `ENVIRONMENT=test`，且回环地址 `TEST_DATABASE_URL` 中的数据库必须恰好为 `academic_submission_agent_test`。Pytest 创建隔离的临时存储。`scripts/test_api.sh` 同样创建临时存储，使用后端端口 `8001`，生成一次性凭据，并通过 trap 终止其后端。测试防护要求显式环境和数据库主机参数，并拒绝正式存储或嵌套在正式存储内的路径。**这些命令会删除并重建测试数据；切勿将其重定向到开发环境。**

常用专项命令为：

```bash
cd "$PROJECT_ROOT/backend"
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_security_matrix.py tests/test_authorization_boundaries.py -q
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_backup_restore.py -q
cd "$PROJECT_ROOT"
npm --prefix frontend test
npm --prefix frontend run test:coverage
npm --prefix frontend run build
```

独立生成并校验已提交的 OpenAPI 契约：

```bash
cd "$PROJECT_ROOT"
PYTHONPATH=backend .venv/bin/python scripts/export_openapi.py
.venv/bin/python -c \
  'import json, sys; from pathlib import Path; from openapi_spec_validator import validate_spec; validate_spec(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))' \
  docs/api/v0.1-openapi.json
git diff --exit-code -- docs/api/v0.1-openapi.json
```

通过 Newman 对隔离后端运行真实 Postman 集合：

```bash
cd "$PROJECT_ROOT"
bash scripts/test_api.sh
```

输入为 `backend/tests/postman/v0.1.postman_collection.json` 和 `backend/tests/postman/local.postman_environment.json`。运行时密码和 Cookie 在内存中生成，不写入集合或报告。

## 7. 存储核对与未知文件提交恢复

将后端配置为预期的开发数据库/存储后，运行：

```bash
cd "$PROJECT_ROOT"
PYTHONPATH=backend .venv/bin/python scripts/reconcile_files.py
```

JSON 报告包含缺失文件 ID、哈希不匹配 ID、孤立文件数量（不含服务器路径），以及通过文件 ID、相对路径和 SHA-256 匹配解决的核对清单条目数。数据库中处于活动状态但缺失或损坏的文件会标记其完整性状态，修复前无法下载。核对不会自动删除状态不确定的文件。

正式文件移动后发生异常且数据库提交结果不确定时，系统会有意保留正式文件，并向 `reconciliation.jsonl` 追加 `unknown_commit` 条目。按以下保守步骤恢复：

1. **不要盲目重复上传，也不要删除正式文件。** 重复上传可能创建第二个文件族版本；删除可能销毁唯一已提交副本。
2. 恢复数据库连接并运行核对命令。将清单中的文件 ID 和 SHA-256 与受保护数据库记录及实际文件摘要比对；不要在日志中暴露存储路径。
3. 如果数据库行存在且摘要匹配，则提交成功。已解决清单计数增加，可恢复正常的授权下载。
4. 如果数据库稳定后仍不存在该行，文件会报告为孤立文件。调查审计轨迹和清单期间保留该文件。仅在确认其未提交后，才移至操作员控制的隔离区；绝不能将自动删除视为恢复。
5. 如果该行存在但文件缺失或哈希不同，保持下载阻断，隔离受损证据，从加密备份恢复已验证对象，然后重新运行核对。

确定的回滚走独立补偿路径；只有结果未知时才需要这种非破坏性清单流程。

## 8. age 密钥、加密备份与隔离恢复

将专用 age 私钥保存在项目和 Git 之外。标准路径为：

```bash
install -d -m 700 "$HOME/.config/academic-submission-agent/age"
umask 077
age-keygen -o "$HOME/.config/academic-submission-agent/age/backup-key.txt"
age-keygen -y "$HOME/.config/academic-submission-agent/age/backup-key.txt" \
  > "$HOME/.config/academic-submission-agent/age/recipient.txt"
chmod 600 "$HOME/.config/academic-submission-agent/age/backup-key.txt" \
  "$HOME/.config/academic-submission-agent/age/recipient.txt"
```

`age-keygen -o` 拒绝覆盖现有密钥。切勿仅为执行日常备份而轮换或替换密钥；丢失唯一私钥会使现有备份无法恢复。每个维护 Shell 均需执行：

```bash
read -r AGE_RECIPIENT < "$HOME/.config/academic-submission-agent/age/recipient.txt"
export AGE_RECIPIENT
export AGE_SECRET_KEY_FILE="$HOME/.config/academic-submission-agent/age/backup-key.txt"
```

接收方标识是公开的，但它和私钥路径均无需提交。私钥文件不得为符号链接，必须位于项目之外，并禁止用户组和其他用户访问。

备份前停止后端、前端、工作进程及所有其他应用写入方，并在恢复验证完成前保持停止。然后运行：

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/backup.py --confirm-writes-stopped
```

默认目标是由 Git 忽略的 `backups/` 目录。归档包含单事务 MySQL 转储、存储文件、`.env.example`，以及逐成员的 SHA-256/大小元数据；排除 `.env`、明文密码、可复用 Cookie 和 `auth_sessions`。Tar 字节直接流式传入 age；只有完整的 `.tar.age` 才会原子发布。失败会删除临时明文和 `.partial` 输出。

恢复时，预置一个**空**的 `academic_submission_agent_restore_test` 模式，以及仅获授权访问该隔离目标的账号。下例创建 `asa_restore@127.0.0.1`，不授予全局、开发、测试或授权选项权限。`ALL PRIVILEGES` 仅限恢复模式，因为导入和 Alembic 需要 DDL（数据定义语言）、行写入和 `LOCK TABLES`；它不会授予任何其他模式的访问权限。生成的密码仅保留在 Shell 变量中，并且只写入受保护的 `.env`，不进入命令参数或输出：

```bash
cd "$PROJECT_ROOT"
RESTORE_PASSWORD="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(36))')"
mysql --user="${MYSQL_ADMIN_USER:-root}" \
  --host="${MYSQL_ADMIN_HOST:-localhost}" --port="${MYSQL_ADMIN_PORT:-3306}" \
  --password <<SQL
CREATE DATABASE IF NOT EXISTS academic_submission_agent_restore_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'asa_restore'@'127.0.0.1' IDENTIFIED BY '${RESTORE_PASSWORD}';
ALTER USER 'asa_restore'@'127.0.0.1' IDENTIFIED BY '${RESTORE_PASSWORD}';
GRANT ALL PRIVILEGES ON academic_submission_agent_restore_test.*
  TO 'asa_restore'@'127.0.0.1';
SQL
export RESTORE_DATABASE_URL="mysql+pymysql://asa_restore:${RESTORE_PASSWORD}@127.0.0.1:3306/academic_submission_agent_restore_test"
.venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path('.env')
lines = path.read_text(encoding='utf-8').splitlines()
setting = f"RESTORE_DATABASE_URL={os.environ['RESTORE_DATABASE_URL']}"
lines = [setting if line.startswith('RESTORE_DATABASE_URL=') else line for line in lines]
if not any(line.startswith('RESTORE_DATABASE_URL=') for line in lines):
    lines.append(setting)
temporary = path.with_name('.env.restore-tmp')
temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
temporary.chmod(0o600)
temporary.replace(path)
PY
unset RESTORE_PASSWORD RESTORE_DATABASE_URL
```

重复运行会有意轮换专用恢复密码；不要将其作为日常启动步骤。确保受保护的 `RESTORE_DATABASE_URL` 与 `--database` 匹配。目标目录必须新建或为空，且位于配置的正式存储树之外。

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/restore.py \
  --backup backups/REPLACE_WITH_BACKUP.tar.age \
  --database academic_submission_agent_restore_test \
  --target-directory /tmp/academic-agent-restored-storage \
  --confirm RESTORE
```

恢复会拒绝开发目标/非 `_test` 目标、非空目标、正式存储、不安全的归档成员、非预期 SQL、限定模式的 SQL 引用及任何哈希不匹配。它验证转储，仅向经过校验的目标导入，将被排除的会话重建为空表，运行 `alembic upgrade head` 和 `alembic check`，并比较行数、恢复文件和哈希。独立恢复检查源表名和行数是否稳定；它本身不能证明源内容或模式不可变。

更强的真实 BACKUP-01 验证还会比较开发库操作前后的表校验和、模式 DDL 哈希和存储哈希，验证 age 封装且不存在明文/不完整产物，并删除解密后的恢复数据。它支持两条互斥的目标路径：

1. 将 `RESTORE_DATABASE_URL` 设置为上述专用 `asa_restore` 账号，且模式已为空。此时不需要也不会使用 `RESTORE_ADMIN_URL`。
2. 不设置 `RESTORE_DATABASE_URL` 或将其留空，并将受保护的 `RESTORE_ADMIN_URL` 设置为模式范围预置账号。验证使用 `TEST_DATABASE_URL` 作为导入身份，在固定恢复模式不存在时创建它、非空时拒绝，并仅向该测试身份授予恢复模式的 `ALL PRIVILEGES`。导入 URL 绝不会获得开发权限。

使用独立的 `asa_restore_admin@127.0.0.1` 账号预置第二条路径。其授权选项及其他所有权限均仅限固定恢复模式：

```bash
cd "$PROJECT_ROOT"
RESTORE_ADMIN_PASSWORD="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(36))')"
mysql --user="${MYSQL_ADMIN_USER:-root}" \
  --host="${MYSQL_ADMIN_HOST:-localhost}" --port="${MYSQL_ADMIN_PORT:-3306}" \
  --password <<SQL
CREATE USER IF NOT EXISTS 'asa_restore_admin'@'127.0.0.1' IDENTIFIED BY '${RESTORE_ADMIN_PASSWORD}';
ALTER USER 'asa_restore_admin'@'127.0.0.1' IDENTIFIED BY '${RESTORE_ADMIN_PASSWORD}';
GRANT ALL PRIVILEGES ON academic_submission_agent_restore_test.*
  TO 'asa_restore_admin'@'127.0.0.1' WITH GRANT OPTION;
SQL
export RESTORE_ADMIN_URL="mysql+pymysql://asa_restore_admin:${RESTORE_ADMIN_PASSWORD}@127.0.0.1:3306"
.venv/bin/python - <<'PY'
import os
from pathlib import Path

path = Path('.env')
lines = path.read_text(encoding='utf-8').splitlines()
setting = f"RESTORE_ADMIN_URL={os.environ['RESTORE_ADMIN_URL']}"
lines = [setting if line.startswith('RESTORE_ADMIN_URL=') else line for line in lines]
if not any(line.startswith('RESTORE_ADMIN_URL=') for line in lines):
    lines.append(setting)
temporary = path.with_name('.env.restore-tmp')
temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
temporary.chmod(0o600)
temporary.replace(path)
PY
unset RESTORE_ADMIN_PASSWORD RESTORE_ADMIN_URL
```

生成的 URL 仅写入受保护的 `.env`；不会输出 URL 或密码。使用此路径时，保持 `RESTORE_DATABASE_URL` 未设置或为空。仅在应用写入方停止时运行验证：

```bash
cd "$PROJECT_ROOT"
.venv/bin/python scripts/test_backup_restore.py
```

如果开发存储为空，验证会创建随后删除的一个唯一命名验证文件；对于非空开发存储则拒绝操作。加密归档保留在由 Git 忽略的 `backups/` 中。格式详情和限制见 `backups/README.md`。
