"""10. Secure Telegram connection: one-time codes and Mini App initData."""
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import TelegramConnection, User
from app.telegram_auth import InitDataError, issue_link_code, redeem_link_code, validate_init_data


def init_data(user_id=4242, token=None, auth_date=None, tamper=False):
    token = token or get_settings().telegram_bot_token
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAE",
              "user": json.dumps({"id": user_id, "first_name": "Test"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": 1, "first_name": "Evil"})
    return urlencode(fields)


def user(db, email="tg@example.com"):
    u = User(email=email, password_hash="x", role="user", profile={})
    db.add(u)
    db.commit()
    return u


def test_init_data_valid():
    data = validate_init_data(init_data(), get_settings().telegram_bot_token)
    assert data["user"]["id"] == 4242


@pytest.mark.parametrize("kwargs,err", [
    ({"tamper": True}, "bad signature"),
    ({"token": "999:other-bot"}, "bad signature"),
    ({"auth_date": int(time.time()) - 3 * 86400}, "expired"),
])
def test_init_data_rejected(kwargs, err):
    with pytest.raises(InitDataError, match=err):
        validate_init_data(init_data(**kwargs), get_settings().telegram_bot_token)


def test_link_code_single_use_and_expiry(db):
    u = user(db)
    code = issue_link_code(db, u.id)
    db.commit()
    conn = db.scalar(select(TelegramConnection))
    assert conn.code_hash and code not in conn.code_hash  # stored hashed
    assert redeem_link_code(db, code, chat_id=111, tg_user_id=4242, username="t") is not None
    db.commit()
    assert redeem_link_code(db, code, chat_id=222, tg_user_id=5555, username="x") is None  # single use
    code2 = issue_link_code(db, u.id)
    conn.code_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert redeem_link_code(db, code2, chat_id=111, tg_user_id=4242, username="t") is None  # expired
    assert redeem_link_code(db, "guessed-code", chat_id=1, tg_user_id=1, username=None) is None


def test_telegram_account_moves_to_new_owner(db):
    a, b = user(db, "a@example.com"), user(db, "b@example.com")
    redeem_link_code(db, issue_link_code(db, a.id), 111, 4242, "t")
    redeem_link_code(db, issue_link_code(db, b.id), 111, 4242, "t")
    db.commit()
    rows = {c.user_id: c for c in db.scalars(select(TelegramConnection))}
    assert rows[b.id].status == "active" and rows[a.id].status == "revoked" and rows[a.id].chat_id is None


def test_connect_endpoint_and_webapp_auth(user_client, db):
    r = user_client.post("/api/v1/telegram/connect")
    assert r.status_code == 200
    link = r.json()["deep_link"]
    assert link.startswith("https://t.me/jobs_test_bot?start=")
    # unlinked Telegram account cannot log into the Mini App
    r = user_client.post("/api/v1/telegram/webapp/auth", json={"init_data": init_data(user_id=4242)})
    assert r.status_code == 403
    code = link.split("start=")[1]
    assert redeem_link_code(db, code, 111, 4242, "t") is not None
    db.commit()
    from fastapi.testclient import TestClient

    from app.main import app
    fresh = TestClient(app, base_url="https://jobs.test")
    r = fresh.post("/api/v1/telegram/webapp/auth", json={"init_data": init_data(user_id=4242)})
    assert r.status_code == 200 and r.json()["user"]["email"] == "user@example.com"
    assert fresh.get("/api/v1/auth/me").status_code == 200
    r = fresh.post("/api/v1/telegram/webapp/auth", json={"init_data": init_data(user_id=4242, tamper=True)})
    assert r.status_code == 401
