# 用户管理功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为系统管理员提供完整的用户列表、新增、编辑、启停用和密码重置功能，并保证密码与最后一名管理员安全。

**Architecture:** 新增独立 `/api/v1/users` API 和 `UserManagementService`，复用现有用户、角色、会话及审计模型。前端新增管理员专属用户管理页面，通过统一 API 类型、路由守卫、成功提示和事务化后端操作完成闭环。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy、MySQL、Argon2、Vue 3、TypeScript、Pinia、Vue Router、Element Plus、Vitest、Pytest。

**Spec:** `docs/superpowers/specs/2026-11-12-user-management-design.md`

## Global Constraints

- 仅 `system_admin` 可访问用户管理接口和页面；所有写操作要求 CSRF。
- 角色只允许 `system_admin`、`submission_operator`、`reviewer`、`author`、`auditor`，至少一项且不重复。
- 密码与确认密码必须一致，并复用 `validate_new_password`；密码、哈希、会话和 CSRF 数据不得进入响应或审计摘要。
- 禁止自我停用、自我移除 `system_admin`，并始终保留至少一名启用中的系统管理员。
- 停用和重置密码必须注销目标用户全部会话，重置后 `must_change_password=true`。
- 不删除用户、不修改用户名、不新增数据库表、不改变现有作者授权逻辑。
- 保留工作区现有未提交修改；每个任务只暂存检查，不自动 commit 或 push。
- 所有生产行为先写失败测试并确认失败原因，再写最小实现；最后运行完整 `scripts/verify.sh`。

## Review Focus

- 大小写或空白不同但规范化后相同的用户名：必须返回 `409`，且不能留下用户或角色关联；Task 2 的重复创建测试覆盖。
- 空角色、重复角色和未知角色：必须返回 `422`，已有角色不得被部分清除；Task 1 的 schema 测试和 Task 4 的 API 测试覆盖。
- 两名管理员并发降权：更新必须锁定当前启用管理员记录并在锁内重新计算；Task 3 检查 `FOR UPDATE` 及最后管理员保护。
- 重置本人密码：返回 `204` 后旧会话必须失效，前端清除本地会话；Task 4 和 Task 7 覆盖。
- 密码出现在响应体、操作日志或异常文本中的泄露风险：任何路径都不得泄露；Task 2、Task 3、Task 4 显式检查敏感字符串不存在。

---

### Task 1: 用户管理 schema 与只读服务

**Files:**
- Create: `backend/app/schemas/users.py`
- Create: `backend/app/services/users.py`
- Create: `backend/tests/test_user_management_service.py`

**Interfaces:**
- Consumes: `DomainService`、`Page`、`InputModel`、`OutputModel`、现有 `User/Role/UserRole` 模型。
- Produces: `RoleCode`、`UserCreate`、`UserUpdate`、`UserPasswordReset`、`ManagedUserResponse`、`UserPage`、`UserManagementService.list_page()`、`UserManagementService.get()`。

- [ ] **Step 1: 写 schema 与只读服务的失败测试**

在 `backend/tests/test_user_management_service.py` 写入：

```python
import pytest
from pydantic import ValidationError

from app.schemas.users import UserCreate, UserUpdate
from app.services.users import UserManagementService


def test_roles_reject_empty_duplicate_and_unknown_values():
    base = {
        "username": "new-user",
        "display_name": "New User",
        "password": "Strong-Passphrase-2026!",
        "password_confirmation": "Strong-Passphrase-2026!",
    }
    for roles in ([], ["author", "author"], ["unknown"]):
        with pytest.raises(ValidationError):
            UserCreate(**base, roles=roles)


def test_update_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        UserUpdate()


def test_list_filters_sorts_and_hides_credentials(db_session, admin, user_factory):
    user_factory("z-operator", roles=("submission_operator",))
    user_factory("a-disabled", roles=("author",), status="disabled")
    service = UserManagementService(db_session, admin, "request-list")
    page = service.list_page(
        page=1, page_size=20, name="operator", status="active",
        sort="username", order="asc",
    )
    assert [item.username for item in page.items] == ["z-operator"]
    assert "password_hash" not in page.model_dump_json()


def test_read_requires_admin(db_session, operator):
    service = UserManagementService(db_session, operator, "request-denied")
    with pytest.raises(Exception) as caught:
        service.list_page(
            page=1, page_size=20, name=None, status=None,
            sort="username", order="asc",
        )
    assert caught.value.status_code == 403
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_user_management_service.py -q
```

Expected: 收集或执行失败，因为 `app.schemas.users` / `app.services.users` 尚不存在。

- [ ] **Step 3: 实现精确 schema**

创建 `backend/app/schemas/users.py`：

```python
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.common import InputModel, OutputModel, Page, require_update_fields

RoleCode = Literal[
    "system_admin", "submission_operator", "reviewer", "author", "auditor"
]
UserStatus = Literal["active", "disabled"]


def validate_roles(value: list[RoleCode]) -> list[RoleCode]:
    if len(value) != len(set(value)):
        raise ValueError("角色不得重复")
    return value


class UserCreate(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    password_confirmation: str = Field(min_length=6, max_length=128)
    roles: list[RoleCode] = Field(min_length=1)

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value):
        return validate_roles(value)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致")
        return self


class UserUpdate(InputModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    roles: list[RoleCode] | None = Field(default=None, min_length=1)
    status: UserStatus | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_display_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value):
        return validate_roles(value) if value is not None else value

    @model_validator(mode="after")
    def require_change(self):
        require_update_fields(self)
        return self


class UserPasswordReset(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    new_password: str = Field(min_length=6, max_length=128)
    password_confirmation: str = Field(min_length=6, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致")
        return self


class ManagedUserResponse(OutputModel):
    id: UUID
    username: str
    display_name: str
    roles: list[RoleCode]
    status: UserStatus
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


UserPage = Page[ManagedUserResponse]
```

- [ ] **Step 4: 实现只读服务骨架**

创建 `backend/app/services/users.py`，实现 `_require_admin`、`_role_codes`、`_response`、`list_page` 和 `get`。核心查询如下：

```python
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Role, User, UserRole
from app.schemas.users import ManagedUserResponse, RoleCode, UserPage, UserStatus
from app.services.authors import DomainService


class UserManagementService(DomainService):
    SORT_FIELDS = {
        "username": User.username,
        "display_name": User.display_name,
        "created_at": User.created_at,
        "updated_at": User.updated_at,
        "last_login_at": User.last_login_at,
    }

    def _role_codes(self, user_id: str) -> list[str]:
        return list(self.db.scalars(
            select(Role.code).join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id).order_by(Role.code)
        ).all())

    def _response(self, user: User) -> ManagedUserResponse:
        def utc(value: datetime | None) -> datetime | None:
            return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
        created_at = utc(user.created_at)
        updated_at = utc(user.updated_at)
        assert created_at is not None and updated_at is not None
        return ManagedUserResponse(
            id=UUID(user.id), username=user.username,
            display_name=user.display_name,
            roles=cast(list[RoleCode], self._role_codes(user.id)),
            status=cast(UserStatus, user.status),
            must_change_password=user.must_change_password,
            last_login_at=utc(user.last_login_at),
            created_at=created_at, updated_at=updated_at,
        )

    def list_page(self, *, page: int, page_size: int, name: str | None,
                  status: str | None, sort: str, order: str) -> UserPage:
        self._require_admin()
        if sort not in self.SORT_FIELDS:
            raise AppError(422, "VALIDATION_ERROR", "不支持的排序字段")
        filters = [User.deleted_at.is_(None)]
        if name and name.strip():
            pattern = f"%{name.strip()}%"
            filters.append(or_(User.username.like(pattern), User.display_name.like(pattern)))
        if status:
            filters.append(User.status == status)
        total = self.db.scalar(select(func.count(User.id)).where(*filters)) or 0
        column = self.SORT_FIELDS[sort]
        records = self.db.scalars(
            select(User).where(*filters)
            .order_by(column.asc() if order == "asc" else column.desc(), User.id)
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return UserPage(
            items=[self._response(user) for user in records],
            page=page, page_size=page_size, total=total,
        )

    def get(self, user_id: str) -> ManagedUserResponse:
        self._require_admin()
        user = self.db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return self._response(user)
```

- [ ] **Step 5: 运行只读测试并检查差异**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_user_management_service.py -q
git diff --check
```

Expected: 测试通过，无空白错误；不提交。

### Task 2: 创建用户与安全审计

**Files:**
- Modify: `backend/app/services/users.py`
- Modify: `backend/tests/test_user_management_service.py`

**Interfaces:**
- Consumes: Task 1 的 `UserCreate`、`ManagedUserResponse`、`DomainService._commit()`。
- Produces: `UserManagementService.create(payload: UserCreate) -> ManagedUserResponse`。

- [ ] **Step 1: 写创建、哈希、角色和重复用户名的失败测试**

追加：

```python
from sqlalchemy import func, select

from app.models import OperationLog, User, UserRole
from app.schemas.users import UserCreate
from app.security.passwords import verify_password


def payload(username="new-user", roles=None):
    return UserCreate(
        username=username, display_name="New User",
        password="Strong-Passphrase-2026!",
        password_confirmation="Strong-Passphrase-2026!",
        roles=roles or ["submission_operator", "reviewer"],
    )


def test_create_hashes_password_assigns_roles_and_audits(db_session, admin):
    service = UserManagementService(db_session, admin, "request-create")
    result = service.create(payload())
    record = db_session.get(User, str(result.id))
    assert verify_password(record.password_hash, "Strong-Passphrase-2026!")
    assert record.must_change_password is True
    assert result.roles == ["reviewer", "submission_operator"]
    log = db_session.scalar(select(OperationLog).where(
        OperationLog.action == "user.create"
    ))
    assert log.after_summary["username"] == "new-user"
    assert "Strong-Passphrase-2026!" not in str(log.after_summary)
    assert "password" not in result.model_dump_json()


def test_duplicate_normalized_username_rolls_back(db_session, admin, user_factory):
    existing = user_factory("Existing-User", roles=("author",))
    existing.normalized_username = "existing-user"
    db_session.commit()
    before_count = db_session.scalar(select(func.count(User.id)))
    service = UserManagementService(db_session, admin, "request-duplicate")
    with pytest.raises(Exception) as caught:
        service.create(payload(" existing-user "))
    assert caught.value.status_code == 409
    assert db_session.scalar(select(func.count(User.id))) == before_count
```

- [ ] **Step 2: 运行并确认 `create` 缺失导致失败**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_user_management_service.py -q
```

Expected: 新测试因 `UserManagementService.create` 不存在而失败。

- [ ] **Step 3: 实现事务化创建**

在 `UserManagementService` 增加 `_audit` 和 `create`：

```python
from sqlalchemy.exc import IntegrityError

from app.schemas.users import UserCreate
from app.security.passwords import hash_password, normalize_username, validate_new_password

AUDIT_FIELDS = frozenset({"username", "display_name", "roles", "status"})


def _validate_password(username: str, password: str) -> None:
    try:
        validate_new_password(username, password)
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc)) from None


def _audit(self, *, action: str, target_id: str, before=None, after=None):
    self.audit.record(
        actor_user_id=self.user.id, actor_type="user", category="business",
        action=action, target_type="user", target_id=target_id,
        request_id=self.request_id, result="success",
        before=before, after=after, allowed_fields=AUDIT_FIELDS,
    )


def create(self, payload: UserCreate) -> ManagedUserResponse:
    self._require_admin()
    normalized = normalize_username(payload.username)
    _validate_password(payload.username, payload.password)
    try:
        roles = list(self.db.scalars(
            select(Role).where(Role.code.in_(payload.roles))
        ).all())
        if {role.code for role in roles} != set(payload.roles):
            raise AppError(422, "VALIDATION_ERROR", "包含无效角色")
        user = User(
            username=payload.username, normalized_username=normalized,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password), status="active",
            must_change_password=True, created_by=self.user.id,
        )
        self.db.add(user)
        self.db.flush()
        for role in roles:
            self.db.add(UserRole(
                user_id=user.id, role_id=role.id, assigned_by=self.user.id
            ))
        self.db.flush()
        self._audit(
            action="user.create", target_id=user.id,
            after={"username": user.username, "display_name": user.display_name,
                   "roles": sorted(payload.roles), "status": "active"},
        )
        self.db.commit()
        return self._response(user)
    except IntegrityError:
        self.db.rollback()
        raise AppError(409, "CONFLICT", "用户名已存在") from None
    except Exception:
        self.db.rollback()
        raise
```

- [ ] **Step 4: 运行创建测试**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_user_management_service.py -q
```

Expected: 全部通过；响应和审计均不包含密码。

### Task 3: 编辑、启停用、管理员保护与密码重置

**Files:**
- Modify: `backend/app/services/users.py`
- Modify: `backend/tests/test_user_management_service.py`

**Interfaces:**
- Consumes: `UserUpdate`、`UserPasswordReset`、`SessionService.revoke_all()`。
- Produces: `update(user_id, payload)`、`reset_password(user_id, payload)`、`_lock_active_admin_ids()`。

- [ ] **Step 1: 写更新、自我保护和最后管理员失败测试**

追加：

```python
from app.schemas.users import UserUpdate


def test_update_roles_and_disable_revokes_sessions(
    db_session, admin, user_factory, auth_context_factory
):
    target = user_factory("target", roles=("reviewer",))
    context = auth_context_factory(target)
    service = UserManagementService(db_session, admin, "request-update")
    result = service.update(
        target.id, UserUpdate(roles=["author", "auditor"], status="disabled")
    )
    db_session.expire_all()
    assert result.roles == ["auditor", "author"]
    assert result.status == "disabled"
    assert context.session.revoked_at is not None


def test_self_disable_and_self_admin_removal_are_rejected(db_session, admin):
    service = UserManagementService(db_session, admin, "request-self")
    with pytest.raises(Exception) as caught:
        service.update(admin.id, UserUpdate(status="disabled"))
    assert caught.value.status_code == 409
    with pytest.raises(Exception) as caught:
        service.update(admin.id, UserUpdate(roles=["auditor"]))
    assert caught.value.status_code == 409


def test_other_admin_can_be_disabled_when_actor_remains(db_session, admin, user_factory):
    other = user_factory("other-admin", roles=("system_admin",))
    service = UserManagementService(db_session, admin, "request-other")
    result = service.update(other.id, UserUpdate(status="disabled"))
    assert result.status == "disabled"
```

- [ ] **Step 2: 写重置密码和锁查询失败测试**

追加：

```python
from sqlalchemy import event

from app.schemas.users import UserPasswordReset


def test_reset_password_revokes_sessions_without_auditing_secret(
    db_session, admin, user_factory, auth_context_factory
):
    target = user_factory("reset-target", roles=("author",))
    context = auth_context_factory(target)
    service = UserManagementService(db_session, admin, "request-reset")
    service.reset_password(target.id, UserPasswordReset(
        new_password="Reset-Passphrase-2026!",
        password_confirmation="Reset-Passphrase-2026!",
    ))
    db_session.expire_all()
    assert verify_password(target.password_hash, "Reset-Passphrase-2026!")
    assert target.must_change_password is True
    assert context.session.revoked_at is not None
    logs = db_session.scalars(select(OperationLog).where(
        OperationLog.action == "user.password.reset"
    )).all()
    assert logs
    assert all("Reset-Passphrase-2026!" not in str(item.after_summary) for item in logs)


def test_admin_protection_query_uses_row_locks(db_session, admin):
    statements = []
    event.listen(db_session, "before_cursor_execute", lambda *args: statements.append(args[2]))
    service = UserManagementService(db_session, admin, "request-lock")
    service._lock_active_admin_ids()
    assert any("FOR UPDATE" in statement.upper() for statement in statements)
```

- [ ] **Step 3: 运行并确认更新/重置方法缺失导致失败**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_user_management_service.py -q
```

Expected: 新方法相关测试失败。

- [ ] **Step 4: 实现管理员锁、更新和重置**

在 `UserManagementService` 增加：

```python
from app.core.config import get_settings
from app.schemas.users import UserPasswordReset, UserUpdate
from app.security.sessions import SessionService


def _lock_active_admin_ids(self) -> set[str]:
    return set(self.db.scalars(
        select(User.id).join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == "system_admin", User.status == "active",
               User.deleted_at.is_(None))
        .with_for_update()
    ).all())


def _locked_user(self, user_id: str) -> User:
    user = self.db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or user.deleted_at is not None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
    return user


def update(self, user_id: str, payload: UserUpdate) -> ManagedUserResponse:
    self._require_admin()
    target = self._locked_user(user_id)
    if target.id == self.user.id and payload.status == "disabled":
        self.db.rollback()
        raise AppError(409, "ADMIN_PROTECTED", "不能停用当前管理员账号")
    if target.id == self.user.id and payload.roles is not None and "system_admin" not in payload.roles:
        self.db.rollback()
        raise AppError(409, "ADMIN_PROTECTED", "不能移除当前账号的管理员角色")
    admin_ids = self._lock_active_admin_ids()
    loses_admin = payload.status == "disabled" or (
        payload.roles is not None and "system_admin" not in payload.roles
    )
    if loses_admin and not admin_ids.difference({target.id}):
        self.db.rollback()
        raise AppError(409, "ADMIN_PROTECTED", "系统至少需要一名启用中的管理员")
    before = {"username": target.username, "display_name": target.display_name,
              "roles": self._role_codes(target.id), "status": target.status}
    try:
        if payload.display_name is not None:
            target.display_name = payload.display_name
        if payload.status is not None:
            target.status = payload.status
        if payload.roles is not None:
            self.db.query(UserRole).filter(UserRole.user_id == target.id).delete()
            roles = list(self.db.scalars(select(Role).where(Role.code.in_(payload.roles))).all())
            if {role.code for role in roles} != set(payload.roles):
                raise AppError(422, "VALIDATION_ERROR", "包含无效角色")
            for role in roles:
                self.db.add(UserRole(user_id=target.id, role_id=role.id, assigned_by=self.user.id))
        if target.status == "disabled":
            SessionService(self.db, get_settings()).revoke_all(target.id)
        self.db.flush()
        self._audit(action="user.update", target_id=target.id, before=before, after={
            "username": target.username, "display_name": target.display_name,
            "roles": sorted(payload.roles) if payload.roles is not None else before["roles"],
            "status": target.status,
        })
        self.db.commit()
        return self._response(target)
    except Exception:
        self.db.rollback()
        raise


def reset_password(self, user_id: str, payload: UserPasswordReset) -> None:
    self._require_admin()
    target = self._locked_user(user_id)
    try:
        _validate_password(target.username, payload.new_password)
        target.password_hash = hash_password(payload.new_password)
        target.must_change_password = True
        SessionService(self.db, get_settings()).revoke_all(target.id)
        self._audit(action="user.password.reset", target_id=target.id)
        self.db.commit()
    except Exception:
        self.db.rollback()
        raise
```

注意：重置密码审计只记录动作，不传 `must_change_password` 摘要，因为现有审计脱敏器会拒绝任何包含 `password` 的键。

- [ ] **Step 5: 运行全部服务测试**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_user_management_service.py -q
```

Expected: 全部通过。

### Task 4: 用户管理 API、CSRF 与 OpenAPI 契约

**Files:**
- Create: `backend/app/api/v1/users.py`
- Modify: `backend/app/main.py:12-22,30-105,266-340,411-419`
- Modify: `backend/app/api/v1/contract_manifest.py`
- Create: `backend/tests/test_users_api.py`
- Modify: `backend/tests/test_contract_manifest.py`
- Modify: `backend/tests/test_openapi_generated.py`
- Generate: `docs/api/v0.1-openapi.json`

**Interfaces:**
- Consumes: Task 1–3 的全部服务方法。
- Produces: `GET/POST /api/v1/users`、`GET/PATCH /api/v1/users/{user_id}`、`POST /api/v1/users/{user_id}/reset-password`。

- [ ] **Step 1: 写管理员权限、CRUD、CSRF 和自我重置失败测试**

创建 `backend/tests/test_users_api.py`：

```python
from sqlalchemy import select

from app.models import OperationLog


def user_payload(username="api-user"):
    return {
        "username": username, "display_name": "API User",
        "password": "Api-Passphrase-2026!",
        "password_confirmation": "Api-Passphrase-2026!",
        "roles": ["submission_operator", "reviewer"],
    }


def test_users_require_admin(client, operator_context):
    assert client.get("/api/v1/users").status_code == 403
    assert client.post("/api/v1/users", json=user_payload()).status_code == 403


def test_create_get_patch_and_reset_user(client, db_session, admin_context):
    created = client.post("/api/v1/users", json=user_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["roles"] == ["reviewer", "submission_operator"]
    assert "Api-Passphrase-2026!" not in created.text
    assert "password_hash" not in created.text

    detail = client.get(f"/api/v1/users/{body['id']}")
    assert detail.status_code == 200
    updated = client.patch(
        f"/api/v1/users/{body['id']}",
        json={"display_name": "Updated User", "roles": ["author"], "status": "disabled"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "disabled"
    reset = client.post(
        f"/api/v1/users/{body['id']}/reset-password",
        json={"new_password": "Reset-Api-2026!", "password_confirmation": "Reset-Api-2026!"},
    )
    assert reset.status_code == 204
    assert b"Reset-Api-2026!" not in reset.content
    logs = db_session.scalars(select(OperationLog)).all()
    assert "Reset-Api-2026!" not in str([item.after_summary for item in logs])


def test_mutations_require_csrf(client, admin_context):
    response = client.post(
        "/api/v1/users", json=user_payload("csrf-user"),
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert response.status_code == 403


def test_self_reset_invalidates_current_session(client, admin, admin_context):
    response = client.post(
        f"/api/v1/users/{admin.id}/reset-password",
        json={"new_password": "Self-Reset-2026!", "password_confirmation": "Self-Reset-2026!"},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_role_sort_and_unknown_user_return_safe_errors(client, admin_context):
    assert client.post("/api/v1/users", json=user_payload() | {"roles": ["unknown"]}).status_code == 422
    assert client.get("/api/v1/users?sort=password_hash").status_code == 422
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/v1/users/{missing}").status_code == 404
```

- [ ] **Step 2: 运行并确认路由不存在导致失败**

Run:

```bash
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_users_api.py -q
```

Expected: 请求返回 `404` 或路由注册断言失败，而不是测试语法错误。

- [ ] **Step 3: 实现 API 路由**

创建 `backend/app/api/v1/users.py`：

```python
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, get_principal, require_csrf
from app.core.database import get_db
from app.schemas.users import (
    ManagedUserResponse, UserCreate, UserPage, UserPasswordReset, UserUpdate,
)
from app.services.users import UserManagementService

router = APIRouter(prefix="/api/v1/users", tags=["users"])
Status = Literal["active", "disabled"]
Order = Literal["asc", "desc"]


def service(db: Session, principal: Principal, request: Request) -> UserManagementService:
    return UserManagementService(db, principal.user, request.state.request_id)


@router.get("", response_model=UserPage)
def list_users(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None, max_length=128), status: Status | None = None,
    sort: str = "created_at", order: Order = "desc",
) -> UserPage:
    return service(db, principal, request).list_page(
        page=page, page_size=page_size, name=name, status=status, sort=sort, order=order
    )


@router.post("", response_model=ManagedUserResponse, status_code=201)
def create_user(
    request: Request, payload: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManagedUserResponse:
    return service(db, principal, request).create(payload)


@router.get("/{user_id}", response_model=ManagedUserResponse)
def get_user(
    user_id: str, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ManagedUserResponse:
    return service(db, principal, request).get(user_id)


@router.patch("/{user_id}", response_model=ManagedUserResponse)
def update_user(
    user_id: str, request: Request, payload: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> ManagedUserResponse:
    return service(db, principal, request).update(user_id, payload)


@router.post("/{user_id}/reset-password", status_code=204, response_model=None)
def reset_user_password(
    user_id: str, request: Request, payload: UserPasswordReset,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Response:
    service(db, principal, request).reset_password(user_id, payload)
    return Response(status_code=204)
```

在 `main.py` 导入并 `app.include_router(users.router)`；在契约清单加入五条精确路由和响应模型。为 `list_users`、`create_user`、`get_user`、`update_user`、`reset_user_password` 添加中文摘要，为 `users` 标签、`UserCreate`、`UserUpdate`、`UserPasswordReset`、`ManagedUserResponse`、`UserPage` 及 `password_confirmation` 添加中文标题。

- [ ] **Step 4: 更新契约测试并生成 OpenAPI**

在 `test_contract_manifest.py` 的 `EXPECTED_ROUTES` 加入上述五条路由。在 `test_openapi_generated.py` 增加：

```python
def test_user_management_contract_hides_password_storage():
    document = app.openapi()
    paths = document["paths"]
    assert "/api/v1/users" in paths
    assert "/api/v1/users/{user_id}/reset-password" in paths
    properties = document["components"]["schemas"]["ManagedUserResponse"]["properties"]
    assert "password_hash" not in properties
    assert "password" not in properties
    assert "last_login_at" in properties
```

Run:

```bash
PYTHONPATH=backend .venv/bin/python scripts/export_openapi.py
cd backend && env ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_users_api.py tests/test_contract_manifest.py tests/test_openapi_generated.py -q
```

Expected: API 与契约测试通过，OpenAPI 文件更新。

### Task 5: 前端用户 API、管理员路由与导航

**Files:**
- Create: `frontend/src/api/users.ts`
- Modify: `frontend/src/router/index.ts:49-79`
- Modify: `frontend/src/router/index.test.ts`
- Modify: `frontend/src/App.vue:12-22,46-60`
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/components/AppIcon.vue:16-25`

**Interfaces:**
- Consumes: Task 4 的 HTTP 契约、现有 `api` Axios 实例和 `Page` 类型。
- Produces: `listUsers`、`createUser`、`getUser`、`updateUser`、`resetUserPassword` 及 `/users` 管理员路由。

- [ ] **Step 1: 写路由和导航失败测试**

在 `router/index.test.ts` 添加：

```typescript
it('allows only system administrators to open user management', async () => {
  const router = createAppRouter(createMemoryHistory())
  const auth = useAuthStore()
  auth.setSession({ ...activeUser, roles: ['submission_operator'] }, 'csrf')
  await router.push('/users')
  expect(router.currentRoute.value.name).toBe('dashboard')

  auth.setSession({ ...activeUser, roles: ['system_admin'] }, 'csrf')
  await router.push('/users')
  expect(router.currentRoute.value.name).toBe('user-list')
})
```

在 `App.test.ts` 添加管理员看到“用户管理”、投稿操作员看不到该入口的测试：

```typescript
it('shows user management only to system administrators', () => {
  useAuthStore().setSession({ ...user, roles: ['system_admin'] }, 'csrf')
  const adminWrapper = mount(App, { global })
  expect(adminWrapper.text()).toContain('用户管理')

  useAuthStore().setSession({ ...user, roles: ['submission_operator'] }, 'csrf')
  const operatorWrapper = mount(App, { global })
  expect(operatorWrapper.text()).not.toContain('用户管理')
})
```

- [ ] **Step 2: 运行并确认 `/users` 与导航缺失导致失败**

Run:

```bash
npm --prefix frontend test -- src/router/index.test.ts src/App.test.ts
```

Expected: 新路由和导航断言失败。

- [ ] **Step 3: 实现前端 API 类型与方法**

创建 `frontend/src/api/users.ts`：

```typescript
import { api } from './client'
import type { Page, SortOrder } from './authors'

export type RoleCode = 'system_admin' | 'submission_operator' | 'reviewer' | 'author' | 'auditor'
export type UserStatus = 'active' | 'disabled'

export interface ManagedUser {
  id: string
  username: string
  display_name: string
  roles: RoleCode[]
  status: UserStatus
  must_change_password: boolean
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export interface UserListQuery {
  page?: number
  page_size?: number
  name?: string
  status?: UserStatus
  sort?: 'username' | 'display_name' | 'created_at' | 'updated_at' | 'last_login_at'
  order?: SortOrder
}

export interface UserCreate {
  username: string
  display_name: string
  password: string
  password_confirmation: string
  roles: RoleCode[]
}

export interface UserUpdate {
  display_name?: string
  roles?: RoleCode[]
  status?: UserStatus
}

export interface UserPasswordReset {
  new_password: string
  password_confirmation: string
}

export async function listUsers(query: UserListQuery = {}): Promise<Page<ManagedUser>> {
  const response = await api.get<Page<ManagedUser>>('/users', {
    params: { page: 1, page_size: 20, sort: 'created_at', order: 'desc', ...query },
  })
  return response.data
}

export async function createUser(payload: UserCreate): Promise<ManagedUser> {
  const response = await api.post<ManagedUser>('/users', payload)
  return response.data
}

export async function getUser(userId: string): Promise<ManagedUser> {
  const response = await api.get<ManagedUser>(`/users/${userId}`)
  return response.data
}

export async function updateUser(userId: string, payload: UserUpdate): Promise<ManagedUser> {
  const response = await api.patch<ManagedUser>(`/users/${userId}`, payload)
  return response.data
}

export async function resetUserPassword(userId: string, payload: UserPasswordReset): Promise<void> {
  await api.post(`/users/${userId}/reset-password`, payload)
}
```

- [ ] **Step 4: 注册管理员路由、导航和图标**

在路由数组加入：

```typescript
{
  path: '/users',
  name: 'user-list',
  component: () => import('../views/users/UserListView.vue'),
  meta: { requiresAuth: true, roles: ['system_admin'] },
},
```

在 `App.vue` 增加 `isAdmin` 计算属性，将导航改为计算列表并仅在管理员时追加：

```typescript
const isAdmin = computed(() => auth.user?.roles.includes('system_admin') ?? false)
const navigation = computed(() => [
  { to: '/dashboard', label: '工作台', icon: 'dashboard' },
  { to: '/manuscripts', label: '稿件管理', icon: 'manuscripts' },
  { to: '/authors', label: '作者与单位', icon: 'authors' },
  { to: '/authorizations', label: '作者授权', icon: 'authorizations' },
  { to: '/journals', label: '期刊管理', icon: 'journals' },
  ...(isAdmin.value ? [{ to: '/users', label: '用户管理', icon: 'users' }] : []),
])
```

在 `AppIcon.vue` 增加用户管理图标分支：

```vue
<template v-else-if="name === 'users'">
  <circle cx="8" cy="8" r="3" />
  <path d="M2.5 20v-2.5A4.5 4.5 0 0 1 7 13h2a4.5 4.5 0 0 1 4.5 4.5V20M16 5.5a3 3 0 0 1 0 5.8M17 14a4.5 4.5 0 0 1 3.5 4.4V20" />
</template>
```

Task 6 创建视图后路由导入才能完整解析；此步允许路由测试暂时因视图文件缺失而失败，但不得跳过该失败进入最终交付。

### Task 6: 用户列表与新增用户页面

**Files:**
- Create: `frontend/src/views/users/UserListView.vue`
- Create: `frontend/src/views/users/UserListView.test.ts`

**Interfaces:**
- Consumes: Task 5 的 `listUsers`、`createUser`、`ManagedUser`、`RoleCode`、`showSaveSuccess`。
- Produces: 用户管理视图及 `data-test="user-create-form"`、`user-list`、`next-users` 等稳定测试接口。

- [ ] **Step 1: 写列表、筛选、分页和新增失败测试**

创建 `UserListView.test.ts`，先定义完整测试上下文，再使用真实 Pinia 和 Axios adapter：

```typescript
import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { expectSaveSuccessToast } from '../../test/toast'
import UserListView from './UserListView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

const managedUser = {
  id: 'u1', username: 'api-user', display_name: 'API User',
  roles: ['submission_operator'], status: 'active', must_change_password: true,
  last_login_at: null, created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }
let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/login', name: 'login', component: { template: '<div />' } }],
})

function mountUser() {
  return mount(UserListView, { global: { plugins: [router] } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().setSession({
    id: 'admin-id', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
    status: 'active', must_change_password: false, last_login_at: null,
  }, 'csrf')
  adapter = vi.fn<AxiosAdapter>()
  api.defaults.adapter = adapter
})
```

至少包含以下行为测试：

```typescript
it('lists filters and paginates users without exposing password fields', async () => {
  adapter.mockImplementation(async (config) => success(config, {
    items: [managedUser], page: 1, page_size: 20, total: 21,
  }))
  const wrapper = mountUser()
  await flushPromises()
  expect(wrapper.text()).toContain('api-user')
  expect(wrapper.text()).toContain('投稿操作员')
  expect(wrapper.text()).not.toContain('password_hash')
  await wrapper.get('[data-test="user-status-filter"]').setValue('active')
  await wrapper.get('[data-test="apply-user-filters"]').trigger('click')
  await flushPromises()
  expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ status: 'active', page: 1 })
  await wrapper.get('[data-test="next-users"]').trigger('click')
  await flushPromises()
  expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
})

it('creates a user with roles and shows the one-second success toast', async () => {
  vi.useFakeTimers()
  adapter.mockImplementation(async (config) => success(config,
    config.method === 'post' ? managedUser : emptyPage,
  ))
  const wrapper = mountUser()
  await flushPromises()
  await wrapper.get('[data-test="add-user"]').trigger('click')
  await wrapper.get('[data-test="new-username"]').setValue('new-user')
  await wrapper.get('[data-test="new-display-name"]').setValue('New User')
  await wrapper.get('[data-test="new-password"]').setValue('Strong-Passphrase-2026!')
  await wrapper.get('[data-test="new-password-confirmation"]').setValue('Strong-Passphrase-2026!')
  await wrapper.get('[data-test="create-role-submission_operator"]').setValue(true)
  await wrapper.get('[data-test="user-create-form"]').trigger('submit')
  await flushPromises()
  const call = adapter.mock.calls.find(([config]) => config.method === 'post')
  expect(JSON.parse(String(call?.[0].data))).toEqual({
    username: 'new-user', display_name: 'New User',
    password: 'Strong-Passphrase-2026!',
    password_confirmation: 'Strong-Passphrase-2026!',
    roles: ['submission_operator'],
  })
  expectSaveSuccessToast()
})
```

同时添加密码不一致和未选角色时不发送 `POST` 的测试：

```typescript
it('validates password confirmation and roles before creating', async () => {
  adapter.mockImplementation(async (config) => success(config, emptyPage))
  const wrapper = mountUser()
  await flushPromises()
  await wrapper.get('[data-test="add-user"]').trigger('click')
  await wrapper.get('[data-test="new-username"]').setValue('new-user')
  await wrapper.get('[data-test="new-display-name"]').setValue('New User')
  await wrapper.get('[data-test="new-password"]').setValue('First-2026!')
  await wrapper.get('[data-test="new-password-confirmation"]').setValue('Second-2026!')
  await wrapper.get('[data-test="user-create-form"]').trigger('submit')
  expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
  expect(wrapper.text()).toContain('两次输入的密码不一致')

  await wrapper.get('[data-test="new-password-confirmation"]').setValue('First-2026!')
  await wrapper.get('[data-test="user-create-form"]').trigger('submit')
  expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
  expect(wrapper.text()).toContain('请至少选择一个角色')
})
```

- [ ] **Step 2: 运行并确认视图不存在导致失败**

Run:

```bash
npm --prefix frontend test -- src/views/users/UserListView.test.ts
```

Expected: 因 `UserListView.vue` 不存在而失败。

- [ ] **Step 3: 实现列表、查询和新增表单**

`UserListView.vue` 使用以下状态与方法签名，保持现有页面 CSS 类：

```typescript
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { SortOrder } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import {
  createUser, listUsers,
  type ManagedUser, type RoleCode, type UserListQuery, type UserStatus,
} from '../../api/users'
import { useAuthStore } from '../../stores/auth'
import { displayText, ROLE_LABELS } from '../../utils/display'
import { showSaveSuccess } from '../../utils/feedback'

const auth = useAuthStore()
const router = useRouter()
const roleCodes = Object.keys(ROLE_LABELS) as RoleCode[]
const saving = ref(false)
let loadSequence = 0

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

const users = ref<ManagedUser[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const creating = ref(false)
const showCreate = ref(false)
const query = reactive({
  page: 1, page_size: 20, name: '', status: '' as UserStatus | '',
  sort: 'created_at' as NonNullable<UserListQuery['sort']>, order: 'desc' as SortOrder,
})
const createForm = reactive({
  username: '', display_name: '', password: '', password_confirmation: '',
  roles: [] as RoleCode[],
})

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await listUsers({ ...query, status: query.status || undefined })
    if (sequence !== loadSequence) return
    users.value = result.items
    total.value = result.total
  } catch (error) {
    if (sequence === loadSequence) errorMessage.value = safeError(error, '无法加载用户。')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function saveCreate(): Promise<void> {
  if (creating.value) return
  errorMessage.value = ''
  if (!createForm.username.trim() || !createForm.display_name.trim()
      || !createForm.password || !createForm.password_confirmation) {
    errorMessage.value = '请填写用户名、显示姓名和两次密码。'
    return
  }
  if (createForm.password !== createForm.password_confirmation) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  if (createForm.roles.length === 0) {
    errorMessage.value = '请至少选择一个角色。'
    return
  }
  creating.value = true
  try {
    await createUser({
      username: createForm.username.trim(), display_name: createForm.display_name.trim(),
      password: createForm.password, password_confirmation: createForm.password_confirmation,
      roles: [...createForm.roles],
    })
    showCreate.value = false
    Object.assign(createForm, {
      username: '', display_name: '', password: '', password_confirmation: '', roles: [],
    })
    await load()
    showSaveSuccess()
  } catch (error) {
    errorMessage.value = safeError(error, '无法创建用户。')
  } finally {
    creating.value = false
  }
}

onMounted(() => void load())
```

模板包含筛选表单、用户表格、分页、新增表单及密码 `type="password" autocomplete="new-password"` 输入框；角色选项从 `ROLE_LABELS` 的五个固定代码生成，显示使用 `displayText(ROLE_LABELS, role)`。表格只渲染 `ManagedUser` 安全字段。使用以下精确结构：

```vue
<template>
  <section class="management-page" aria-labelledby="user-list-title">
    <h1 id="user-list-title">用户管理</h1>
    <div class="toolbar">
      <label>姓名或用户名<input v-model="query.name" data-test="user-name-filter"></label>
      <label>状态<select v-model="query.status" data-test="user-status-filter">
        <option value="">全部状态</option><option value="active">启用</option><option value="disabled">停用</option>
      </select></label>
      <label>排序<select v-model="query.sort" data-test="user-sort" @change="query.page = 1; load()">
        <option value="created_at">创建时间</option><option value="updated_at">更新时间</option>
        <option value="username">用户名</option><option value="display_name">显示姓名</option>
        <option value="last_login_at">最后登录时间</option>
      </select></label>
      <label>顺序<select v-model="query.order" @change="query.page = 1; load()">
        <option value="desc">降序</option><option value="asc">升序</option>
      </select></label>
      <button type="button" data-test="apply-user-filters" @click="query.page = 1; load()">应用筛选</button>
      <button type="button" data-test="add-user" @click="showCreate = true">新增用户</button>
    </div>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <form v-if="showCreate" data-test="user-create-form" class="stacked-form" novalidate @submit.prevent="saveCreate">
      <h2>新增用户</h2>
      <label>用户名<input v-model="createForm.username" data-test="new-username" maxlength="64" required></label>
      <label>显示姓名<input v-model="createForm.display_name" data-test="new-display-name" maxlength="128" required></label>
      <label>初始密码<input v-model="createForm.password" data-test="new-password" type="password" autocomplete="new-password" required></label>
      <label>确认初始密码<input v-model="createForm.password_confirmation" data-test="new-password-confirmation" type="password" autocomplete="new-password" required></label>
      <fieldset><legend>角色</legend>
        <label v-for="code in roleCodes" :key="code">
          <input v-model="createForm.roles" type="checkbox" :value="code" :data-test="`create-role-${code}`">
          {{ displayText(ROLE_LABELS, code) }}
        </label>
      </fieldset>
      <button type="submit" :disabled="creating">保存用户</button>
      <button type="button" @click="showCreate = false">取消</button>
    </form>

    <p v-if="loading">正在加载用户…</p>
    <table v-else data-test="user-list"><thead><tr>
      <th>用户名</th><th>显示姓名</th><th>角色</th><th>状态</th><th>需改密</th><th>最后登录</th><th>操作</th>
    </tr></thead><tbody><tr v-for="user in users" :key="user.id">
      <td>{{ user.username }}</td><td>{{ user.display_name }}</td>
      <td>{{ user.roles.map((role) => displayText(ROLE_LABELS, role)).join('、') }}</td>
      <td>{{ user.status === 'active' ? '启用' : '停用' }}</td>
      <td>{{ user.must_change_password ? '是' : '否' }}</td>
      <td>{{ user.last_login_at ?? '—' }}</td>
      <td></td>
    </tr></tbody></table>
    <nav class="pagination" aria-label="用户分页">
      <span>第 {{ query.page }} 页 · 共 {{ total }} 条</span>
      <button type="button" data-test="next-users" :disabled="query.page * query.page_size >= total || loading" @click="query.page += 1; load()">下一页</button>
    </nav>
  </section>
</template>
```

Task 7 在操作列加入编辑和重置按钮。

- [ ] **Step 4: 运行页面与基础设施测试**

Run:

```bash
npm --prefix frontend test -- src/views/users/UserListView.test.ts src/router/index.test.ts src/App.test.ts
```

Expected: 全部通过。

### Task 7: 编辑、启停用、重置密码与完整验证

**Files:**
- Modify: `frontend/src/views/users/UserListView.vue`
- Modify: `frontend/src/views/users/UserListView.test.ts`

**Interfaces:**
- Consumes: Task 5 的 `getUser`、`updateUser`、`resetUserPassword`，Pinia `useAuthStore`，Vue Router。
- Produces: `openEdit`、`saveEdit`、`openReset`、`saveReset` 完整用户管理闭环。

- [ ] **Step 1: 写编辑和停用失败测试**

追加：

```typescript
it('loads details and updates name roles and status', async () => {
  adapter.mockImplementation(async (config) => {
    if (config.url === '/users/u1' && config.method === 'get') return success(config, managedUser)
    if (config.method === 'patch') return success(config, { ...managedUser, status: 'disabled' })
    return success(config, { ...emptyPage, items: [managedUser], total: 1 })
  })
  const wrapper = mountUser()
  await flushPromises()
  await wrapper.get('[data-test="edit-user-u1"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="edit-display-name"]').setValue('Updated User')
  await wrapper.get('[data-test="edit-role-author"]').setValue(true)
  await wrapper.get('[data-test="edit-role-submission_operator"]').setValue(false)
  await wrapper.get('[data-test="edit-status"]').setValue('disabled')
  await wrapper.get('[data-test="user-edit-form"]').trigger('submit')
  await flushPromises()
  expect(JSON.parse(String(adapter.mock.calls.find(([config]) => config.method === 'patch')?.[0].data))).toEqual({
    display_name: 'Updated User', roles: ['author'], status: 'disabled',
  })
  expectSaveSuccessToast()
})
```

- [ ] **Step 2: 写其他用户与本人重置密码失败测试**

追加两个完整测试，分别验证其他用户与本人重置：

```typescript
it('resets another user password and keeps the admin session', async () => {
  const other = { ...managedUser, id: 'u2', username: 'other-user' }
  adapter.mockImplementation(async (config) => {
    if (config.url === '/users/u2/reset-password' && config.method === 'post') {
      return success(config, null)
    }
    return success(config, { ...emptyPage, items: [other], total: 1 })
  })
  const wrapper = mountUser()
  await flushPromises()
  await wrapper.get('[data-test="reset-user-u2"]').trigger('click')
  await wrapper.get('[data-test="reset-new-password"]').setValue('Reset-Passphrase-2026!')
  await wrapper.get('[data-test="reset-password-confirmation"]').setValue('Reset-Passphrase-2026!')
  await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
  await flushPromises()
  const call = adapter.mock.calls.find(([config]) => config.method === 'post')
  expect(JSON.parse(String(call?.[0].data))).toEqual({
    new_password: 'Reset-Passphrase-2026!',
    password_confirmation: 'Reset-Passphrase-2026!',
  })
  expect(useAuthStore().isAuthenticated).toBe(true)
  expectSaveSuccessToast()
})

it('clears the local session after resetting the current admin password', async () => {
  const current = { ...managedUser, id: 'admin-id', username: 'admin' }
  adapter.mockImplementation(async (config) => {
    if (config.url === '/users/admin-id/reset-password' && config.method === 'post') {
      return success(config, null)
    }
    return success(config, { ...emptyPage, items: [current], total: 1 })
  })
  const wrapper = mountUser()
  await flushPromises()
  await wrapper.get('[data-test="reset-user-admin-id"]').trigger('click')
  await wrapper.get('[data-test="reset-new-password"]').setValue('Self-Reset-2026!')
  await wrapper.get('[data-test="reset-password-confirmation"]').setValue('Self-Reset-2026!')
  await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
  await flushPromises()
  expect(useAuthStore().isAuthenticated).toBe(false)
})
```

请求体必须精确等于上述密码字段，且不得附带用户名、角色或旧密码。另加确认密码不一致测试：

```typescript
it('rejects mismatched password confirmation before resetting', async () => {
  adapter.mockImplementation(async (config) => success(config, {
    ...emptyPage, items: [managedUser], total: 1,
  }))
  const wrapper = mountUser()
  await flushPromises()
  await wrapper.get('[data-test="reset-user-u1"]').trigger('click')
  await wrapper.get('[data-test="reset-new-password"]').setValue('First-2026!')
  await wrapper.get('[data-test="reset-password-confirmation"]').setValue('Second-2026!')
  await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
  expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
  expect(wrapper.text()).toContain('两次输入的密码不一致')
})
```

- [ ] **Step 3: 运行并确认编辑/重置接口不存在导致失败**

Run:

```bash
npm --prefix frontend test -- src/views/users/UserListView.test.ts
```

Expected: 找不到编辑/重置控件或行为断言失败。

- [ ] **Step 4: 实现编辑和重置**

将组件的 API 导入扩展为：

```typescript
import {
  createUser, getUser, listUsers, resetUserPassword, updateUser,
  type ManagedUser, type RoleCode, type UserListQuery, type UserStatus,
} from '../../api/users'
```

增加以下状态和方法，接口保存成功且本地状态更新后再提示：

```typescript
const editing = ref<ManagedUser | null>(null)
const resetting = ref<ManagedUser | null>(null)
const editForm = reactive({ display_name: '', roles: [] as RoleCode[], status: 'active' as UserStatus })
const resetForm = reactive({ new_password: '', password_confirmation: '' })

async function openEdit(user: ManagedUser): Promise<void> {
  errorMessage.value = ''
  try {
    const detail = await getUser(user.id)
    editing.value = detail
    Object.assign(editForm, {
      display_name: detail.display_name, roles: [...detail.roles], status: detail.status,
    })
  } catch (error) {
    errorMessage.value = safeError(error, '无法加载用户详情。')
  }
}

async function saveEdit(): Promise<void> {
  const current = editing.value
  if (!current || saving.value) return
  if (!editForm.display_name.trim()) {
    errorMessage.value = '请填写显示姓名。'
    return
  }
  if (editForm.roles.length === 0) {
    errorMessage.value = '请至少选择一个角色。'
    return
  }
  saving.value = true
  try {
    await updateUser(current.id, {
      display_name: editForm.display_name.trim(), roles: [...editForm.roles], status: editForm.status,
    })
    editing.value = null
    await load()
    showSaveSuccess()
  } catch (error) {
    errorMessage.value = safeError(error, '无法更新用户。')
  } finally {
    saving.value = false
  }
}

function openReset(user: ManagedUser): void {
  errorMessage.value = ''
  resetting.value = user
  Object.assign(resetForm, { new_password: '', password_confirmation: '' })
}

async function saveReset(): Promise<void> {
  const current = resetting.value
  if (!current || saving.value) return
  if (!resetForm.new_password || !resetForm.password_confirmation) {
    errorMessage.value = '请填写两次新密码。'
    return
  }
  if (resetForm.new_password !== resetForm.password_confirmation) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  saving.value = true
  try {
    await resetUserPassword(current.id, {
      new_password: resetForm.new_password,
      password_confirmation: resetForm.password_confirmation,
    })
    resetting.value = null
    if (current.id === auth.user?.id) {
      auth.clearSession()
      await router.replace({ name: 'login' })
      return
    }
    await load()
    showSaveSuccess()
  } catch (error) {
    errorMessage.value = safeError(error, '无法重置密码。')
  } finally {
    saving.value = false
  }
}
```

模板为编辑和重置分别提供独立表单，防止重复提交，密码不得显示在用户列表或成功响应中。操作列加入：

```vue
<button type="button" :data-test="`edit-user-${user.id}`" @click="openEdit(user)">编辑</button>
<button type="button" :data-test="`reset-user-${user.id}`" @click="openReset(user)">重置密码</button>
```

在列表前加入以下表单：

```vue
<form v-if="editing" data-test="user-edit-form" class="stacked-form" novalidate @submit.prevent="saveEdit">
  <h2>编辑用户</h2>
  <label>显示姓名<input v-model="editForm.display_name" data-test="edit-display-name" maxlength="128" required></label>
  <fieldset><legend>角色</legend>
    <label v-for="code in roleCodes" :key="code">
      <input v-model="editForm.roles" type="checkbox" :value="code" :data-test="`edit-role-${code}`">
      {{ displayText(ROLE_LABELS, code) }}
    </label>
  </fieldset>
  <label>状态<select v-model="editForm.status" data-test="edit-status">
    <option value="active">启用</option><option value="disabled">停用</option>
  </select></label>
  <p v-if="editing.id === auth.user?.id">不能停用本人或移除本人的系统管理员角色。</p>
  <button type="submit" :disabled="saving">保存修改</button>
  <button type="button" @click="editing = null">取消</button>
</form>

<form v-if="resetting" data-test="user-reset-form" class="stacked-form" novalidate @submit.prevent="saveReset">
  <h2>重置密码</h2>
  <label>新密码<input v-model="resetForm.new_password" data-test="reset-new-password" type="password" autocomplete="new-password" required></label>
  <label>确认新密码<input v-model="resetForm.password_confirmation" data-test="reset-password-confirmation" type="password" autocomplete="new-password" required></label>
  <button type="submit" :disabled="saving">保存新密码</button>
  <button type="button" @click="resetting = null">取消</button>
</form>
```

- [ ] **Step 5: 运行用户页面完整测试**

Run:

```bash
npm --prefix frontend test -- src/views/users/UserListView.test.ts
```

Expected: 全部通过，包括本人重置后的会话清除。

- [ ] **Step 6: 运行完整项目验证并检查工作区**

Run:

```bash
bash scripts/verify.sh
git diff --check
git status --short
```

Expected: 后端、前端、覆盖率、OpenAPI、Newman、类型检查和生产构建全部通过。报告实际测试数量及任何未解决失败，不自动提交或推送。
