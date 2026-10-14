"""One collection run of one source.

Budget per run = collector_max_pages_per_run page fetches:
1. new candidates (not in DB) first,
2. then known candidates whose listing lastmod is newer than our last fetch,
3. then re-checks of active jobs that disappeared from the listing (expiry checks),
4. then refreshes of the oldest-seen known candidates.
Whatever does not fit is reported as deferred in the run's coverage note.

Expiry is conservative: a job is marked expired only when its own page says so
(404/410 or an explicit expired flag) during a run that is not blocked/failing.
"""
from __future__ import annotations

import traceback
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import Candidate
from app.collectors.http import BlockedError, DisallowedError
from app.collectors.registry import get_adapter
from app.config import get_settings
from app.models import Job, Source, SourceRun
from app.pipeline.ingest import ingest, mark_expired

log = structlog.get_logger()

MAX_ERRORS_KEPT = 50
DEGRADED_FAILURE_RATIO = 0.2
STALE_RECHECK = timedelta(days=3)


def _now() -> datetime:
    return datetime.now(UTC)


def run_source(db: Session, source_key: str, trigger: str = "schedule", *, adapter=None) -> SourceRun:
    source = db.scalar(select(Source).where(Source.key == source_key))
    if source is None:
        raise ValueError(f"unknown source {source_key}")
    adapter = adapter or get_adapter(source_key)
    run = SourceRun(source_id=source.id, trigger=trigger, is_baseline=not source.baseline_done)
    db.add(run)
    source.last_run_at = _now()
    db.commit()

    if not source.enabled:
        run.status = "skipped"
        run.coverage_note = "source disabled by admin"
        run.finished_at = _now()
        source.status = "disabled"
        db.commit()
        return run

    errors: list[str] = []
    client = adapter.client()
    budget = get_settings().collector_max_pages_per_run
    stats = {k: 0 for k in ("fetched", "parsed", "relevant", "new_jobs", "changed_jobs", "expired_jobs",
                            "failed", "skipped")}
    discovered = 0

    def sync_stats():
        # Counters live outside the ORM row: a rollback expires the row's attributes.
        for k, v in stats.items():
            setattr(run, k, v)
        run.discovered = discovered

    try:
        robots = client.load_robots()
        source.robots_summary = robots[:4000]
        source.robots_checked_at = _now()
        db.commit()

        discovery = adapter.discover(client, source.config or {}, source.state or {})
        errors += discovery.errors
        discovered = len(discovery.candidates)
        known = {
            j.source_job_id: j
            for j in db.scalars(select(Job).where(Job.source_id == source.id))
        }
        listed_ids = discovery.all_listed_ids or {c.source_job_id for c in discovery.candidates}
        new = [c for c in discovery.candidates if c.source_job_id not in known]
        updated = [c for c in discovery.candidates if c.source_job_id in known and c.lastmod
                   and c.lastmod > (known[c.source_job_id].last_seen_at or datetime.min.replace(tzinfo=UTC))]
        # A sitemap lists every live ad, so absence is a strong signal -> re-check now.
        # A search listing only shows the top pages, so re-check only stale ones.
        min_age = timedelta(0) if adapter.complete_listing else STALE_RECHECK
        missing = [j for j in known.values() if j.status == "active" and j.source_job_id not in listed_ids
                   and _now() - j.last_seen_at >= min_age] if not discovery.errors else []
        # Listings with lastmod tell us unchanged ads need no fetch; without lastmod
        # (search pages) known ads are refreshed when not seen for 20h.
        refresh = sorted((c for c in discovery.candidates if c.source_job_id in known and c.lastmod is None),
                         key=lambda c: known[c.source_job_id].last_seen_at or datetime.min.replace(tzinfo=UTC))

        queue: list[tuple[str, Candidate | Job]] = (
            [("job", c) for c in new] + [("job", c) for c in updated] + [("recheck", j) for j in missing]
            + [("job", c) for c in refresh if (_now() - known[c.source_job_id].last_seen_at) > timedelta(hours=20)]
        )
        seen_now = _now()
        for c in discovery.candidates:
            j = known.get(c.source_job_id)
            if j is not None and c.lastmod is not None and c not in updated and j.status == "active":
                j.last_seen_at = seen_now  # still listed, unchanged since our last fetch
        db.commit()
        deferred = max(0, len(queue) - budget)
        queue = queue[:budget]

        for kind, item in queue:
            url = adapter.job_url(item.source_job_id, item.url if kind == "job" else item.canonical_url)
            try:
                page = client.get(url)
                stats["fetched"] += 1
                outcome = adapter.parse_job(page)
            except BlockedError:
                raise
            except DisallowedError:
                stats["skipped"] += 1
                errors.append(f"robots.txt disallows {url}")
                continue
            except Exception as exc:  # one bad page never stops the run
                stats["failed"] += 1
                errors.append(f"{url}: {type(exc).__name__}: {exc}"[:300])
                continue
            try:
                if outcome.status in ("gone",):
                    job = known.get(item.source_job_id)
                    if job is not None and mark_expired(db, job, reason=f"page returned HTTP {page.status}",
                                                        run_id=run.id, baseline=run.is_baseline):
                        stats["expired_jobs"] += 1
                elif outcome.status == "not_job":
                    stats["skipped"] += 1
                elif outcome.job is not None:
                    stats["parsed"] += 1
                    res = ingest(db, source.id, source.key, outcome.job, run_id=run.id, baseline=run.is_baseline)
                    if res.job.is_relevant:
                        stats["relevant"] += 1
                    if res.created and res.job.is_relevant:
                        stats["new_jobs"] += 1
                    elif res.changed and res.job.is_relevant:
                        stats["changed_jobs"] += 1
                    if outcome.status == "expired" and not res.created:
                        if mark_expired(db, res.job, reason="source marks the ad as expired",
                                        run_id=run.id, baseline=run.is_baseline):
                            stats["expired_jobs"] += 1
                    known[res.job.source_job_id] = res.job
                sync_stats()
                db.commit()
            except Exception as exc:
                db.rollback()  # also expires the run row; counters are re-applied from stats
                stats["failed"] += 1
                errors.append(f"store {url}: {type(exc).__name__}: {exc}"[:300])
                log.error("ingest_failed", url=url, error=str(exc), tb=traceback.format_exc()[-1500:])

        sync_stats()
        ratio = run.failed / run.fetched if run.fetched else 0
        run.status = "success" if ratio < DEGRADED_FAILURE_RATIO and not discovery.errors else "partial"
        source.status = "healthy" if run.status == "success" else "degraded"
        run.coverage_note = discovery.coverage_note + (
            f"; {deferred} page fetches deferred to the next run (budget {budget}/run)" if deferred else "")
        if run.parsed > 0:
            source.last_success_at = _now()
            if not source.baseline_done:
                source.baseline_done = True
        source.last_error = "; ".join(errors[:3]) or None
    except BlockedError as exc:
        db.rollback()
        run.status = "blocked"
        source.status = "blocked"
        source.last_error = str(exc)
        errors.append(str(exc))
        log.warning("source_blocked", source=source.key, error=str(exc))
    except Exception as exc:
        db.rollback()
        run.status = "failed"
        source.status = "degraded"
        source.last_error = f"{type(exc).__name__}: {exc}"[:500]
        errors.append(source.last_error)
        log.error("source_run_failed", source=source.key, tb=traceback.format_exc()[-2000:])
    finally:
        client.close()
    sync_stats()
    run.http_status_counts = dict(client.status_counts)
    run.errors = errors[:MAX_ERRORS_KEPT]
    run.finished_at = _now()
    interval = max(source.interval_minutes, source.min_interval_minutes)
    source.next_run_at = _now() + timedelta(minutes=interval)
    db.commit()
    return run
