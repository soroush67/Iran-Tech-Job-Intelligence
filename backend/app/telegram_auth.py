"""Telegram ownership checks.

* Account linking: the web app issues a single-use code (stored hashed, 10 min
  TTL) and a t.me/<bot>?start=<code> link. The bot receives /start <code> from
  Telegram itself, so chat_id/user_id come from Telegram - never from the client.
* Mini App: initData is validated with HMAC-SHA256 exactly as specified by
  Telegram (secret = HMAC("WebAppData", bot_token)), with a freshness window.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TelegramConnection
from app.security import new_token, token_hash

LINK_CODE_TTL = timedelta(minutes=10)
INIT_DATA_MAX_AGE = 24 * 3600


class InitDataError(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int = INIT_DATA_MAX_AGE, now: float | None = None) -> dict:
    if not bot_token:
        raise InitDataError("bot token not configured")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("hash missing")
    pairs.pop("signature", None)  # Ed25519 third-party signature, not part of the HMAC check
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError("bad signature")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if (now or time.time()) - auth_date > max_age:
        raise InitDataError("initData expired")
    user = json.loads(pairs.get("user", "{}") or "{}")
    if not user.get("id"):
        raise InitDataError("no user in initData")
    return {"user": user, "auth_date": auth_date, "query_id": pairs.get("query_id")}


def issue_link_code(db: Session, user_id: int) -> str:
    code = new_token(18)
    conn = db.scalar(select(TelegramConnection).where(TelegramConnection.user_id == user_id))
    if conn is None:
        conn = TelegramConnection(user_id=user_id, status="pending")
        db.add(conn)
    elif conn.status == "active":
        pass  # keep the active link until the new code is redeemed
    else:
        conn.status = "pending"
    conn.code_hash = token_hash(code)
    conn.code_expires_at = datetime.now(UTC) + LINK_CODE_TTL
    db.flush()
    return code


def redeem_link_code(db: Session, code: str, chat_id: int, tg_user_id: int, username: str | None) -> TelegramConnection | None:
    conn = db.scalar(select(TelegramConnection).where(TelegramConnection.code_hash == token_hash(code)))
    if conn is None or not conn.code_expires_at or conn.code_expires_at < datetime.now(UTC):
        return None
    # A Telegram account can be linked to one site user only: release any previous link.
    for other in db.scalars(select(TelegramConnection).where(
            (TelegramConnection.chat_id == chat_id) | (TelegramConnection.telegram_user_id == tg_user_id),
            TelegramConnection.id != conn.id)):
        other.chat_id = None
        other.telegram_user_id = None
        other.status = "revoked"
    db.flush()
    conn.chat_id = chat_id
    conn.telegram_user_id = tg_user_id
    conn.username = username
    conn.status = "active"
    conn.code_hash = None  # single use
    conn.code_expires_at = None
    conn.connected_at = datetime.now(UTC)
    db.flush()
    return conn
