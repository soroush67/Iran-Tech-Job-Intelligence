"""Background jobs executed by the `worker` service (RQ on Redis)."""
from __future__ import annotations

import structlog
from redis import Redis
from rq import Queue, Retry

from app.config import get_settings
from app.db import session_scope
from app.logging_setup import setup_logging

setup_logging()
log = structlog.get_logger()

QUEUES = ("collect", "analyze", "notify")


def redis_conn() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def queue(name: str) -> Queue:
    return Queue(name, connection=redis_conn())


def collect_source(source_key: str, trigger: str = "schedule") -> dict:
    from app.collectors.runner import run_source

    r = redis_conn()
    lock = r.lock(f"lock:collect:{source_key}", timeout=3 * 3600, blocking=False)
    if not lock.acquire(blocking=False):
        log.info("collect_skipped_running", source=source_key)
        return {"skipped": "already running"}
    try:
        with session_scope() as db:
            run = run_source(db, source_key, trigger)
            result = {"run_id": run.id, "status": run.status, "new": run.new_jobs, "changed": run.changed_jobs,
                      "expired": run.expired_jobs, "fetched": run.fetched, "failed": run.failed}
        log.info("collect_done", source=source_key, **result)
        queue("notify").enqueue(dispatch_notifications)
        queue("analyze").enqueue(sync_llm, 100, False)
        return result
    finally:
        try:
            lock.release()
        except Exception:
            pass


def analyze_jobs(job_ids: list[int], use_llm: bool = True, force: bool = False) -> dict:
    from app.ai.engine import analyze_job
    from app.models import Job

    done = 0
    for jid in job_ids:
        with session_scope() as db:
            job = db.get(Job, jid)
            if job is None:
                continue
            if analyze_job(db, job, use_llm=use_llm, force=force) is not None:
                done += 1
    return {"analyzed": done}


def sync_llm(limit: int = 200, manual: bool = True) -> dict:
    """The Settings 'Sync' button: send pending jobs to the configured LLM.
    Automatic runs after a crawl only happen when ai.auto_analyze_new is on."""
    from app import settings_store
    from app.ai.engine import get_provider, pending_llm_jobs

    r = redis_conn()
    lock = r.lock("lock:sync_llm", timeout=6 * 3600, blocking=False)
    if not lock.acquire(blocking=False):
        return {"skipped": "sync already running"}
    try:
        with session_scope() as db:
            if not manual and not settings_store.get(db, "ai.auto_analyze_new"):
                return {"skipped": "auto analysis disabled"}
            if get_provider(db) is None:
                return {"skipped": "AI disabled or not configured"}
            ids = pending_llm_jobs(db, limit)
        r.set("ai:sync:status", f"running:{len(ids)}")
        res = analyze_jobs(ids, use_llm=True)
        r.set("ai:sync:status", f"done:{res['analyzed']}/{len(ids)}")
        return {"pending": len(ids), **res}
    finally:
        try:
            lock.release()
        except Exception:
            pass


def dispatch_notifications() -> dict:
    from app.notifications.dispatcher import dispatch_instant, retry_pending

    with session_scope() as db:
        res = dispatch_instant(db)
        res["retried"] = retry_pending(db)
    return res


def send_daily_digest() -> dict:
    from app.notifications.dispatcher import dispatch_digest

    with session_scope() as db:
        return dispatch_digest(db)


def reanalyze_rules() -> dict:
    """Re-run the deterministic analysis on jobs whose current analysis is rule-based
    (after a RULES_VERSION bump). LLM analyses are left alone."""
    from sqlalchemy import select

    from app.ai.engine import analyze_job
    from app.models import Job, JobAnalysis

    with session_scope() as db:
        ids = db.scalars(select(Job.id).outerjoin(JobAnalysis, (JobAnalysis.job_id == Job.id) & JobAnalysis.is_current)
                         .where((JobAnalysis.engine == "rules") | JobAnalysis.id.is_(None))).all()
    n = 0
    for jid in ids:
        with session_scope() as db:
            job = db.get(Job, jid)
            if job is not None and analyze_job(db, job, use_llm=False) is not None:
                n += 1
    return {"reanalyzed": n, "checked": len(ids)}


def refresh_salaries() -> dict:
    """Recompute salary status/estimates after a dataset change."""
    from sqlalchemy import select

    from app.models import Job
    from app.pipeline.salary import apply_salary

    n = 0
    with session_scope() as db:
        for job in db.scalars(select(Job).where(Job.is_relevant)):
            apply_salary(db, job)
            n += 1
    return {"recomputed": n}


def retry_kwargs() -> dict:
    return {"retry": Retry(max=3, interval=[60, 300, 900])}
