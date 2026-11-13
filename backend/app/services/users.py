from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Role, User, UserRole
from app.schemas.users import (
    ManagedUserResponse,
    RoleCode,
    UserCreate,
    UserPage,
    UserPasswordReset,
    UserStatus,
    UserUpdate,
)
from app.security.passwords import hash_password, normalize_username, validate_new_password
from app.security.sessions import SessionService
from app.services.authors import DomainService


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


_AUDIT_FIELDS = frozenset({"username", "display_name", "roles", "status"})


def _validate_password(username: str, password: str) -> None:
    try:
        validate_new_password(username, password)
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc)) from None


class UserManagementService(DomainService):
    SORT_FIELDS = {
        "username": User.username,
        "display_name": User.display_name,
        "created_at": User.created_at,
        "updated_at": User.updated_at,
        "last_login_at": User.last_login_at,
    }

    def _role_codes(self, user_id: str) -> list[str]:
        return list(
            self.db.scalars(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
                .order_by(Role.code)
            ).all()
        )

    def _response(self, user: User) -> ManagedUserResponse:
        created_at = _utc(user.created_at)
        updated_at = _utc(user.updated_at)
        assert created_at is not None and updated_at is not None
        return ManagedUserResponse(
            id=UUID(user.id),
            username=user.username,
            display_name=user.display_name,
            roles=cast(list[RoleCode], self._role_codes(user.id)),
            status=cast(UserStatus, user.status),
            must_change_password=user.must_change_password,
            last_login_at=_utc(user.last_login_at),
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        status: str | None,
        sort: str,
        order: str,
    ) -> UserPage:
        self._require_admin()
        if sort not in self.SORT_FIELDS:
            raise AppError(422, "VALIDATION_ERROR", "不支持的排序字段")
        filters: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
        if name and name.strip():
            pattern = f"%{name.strip()}%"
            filters.append(
                or_(User.username.like(pattern), User.display_name.like(pattern))
            )
        if status:
            filters.append(User.status == status)
        total = self.db.scalar(select(func.count(User.id)).where(*filters)) or 0
        column = self.SORT_FIELDS[sort]
        records = self.db.scalars(
            select(User)
            .where(*filters)
            .order_by(column.asc() if order == "asc" else column.desc(), User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return UserPage(
            items=[self._response(user) for user in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    def _audit(
        self,
        *,
        action: str,
        target_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        self.audit.record(
            actor_user_id=self.user.id,
            actor_type="user",
            category="business",
            action=action,
            target_type="user",
            target_id=target_id,
            request_id=self.request_id,
            result="success",
            before=before,
            after=after,
            allowed_fields=_AUDIT_FIELDS,
        )

    def create(self, payload: UserCreate) -> ManagedUserResponse:
        self._require_admin()
        normalized = normalize_username(payload.username)
        if not normalized or len(normalized) > 64:
            raise AppError(422, "VALIDATION_ERROR", "规范化后的用户名必须为 1 至 64 个字符")
        _validate_password(payload.username, payload.password)
        try:
            roles = list(
                self.db.scalars(select(Role).where(Role.code.in_(payload.roles))).all()
            )
            if {role.code for role in roles} != set(payload.roles):
                raise AppError(422, "VALIDATION_ERROR", "包含无效角色")
            user = User(
                username=payload.username,
                normalized_username=normalized,
                display_name=payload.display_name,
                password_hash=hash_password(payload.password),
                status="active",
                must_change_password=True,
                created_by=self.user.id,
            )
            self.db.add(user)
            self.db.flush()
            for role in roles:
                self.db.add(
                    UserRole(
                        user_id=user.id,
                        role_id=role.id,
                        assigned_by=self.user.id,
                    )
                )
            self.db.flush()
            self._audit(
                action="user.create",
                target_id=user.id,
                after={
                    "username": user.username,
                    "display_name": user.display_name,
                    "roles": sorted(payload.roles),
                    "status": "active",
                },
            )
            self.db.commit()
            return self._response(user)
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "CONFLICT", "用户名已存在") from None
        except SQLAlchemyError:
            self.db.rollback()
            raise AppError(500, "INTERNAL_SERVER_ERROR", "服务器内部错误") from None
        except Exception:
            self.db.rollback()
            raise

    def _lock_active_admin_ids(self) -> set[str]:
        return set(
            self.db.scalars(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    Role.code == "system_admin",
                    User.status == "active",
                    User.deleted_at.is_(None),
                )
                .order_by(User.id)
                .with_for_update()
            ).all()
        )

    def _locked_user(self, user_id: str) -> User:
        user = self.db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.deleted_at is not None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return user

    def update(self, user_id: str, payload: UserUpdate) -> ManagedUserResponse:
        self._require_admin()
        admin_ids = self._lock_active_admin_ids()
        target = self._locked_user(user_id)
        if target.id == self.user.id and payload.status == "disabled":
            self.db.rollback()
            raise AppError(409, "ADMIN_PROTECTED", "不能停用当前管理员账号")
        if (
            target.id == self.user.id
            and payload.roles is not None
            and "system_admin" not in payload.roles
        ):
            self.db.rollback()
            raise AppError(409, "ADMIN_PROTECTED", "不能移除当前账号的管理员角色")
        loses_admin = payload.status == "disabled" or (
            payload.roles is not None and "system_admin" not in payload.roles
        )
        if loses_admin and not admin_ids.difference({target.id}):
            self.db.rollback()
            raise AppError(409, "ADMIN_PROTECTED", "系统至少需要一名启用中的管理员")
        before = {
            "username": target.username,
            "display_name": target.display_name,
            "roles": self._role_codes(target.id),
            "status": target.status,
        }
        try:
            if payload.display_name is not None:
                target.display_name = payload.display_name
            if payload.status is not None:
                target.status = payload.status
            if payload.roles is not None:
                self.db.execute(delete(UserRole).where(UserRole.user_id == target.id))
                roles = list(
                    self.db.scalars(
                        select(Role).where(Role.code.in_(payload.roles))
                    ).all()
                )
                if {role.code for role in roles} != set(payload.roles):
                    raise AppError(422, "VALIDATION_ERROR", "包含无效角色")
                for role in roles:
                    self.db.add(
                        UserRole(
                            user_id=target.id,
                            role_id=role.id,
                            assigned_by=self.user.id,
                        )
                    )
            if target.status == "disabled":
                SessionService(self.db, get_settings()).revoke_all(target.id)
            self.db.flush()
            self._audit(
                action="user.update",
                target_id=target.id,
                before=before,
                after={
                    "username": target.username,
                    "display_name": target.display_name,
                    "roles": (
                        sorted(payload.roles)
                        if payload.roles is not None
                        else before["roles"]
                    ),
                    "status": target.status,
                },
            )
            self.db.commit()
            return self._response(target)
        except SQLAlchemyError:
            self.db.rollback()
            raise AppError(500, "INTERNAL_SERVER_ERROR", "服务器内部错误") from None
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
        except SQLAlchemyError:
            self.db.rollback()
            raise AppError(500, "INTERNAL_SERVER_ERROR", "服务器内部错误") from None
        except Exception:
            self.db.rollback()
            raise

    def get(self, user_id: str) -> ManagedUserResponse:
        self._require_admin()
        user = self.db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return self._response(user)
