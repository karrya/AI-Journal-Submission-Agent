import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_password_hasher = PasswordHasher()

_COMMON_WEAK_PASSWORDS = frozenset(
    {
        "111111",
        "123456",
        "admin123",
        "admin12345678",
        "adminadmin12",
        "changeme123!",
        "letmeinletmein",
        "p@ssw0rd123!",
        "password",
        "password123!",
        "password1234",
        "qwerty",
        "qwertyqwerty",
        "welcome123!",
    }
)


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().casefold()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (Argon2Error, ValueError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except ValueError:
        return True


def validate_new_password(username: str, password: str) -> None:
    if not 6 <= len(password) <= 128:
        raise ValueError("密码长度必须为 6–128 个字符")
    normalized = normalize_username(password)
    if normalized == normalize_username(username):
        raise ValueError("新密码不得与用户名相同")
    if normalized in _COMMON_WEAK_PASSWORDS:
        raise ValueError("新密码不能使用常见弱密码")
