"""Idempotent startup: seed the source rows and the first admin from the environment.
Run after `alembic upgrade head` (see docker/entrypoint.sh)."""
from sqlalchemy import func, select

from app.collectors.registry import ADAPTERS
from app.config import get_settings
from app.db import session_scope
from app.logging_setup import setup_logging
from app.models import Source, User
from app.security import hash_password

setup_logging()


def seed() -> list[str]:
    s = get_settings()
    out = []
    with session_scope() as db:
        for key, ad in ADAPTERS.items():
            src = db.scalar(select(Source).where(Source.key == key))
            if src is None:
                src = Source(key=key, name=ad.name, base_url=ad.base_url, enabled=True, status="unknown",
                             interval_minutes=max(s.collect_interval_minutes, ad.min_interval_minutes), config={})
                db.add(src)
                out.append(f"source {key} created")
            # descriptive fields always follow the code
            src.name, src.base_url = ad.name, ad.base_url
            src.access_method, src.limitations = ad.access_method, ad.limitations
            src.min_interval_minutes = ad.min_interval_minutes
        if s.admin_email and s.admin_password:
            email = s.admin_email.lower()
            if db.scalar(select(User).where(func.lower(User.email) == email)) is None:
                db.add(User(email=email, password_hash=hash_password(s.admin_password), role="admin",
                            display_name="Admin", profile={}))
                out.append(f"admin {email} created")
        from app import settings_store
        from app.pipeline.rules import RULES_VERSION
        if settings_store.get(db, "rules.version") != RULES_VERSION:
            settings_store.set_value(db, "rules.version", RULES_VERSION)
            try:
                from app import tasks
                tasks.queue("analyze").enqueue(tasks.reanalyze_rules, job_timeout=3600)
                out.append(f"rules {RULES_VERSION}: re-analysis queued")
            except Exception as exc:  # redis down at boot: next start retries
                settings_store.set_value(db, "rules.version", "")
                out.append(f"rules re-analysis not queued: {exc}")
    return out


if __name__ == "__main__":
    for line in seed():
        print(line)
