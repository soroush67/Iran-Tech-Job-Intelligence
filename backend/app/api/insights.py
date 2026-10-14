"""Dashboard + market insights. Every number is computed from stored data;
salary distributions are only returned for groups with enough samples."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Job, JobCategory, JobEvent, JobSkill, Source, SourceRun, User
from app.pipeline.salary import MIN_MARKET_SAMPLES

router = APIRouter(tags=["insights"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = datetime.now(UTC)
    rel = and_(Job.is_relevant.is_(True))
    active = and_(rel, Job.status == "active")
    by_cat = db.execute(select(JobCategory.category, func.count(func.distinct(JobCategory.job_id))).join(Job)
                        .where(active).group_by(JobCategory.category)).all()
    last_runs = db.execute(
        select(SourceRun, Source.key).join(Source).order_by(SourceRun.started_at.desc()).limit(6)).all()
    return {
        "total_relevant_active": db.scalar(select(func.count()).select_from(Job).where(active)),
        "total_relevant": db.scalar(select(func.count()).select_from(Job).where(rel)),
        "new_24h": db.scalar(select(func.count()).select_from(JobEvent).where(
            JobEvent.event_type == "NEW_JOB", JobEvent.created_at >= now - timedelta(hours=24),
            JobEvent.is_baseline.is_(False))),
        "first_seen_24h": db.scalar(select(func.count()).select_from(Job).where(rel, Job.first_seen_at >= now - timedelta(hours=24))),
        "changed_24h": db.scalar(select(func.count(func.distinct(JobEvent.job_id))).where(
            JobEvent.event_type.in_(["SALARY_CHANGED", "DESCRIPTION_CHANGED", "REQUIREMENTS_CHANGED", "WORK_MODE_CHANGED"]),
            JobEvent.created_at >= now - timedelta(hours=24))),
        "expired_24h": db.scalar(select(func.count()).select_from(JobEvent).where(
            JobEvent.event_type == "JOB_EXPIRED", JobEvent.created_at >= now - timedelta(hours=24))),
        "by_category": {c: n for c, n in by_cat},
        "salary_status": {s: n for s, n in db.execute(select(Job.salary_status, func.count()).where(active)
                                                      .group_by(Job.salary_status)).all()},
        "sources": _sources_health(db),
        "last_runs": [_run_out(r, k) for r, k in last_runs],
    }


def _run_out(r: SourceRun, key: str) -> dict:
    return {"id": r.id, "source": key, "status": r.status, "trigger": r.trigger, "is_baseline": r.is_baseline,
            "started_at": r.started_at, "finished_at": r.finished_at, "discovered": r.discovered, "fetched": r.fetched,
            "parsed": r.parsed, "relevant": r.relevant, "new_jobs": r.new_jobs, "changed_jobs": r.changed_jobs,
            "expired_jobs": r.expired_jobs, "failed": r.failed, "skipped": r.skipped,
            "http_status_counts": r.http_status_counts, "coverage_note": r.coverage_note, "errors": r.errors[:10]}


def _sources_health(db: Session) -> list[dict]:
    out = []
    for s in db.scalars(select(Source).order_by(Source.id)):
        jobs = db.scalar(select(func.count()).select_from(Job).where(Job.source_id == s.id))
        relevant = db.scalar(select(func.count()).select_from(Job).where(Job.source_id == s.id, Job.is_relevant.is_(True)))
        active = db.scalar(select(func.count()).select_from(Job).where(Job.source_id == s.id, Job.is_relevant.is_(True),
                                                                      Job.status == "active"))
        last = db.scalar(select(SourceRun).where(SourceRun.source_id == s.id, SourceRun.status != "skipped")
                         .order_by(SourceRun.started_at.desc()).limit(1))
        out.append({
            "key": s.key, "name": s.name, "base_url": s.base_url, "enabled": s.enabled,
            "status": "disabled" if not s.enabled else s.status,
            "jobs_total": jobs, "jobs_relevant": relevant, "jobs_relevant_active": active,
            "last_run_at": s.last_run_at, "last_success_at": s.last_success_at, "next_run_at": s.next_run_at,
            "interval_minutes": s.interval_minutes, "min_interval_minutes": s.min_interval_minutes,
            "access_method": s.access_method, "limitations": s.limitations, "last_error": s.last_error,
            "robots_checked_at": s.robots_checked_at, "baseline_done": s.baseline_done,
            "running": bool(last and last.status == "running"),
            "coverage_note": last.coverage_note if last else None,
            "last_run": _run_out(last, s.key) if last else None,
        })
    return out


@router.get("/sources/health")
def sources_health(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"sources": _sources_health(db)}


@router.get("/insights")
def insights(
    weeks: int = Query(12, ge=2, le=52),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    now = datetime.now(UTC)
    since = now - timedelta(weeks=weeks)
    rel = Job.is_relevant.is_(True)
    week = func.date_trunc("week", Job.first_seen_at)
    trend = db.execute(
        select(week.label("week"), JobCategory.category, func.count(func.distinct(Job.id)))
        .join(JobCategory, JobCategory.job_id == Job.id)
        .where(rel, Job.first_seen_at >= since).group_by("week", JobCategory.category).order_by("week")
    ).all()
    demand = db.execute(select(JobCategory.category, JobCategory.subcategory, func.count()).join(Job)
                        .where(rel, Job.status == "active").group_by(JobCategory.category, JobCategory.subcategory)
                        .order_by(func.count().desc())).all()
    top_skills = db.execute(select(JobSkill.skill, func.count()).join(Job).where(rel, Job.status == "active")
                            .group_by(JobSkill.skill).order_by(func.count().desc()).limit(30)).all()
    skills_by_cat = {}
    for cat in ("devops", "sre", "python", "ai_ml", "mlops_data"):
        skills_by_cat[cat] = [{"skill": s, "count": n} for s, n in db.execute(
            select(JobSkill.skill, func.count()).join(Job).join(JobCategory, JobCategory.job_id == Job.id)
            .where(rel, Job.status == "active", JobCategory.category == cat)
            .group_by(JobSkill.skill).order_by(func.count().desc()).limit(12)).all()]
    work_modes = db.execute(select(Job.work_mode, func.count()).where(rel, Job.status == "active")
                            .group_by(Job.work_mode)).all()
    cities = db.execute(select(Job.city, func.count()).where(rel, Job.status == "active", Job.city.is_not(None))
                        .group_by(Job.city).order_by(func.count().desc()).limit(12)).all()
    seniority = db.execute(select(Job.seniority, func.count()).where(rel, Job.status == "active")
                           .group_by(Job.seniority)).all()

    # Reported salaries only (estimates would be circular), per category x seniority,
    # returned only when the group has enough samples.
    sal_rows = db.execute(
        select(JobCategory.category, Job.seniority, Job.salary_min, Job.salary_max)
        .join(JobCategory, JobCategory.job_id == Job.id)
        .where(rel, Job.salary_status == "reported", Job.salary_currency == "IRT",
               Job.first_seen_at >= now - timedelta(days=180))
    ).all()
    groups: dict[tuple[str, str], list[float]] = {}
    for cat, sen, lo, hi in sal_rows:
        groups.setdefault((cat, sen), []).append(((lo or hi) + (hi or lo)) / 2)
    salary = []
    for (cat, sen), vals in sorted(groups.items()):
        vals.sort()
        n = len(vals)
        entry = {"category": cat, "seniority": sen, "samples": n}
        if n >= MIN_MARKET_SAMPLES:
            entry.update({"p25": vals[n // 4], "median": vals[n // 2], "p75": vals[(3 * n) // 4],
                          "min": vals[0], "max": vals[-1]})
        else:
            entry["insufficient"] = True
        salary.append(entry)
    total_active = db.scalar(select(func.count()).select_from(Job).where(rel, Job.status == "active"))
    reported = db.scalar(select(func.count()).select_from(Job).where(rel, Job.status == "active",
                                                                   Job.salary_status == "reported"))
    return {
        "generated_at": now, "weeks": weeks, "total_active": total_active,
        "trend": [{"week": w, "category": c, "count": n} for w, c, n in trend],
        "demand": [{"category": c, "subcategory": s, "count": n} for c, s, n in demand],
        "top_skills": [{"skill": s, "count": n} for s, n in top_skills],
        "skills_by_category": skills_by_cat,
        "work_modes": [{"work_mode": m or "unknown", "count": n} for m, n in work_modes],
        "cities": [{"city": c, "count": n} for c, n in cities],
        "seniority": [{"seniority": s, "count": n} for s, n in seniority],
        "salary": {"groups": salary, "reported_share": (reported / total_active) if total_active else None,
                   "min_samples": MIN_MARKET_SAMPLES,
                   "note": "فقط حقوق‌های اعلام‌شده در آگهی‌ها (۱۸۰ روز اخیر)؛ گروه‌های کمتر از حداقل نمونه نمایش داده نمی‌شوند."},
        "coverage_note": "آمار فقط از آگهی‌های جمع‌آوری‌شده از منابع فعال است و نماینده کل بازار نیست؛ پوشش هر منبع در صفحه منابع آمده است.",
    }
