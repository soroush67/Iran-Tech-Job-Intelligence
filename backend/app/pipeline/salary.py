"""Salary Intelligence Engine.

reported  - the ad states a figure (always wins).
estimated - from an admin-uploaded, versioned benchmark dataset or from enough
            reported salaries of comparable collected ads (same category and
            seniority, last 180 days). The method, source, data year, sample size
            and confidence are always returned.
unknown   - not enough data. We never fill a number without backing data, and a
            missing salary is never treated as a low salary.
"""
from __future__ import annotations

import statistics
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Job, JobCategory, SalaryBenchmark, SalaryDataset

MIN_MARKET_SAMPLES = 5
HOURS_PER_MONTH = 176


def jalali_year(d: date | None = None) -> int:
    """Solar Hijri year of a Gregorian date (Nowruz ~ March 21)."""
    d = d or date.today()
    return d.year - 621 if (d.month, d.day) >= (3, 21) else d.year - 622


def monthly(amount: int | None, period: str | None) -> int | None:
    if amount is None:
        return None
    if period == "yearly":
        return amount // 12
    if period == "hourly":
        return amount * HOURS_PER_MONTH
    return amount


def _primary_category(job: Job) -> str | None:
    cats = sorted(job.categories, key=lambda c: (not c.is_primary, -c.confidence))
    return cats[0].category if cats else None


def _from_dataset(db: Session, category: str, seniority: str, city: str | None) -> dict | None:
    q = (
        select(SalaryBenchmark, SalaryDataset)
        .join(SalaryDataset, SalaryDataset.id == SalaryBenchmark.dataset_id)
        .where(SalaryDataset.is_active, SalaryBenchmark.category == category)
    )
    rows = db.execute(q).all()
    if not rows:
        return None

    def rank(row):
        b, ds = row
        s = 0
        if seniority != "unknown" and b.seniority == seniority:
            s += 4
        elif b.seniority not in (None, "", seniority):
            return -1  # explicit different level: not comparable
        if city and b.city == city:
            s += 2
        elif b.city not in (None, "", city):
            return -1
        return s * 10000 + ds.data_year

    best = max(rows, key=rank)
    if rank(best) < 0:
        return None
    b, ds = best
    exact = (seniority != "unknown" and b.seniority == seniority) + bool(city and b.city == city)
    confidence = 0.75 if exact == 2 else 0.6 if exact == 1 else 0.45
    if jalali_year() - ds.data_year >= 2:
        confidence -= 0.15  # stale data
    return {
        "status": "estimated", "min": b.salary_min, "max": b.salary_max, "median": b.salary_median,
        "currency": "IRT", "period": "monthly", "method": "benchmark_dataset",
        "source": ds.source_name, "source_url": ds.source_url, "dataset": f"{ds.name} v{ds.version}",
        "data_year": ds.data_year, "sample_size": b.sample_size,
        "matched_on": {"category": category, "seniority": b.seniority, "city": b.city},
        "confidence": round(max(confidence, 0.2), 2),
    }


def _from_market(db: Session, job: Job, category: str, seniority: str) -> dict | None:
    since = datetime.now(UTC) - timedelta(days=180)
    q = (
        select(Job.salary_min, Job.salary_max, Job.salary_period, Job.city)
        .join(JobCategory, and_(JobCategory.job_id == Job.id, JobCategory.category == category))
        .where(
            Job.id != job.id, Job.salary_min.is_not(None), Job.salary_currency == "IRT",
            Job.first_seen_at >= since, Job.seniority == seniority,
            or_(Job.employment_type == job.employment_type, Job.employment_type.is_(None), job.employment_type is None),
        )
    )
    rows = db.execute(q).all()
    city_rows = [r for r in rows if job.city and r.city == job.city]
    use, scope = (city_rows, "same city") if len(city_rows) >= MIN_MARKET_SAMPLES else (rows, "all cities")
    if len(use) < MIN_MARKET_SAMPLES or seniority == "unknown":
        return None
    mids = sorted(((monthly(r.salary_min, r.salary_period) or 0) + (monthly(r.salary_max, r.salary_period) or 0)) / 2
                  for r in use)
    q1, med, q3 = statistics.quantiles(mids, n=4) if len(mids) >= 4 else (mids[0], statistics.median(mids), mids[-1])
    n = len(use)
    return {
        "status": "estimated", "min": int(q1), "max": int(q3), "median": int(med), "currency": "IRT",
        "period": "monthly", "method": "collected_reported_salaries",
        "source": "حقوق‌های اعلام‌شده در آگهی‌های جمع‌آوری‌شده همین سامانه (۱۸۰ روز اخیر)",
        "data_year": jalali_year(), "sample_size": n,
        "matched_on": {"category": category, "seniority": seniority, "scope": scope},
        "confidence": 0.7 if n >= 20 else 0.55 if n >= 10 else 0.4,
    }


def estimate(db: Session, job: Job) -> dict:
    if job.salary_min:
        lo, hi = monthly(job.salary_min, job.salary_period), monthly(job.salary_max or job.salary_min, job.salary_period)
        return {
            "status": "reported", "min": lo, "max": hi, "currency": job.salary_currency or "IRT", "period": "monthly",
            "original": job.salary_original, "method": "stated_in_ad", "confidence": 1.0,
        }
    category = _primary_category(job)
    reason = None
    if not category:
        reason = "آگهی در دسته‌های هدف نیست"
    elif job.seniority == "unknown":
        reason = "سطح ارشدیت مشخص نیست؛ تخمین قابل اتکا ممکن نیست"
    else:
        est = _from_dataset(db, category, job.seniority, job.city) or _from_market(db, job, category, job.seniority)
        if est:
            return est
        reason = "داده کافی (دیتاست معتبر یا حداقل ۵ نمونه مشابه) وجود ندارد"
    return {"status": "unknown", "reason": reason, "note": "نبودن حقوق در آگهی به معنای پایین بودن حقوق نیست."}


def apply_salary(db: Session, job: Job) -> None:
    est = estimate(db, job)
    job.salary_status = est["status"]
    job.salary_estimate = est
    job.effective_salary_min = est.get("min")
    job.effective_salary_max = est.get("max")
