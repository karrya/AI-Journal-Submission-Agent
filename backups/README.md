# 加密备份与隔离恢复

备份包含一致性 MySQL 转储、稿件存储、`.env.example` 和 SHA-256（安全哈希算法 256 位）清单。实际 `.env`、明文密码、可复用 Cookie 及 `auth_sessions` 内容均会排除。恢复时，在 Alembic 验证之前，仅根据当前模型元数据重新创建上述被排除的表；该表保持为空，且迁移历史不变。Tar 字节流直接传入 `age`；只有 `.partial` 文件完整写入成功后，才发布加密 `.tar.age` 文件。

## 前置条件

备份前停止后端、前端、工作进程及所有其他应用写入方，并保持停止状态直至验证完成。安装 `age`、`mysqldump` 和 `mysql`。将专用私钥保存在本项目及 Git 之外。为本项目生成的密钥通常位于：

- `~/.config/academic-submission-agent/age/backup-key.txt`
- `~/.config/academic-submission-agent/age/recipient.txt`

这两个文件及其父目录必须仅供操作员访问。如果专用密钥已存在，不要轮换或覆盖。通过受保护环境提供现有配置：

```bash
read -r AGE_RECIPIENT < ~/.config/academic-submission-agent/age/recipient.txt
export AGE_RECIPIENT
export AGE_SECRET_KEY_FILE="$HOME/.config/academic-submission-agent/age/backup-key.txt"
```

切勿将私钥、接收方标识、数据库 URL 或密码放入 Git、命令参数、日志或本目录。

## 备份

停止应用写入后，在项目根目录运行：

```bash
.venv/bin/python scripts/backup.py --confirm-writes-stopped
```

默认输出目录为 `backups/`。数据库密码仅通过 `MYSQL_PWD` 传给 `mysqldump` 子进程。转储、tar 或 age 任一步骤失败，都会删除不完整产物和未加密临时文件。

## 隔离恢复

预置一个名为 `academic_submission_agent_restore_test` 的**空**数据库，以及仅能导入和迁移该数据库的账号。通过受保护环境中的 `RESTORE_DATABASE_URL` 提供其 URL。使用[运维手册](../docs/operations.md#8-age-密钥加密备份与隔离恢复)中的专用 `asa_restore` 示例及精确的模式范围授权命令；不要假定 `asa_test` 拥有恢复模式权限。恢复目标目录必须新建或为空，且位于实际配置的 `STORAGE_ROOT` 之外；独立恢复会从受保护环境读取该根目录，并拒绝使用该根目录及其任何子目录。

```bash
.venv/bin/python scripts/restore.py \
  --backup backups/REPLACE_WITH_BACKUP.tar.age \
  --database academic_submission_agent_restore_test \
  --target-directory /tmp/academic-agent-restored-storage \
  --confirm RESTORE
```

该命令会拒绝开发数据库、格式错误或不以 `_test` 结尾的名称、非空目标、正式存储路径、不安全的归档成员和哈希不匹配。支持 MySQL 的词法分析器仅接受预期的 mysqldump 语句形式及完全匹配的初始化/清理 `SET` 签名；任意 SQL 模式、用户变量及影响解析器的语句均会被拒绝。所有限定模式的引用都会被拒绝，包括带引号、被注释拆分及可执行注释等变体。导入过程自行设置 `NO_AUTO_VALUE_ON_ZERO`，使用 `mysql --one-database`，并且仅在归档验证通过后，在内容前添加经过校验的隔离目标 `USE` 语句。

该命令在迁移前比较转储表，运行 `alembic upgrade head` 和 `alembic check`，比较除被排除会话外的所有源表行数，验证每个清单哈希，并比较恢复后的存储文件名、数量和哈希。会话必须保持为空。独立恢复会检查源表名和行数是否稳定，但不声称源内容或模式不可变。下方的真实验证还会比较操作前后的表校验和、模式 DDL（数据定义语言）哈希及存储哈希。任何解密、恢复、中断或清理失败都会阻止成功输出，并删除解密后的临时数据。

## 可重复的 BACKUP-01 验证

以下命令会执行一次真实备份和恢复，随后删除解密后的恢复目录，并将加密备份保留在 `backups/`：

```bash
.venv/bin/python scripts/test_backup_restore.py
```

默认情况下，验证从 `TEST_DATABASE_URL` 派生目标凭据，并要求固定恢复数据库已存在。也可以不设置 `RESTORE_DATABASE_URL` 或将其留空，并在受保护环境中设置 `RESTORE_ADMIN_URL`。运维手册会预置专用 `asa_restore_admin`，其权限和授权选项仅限固定恢复模式。随后，验证仅使用该管理连接在固定 `_test` 数据库不存在时创建它、拒绝非空数据库，并仅向现有测试账号授予该模式的访问权限。验证绝不会创建开发数据库、对其授权、向其导入数据或覆盖它。

当开发存储为空时，验证会创建一个名称唯一、明确标记的临时文本文件，使真实运行能够验证非零存储文件数量及哈希。验证会拒绝非空开发存储，绝不覆盖现有路径，只删除自己创建的验证文件，并且仅在存储根目录由验证创建时才删除该目录。开发文件清理后，加密备份仍保留经过验证的验证文件副本。
