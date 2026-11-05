"""提供角色能力校验和数据库支持的作者授权。"""

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, NoReturn
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.api.v1.deps import Principal, get_principal
from app.core.errors import AppError
from app.models import Author, Role, User, UserRole, utc_now
from app.repositories.authorizations import AuthorizationRepository
from app.services.audit import AuditService


class Permission(str, Enum):
    MANUSCRIPT_READ = "manuscript:read"
    MANUSCRIPT_CREATE = "manuscript:create"
    MANUSCRIPT_UPDATE = "manuscript:update"
    MANUSCRIPT_FILE_MANAGE = "manuscript:file:manage"
    AUTHOR_PROFILE_READ = "author:profile:read"
    AUTHOR_EMAIL_READ = "author:email:read"
    AUTHOR_PHONE_READ = "author:phone:read"
    AUTHOR_ADDRESS_READ = "author:address:read"
    AUTHOR_PROFILE_UPDATE = "author:profile:update"


_READ_PERMISSIONS = frozenset(
    {
        Permission.MANUSCRIPT_READ,
        Permission.AUTHOR_PROFILE_READ,
        Permission.AUTHOR_EMAIL_READ,
        Permission.AUTHOR_PHONE_READ,
        Permission.AUTHOR_ADDRESS_READ,
    }
)
_ROLE_PERMISSIONS = {
    "submission_operator": frozenset(Permission),
    "reviewer": _READ_PERMISSIONS,
    "author": _READ_PERMISSIONS,
    "auditor": frozenset(),
}


def _mysql_utc(value: datetime | None) -> datetime:
    value = value or utc_now()
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _active_role_codes(db: Session, user: User) -> set[str]:
    statement = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .join(User, User.id == UserRole.user_id)
        .where(
            UserRole.user_id == user.id,
            User.status == "active",
            User.deleted_at.is_(None),
        )
    )
    return set(db.scalars(statement).all())


def _role_allows(roles: set[str], permission: Permission) -> bool:
    if "system_admin" in roles:
        return True
    capabilities = frozenset().union(
        *(_ROLE_PERMISSIONS.get(role, frozenset()) for role in roles)
    )
    return permission in capabilities


def has_author_permission(
    db: Session,
    user: User,
    author_id: str,
    permission: Permission,
    now_utc: datetime | None = None,
) -> bool:
    roles = _active_role_codes(db, user)
    if not _role_allows(roles, permission):
        return False
    if "system_admin" in roles:
        return True
    return AuthorizationRepository(db).any_active(
        user_id=user.id,
        author_id=author_id,
        permission=permission.value,
        now_utc=_mysql_utc(now_utc),
    )


def _deny_author_permission(
    db: Session,
    user: User,
    author_id: str,
    permission: Permission,
    request_id: str | None,
    error_code: str,
    established_author_relationship: bool,
) -> NoReturn:
    """持久化脱敏的拒绝记录，同时不泄露作者是否存在。"""
    message = (
        "作者授权未生效、已过期或已撤销"
        if error_code == "AUTHORIZATION_EXPIRED"
        else "当前用户无权执行此操作"
    )
    AuditService(db).record(
        actor_user_id=user.id,
        actor_type="user",
        category="authorization",
        action=(
            "authorization.expired"
            if error_code == "AUTHORIZATION_EXPIRED"
            else "authorization.permission_denied"
        ),
        target_type="author",
        target_id=author_id,
        author_id=author_id if established_author_relationship else None,
        request_id=request_id or str(uuid4()),
        result="failure",
        after={"permission": permission.value},
        allowed_fields={"permission"},
        error_code=error_code,
        error_message=message,
    )
    db.commit()
    raise AppError(403, error_code, message)


def require_author_permission(
    db: Session,
    user: User,
    author_id: str,
    permission: Permission,
    now_utc: datetime | None = None,
    request_id: str | None = None,
) -> Author:
    roles = _active_role_codes(db, user)
    if not _role_allows(roles, permission):
        established_relationship = AuthorizationRepository(db).any_record(
            user_id=user.id, author_id=author_id
        )
        _deny_author_permission(
            db,
            user,
            author_id,
            permission,
            request_id,
            "PERMISSION_DENIED",
            established_relationship,
        )

    if "system_admin" in roles:
        author = db.get(Author, author_id)
        if author is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return author

    now = _mysql_utc(now_utc)
    repository = AuthorizationRepository(db)
    if repository.any_active(
        user_id=user.id,
        author_id=author_id,
        permission=permission.value,
        now_utc=now,
    ):
        author = db.get(Author, author_id)
        if author is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
        return author
    if repository.any_current(user_id=user.id, author_id=author_id, now_utc=now):
        _deny_author_permission(
            db, user, author_id, permission, request_id, "PERMISSION_DENIED", True
        )
    if repository.any_record(user_id=user.id, author_id=author_id):
        _deny_author_permission(
            db, user, author_id, permission, request_id, "AUTHORIZATION_EXPIRED", True
        )
    raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")


def require_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def dependency(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> Principal:
        db = object_session(principal.user)
        if db is None:
            raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")
        roles = _active_role_codes(db, principal.user)
        if "system_admin" in roles or not allowed.isdisjoint(roles):
            return principal
        raise AppError(403, "PERMISSION_DENIED", "当前用户无权执行此操作")

    return dependency
