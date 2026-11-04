"""Initialize the single local system administrator without a default password."""

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
        "System Administrator",
        "Full local administration and audit access",
    ),
    (
        "submission_operator",
        "Submission Operator",
        "Authorized author and manuscript operations",
    ),
    ("reviewer", "Reviewer", "Read-only review within explicit author grants"),
    ("author", "Author", "Reserved read-only author identity"),
    ("auditor", "Auditor", "Read-only access to operation logs"),
)


def initialize_admin(db: Session, username: str, password: str) -> User:
    username = username.strip()
    normalized = normalize_username(username)
    if not normalized or len(normalized) > 64 or len(username) > 64:
        raise ValueError(
            "administrator username must contain 1–64 normalized characters"
        )
    if db.scalar(select(User.id).limit(1)) is not None:
        raise ValueError("administrator initialization has already been completed")
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
    username = input("Administrator username: ")
    password = getpass.getpass("Initial password (hidden): ")
    confirmation = getpass.getpass("Confirm initial password (hidden): ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no administrator was created.")

    db = SessionLocal()
    try:
        initialize_admin(db, username, password)
    except (ValueError, SQLAlchemyError):
        raise SystemExit(
            "Administrator initialization failed; no credentials were written."
        ) from None
    finally:
        db.close()
    print("Administrator created; password change is required at first login.")


if __name__ == "__main__":
    main()
