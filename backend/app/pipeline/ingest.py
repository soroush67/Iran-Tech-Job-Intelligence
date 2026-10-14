"""Turn a RawJob into DB state: company upsert, job upsert, snapshot, change events.

Change detection compares *normalised* field values (compare_key), so HTML reflow,
whitespace/ZWNJ differences and tracking parameters never create events.
"""
from __future__ import annotations

import difflib
import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import RawJob
from app.models import Company, Job, JobEvent, JobSnapshot
from app.pipeline import company as company_assessment
from app.pipeline import rules
from app.pipeline.normalize import compare_key, normalize_name, normalize_text, parse_experience_years, stable_hash

DESCRIPTION_SIMILARITY_THRESHOLD = 0.97


def _now() -> datetime:
    return datetime.now(UTC)


def snapshot_of(raw: RawJob, work_mode: str | None, benefits: list[str]) -> dict:
    """The fields that define the ad's content (what a snapshot stores)."""
    return {
        "title": raw.title,
        "company_name": raw.company_name,
        "city": raw.city,
        "province": raw.province,
        "work_mode": work_mode,
        "employment_type": raw.employment_type,
        "experience_required": raw.experience_required,
        "required_skills": sorted(set(raw.required_skills)),
        "optional_skills": sorted(set(raw.optional_skills)),
        "description": raw.description,
        "benefits": sorted(set(benefits)),
        "salary_original": raw.salary_original,
        "salary_min": raw.salary_min,
        "salary_max": raw.salary_max,
    }


def content_hash(snap: dict) -> str:
    keyed = {k: ([compare_key(x) for x in v] if isinstance(v, list) else compare_key(str(v)) if v is not None else None)
             for k, v in snap.items()}
    return stable_hash(keyed)


def dedup_key(company: str | None, title: str, city: str | None) -> str:
    raw = f"{normalize_name(company)}|{normalize_name(title)}|{normalize_name(city)}"
    return hashlib.sha1(raw.encode()).hexdigest()


def upsert_company(db: Session, raw: RawJob, source_key: str) -> Company | None:
    if not raw.company_name:
        return None
    key = normalize_name(raw.company_name)[:255]
    if not key:
        return None
    company = db.scalar(select(Company).where(Company.normalized_name == key))
    if company is None:
        company = Company(name=normalize_text(raw.company_name)[:255], normalized_name=key, profiles=[])
        db.add(company)
    for attr, val in (("website", raw.company_website), ("size", raw.company_size),
                      ("industry", raw.company_industry), ("logo_url", raw.company_logo_url),
                      ("city", raw.city)):
        if val and not getattr(company, attr):
            setattr(company, attr, val[:500] if isinstance(val, str) else val)
    if raw.company_description and len(raw.company_description) > len(company.description or ""):
        company.description = raw.company_description
    if raw.company_profile_url:
        profiles = [p for p in (company.profiles or []) if p.get("source") != source_key]
        profiles.append({"source": source_key, "url": raw.company_profile_url, "seen_at": _now().isoformat(),
                         "facts": {k: v for k, v in {
                             "website": raw.company_website, "size": raw.company_size,
                             "industry": raw.company_industry,
                             "establishment_year": raw.extra.get("company_establishment_year"),
                             "company_type": raw.extra.get("company_type"),
                             "has_description": bool(raw.company_description),
                         }.items() if v}})
        company.profiles = profiles
    company.profile_fetched_at = _now()
    company_assessment.apply(company)
    db.flush()
    return company


def diff_events(old: dict, new: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []

    def changed(*keys) -> bool:
        for k in keys:
            a, b = old.get(k), new.get(k)
            if isinstance(a, list) or isinstance(b, list):
                if {compare_key(x) for x in a or []} != {compare_key(x) for x in b or []}:
                    return True
            elif compare_key(str(a or "")) != compare_key(str(b or "")):
                return True
        return False

    if changed("salary_min", "salary_max", "salary_original"):
        events.append(("SALARY_CHANGED", {k: {"old": old.get(k), "new": new.get(k)}
                                           for k in ("salary_original", "salary_min", "salary_max")}))
    if changed("description"):
        a, b = normalize_text(old.get("description")), normalize_text(new.get("description"))
        ratio = difflib.SequenceMatcher(None, compare_key(a), compare_key(b), autojunk=False).ratio()
        if ratio < DESCRIPTION_SIMILARITY_THRESHOLD:
            udiff = list(difflib.unified_diff(a.split("\n"), b.split("\n"), lineterm="", n=1))[2:80]
            events.append(("DESCRIPTION_CHANGED", {"similarity": round(ratio, 3), "diff": udiff}))
    if changed("required_skills", "optional_skills", "experience_required"):
        events.append(("REQUIREMENTS_CHANGED", {
            "required_skills": {"old": old.get("required_skills"), "new": new.get("required_skills"),
                                "added": sorted(set(new.get("required_skills") or []) - set(old.get("required_skills") or [])),
                                "removed": sorted(set(old.get("required_skills") or []) - set(new.get("required_skills") or []))},
            "optional_skills": {"old": old.get("optional_skills"), "new": new.get("optional_skills")},
            "experience_required": {"old": old.get("experience_required"), "new": new.get("experience_required")},
        }))
    if changed("work_mode"):
        events.append(("WORK_MODE_CHANGED", {"work_mode": {"old": old.get("work_mode"), "new": new.get("work_mode")}}))
    return events


class IngestResult:
    def __init__(self, job: Job, created: bool, changed: bool, events: list[str]):
        self.job, self.created, self.changed, self.events = job, created, changed, events


def ingest(db: Session, source_id: int, source_key: str, raw: RawJob, *, run_id: int | None, baseline: bool) -> IngestResult:
    now = _now()
    text = f"{raw.title}\n{raw.description}"
    work_mode, mode_evidence = rules.detect_work_mode(raw.work_mode, text)
    benefits = rules.extract_benefits(raw.benefits, raw.description)
    snap = snapshot_of(raw, work_mode, benefits)
    h = content_hash(snap)
    company = upsert_company(db, raw, source_key)

    job = db.scalar(select(Job).where(Job.source_id == source_id, Job.source_job_id == raw.source_job_id))
    created = job is None
    event_types: list[tuple[str, dict]] = []
    if created:
        job = Job(source_id=source_id, source_job_id=raw.source_job_id, first_seen_at=now, content_hash=h)
        db.add(job)
        event_types.append(("NEW_JOB", {}))
        changed = True
    else:
        changed = job.content_hash != h
        if changed:
            last = db.scalar(select(JobSnapshot).where(JobSnapshot.job_id == job.id)
                             .order_by(JobSnapshot.captured_at.desc(), JobSnapshot.id.desc()).limit(1))
            event_types += diff_events(last.data if last else {}, snap)
        if job.status == "expired" and not raw.is_expired:
            event_types.append(("JOB_REOPENED", {"expired_since": job.last_changed_at.isoformat() if job.last_changed_at else None}))

    job.canonical_url = raw.canonical_url
    job.title = raw.title[:500]
    job.company_id = company.id if company else None
    job.company_name = raw.company_name
    job.company_profile_url = raw.company_profile_url
    job.city, job.province = raw.city, raw.province
    job.work_mode = work_mode
    job.employment_type = raw.employment_type
    job.experience_required = raw.experience_required
    job.experience_min_years = parse_experience_years(raw.experience_required)
    job.required_skills = list(dict.fromkeys(raw.required_skills))
    job.optional_skills = list(dict.fromkeys(raw.optional_skills))
    job.description = raw.description
    job.benefits = benefits
    job.salary_original = raw.salary_original
    job.salary_min, job.salary_max = raw.salary_min, raw.salary_max
    job.salary_currency, job.salary_period = raw.salary_currency, raw.salary_period
    job.published_at = raw.published_at  # stays NULL when the source does not state it
    job.expires_at = raw.expires_at
    job.last_seen_at = now
    job.missing_checks = 0
    if not raw.is_expired:
        job.status = "active"
    elif created:
        job.status = "expired"  # first seen already expired: stored, no events
    # an existing job that is now expired is handled by mark_expired() (records JOB_EXPIRED)
    job.content_hash = h
    job.dedup_key = dedup_key(raw.company_name, raw.title, raw.city)
    job.extra = {**raw.extra, "seniority_hint": raw.seniority_hint, "source_categories": raw.source_categories,
                 "work_mode_evidence": mode_evidence}
    job.search_text = normalize_text(" ".join(filter(None, [raw.title, raw.company_name, raw.city, raw.province,
                                                            " ".join(raw.required_skills)]))).lower()
    if changed or created:
        job.last_changed_at = now if not created else None
    db.flush()

    if created or changed:
        db.add(JobSnapshot(job_id=job.id, content_hash=h, data=snap, captured_at=now, source_run_id=run_id))

    # Rule analysis is cheap and keeps categories/quality consistent with the content.
    if created or changed or not job.categories:
        from app.ai.engine import analyze_job
        analyze_job(db, job, use_llm=False, force=True)

    names = []
    if job.is_relevant:
        for etype, diff in event_types:
            db.add(JobEvent(job_id=job.id, event_type=etype, diff=diff, is_baseline=baseline, source_run_id=run_id))
            names.append(etype)
    db.flush()
    return IngestResult(job, created, changed and not created, names)


def mark_expired(db: Session, job: Job, *, reason: str, run_id: int | None, baseline: bool) -> bool:
    if job.status == "expired":
        return False
    job.status = "expired"
    job.last_changed_at = _now()
    if job.is_relevant:
        db.add(JobEvent(job_id=job.id, event_type="JOB_EXPIRED", diff={"reason": reason},
                        is_baseline=baseline, source_run_id=run_id))
    db.flush()
    return True
