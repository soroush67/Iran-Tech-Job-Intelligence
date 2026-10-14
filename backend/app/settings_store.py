"""Runtime settings: admin UI values (app_settings table) override the environment.

Secret values are stored Fernet-encrypted and are never returned by the API -
callers get `configured: true` and a masked tail instead.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting
from app.security import decrypt, encrypt

# key -> (env attribute, is_secret, default)
SETTINGS_SPEC: dict[str, tuple[str | None, bool, Any]] = {
    # AI
    "ai.enabled": (None, False, False),
    "ai.provider": (None, False, "claude"),  # claude | ollama
    "ai.model": ("ai_model", False, "claude-opus-5-5"),
    "ai.effort": (None, False, "low"),
    "ai.anthropic_api_key": ("anthropic_api_key", True, ""),
    "ai.ollama_base_url": ("ollama_base_url", False, "http://ollama:11434"),
    "ai.ollama_model": ("ollama_model", False, "qwen2.5:7b"),
    "ai.auto_analyze_new": (None, False, True),
    # SMTP
    "smtp.host": ("smtp_host", False, ""),
    "smtp.port": ("smtp_port", False, 587),
    "smtp.username": ("smtp_username", False, ""),
    "smtp.password": ("smtp_password", True, ""),
    "smtp.from": ("smtp_from", False, ""),
    "smtp.starttls": ("smtp_starttls", False, True),
    "smtp.ssl": ("smtp_ssl", False, False),
    # Notifications
    "notify.daily_digest_hour": ("daily_digest_hour", False, 8),
    "notify.max_per_user_per_hour": (None, False, 30),
    # Collector
    "collector.paused": (None, False, False),
    # Internal state
    "notify.event_cursor": (None, False, 0),
    "notify.last_digest_day": (None, False, ""),
    "rules.version": (None, False, ""),
}


def get(db: Session, key: str) -> Any:
    env_attr, secret, default = SETTINGS_SPEC[key]
    row = db.get(AppSetting, key)
    if row is not None:
        if secret:
            if row.encrypted_value:
                return decrypt(row.encrypted_value) or ""
        elif row.value is not None:
            return row.value.get("v")
    if env_attr:
        env_val = getattr(get_settings(), env_attr)
        if env_val not in (None, ""):
            return env_val
    return default


def set_value(db: Session, key: str, value: Any, user_id: int | None = None) -> None:
    if key not in SETTINGS_SPEC:
        raise KeyError(key)
    _, secret, _ = SETTINGS_SPEC[key]
    row = db.get(AppSetting, key) or AppSetting(key=key)
    if secret:
        row.encrypted_value = encrypt(value) if value else None
        row.value = None
    else:
        row.value = {"v": value}
    row.updated_by = user_id
    db.add(row)


def public_view(db: Session, prefix: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, (_, secret, _) in SETTINGS_SPEC.items():
        if not key.startswith(prefix):
            continue
        val = get(db, key)
        short = key[len(prefix):].lstrip(".")
        if secret:
            out[short + "_configured"] = bool(val)
        else:
            out[short] = val
    return out
