import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, rate_limit
from app.db import SessionLocal, get_db
from app.filters import SORTS, JobFilters, apply_filters, job_query
from app.models import Job, JobAnalysis, JobCategory, JobEvent, JobSkill, JobSnapshot, Source, User
from app.pipeline import taxonomy as tx
from app.pipeline.matching import match

router = APIRouter(tags=["jobs"])


def filters_dep(
    q: str | None = Query(None, max_length=200),
    title: str | None = Query(None, max_length=200),
    company: str | None = Query(None, max_length=200),
    sources: list[str] = Query([]),
    categories: list[str] = Query([]),
    subcategories: list[str] = Query([]),
    provinces: list[str] = Query([]),
    cities: list[str] = Query([]),
    work_modes: list[Literal["onsite", "hybrid", "remote"]] = Query([]),
    seniority: list[str] = Query([]),
    skills: list[str] = Query([]),
    salary_min: int | None = Query(None, ge=0),
    salary_max: int | None = Query(None, ge=0),
    salary_status: list[Literal["reported", "estimated", "unknown"]] = Query([]),
    quality_min: int | None = Query(None, ge=0, le=100),
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    changed_from: datetime | None = None,
    status: list[Literal["active", "expired", "unknown"]] = Query(["active"]),
    relevant_only: bool = True,
) -> JobFilters:
    return JobFilters(**{k: v for k, v in locals().items()})


def job_summary(j: Job, source_keys: dict[int, str]) -> dict:
    cats = sorted(j.categories, key=lambda c: (not c.is_primary, -c.confidence))
    return {
        "id": j.id, "source": source_keys.get(j.source_id), "title": j.title, "company_name": j.company_name,
        "company_id": j.company_id, "city": j.city, "province": j.province, "work_mode": j.work_mode,
        "employment_type": j.employment_type, "seniority": j.seniority,
        "categories": [{"category": c.category, "subcategory": c.subcategory, "confidence": c.confidence,
                        "primary": c.is_primary} for c in cats],
        "required_skills": [s.skill for s in j.skills if s.skill_type == "required"][:12],
        "salary_status": j.salary_status, "salary_min": j.effective_salary_min, "salary_max": j.effective_salary_max,
        "salary_original": j.salary_original, "quality_score": j.quality_score, "status": j.status,
        "published_at": j.published_at, "first_seen_at": j.first_seen_at, "last_changed_at": j.last_changed_at,
        "canonical_url": j.canonical_url,
    }


def _source_keys(db: Session) -> dict[int, str]:
    return dict(db.execute(select(Source.id, Source.key)).all())


@router.get("/jobs")
def list_jobs(
    f: JobFilters = Depends(filters_dep),
    sort: str = Query("newest", pattern="^(" + "|".join(SORTS) + ")$"),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    total = db.scalar(apply_filters(select(func.count()).select_from(Job), f))
    rows = db.scalars(job_query(f, sort).offset((page - 1) * page_size).limit(page_size)).all()
    keys = _source_keys(db)
    profile = user.profile or {}
    items = []
    for j in rows:
        item = job_summary(j, keys)
        if profile.get("skills"):
            item["match_score"] = match(profile, j)["match_score"]
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/jobs/facets")
def facets(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rel = Job.is_relevant.is_(True)
    cities = db.execute(select(Job.city, func.count()).where(rel, Job.city.is_not(None)).group_by(Job.city)
                        .order_by(func.count().desc()).limit(60)).all()
    provinces = db.execute(select(Job.province, func.count()).where(rel, Job.province.is_not(None))
                           .group_by(Job.province).order_by(func.count().desc())).all()
    subcats = db.execute(select(JobCategory.category, JobCategory.subcategory, func.count()).join(Job)
                         .where(rel).group_by(JobCategory.category, JobCategory.subcategory)
                         .order_by(func.count().desc())).all()
    skills = db.execute(select(JobSkill.skill, func.count()).join(Job).where(rel, JobSkill.skill_type == "required")
                        .group_by(JobSkill.skill).order_by(func.count().desc()).limit(80)).all()
    return {
        "sources": [{"key": k, "name": n} for k, n in db.execute(select(Source.key, Source.name)).all()],
        "categories": [{"key": k, "label": v} for k, v in tx.CATEGORY_LABELS_FA.items()],
        "subcategories": [{"category": c, "subcategory": s, "count": n} for c, s, n in subcats if s],
        "provinces": [{"value": p, "count": n} for p, n in provinces],
        "cities": [{"value": c, "count": n} for c, n in cities],
        "skills": [{"value": s, "count": n} for s, n in skills],
        "seniority": ["junior", "mid", "senior", "staff", "principal", "unknown"],
        "sorts": list(SORTS),
    }


CSV_COLUMNS = ["id", "source", "title", "company_name", "province", "city", "work_mode", "employment_type",
               "seniority", "categories", "required_skills", "salary_status", "salary_min", "salary_max",
               "salary_original", "quality_score", "status", "published_at", "first_seen_at", "last_changed_at",
               "canonical_url"]


def _csv_safe(v) -> str:
    s = "" if v is None else str(v)
    # Spreadsheet formula injection guard.
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@router.get("/jobs/export.csv", dependencies=[Depends(rate_limit("export", 10, 60))])
def export_csv(f: JobFilters = Depends(filters_dep), sort: str = "newest", user: User = Depends(current_user)):
    def gen():
        # Own session: the response streams after the request's dependencies are done,
        # and a session left open here would sit "idle in transaction" holding locks.
        db = SessionLocal()
        try:
            keys = _source_keys(db)
            buf = io.StringIO()
            w = csv.writer(buf)
            buf.write("\ufeff")  # Excel needs the BOM to read UTF-8 Persian
            w.writerow(CSV_COLUMNS)
            for j in db.scalars(job_query(f, sort).limit(20000)):
                s = job_summary(j, keys)
                s["categories"] = "|".join(c["category"] for c in s["categories"])
                s["required_skills"] = "|".join(s["required_skills"])
                w.writerow([_csv_safe(s.get(c)) for c in CSV_COLUMNS])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        finally:
            db.rollback()
            db.close()

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="jobs.csv"'})


@router.get("/jobs/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    keys = _source_keys(db)
    analysis = db.scalar(select(JobAnalysis).where(JobAnalysis.job_id == j.id, JobAnalysis.is_current))
    snaps = db.scalars(select(JobSnapshot).where(JobSnapshot.job_id == j.id).order_by(JobSnapshot.captured_at.desc())
                       .limit(30)).all()
    events = db.scalars(select(JobEvent).where(JobEvent.job_id == j.id).order_by(JobEvent.created_at.desc())
                        .limit(50)).all()
    dupes = []
    if j.dedup_key:
        dupes = [{"id": d.id, "source": keys.get(d.source_id), "title": d.title, "status": d.status,
                  "canonical_url": d.canonical_url}
                 for d in db.scalars(select(Job).where(Job.dedup_key == j.dedup_key, Job.id != j.id).limit(10))]
    out = job_summary(j, keys)
    out.update({
        "description": j.description, "benefits": j.benefits, "experience_required": j.experience_required,
        "experience_min_years": j.experience_min_years,
        "optional_skills": [s.skill for s in j.skills if s.skill_type == "optional"],
        "skills": [{"name": s.skill, "type": s.skill_type, "origin": s.origin} for s in j.skills],
        "company_profile_url": j.company_profile_url, "expires_at": j.expires_at, "last_seen_at": j.last_seen_at,
        "salary_estimate": j.salary_estimate, "salary_currency": j.salary_currency, "salary_period": j.salary_period,
        "published_at_note": None if j.published_at else "تاریخ انتشار در منبع مشخص نیست؛ «اولین مشاهده» تاریخ دیده شدن آگهی توسط این سامانه است.",
        "extra": {k: v for k, v in (j.extra or {}).items() if k in ("work_days", "source_categories", "work_mode_evidence", "gender", "education", "military")},
        "analysis": {"engine": analysis.engine, "model": analysis.model, "created_at": analysis.created_at,
                     "error": analysis.error, **analysis.result} if analysis else None,
        "history": [{"captured_at": s.captured_at, "content_hash": s.content_hash} for s in snaps],
        "events": [{"id": e.id, "type": e.event_type, "diff": e.diff, "created_at": e.created_at,
                    "is_baseline": e.is_baseline} for e in events],
        "duplicates": dupes,
    })
    if (user.profile or {}).get("skills"):
        out["match"] = match(user.profile, j)
    return out


@router.get("/jobs/{job_id}/snapshots/{snapshot_index}")
def job_snapshot(job_id: int, snapshot_index: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    snaps = db.scalars(select(JobSnapshot).where(JobSnapshot.job_id == job_id).order_by(JobSnapshot.captured_at.desc())).all()
    if snapshot_index < 0 or snapshot_index >= len(snaps):
        raise HTTPException(404, "snapshot not found")
    s = snaps[snapshot_index]
    return {"captured_at": s.captured_at, "data": s.data}


@router.get("/events")
def list_events(
    types: list[str] = Query([]),
    include_baseline: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(JobEvent, Job).join(Job, Job.id == JobEvent.job_id)
    if types:
        stmt = stmt.where(JobEvent.event_type.in_(types))
    if not include_baseline:
        stmt = stmt.where(JobEvent.is_baseline.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(JobEvent.created_at.desc(), JobEvent.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [{
        "id": e.id, "type": e.event_type, "created_at": e.created_at, "diff": e.diff, "is_baseline": e.is_baseline,
        "job": {"id": j.id, "title": j.title, "company_name": j.company_name, "status": j.status},
    } for e, j in rows]}
