"""`scheduler` service: decides *when*, the worker does the work.

* collection per source when next_run_at is due (interval is never below the
  source's own minimum),
* notification dispatch every minute,
* daily digest once a day at notify.daily_digest_hour (Asia/Tehran),
* heartbeat key in Redis for the health check.
"""
from __future__ import annotations

import signal
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select

from app import settings_store
from app.config import get_settings
from app.db import session_scope
from app.logging_setup import setup_logging
from app.models import Source, SourceRun
from app.tasks import collect_source, dispatch_notifications, queue, redis_conn, retry_kwargs, send_daily_digest

setup_logging()
log = structlog.get_logger()
_stop = False


def _handle(*_):
    global _stop
    _stop = True


def tick(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    actions = []
    r = redis_conn()
    with session_scope() as db:
        # Runs left "running" by a killed worker (collect jobs time out after 3h).
        for run in db.scalars(select(SourceRun).where(SourceRun.status == "running",
                                                      SourceRun.started_at < now - timedelta(hours=4))):
            run.status = "failed"
            run.errors = (run.errors or []) + ["interrupted (worker stopped or timed out)"]
            run.finished_at = now
        paused = settings_store.get(db, "collector.paused")
        for src in db.scalars(select(Source).where(Source.enabled)):
            if paused:
                break
            if src.next_run_at is None or src.next_run_at <= now:
                if r.set(f"sched:collect:{src.key}", "1", nx=True, ex=600):
                    queue("collect").enqueue(collect_source, src.key, "schedule", job_timeout=3 * 3600, **retry_kwargs())
                    # provisional; the run itself sets the definitive next_run_at when it finishes
                    src.next_run_at = now + timedelta(minutes=max(src.interval_minutes, src.min_interval_minutes))
                    actions.append(f"collect:{src.key}")
        hour = int(settings_store.get(db, "notify.daily_digest_hour") or 8)
        local = now.astimezone(ZoneInfo(get_settings().timezone))
        day = local.date().isoformat()
        if local.hour >= hour and settings_store.get(db, "notify.last_digest_day") != day:
            settings_store.set_value(db, "notify.last_digest_day", day)
            queue("notify").enqueue(send_daily_digest)
            actions.append("digest")
    if r.set("sched:dispatch", "1", nx=True, ex=55):
        queue("notify").enqueue(dispatch_notifications)
        actions.append("dispatch")
    r.set("heartbeat:scheduler", int(time.time()), ex=600)
    return actions


def main() -> None:
    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    log.info("scheduler_started")
    while not _stop:
        try:
            acts = tick()
            if acts:
                log.info("scheduler_tick", actions=acts)
        except Exception as exc:
            log.error("scheduler_tick_failed", error=str(exc))
        for _ in range(30):
            if _stop:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
