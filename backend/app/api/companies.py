from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.jobs import _source_keys, job_summary
from app.db import get_db
from app.filters import _like
from app.models import Company, Job, User

router = APIRouter(tags=["companies"])


@router.get("/companies")
def list_companies(
    q: str | None = Query(None, max_length=200),
    transparency: list[str] = Query([]),
    with_active_jobs: bool = True,
    sort: str = Query("jobs", pattern="^(jobs|name|transparency)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    active = func.count(Job.id).filter(and_(Job.status == "active", Job.is_relevant.is_(True)))
    relevant = func.count(Job.id).filter(Job.is_relevant.is_(True))
    stmt = (select(Company, active.label("active_jobs"), relevant.label("relevant_jobs"))
            .outerjoin(Job, Job.company_id == Company.id).group_by(Company.id))
    if q:
        stmt = stmt.where(Company.name.ilike(_like(q)))
    if transparency:
        stmt = stmt.where(Company.transparency_level.in_(transparency))
    if with_active_jobs:
        stmt = stmt.having(relevant > 0)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"jobs": (active.desc(), Company.name), "name": (Company.name,),
             "transparency": (Company.transparency_score.desc().nulls_last(), Company.name)}[sort]
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [{
        "id": c.id, "name": c.name, "website": c.website, "size": c.size, "industry": c.industry, "city": c.city,
        "logo_url": c.logo_url, "transparency_level": c.transparency_level, "transparency_score": c.transparency_score,
        "active_jobs": a, "relevant_jobs": r, "sources": [p.get("source") for p in c.profiles or []],
    } for c, a, r in rows]}


@router.get("/companies/{company_id}")
def company_detail(company_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(Company, company_id)
    if c is None:
        raise HTTPException(404, "company not found")
    keys = _source_keys(db)
    jobs = db.scalars(select(Job).where(Job.company_id == c.id).order_by(Job.first_seen_at.desc()).limit(100)).all()
    return {
        "id": c.id, "name": c.name, "website": c.website, "description": c.description, "size": c.size,
        "industry": c.industry, "city": c.city, "logo_url": c.logo_url, "profiles": c.profiles,
        "transparency": c.transparency, "transparency_level": c.transparency_level,
        "transparency_score": c.transparency_score, "assessed_at": c.assessed_at,
        "jobs": [job_summary(j, keys) for j in jobs],
        "data_status": {
            "profile_sources": len(c.profiles or []),
            "last_seen": c.profile_fetched_at,
            "missing": [k for k, v in {"website": c.website, "size": c.size, "industry": c.industry,
                                       "description": c.description}.items() if not v],
        },
    }
