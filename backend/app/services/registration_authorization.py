"""Enforce explicit author consent for registration-related actions."""

from collections.abc import Collection

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Author, User, utc_now
from app.repositories.authorizations import AuthorizationRepository
from app.services.permissions import Permission, has_author_permission

REGISTRATION_PERMISSIONS = frozenset(
    {"account:register", "email:verification:read", "credential:use"}
)


def require_registration_consent(
    db: Session,
    user: User,
    author_id: str,
    authorization_id: str,
    permissions: Collection[str],
    request_id: str | None,
) -> Author:
    repository = AuthorizationRepository(db)
    for permission in permissions:
        if not has_author_permission(db, user, author_id, Permission(permission)):
            raise AppError(403, "PERMISSION_DENIED", "当前角色无权执行注册相关操作")
        if not repository.any_active(
            user_id=user.id,
            author_id=author_id,
            permission=permission,
            now_utc=utc_now(),
            authorization_id=authorization_id,
        ):
            raise AppError(
                403, "AUTHORIZATION_INVALID", "作者注册授权未生效、已过期或已撤销"
            )
    author = db.get(Author, author_id)
    if author is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "资源不存在")
    return author
