"""Job filter model + SQL builder, shared by the API, CSV export, saved searches
and the notification matcher (so an alert matches exactly what the user saw)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, exists, func, or_, select

from app.models import Job, JobCategory, JobSkill, Source
from app.pipeline.normalize import normalize_text

SORTS = {
    "newest": (Job.first_seen_at.desc(), Job.id.desc()),
    "published": (Job.published_at.desc().nulls_last(), Job.id.desc()),
    "changed": (Job.last_changed_at.desc().nulls_last(), Job.id.desc()),
    "salary": (Job.effective_salary_max.desc().nulls_last(), Job.id.desc()),
    "quality": (Job.quality_score.desc().nulls_last(), Job.id.desc()),
    "title": (Job.title.asc(), Job.id.asc()),
}


class JobFilters(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    sources: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    subcategories: list[str] = Field(default_factory=list)
    provinces: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    work_modes: list[Literal["onsite", "hybrid", "remote"]] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)  # all must be required skills of the job
    salary_min: int | None = None
    salary_max: int | None = None
    salary_status: list[Literal["reported", "estimated", "unknown"]] = Field(default_factory=list)
    quality_min: int | None = Field(default=None, ge=0, le=100)
    published_from: datetime | None = None
    published_to: datetime | None = None
    changed_from: datetime | None = None
    status: list[Literal["active", "expired", "unknown"]] = Field(default_factory=lambda: ["active"])
    relevant_only: bool = True


def _like(v: str) -> str:
    v = v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{v}%"


def apply_filters(stmt: Select, f: JobFilters) -> Select:
    conds = []
    if f.relevant_only:
        conds.append(Job.is_relevant.is_(True))
    if f.status:
        conds.append(Job.status.in_(f.status))
    if f.q:
        q = normalize_text(f.q).lower()
        conds.append(or_(Job.search_text.ilike(_like(q)), Job.description.ilike(_like(q)), Job.title.ilike(_like(q))))
    if f.title:
        conds.append(Job.title.ilike(_like(normalize_text(f.title))))
    if f.company:
        conds.append(Job.company_name.ilike(_like(normalize_text(f.company))))
    if f.sources:
        conds.append(Job.source_id.in_(select(Source.id).where(Source.key.in_(f.sources))))
    if f.categories:
        conds.append(exists().where(JobCategory.job_id == Job.id, JobCategory.category.in_(f.categories)))
    if f.subcategories:
        conds.append(exists().where(JobCategory.job_id == Job.id, JobCategory.subcategory.in_(f.subcategories)))
    if f.provinces:
        conds.append(Job.province.in_(f.provinces))
    if f.cities:
        conds.append(Job.city.in_(f.cities))
    if f.work_modes:
        conds.append(Job.work_mode.in_(f.work_modes))
    if f.seniority:
        conds.append(Job.seniority.in_(f.seniority))
    for skill in f.skills:
        conds.append(exists().where(JobSkill.job_id == Job.id, func.lower(JobSkill.skill) == skill.lower(),
                                    JobSkill.skill_type == "required"))
    if f.salary_min is not None:
        conds.append(Job.effective_salary_max >= f.salary_min)
    if f.salary_max is not None:
        conds.append(Job.effective_salary_min <= f.salary_max)
    if f.salary_status:
        conds.append(Job.salary_status.in_(f.salary_status))
    if f.quality_min is not None:
        conds.append(Job.quality_score >= f.quality_min)
    if f.published_from:
        conds.append(func.coalesce(Job.published_at, Job.first_seen_at) >= f.published_from)
    if f.published_to:
        conds.append(func.coalesce(Job.published_at, Job.first_seen_at) <= f.published_to)
    if f.changed_from:
        conds.append(Job.last_changed_at >= f.changed_from)
    return stmt.where(and_(*conds)) if conds else stmt


def job_query(f: JobFilters, sort: str = "newest") -> Select:
    return apply_filters(select(Job), f).order_by(*SORTS.get(sort, SORTS["newest"]))
