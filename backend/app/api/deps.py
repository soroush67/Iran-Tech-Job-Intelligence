from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request, status
from redis import Redis
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, User
from app.security import decode_access_token

COOKIE_NAME = "jti_session"
_redis: Redis | None = None


def redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, socket_timeout=3)
    return _redis


def client_ip(request: Request) -> str:
    # nginx sets X-Real-IP; the backend port is not published outside the compose network.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    tok = _token(request)
    if not tok:
        return None
    payload = decode_access_token(tok)
    if not payload:
        return None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        return None
    return user


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def rate_limit(name: str, limit: int, window_seconds: int = 60):
    """Fixed-window limiter per client IP (and per user when logged in)."""

    def dep(request: Request):
        bucket = int(time.time() // window_seconds)
        key = f"rl:{name}:{client_ip(request)}:{bucket}"
        try:
            n = redis().incr(key)
            if n == 1:
                redis().expire(key, window_seconds + 1)
        except Exception:
            return  # the limiter must never take the API down
        if n > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many requests, slow down",
                                headers={"Retry-After": str(window_seconds)})

    return dep


def audit(db: Session, request: Request | None, user: User | None, action: str, target: str | None = None,
          details: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, target=target, details=details or {},
                    ip=client_ip(request) if request else None))
