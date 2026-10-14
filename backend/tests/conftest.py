"""Test harness: a real PostgreSQL (TEST_DATABASE_URL) migrated with Alembic, a
Redis DB reserved for tests, an in-process SMTP server (aiosmtpd) and mocked
HTTP for the sources (respx). No external network is used."""
import os
import socket

os.environ.setdefault("ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://jobintel:jobintel@127.0.0.1:55432/jobintel_test")
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:56379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-1234567890")
os.environ.setdefault("PUBLIC_BASE_URL", "https://jobs.test")
os.environ.setdefault("COLLECTOR_REQUEST_DELAY_SECONDS", "0")
os.environ.setdefault("COLLECTOR_BACKOFF_FACTOR", "0")
# Any un-mocked Claude call must fail locally, never reach the internet.
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:9"
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "admin-password-123")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-token-for-hmac-only")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "jobs_test_bot")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = ["notification_deliveries", "notification_subscriptions", "saved_searches", "telegram_connections",
          "job_analyses", "job_events", "job_snapshots", "job_skills", "job_categories", "jobs", "companies",
          "salary_benchmarks", "salary_datasets", "source_runs", "sources", "audit_logs", "app_settings", "users"]


def _ensure_database(url: str) -> None:
    u = make_url(url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        if not c.execute(text("select 1 from pg_database where datname=:d"), {"d": u.database}).scalar():
            c.execute(text(f'create database "{u.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    url = os.environ["DATABASE_URL"]
    _ensure_database(url)
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("drop schema public cascade; create schema public"))
    eng.dispose()
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    from app.db import reset_engine
    reset_engine(url)
    yield


@pytest.fixture(autouse=True)
def clean(database):
    from app.db import get_engine
    with get_engine().begin() as c:
        c.execute(text("truncate " + ", ".join(TABLES) + " restart identity cascade"))
    from app.api.deps import redis
    try:
        redis().flushdb()
    except Exception:
        pass
    from app.bootstrap import seed
    seed()
    yield


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app, base_url="https://jobs.test")


def _login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r


@pytest.fixture
def admin_client(client):
    _login(client, get_settings().admin_email, get_settings().admin_password)
    return client


@pytest.fixture
def user_client():
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app, base_url="https://jobs.test")
    r = c.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "user-password-1", "display_name": "U"})
    assert r.status_code == 200, r.text
    return c


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Sink:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append({"from": envelope.mail_from, "to": envelope.rcpt_tos,
                              "data": envelope.content.decode("utf8", errors="replace")})
        return "250 OK"


@pytest.fixture
def smtp_server(db):
    from aiosmtpd.controller import Controller

    from app import settings_store
    sink = _Sink()
    port = _free_port()
    ctl = Controller(sink, hostname="127.0.0.1", port=port)
    ctl.start()
    for k, v in {"host": "127.0.0.1", "port": port, "from": "alerts@example.com", "starttls": False, "ssl": False,
                 "username": ""}.items():
        settings_store.set_value(db, f"smtp.{k}", v)
    db.commit()
    yield sink
    ctl.stop()
