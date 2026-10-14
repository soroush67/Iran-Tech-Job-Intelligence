"""Process configuration, read from the environment (.env via compose).

Secrets (DB password, JWT secret, SMTP password, bot token, API keys) only ever
come from here or from the encrypted app_settings table - never from code.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: str = "production"
    database_url: str = "postgresql+psycopg://jobintel:jobintel@postgres:5432/jobintel"
    redis_url: str = "redis://redis:6379/0"

    # Public URL the users open (used in e-mails, Telegram links, CORS).
    public_base_url: str = "https://localhost:8443"

    secret_key: str = Field(default="", description="JWT signing key")
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt secrets stored in the DB.
    encryption_key: str = ""
    access_token_minutes: int = 60 * 12

    admin_email: str = ""
    admin_password: str = ""
    allow_registration: bool = True

    # Collector
    collector_user_agent: str = (
        "IranTechJobIntelligenceBot/1.0 (+job market research; contact: admin)"
    )
    collect_interval_minutes: int = 240
    collector_request_delay_seconds: float = 2.5
    collector_timeout_seconds: float = 25.0
    collector_max_pages_per_run: int = 250
    collector_backoff_factor: float = 1.0  # multiplies retry/backoff waits (0 in tests)
    collector_proxy: str = ""

    # SMTP (can also be set from the admin UI; DB value wins)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_mode: str = "polling"  # polling | webhook
    telegram_webhook_secret: str = ""
    telegram_proxy: str = ""

    # AI
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-5-5"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b"

    daily_digest_hour: int = 8  # Asia/Tehran
    timezone: str = "Asia/Tehran"

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
