"""Send Telegram messages from the worker via the Bot API (the bot process only
handles user commands). The token never leaves the process / logs."""
from __future__ import annotations

import html

import httpx

from app.config import get_settings


class TelegramNotConfigured(Exception):
    pass


class TelegramSendError(Exception):
    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


def _api(method: str) -> str:
    token = get_settings().telegram_bot_token
    if not token:
        raise TelegramNotConfigured("TELEGRAM_BOT_TOKEN is not set")
    return f"https://api.telegram.org/bot{token}/{method}"


def send_message(chat_id: int, text_html: str, buttons: list[tuple[str, str]] | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text_html, "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": t, "url": u}] for t, u in buttons]}
    proxy = get_settings().telegram_proxy or None
    try:
        resp = httpx.post(_api("sendMessage"), json=payload, timeout=20, proxy=proxy)
    except httpx.HTTPError as exc:
        raise TelegramSendError(f"cannot reach api.telegram.org: {type(exc).__name__}") from None
    if resp.status_code == 200:
        return
    desc = resp.json().get("description", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
    # 403 = user blocked the bot / 400 chat not found: retrying will not help.
    raise TelegramSendError(f"Telegram HTTP {resp.status_code}: {desc[:200]}", permanent=resp.status_code in (400, 403))


def esc(v) -> str:
    return html.escape(str(v or ""), quote=False)
