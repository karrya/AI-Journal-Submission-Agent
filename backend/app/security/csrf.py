import base64
import hashlib
import hmac


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(session_token_hash: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode(),
        b"csrf:" + session_token_hash.encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def validate_csrf_secret(secret: str) -> None:
    if not secret or len(secret.encode()) < 32:
        raise ValueError("CSRF_SECRET_KEY must contain at least 32 bytes")
