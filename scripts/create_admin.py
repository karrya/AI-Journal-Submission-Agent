"""初始化唯一的本地系统管理员，不设置默认密码。"""

import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import Role, User, UserRole  # noqa: E402
from app.security.passwords import (  # noqa: E402
    hash_password,
    normalize_username,
    validate_new_password,
)

ROLE_DEFINITIONS = (
    (
        "system_admin",
        "系统管理员",
        "完整的本地管理和审计访问权限",
    ),
    (
        "submission_operator",
        "投稿操作员",
        "经授权的作者和稿件操作权限",
    ),
    ("reviewer", "审稿人", "在明确的作者授权范围内只读审稿"),
    ("author", "作者", "保留的只读作者身份"),
    ("auditor", "审计员", "操作日志只读访问权限"),
)


def initialize_admin(db: Session, username: str, password: str) -> User:
    username = username.strip()
    normalized = normalize_username(username)
    if not normalized or len(normalized) > 64 or len(username) > 64:
        raise ValueError(
            "管理员用户名规范化后必须包含 1–64 个字符"
        )
    if db.scalar(select(User.id).limit(1)) is not None:
        raise ValueError("管理员初始化已经完成")
    validate_new_password(username, password)

    try:
        roles = {role.code: role for role in db.scalars(select(Role)).all()}
        for code, name, description in ROLE_DEFINITIONS:
            if code not in roles:
                role = Role(code=code, name=name, description=description)
                db.add(role)
                roles[code] = role
        user = User(
            username=username,
            normalized_username=normalized,
            display_name=username,
            password_hash=hash_password(password),
            status="active",
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=roles["system_admin"].id))
        db.commit()
        return user
    except Exception:
        db.rollback()
        raise


def main() -> None:
    username = input("管理员用户名：")
    password = getpass.getpass("初始密码（输入不显示）：")
    confirmation = getpass.getpass("确认初始密码（输入不显示）：")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致，未创建管理员。")

    db = SessionLocal()
    try:
        initialize_admin(db, username, password)
    except (ValueError, SQLAlchemyError):
        raise SystemExit(
            "管理员初始化失败，未写入任何凭据。"
        ) from None
    finally:
        db.close()
    print("管理员已创建，首次登录时必须修改密码。")


if __name__ == "__main__":
    main()
