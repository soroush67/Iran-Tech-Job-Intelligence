import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_ph = PasswordHasher()
JWT_ALG = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _secret_key() -> str:
    key = get_settings().secret_key
    if not key or len(key) < 32:
        raise RuntimeError("SECRET_KEY must be set (at least 32 characters)")
    return key


def create_access_token(user_id: int, role: str, minutes: int | None = None) -> str:
    minutes = minutes or get_settings().access_token_minutes
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, _secret_key(), algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret_key(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    """One-time codes and verification links are stored hashed, never in clear."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        # Derive from SECRET_KEY so a deployment always has *some* key; an explicit
        # ENCRYPTION_KEY lets the JWT key rotate without losing stored secrets.
        key = base64.urlsafe_b64encode(hashlib.sha256(_secret_key().encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask(secret: str | None) -> str | None:
    if not secret:
        return None
    return "•" * 6 + secret[-4:] if len(secret) > 8 else "•" * 6
