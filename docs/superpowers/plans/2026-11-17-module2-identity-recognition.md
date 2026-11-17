# 模块 2 第一期：出版社与期刊身份识别实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有出版社、平台和期刊 CRUD 的前提下，实现候选搜索、确定性身份识别、冲突处理、人工确认及识别工作台。

**Architecture:** 通过 Alembic 增量迁移补充别名、标识、身份状态和任务表；新增独立识别服务，复用现有角色、审计和事务模式。识别仅处理本地数据库与手工输入，不访问外部网络，后续阶段复用 `discovery_tasks`。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy 2.0、Alembic、MySQL 8、Vue 3、TypeScript、Vitest、Pytest。

**Spec:** `docs/superpowers/specs/2026-11-17-module2-identity-recognition-design.md`

## Global Constraints

- 不访问外部网站，不调用 AI，不实现投稿入口发现、平台自动识别、指南抓取或合规检查。
- 现有 CRUD 字段、路由、角色和前端三个 Tab 必须保持兼容；读取为 `system_admin/submission_operator/reviewer`，写入及身份确认仅 `system_admin` 并要求 CSRF。
- `status` 继续作为档案管理状态，`identity_status` 独立表示身份识别状态。
- 所有新增表使用 UUID、InnoDB、utf8mb4、UTC `DATETIME(6)` 和 `ON DELETE RESTRICT`。
- 多候选不得默认选中第一项；未确认不得显示为 `VERIFIED`。
- 使用独立 MySQL 8 测试数据库，不使用 SQLite 替代。
- 保留当前工作区其他修改；不自动 commit 或 push，提交和合并仍由用户明确指示。

## Review Focus

- 错误 ISSN 格式或校验位：必须 422，且不得创建任务、出版社或期刊；Task 3 覆盖。
- 无匹配期刊且无法确定出版社：必须 422 并完整回滚；Task 3 覆盖。
- 相同规范化输入并发识别：唯一任务约束生效，不重复创建候选；Task 3 覆盖。
- 过期 `expected_updated_at` 或并发确认：必须 409，不能覆盖新状态；Task 4 覆盖。
- `/search` 与 `/{publisher_id}`、`/{journal_id}` 路由冲突：搜索必须命中静态路由，不能被 UUID 参数解析拦截；Task 5 覆盖。

---

### Task 1: 身份模型与 Alembic 增量迁移

**Files:**
- Create: `backend/alembic/versions/0004_module2_identity_recognition.py`
- Create: `backend/app/models/discovery.py`
- Modify: `backend/app/models/journals.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/test_schema_constraints.py`

**Interfaces:**
- Produces: `PublisherAlias`、`JournalAlias`、`JournalIdentifier`、`DiscoveryTask`，以及出版社/期刊新增身份字段。

- [ ] **Step 1: 先写失败的 schema 与迁移测试**

在 `backend/tests/test_schema_constraints.py` 更新预期：

```python
EXPECTED_TABLES = {
    *EXPECTED_TABLES,
    "publisher_aliases",
    "journal_aliases",
    "journal_identifiers",
    "discovery_tasks",
}
NEW_MODELS.update({
    "PublisherAlias", "JournalAlias", "JournalIdentifier", "DiscoveryTask",
})

EXPECTED_NEW_COLUMNS["publisher_aliases"] = {
    "id", "publisher_id", "alias", "normalized_alias", "source_url",
    "verified_at", "created_at",
}
EXPECTED_NEW_COLUMNS["journal_aliases"] = {
    "id", "journal_id", "alias", "normalized_alias", "source_url",
    "verified_at", "created_at",
}
EXPECTED_NEW_COLUMNS["journal_identifiers"] = {
    "id", "journal_id", "identifier_type", "identifier_value", "source_url",
    "verified_at", "created_at",
}
EXPECTED_NEW_COLUMNS["discovery_tasks"] = {
    "id", "task_type", "journal_id", "owner_author_id", "idempotency_key",
    "payload", "status", "progress", "attempt_count", "max_attempts",
    "checkpoint", "last_error_code", "last_error_message", "created_by",
    "created_at", "started_at", "completed_at", "updated_at",
}
EXPECTED_NEW_COLUMNS["publishers"].update({
    "publisher_name_en", "primary_domain", "country", "publisher_type",
    "parent_organization_id", "status", "source_url", "verified_at",
})
EXPECTED_NEW_COLUMNS["journals"].update({
    "journal_name_en", "aims_scope", "open_access_status", "identity_status",
    "source_url", "verified_at",
})
```

将预期 Alembic head 从 `0003` 改为 `0004`，并新增：

```python
def test_identity_migration_backfills_existing_issn(db_engine, db_session):
    from alembic import command
    from alembic.config import Config
    from conftest import BACKEND_DIR
    from app.models import Journal, JournalIdentifier, Publisher
    from sqlalchemy import select

    publisher = Publisher(name="Migration Publisher", normalized_name="migration publisher")
    db_session.add(publisher)
    db_session.flush()
    journal = Journal(
        publisher_id=publisher.id, name="Migration Journal", issn="03785955", eissn="18781128"
    )
    db_session.add(journal)
    db_session.add_all([publisher, journal])
    db_session.commit()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "0003")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "0004")
    rows = db_session.scalars(select(JournalIdentifier)).all()
    assert {(row.identifier_type, row.identifier_value) for row in rows} == {
        ("ISSN", "03785955"), ("EISSN", "18781128")
    }
```

- [ ] **Step 2: 运行测试确认失败原因**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_schema_constraints.py -q`

Expected: 新表或 `JournalIdentifier` 不存在，当前 head 不是 `0004`。

- [ ] **Step 3: 实现模型**

在 `models/journals.py` 为 `Publisher` 和 `Journal` 添加规格字段，并新增三个关联模型。核心结构：

```python
class PublisherAlias(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "publisher_aliases"
    __table_args__ = (
        UniqueConstraint("publisher_id", "normalized_alias", name="uq_publisher_alias"),
        Index("ix_publisher_alias_normalized", "normalized_alias"),
        MYSQL_TABLE_OPTIONS,
    )
    publisher_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    alias: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(VARCHAR(2048), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class JournalAlias(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "journal_aliases"
    __table_args__ = (
        UniqueConstraint("journal_id", "normalized_alias", name="uq_journal_alias"),
        Index("ix_journal_alias_normalized", "normalized_alias"),
        MYSQL_TABLE_OPTIONS,
    )
    journal_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False
    )
    alias: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(VARCHAR(2048), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class JournalIdentifier(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "journal_identifiers"
    __table_args__ = (
        UniqueConstraint("identifier_type", "identifier_value", name="uq_journal_identifier"),
        Index("ix_journal_identifiers_journal", "journal_id"),
        MYSQL_TABLE_OPTIONS,
    )
    journal_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    identifier_value: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(VARCHAR(2048), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
```

`DiscoveryTask` 使用规格中的全部字段，`progress` 添加 `CheckConstraint("progress BETWEEN 0 AND 100", name="ck_discovery_progress")`，并在 `models/__init__.py` 导出。

- [ ] **Step 4: 实现迁移与回填**

创建 `0004_module2_identity_recognition.py`：

```python
revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    for column in (
        sa.Column("publisher_name_en", sa.VARCHAR(255), nullable=True),
        sa.Column("primary_domain", sa.VARCHAR(255), nullable=True),
        sa.Column("country", sa.VARCHAR(100), nullable=True),
        sa.Column("publisher_type", sa.VARCHAR(50), nullable=True),
        sa.Column("parent_organization_id", sa.CHAR(36), nullable=True),
        sa.Column("status", sa.VARCHAR(30), nullable=False, server_default="ACTIVE"),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", sa.DATETIME(fsp=6), nullable=True),
    ):
        op.add_column("publishers", column)
    op.create_foreign_key(
        "fk_publishers_parent", "publishers", "publishers",
        ["parent_organization_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_publishers_domain", "publishers", ["primary_domain"])
    for column in (
        sa.Column("journal_name_en", sa.VARCHAR(500), nullable=True),
        sa.Column("aims_scope", sa.TEXT(), nullable=True),
        sa.Column("open_access_status", sa.VARCHAR(50), nullable=True),
        sa.Column("identity_status", sa.VARCHAR(30), nullable=False, server_default="UNVERIFIED"),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", sa.DATETIME(fsp=6), nullable=True),
    ):
        op.add_column("journals", column)
    op.create_index("ix_journals_identity_status", "journals", ["identity_status"])
    op.create_table(
        "publisher_aliases",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("publisher_id", sa.CHAR(36), nullable=False),
        sa.Column("alias", sa.VARCHAR(500), nullable=False),
        sa.Column("normalized_alias", sa.VARCHAR(500), nullable=False),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", sa.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", sa.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("publisher_id", "normalized_alias", name="uq_publisher_alias"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_publisher_alias_normalized", "publisher_aliases", ["normalized_alias"])
    op.create_table(
        "journal_aliases",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("journal_id", sa.CHAR(36), nullable=False),
        sa.Column("alias", sa.VARCHAR(500), nullable=False),
        sa.Column("normalized_alias", sa.VARCHAR(500), nullable=False),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", sa.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", sa.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("journal_id", "normalized_alias", name="uq_journal_alias"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_journal_alias_normalized", "journal_aliases", ["normalized_alias"])
    op.create_table(
        "journal_identifiers",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("journal_id", sa.CHAR(36), nullable=False),
        sa.Column("identifier_type", sa.VARCHAR(30), nullable=False),
        sa.Column("identifier_value", sa.VARCHAR(50), nullable=False),
        sa.Column("source_url", sa.VARCHAR(2048), nullable=True),
        sa.Column("verified_at", sa.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", sa.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("identifier_type", "identifier_value", name="uq_journal_identifier"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_journal_identifiers_journal", "journal_identifiers", ["journal_id"])
    op.create_table(
        "discovery_tasks",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("task_type", sa.VARCHAR(50), nullable=False),
        sa.Column("journal_id", sa.CHAR(36), nullable=True),
        sa.Column("owner_author_id", sa.CHAR(36), nullable=True),
        sa.Column("idempotency_key", sa.VARCHAR(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.VARCHAR(30), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.TINYINT(unsigned=True), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("last_error_code", sa.VARCHAR(64), nullable=True),
        sa.Column("last_error_message", sa.TEXT(), nullable=True),
        sa.Column("created_by", sa.CHAR(36), nullable=False),
        sa.Column("created_at", sa.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", sa.DATETIME(fsp=6), nullable=True),
        sa.Column("completed_at", sa.DATETIME(fsp=6), nullable=True),
        sa.Column("updated_at", sa.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_author_id"], ["authors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("task_type", "idempotency_key", name="uq_discovery_task_idempotency"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_discovery_progress"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_discovery_status_updated", "discovery_tasks", ["status", "updated_at"])
    op.create_index("ix_discovery_owner", "discovery_tasks", ["owner_author_id", "created_at"])
    rows = op.get_bind().execute(sa.text("SELECT id, issn, eissn FROM journals")).mappings()
    for row in rows:
        for identifier_type, column in (("ISSN", "issn"), ("EISSN", "eissn")):
            if row[column] is not None:
                op.execute(
                    "INSERT INTO journal_identifiers "
                    "(id, journal_id, identifier_type, identifier_value, created_at) "
                    f"VALUES (UUID(), '{row['id']}', '{identifier_type}', "
                    f"'{normalize_issn(row[column])}', CURRENT_TIMESTAMP(6))"
                )


def downgrade() -> None:
    op.drop_table("discovery_tasks")
    op.drop_table("journal_identifiers")
    op.drop_table("journal_aliases")
    op.drop_table("publisher_aliases")
    for column in (
        "verified_at", "source_url", "identity_status", "open_access_status",
        "aims_scope", "journal_name_en",
    ):
        op.drop_column("journals", column)
    op.drop_constraint("fk_publishers_parent", "publishers", type_="foreignkey")
    op.drop_index("ix_publishers_domain", table_name="publishers")
    for column in (
        "verified_at", "source_url", "status", "parent_organization_id",
        "publisher_type", "country", "primary_domain", "publisher_name_en",
    ):
        op.drop_column("publishers", column)
```

实现时必须展开上述循环中的字段定义，不得省略 journals 或任务表结构。回填复用 `normalize_issn`，遇到非法历史值立即抛出并回滚。

- [ ] **Step 5: 验证模型、迁移和旧 head 可重复性**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_schema_constraints.py -q`

Expected: 全部通过，包括空库 upgrade/downgrade、重复 head 和现有 ISSN 回填。

### Task 2: 识别 Schema、Repository 与出版社候选服务

**Files:**
- Create: `backend/app/schemas/identification.py`
- Create: `backend/app/repositories/identification.py`
- Create: `backend/app/services/identification.py`
- Create: `backend/tests/test_identification_service.py`
- Modify: `backend/app/schemas/journals.py`
- Modify: `backend/app/services/journals.py`

**Interfaces:**
- Produces: `PublisherCandidate`、`PublisherSearchResponse`、`PublisherIdentificationService.search()`、出版社别名同步。

- [ ] **Step 1: 写出版社域名与别名匹配失败测试**

```python
def test_publisher_search_matches_alias_and_domain(db_session, admin):
    service = PublisherIdentificationService(db_session, admin, "request-publisher")
    publisher = service.create_publisher(
        name="Elsevier", website_url="https://www.elsevier.com/", aliases=["RELX"]
    )
    by_alias = service.search(name="relx", website_url=None, page=1, page_size=20)
    by_domain = service.search(name=None, website_url="HTTPS://ELSEVIER.COM", page=1, page_size=20)
    assert [item.id for item in by_alias.items] == [publisher.id]
    assert by_alias.items[0].match_reasons == ["别名精确匹配"]
    assert [item.id for item in by_domain.items] == [publisher.id]
    assert by_domain.items[0].match_reasons == ["官方域名匹配"]
```

- [ ] **Step 2: 运行并确认服务不存在**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_service.py -q`

Expected: `app.services.identification` 不存在。

- [ ] **Step 3: 实现候选 schema 与规范化**

在 `schemas/identification.py` 定义：

```python
class PublisherCandidate(OutputModel):
    id: UUID
    name: str
    website_url: str | None
    primary_domain: str | None
    status: str
    match_reasons: list[str]


class PublisherSearchResponse(OutputModel):
    items: list[PublisherCandidate]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = validate_secure_url(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("官网必须包含有效域名")
    return host
```

Repository 提供 `search_publishers(name, domain, page, page_size)`，使用 ORM 绑定参数和稳定 `name, id` 排序。

- [ ] **Step 4: 实现出版社服务与别名同步**

`PublisherIdentificationService` 提供：

```python
def create_publisher(self, *, name: str, website_url: str | None,
                     aliases: list[str]) -> Publisher:
    self._require_admin()
    publisher = Publisher(
        name=normalize_display_name(name),
        normalized_name=normalize_comparison(name),
        website_url=website_url,
        primary_domain=normalize_domain(website_url),
        created_by=self.user.id,
    )
    self.db.add(publisher)
    self.db.flush()
    self.replace_publisher_aliases(publisher, aliases)
    self.db.commit()
    return publisher


def replace_publisher_aliases(self, publisher: Publisher, aliases: list[str]) -> None:
    self.db.execute(delete(PublisherAlias).where(PublisherAlias.publisher_id == publisher.id))
    for alias in dict.fromkeys(alias.strip() for alias in aliases if alias.strip()):
        self.db.add(PublisherAlias(
            publisher_id=publisher.id, alias=alias,
            normalized_alias=normalize_comparison(alias),
        ))
    self.db.flush()


def search(self, *, name: str | None, website_url: str | None,
           page: int, page_size: int) -> PublisherSearchResponse:
    self._require_reader()
    domain = normalize_domain(website_url)
    records, total = self.repository.search_publishers(name, domain, page, page_size)
    return PublisherSearchResponse(
        items=[self._candidate(record, name, domain) for record in records],
        page=page, page_size=page_size, total=total,
    )
```

扩展现有出版社创建/更新以同步可选 `aliases`，并保持旧请求不带该字段时的行为。

- [ ] **Step 5: 运行出版社测试**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_service.py -q`

Expected: 别名、域名、重复别名去重和既有出版社 CRUD 测试通过。

### Task 3: 期刊候选、识别任务与幂等创建

**Files:**
- Modify: `backend/app/schemas/identification.py`
- Modify: `backend/app/repositories/identification.py`
- Modify: `backend/app/services/identification.py`
- Modify: `backend/app/services/journals.py`
- Modify: `backend/tests/test_identification_service.py`

**Interfaces:**
- Produces: `JournalCandidate`、`IdentifyRequest`、`IdentifyResponse`、`JournalSearchResponse`、`JournalIdentificationService.search()`、`JournalIdentificationService.identify()`。

- [ ] **Step 1: 写 ISSN、别名、多候选和错误输入失败测试**

```python
def test_identify_uses_exact_issn_without_creating_duplicates(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-identify")
    journal = service.create_journal(
        publisher_name="Elsevier", name="Journal One", issn="03785955", aliases=["J1"]
    )
    result = service.identify(IdentifyRequest(
        journal_name="J1", issn="0378-5955", idempotency_key=None
    ))
    assert result.status == "SUCCEEDED"
    assert len(result.candidates) == 1
    assert result.candidates[0].identity_status == "VERIFIED"
    assert result.candidates[0].id == journal.id


def test_identify_rejects_invalid_issn_without_writes(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-invalid")
    with pytest.raises(AppError) as caught:
        service.identify(IdentifyRequest(journal_name="Bad ISSN", issn="00000000"))
    assert caught.value.status_code == 422
    assert db_session.scalar(select(func.count(DiscoveryTask.id))) == 0


def test_identify_requires_publisher_when_creating_candidate(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-no-publisher")
    with pytest.raises(AppError) as caught:
        service.identify(IdentifyRequest(journal_name="Unknown Journal"))
    assert caught.value.status_code == 422
    assert db_session.scalar(select(func.count(Journal.id))) == 0


def test_identify_returns_all_similar_candidates_without_default_selection(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-similar")
    service.create_journal(publisher_name="P1", name="Journal of Science", aliases=[])
    service.create_journal(publisher_name="P2", name="Journal of Science", aliases=[])
    result = service.identify(IdentifyRequest(journal_name="Journal of Science"))
    assert result.candidates[0].identity_status == "NEEDS_CONFIRMATION"
    assert len(result.candidates) == 2
```

- [ ] **Step 2: 运行并确认识别方法缺失**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_service.py -q`

Expected: `create_journal` 或 `identify` 不存在。

- [ ] **Step 3: 实现确定性候选与候选创建**

测试辅助及后续共用的创建方法签名为：

```python
def create_journal(self, *, publisher_name: str, name: str,
                   issn: str | None = None, eissn: str | None = None,
                   aliases: list[str]) -> Journal:
    """仅管理员可创建；同步出版社、期刊、标识和别名。"""
```

同时扩展现有期刊创建/更新，支持可选 `aliases` 并在事务内同步 `journal_aliases`。

定义输入和候选：

```python
class JournalCandidate(OutputModel):
    id: UUID
    name: str
    publisher_id: UUID
    publisher_name: str
    issn: str | None
    eissn: str | None
    website_url: str | None
    identity_status: str
    match_reasons: list[str]
    conflict_reason: str | None
    updated_at: datetime


class IdentifyRequest(InputModel):
    publisher_name: str | None = Field(default=None, max_length=255)
    journal_name: str = Field(min_length=1, max_length=500)
    issn: str | None = Field(default=None, max_length=9)
    eissn: str | None = Field(default=None, max_length=9)
    website_url: SecureUrl | None = Field(default=None, max_length=2048)
    article_type: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class IdentifyResponse(OutputModel):
    task_id: UUID
    status: str
    candidates: list[JournalCandidate]


class JournalSearchResponse(OutputModel):
    items: list[JournalCandidate]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
```

`identify()` 必须按以下顺序处理：

1. 校验管理员和 ISSN，规范化名称、域名和输入。
2. 计算 `SHA256(task_type + canonical_input)`，查询已有任务并直接返回已有结果。
3. 依次执行标识精确匹配、域名匹配、规范名称匹配、别名匹配。
4. 唯一 ISSN 精确匹配且无冲突时返回 `VERIFIED`；多个候选时全部返回 `NEEDS_CONFIRMATION`；标识冲突返回 `CONFLICT`。
5. 没有候选时，精确匹配出版社或由非空 `publisher_name` 创建出版社，否则 422 并回滚。
6. 创建 `UNVERIFIED` 候选、ISSN/EISSN 标识关联和 `SUCCEEDED` 任务，在同一事务提交。

同时提供只读 `search(name, issn, eissn, publisher_id, website_url, page, page_size)`，复用相同候选匹配逻辑并返回 `JournalSearchResponse`，但不创建候选或任务。

- [ ] **Step 4: 实现任务幂等和冲突回滚**

```python
def _identify_locked(self, payload: IdentifyRequest) -> IdentifyResponse:
    normalized_issn = normalize_issn(payload.issn) if payload.issn else None
    normalized_eissn = normalize_issn(payload.eissn) if payload.eissn else None
    canonical_values = {
        "publisher_name": normalize_comparison(payload.publisher_name or ""),
        "journal_name": normalize_comparison(payload.journal_name),
        "issn": normalized_issn,
        "eissn": normalized_eissn,
        "website_url": normalize_domain(payload.website_url),
        "article_type": payload.article_type,
    }
    canonical = json.dumps(canonical_values, sort_keys=True, ensure_ascii=False)
    key = hashlib.sha256(f"journal.identify:{canonical}".encode()).hexdigest()
    existing = self.db.scalar(
        select(DiscoveryTask).where(
            DiscoveryTask.task_type == "journal.identify",
            DiscoveryTask.idempotency_key == key,
        )
    )
    if existing:
        return IdentifyResponse.model_validate(existing.checkpoint["response"])
    try:
        response = self._build_candidates(payload)
        task = DiscoveryTask(
            task_type="journal.identify", idempotency_key=key,
            journal_id=response.candidates[0].id if response.candidates else None,
            payload=json.loads(canonical), status="SUCCEEDED", progress=100,
            checkpoint={"response": response.model_dump(mode="json")},
            created_by=self.user.id,
        )
        self.db.add(task)
        self.db.flush()
        self.db.commit()
        return response
    except IntegrityError:
        self.db.rollback()
        raise AppError(409, "CONFLICT", "识别任务已存在，请查询现有任务") from None
    except Exception:
        self.db.rollback()
        raise
```

客户端 `idempotency_key` 只用于关联，不参与服务端唯一性判断。所有错误不得泄露 SQL 参数。

- [ ] **Step 5: 运行识别服务测试**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_service.py -q`

Expected: 精确匹配、多候选、无出版社回滚、错误 ISSN、任务幂等测试通过。

### Task 4: 人工确认与并发保护

**Files:**
- Modify: `backend/app/schemas/identification.py`
- Modify: `backend/app/services/identification.py`
- Modify: `backend/tests/test_identification_service.py`

**Interfaces:**
- Produces: `ConfirmIdentityRequest`、`JournalIdentificationService.confirm_identity()`。

- [ ] **Step 1: 写确认权限、状态与并发失败测试**

```python
def test_confirm_identity_requires_current_timestamp(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-confirm")
    journal = service.create_journal(
        publisher_name="Publisher", name="Candidate", aliases=[]
    )
    response = service.confirm_identity(
        journal.id,
        ConfirmIdentityRequest(
            expected_updated_at=journal.updated_at.replace(tzinfo=UTC),
            confirmation_note="confirmed by test",
        ),
    )
    assert response.identity_status == "VERIFIED"
    assert response.verified_at is not None
    with pytest.raises(AppError) as caught:
        service.confirm_identity(
            journal.id,
            ConfirmIdentityRequest(
                expected_updated_at=journal.updated_at.replace(tzinfo=UTC),
                confirmation_note=None,
            ),
        )
    assert caught.value.status_code == 409


def test_non_admin_cannot_confirm_identity(db_session, operator):
    service = JournalIdentificationService(db_session, operator, "request-denied")
    with pytest.raises(AppError) as caught:
        service.confirm_identity(
            "00000000-0000-4000-8000-000000000000",
            ConfirmIdentityRequest(expected_updated_at=datetime.now(UTC)),
        )
    assert caught.value.status_code == 403
```

- [ ] **Step 2: 运行并确认确认方法不存在**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_service.py -q`

Expected: `confirm_identity` 不存在。

- [ ] **Step 3: 实现带锁确认**

```python
class ConfirmIdentityRequest(InputModel):
    expected_updated_at: datetime
    confirmation_note: str | None = Field(default=None, max_length=2000)

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expected_updated_at 必须包含时区")
        return value.astimezone(UTC)


def confirm_identity(self, journal_id: str,
                     payload: ConfirmIdentityRequest) -> JournalCandidate:
    self._require_admin()
    try:
        journal = self.db.scalar(
            select(Journal).where(Journal.id == journal_id).with_for_update()
        )
        if journal is None or journal.deleted_at is not None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        current = _utc(journal.updated_at)
        if current != payload.expected_updated_at:
            raise AppError(409, "CONCURRENT_MODIFICATION", "期刊已被修改，请刷新后重试")
        if journal.identity_status not in {"UNVERIFIED", "NEEDS_CONFIRMATION", "CONFLICT"}:
            raise AppError(409, "INVALID_IDENTITY_STATE", "当前身份状态不允许确认")
        if journal.identity_status == "CONFLICT":
            raise AppError(409, "IDENTITY_CONFLICT", "请先处理身份冲突")
        before = {"identity_status": journal.identity_status}
        journal.identity_status = "VERIFIED"
        journal.verified_at = utc_now()
        self._business_audit(
            action="journal.identity.confirm", target_type="journal", target_id=journal.id,
            before=before, after={"identity_status": "VERIFIED"},
        )
        self.db.commit()
        return self._candidate(journal)
    except Exception:
        self.db.rollback()
        raise
```

- [ ] **Step 4: 运行确认和现有服务回归测试**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_service.py tests/test_journals_api.py -q`

Expected: 确认、时间戳冲突、权限和既有 CRUD 全部通过。

### Task 5: 识别 API、任务查询与 OpenAPI

**Files:**
- Create: `backend/app/api/v1/identification.py`
- Modify: `backend/app/api/v1/journals.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/contract_manifest.py`
- Create: `backend/tests/test_identification_api.py`
- Modify: `backend/tests/test_contract_manifest.py`
- Modify: `backend/tests/test_openapi_generated.py`
- Generate: `docs/api/v0.1-openapi.json`

**Interfaces:**
- Produces: `/publishers/search`、`/journals/search`、`/journals/identify`、`/journals/{journal_id}/confirm-identity`、`/tasks/{task_id}`。

- [ ] **Step 1: 写 API 权限、路由顺序和识别流程失败测试**

```python
def test_search_and_identification_routes(client, admin_context):
    publisher = client.post("/api/v1/publishers", json={
        "name": "Elsevier", "website_url": "https://www.elsevier.com/", "aliases": ["RELX"]
    })
    assert publisher.status_code == 201
    search = client.get("/api/v1/publishers/search?name=relx")
    assert search.status_code == 200
    assert search.json()["items"][0]["match_reasons"] == ["别名精确匹配"]
    identified = client.post("/api/v1/journals/identify", json={
        "publisher_name": "Elsevier", "journal_name": "Journal One", "issn": "0378-5955"
    })
    assert identified.status_code == 200, identified.text
    task = client.get(f"/api/v1/tasks/{identified.json()['task_id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "SUCCEEDED"


def test_identification_mutations_require_admin_and_csrf(client, operator_context):
    response = client.post("/api/v1/journals/identify", json={"journal_name": "Denied"})
    assert response.status_code == 403
```

- [ ] **Step 2: 运行并确认路由缺失**

Run: `cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_api.py -q`

Expected: 404 或契约路径缺失。

- [ ] **Step 3: 实现 API 与任务查询**

路由依赖使用 `get_principal`（读取）和 `require_csrf`（写操作）。出版社搜索放在现有 `journals.py` 的动态 ID 路由之前，调用 `PublisherIdentificationService.search()`；识别和确认调用 `JournalIdentificationService.identify()` 与 `confirm_identity()`：

```python
# backend/app/api/v1/journals.py：必须位于 /publishers/{publisher_id} 之前
@router.get("/publishers/search", response_model=PublisherSearchResponse)
def search_publishers(request, db=Depends(get_db), principal=Depends(get_principal),
                      name: str | None = None, website_url: str | None = None,
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return PublisherIdentificationService(db, principal.user, request.state.request_id).search(
        name=name, website_url=website_url, page=page, page_size=page_size
    )

# 同文件在 /journals/{journal_id} 之前增加 GET /journals/search，并调用
# JournalIdentificationService 的候选搜索方法。
```

`identification.py` 用于识别、确认和任务查询：

```python
def identification_service(db, principal, request):
    return JournalIdentificationService(db, principal.user, request.state.request_id)


@router.post("/journals/identify", response_model=IdentifyResponse)
def identify_journal(request, payload: IdentifyRequest,
                     db=Depends(get_db), principal=Depends(require_csrf)):
    return identification_service(db, principal, request).identify(payload)


@router.post("/journals/{journal_id}/confirm-identity", response_model=JournalCandidate)
def confirm_identity(journal_id: UUID, request, payload: ConfirmIdentityRequest,
                     db=Depends(get_db), principal=Depends(require_csrf)):
    return identification_service(db, principal, request).confirm_identity(
        str(journal_id), payload
    )
```

静态 `/search` 注册在动态 ID 路由之前。`GET /tasks/{task_id}` 按以下结构返回，含 `owner_author_id` 时执行作者授权校验：

```python
class TaskResponse(OutputModel):
    task_id: UUID
    task_type: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str | None
    candidates: list[JournalCandidate]


def task_response(task: DiscoveryTask) -> TaskResponse:
    checkpoint = task.checkpoint or {}
    return TaskResponse(
        task_id=UUID(task.id), task_type=task.task_type, status=task.status,
        progress=task.progress, message=task.last_error_message,
        candidates=checkpoint.get("response", {}).get("candidates", []),
    )
```

- [ ] **Step 4: 更新契约并生成 OpenAPI**

在 manifest 增加上述五条路由；为请求、候选、任务和确认模型增加中文标题、摘要及标签。新增契约测试：

```python
def test_identification_contract_present():
    paths = app.openapi()["paths"]
    assert "/api/v1/publishers/search" in paths
    assert "/api/v1/journals/identify" in paths
    assert "/api/v1/journals/{journal_id}/confirm-identity" in paths
    assert "/api/v1/tasks/{task_id}" in paths
```

Run: `PYTHONPATH=backend .venv/bin/python scripts/export_openapi.py && cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_identification_api.py tests/test_contract_manifest.py tests/test_openapi_generated.py -q`

Expected: API、路由顺序和契约全部通过。

### Task 6: 前端识别 API 与识别工作台

**Files:**
- Create: `frontend/src/api/identification.ts`
- Create: `frontend/src/views/journals/JournalIdentificationPanel.vue`
- Create: `frontend/src/views/journals/JournalIdentificationPanel.test.ts`
- Modify: `frontend/src/views/journals/JournalListView.vue`
- Modify: `frontend/src/views/journals/JournalListView.test.ts`

**Interfaces:**
- Consumes: Task 5 的搜索、识别和确认接口。
- Produces: 识别 Tab、候选选择、人工确认和任务状态展示。

- [ ] **Step 1: 写识别工作台失败测试**

```typescript
it('shows candidates and requires manual selection before confirmation', async () => {
  adapter.mockImplementation(async (config) => {
    if (config.url === '/journals/identify') return success(config, identifyResponse)
    if (config.url?.endsWith('/confirm-identity')) return success(config, verifiedCandidate)
    return success(config, emptyPage)
  })
  const wrapper = mount(JournalIdentificationPanel)
  await wrapper.get('[data-test="identify-journal-name"]').setValue('Journal of Science')
  await wrapper.get('[data-test="identify-publisher-name"]').setValue('Publisher')
  await wrapper.get('[data-test="identify-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.findAll('[data-test="identity-candidate"]').length).toBe(2)
  expect(wrapper.get('[data-test="confirm-identity"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="select-candidate-j2"]').setValue(true)
  await wrapper.get('[data-test="confirm-identity"]').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('已验证')
  expectSaveSuccessToast()
})
```

测试夹具 `identifyResponse` 必须包含两个不同 `journal_id`、`updated_at` 和 `NEEDS_CONFIRMATION`；`verifiedCandidate` 必须与选中候选 ID 一致且包含 `VERIFIED`。

另测错误 ISSN 显示 422、无候选、冲突候选不可确认、未确认不得显示 `VERIFIED`。

- [ ] **Step 2: 运行并确认组件不存在**

Run: `npm --prefix frontend test -- src/views/journals/JournalIdentificationPanel.test.ts`

Expected: 组件解析失败。

- [ ] **Step 3: 实现 API 类型与组件**

`api/identification.ts` 定义与后端一致的 `JournalCandidate`、`IdentifyRequest`、`IdentifyResponse`，实现 `identifyJournal`、`confirmIdentity` 和 `getDiscoveryTask`。

组件状态：

```typescript
const form = reactive({
  publisher_name: '', journal_name: '', issn: '', eissn: '', website_url: '', article_type: '',
})
const candidates = ref<JournalCandidate[]>([])
const selectedJournalId = ref('')
const identifying = ref(false)
const confirming = ref(false)
const errorMessage = ref('')

const canConfirm = computed(() => Boolean(
  selectedJournalId.value
  && candidates.value.length > 0
  && candidates.value.every((candidate) => candidate.identity_status !== 'CONFLICT')
))
```

提交识别后仅在用户点击候选时设置 `selectedJournalId`，不得自动赋值。确认请求携带选中候选的 `updated_at` 和确认说明；409 时清空候选并提示重新识别。

- [ ] **Step 4: 接入现有 Tab 并运行前端测试**

在 `JournalListView.vue` 的 `activeTab` 联合类型加入 `'identification'`，增加识别 Tab 和组件：

```vue
<button type="button" role="tab" data-test="identification-tab"
        :aria-selected="activeTab === 'identification'"
        @click="selectTab('identification')">识别</button>
<JournalIdentificationPanel v-if="activeTab === 'identification'" />
```

保持原三个 Tab 的内容与加载逻辑不变。

Run: `npm --prefix frontend test -- src/views/journals/JournalIdentificationPanel.test.ts src/views/journals/JournalListView.test.ts`

Expected: 新组件和原页面测试全部通过。

### Task 7: 全量回归与交付检查

**Files:**
- Modify only files required by verification failures.

**Interfaces:**
- Consumes: Tasks 1–6 的全部实现。

- [ ] **Step 1: 运行完整项目验证**

Run:

```bash
bash scripts/verify.sh
git diff --check
git status --short
```

Expected: Ruff、Mypy、后端、前端、覆盖率、OpenAPI、Newman 和生产构建全部通过。

- [ ] **Step 2: 核对第一期验收边界**

逐项确认：

- 正确 ISSN 可识别，错误 ISSN 422。
- 多候选必须人工选择，冲突不得直接确认。
- 无出版社候选创建完整回滚。
- 重复识别不重复创建任务或候选。
- 过期确认返回 409。
- 原出版社、平台和期刊 CRUD 均通过。
- 未实现外部抓取、AI、投稿入口自动发现和自动提交，文档与界面未将这些能力写成已完成。

不自动提交或推送；报告实际测试数量、变更文件和任何遗留问题。
