"""Analysis pipeline, independent from the collector.

rules (always) -> optional LLM refinement -> merge -> persist (job_analyses,
job_categories, job_skills, denormalised job columns).
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import settings_store
from app.ai.providers import PROMPT_VERSION, ClaudeProvider, OllamaProvider, ProviderError
from app.models import Job, JobAnalysis, JobCategory, JobSkill
from app.pipeline import rules
from app.pipeline import taxonomy as tx
from app.pipeline.normalize import compare_key, stable_hash
from app.pipeline.salary import apply_salary
from app.schemas_ai import AnalysisResult, CategoryVerdict, LLMAnalysis, RedFlag, SeniorityVerdict, SkillItem

log = structlog.get_logger()


def job_text(job: Job) -> str:
    parts = [f"Title: {job.title}"]
    if job.company_name:
        parts.append(f"Company: {job.company_name}")
    loc = " / ".join(x for x in (job.province, job.city) if x)
    if loc:
        parts.append(f"Location: {loc}")
    if job.employment_type:
        parts.append(f"Employment type: {job.employment_type}")
    if job.experience_required:
        parts.append(f"Experience: {job.experience_required}")
    if job.required_skills:
        parts.append("Listed skills: " + ", ".join(job.required_skills))
    if job.salary_original:
        parts.append(f"Salary: {job.salary_original}")
    parts.append("Description:\n" + (job.description or "")[:12000])
    return "\n".join(parts)


def get_provider(db: Session):
    """Configured LLM provider, or None when AI is disabled / not configured."""
    if not settings_store.get(db, "ai.enabled"):
        return None
    provider = settings_store.get(db, "ai.provider")
    if provider == "ollama":
        return OllamaProvider(settings_store.get(db, "ai.ollama_base_url"), settings_store.get(db, "ai.ollama_model"))
    key = settings_store.get(db, "ai.anthropic_api_key")
    if not key:
        return None
    return ClaudeProvider(key, settings_store.get(db, "ai.model"), settings_store.get(db, "ai.effort") or "low")


def _quote_ok(quote: str, haystack_key: str) -> bool:
    q = compare_key(quote)
    return bool(q) and q in haystack_key


def merge(base: AnalysisResult, llm: LLMAnalysis, source_text: str, engine: str, model: str) -> AnalysisResult:
    """LLM output wins where it brings verifiable evidence; unverifiable items are dropped."""
    hay = compare_key(source_text)
    notes: list[str] = []

    cats: list[CategoryVerdict] = []
    if llm.is_relevant_tech_role:
        for c in llm.categories:
            if not _quote_ok(c.evidence_quote, hay):
                notes.append(f"دسته {c.category} حذف شد: شاهد در متن آگهی یافت نشد")
                continue
            cats.append(CategoryVerdict(category=c.category, subcategory=c.subcategory,
                                        confidence=round(min(max(c.confidence, 0), 1), 2),
                                        evidence=[f"«{c.evidence_quote}»"]))
    elif base.categories:
        notes.append("مدل این آگهی را نقش فنی مرتبط تشخیص نداد")
    # keep deterministic title matches the model missed - they carry their own evidence
    have = {c.category for c in cats}
    if llm.is_relevant_tech_role:
        cats += [c for c in base.categories if c.category not in have and c.confidence >= 0.85]
    cats.sort(key=lambda c: c.confidence, reverse=True)
    for i, c in enumerate(cats):
        c.primary = i == 0

    skills = {s.name: s for s in base.skills}
    for s in llm.skills:
        if not _quote_ok(s.evidence_quote, hay):
            continue
        name = tx.canonical_skill(s.name) or s.name.strip()
        if name not in skills:
            skills[name] = SkillItem(name=name, required=s.required, evidence=s.evidence_quote, origin="llm")

    sen = base.seniority
    if llm.seniority.level != "unknown" and _quote_ok(llm.seniority.evidence_quote, hay):
        sen = SeniorityVerdict(level=llm.seniority.level, confidence=round(min(max(llm.seniority.confidence, 0), 1), 2),
                               evidence=[f"«{llm.seniority.evidence_quote}»"] + base.seniority.evidence,
                               years_min=base.seniority.years_min)

    flags = list(base.red_flags)
    codes = {f.code for f in flags}
    for f in llm.red_flags:
        if f.code not in codes and _quote_ok(f.evidence_quote, hay):
            flags.append(RedFlag(code=f.code, message=f.message_fa, evidence=f"«{f.evidence_quote}»"))
            codes.add(f.code)

    return AnalysisResult(
        categories=cats, skills=list(skills.values()), seniority=sen, quality=base.quality, red_flags=flags,
        summary_fa=llm.summary_fa.strip() or base.summary_fa, engine=engine, model=model, llm_notes=notes,
    )


def persist(db: Session, job: Job, result: AnalysisResult, input_hash: str, error: str | None = None) -> JobAnalysis:
    db.execute(update(JobAnalysis).where(JobAnalysis.job_id == job.id).values(is_current=False))
    row = JobAnalysis(
        job_id=job.id, engine=result.engine, model=result.model, input_hash=input_hash,
        result=result.model_dump(mode="json"), quality_score=result.quality.total,
        seniority=result.seniority.level, seniority_confidence=result.seniority.confidence,
        is_current=True, error=error,
    )
    db.add(row)
    job.categories.clear()
    job.skills.clear()
    db.flush()
    for c in result.categories:
        job.categories.append(JobCategory(category=c.category, subcategory=c.subcategory, confidence=c.confidence,
                                          is_primary=c.primary, method=result.engine, evidence=c.evidence))
    for s in result.skills:
        job.skills.append(JobSkill(skill=s.name[:80], skill_type="required" if s.required else "optional",
                                   origin=s.origin))
    job.is_relevant = bool(result.categories)
    job.seniority = result.seniority.level
    job.quality_score = result.quality.total
    if result.seniority.years_min is not None:
        job.experience_min_years = result.seniority.years_min
    apply_salary(db, job)
    return row


def analysis_input_hash(job: Job, engine: str, model: str | None) -> str:
    version = rules.RULES_VERSION if engine == "rules" else PROMPT_VERSION
    return stable_hash([job.content_hash, engine, model or "", version])


def analyze_job(db: Session, job: Job, *, use_llm: bool = True, force: bool = False) -> JobAnalysis | None:
    """Rules always; LLM when enabled. Returns the new current analysis (None = unchanged)."""
    base = rules.analyze(job)
    provider = get_provider(db) if use_llm else None
    engine = provider.name if provider else "rules"
    model = getattr(provider, "model", None)
    h = analysis_input_hash(job, engine, model)
    if not force:
        current = db.scalar(select(JobAnalysis).where(JobAnalysis.job_id == job.id, JobAnalysis.is_current))
        if current and current.input_hash == h and not current.error:
            return None
    if provider is None:
        return persist(db, job, base, h)
    try:
        llm = provider.analyze(job_text(job))
    except (ProviderError, ValueError) as exc:
        log.warning("llm_analysis_failed", job_id=job.id, error=str(exc))
        # Keep the deterministic analysis; record the failure so Sync can retry it.
        base.llm_notes.append(f"تحلیل مدل انجام نشد: {exc}")
        return persist(db, job, base, analysis_input_hash(job, "rules", None), error=str(exc))
    merged = merge(base, llm, job_text(job), engine, model or "")
    return persist(db, job, merged, h)


def pending_llm_jobs(db: Session, limit: int = 200) -> list[int]:
    """Relevant jobs whose current analysis is not from the configured LLM (or failed / outdated)."""
    provider = get_provider(db)
    if provider is None:
        return []
    engine, model = provider.name, provider.model
    rows = db.execute(
        select(Job.id, Job.content_hash, JobAnalysis.input_hash, JobAnalysis.error)
        .outerjoin(JobAnalysis, (JobAnalysis.job_id == Job.id) & JobAnalysis.is_current)
        .where(Job.is_relevant, Job.status == "active")
        .order_by(Job.first_seen_at.desc())
    ).all()
    out = []
    for job_id, content_hash, input_hash, error in rows:
        want = stable_hash([content_hash, engine, model or "", PROMPT_VERSION])
        if input_hash != want or error:
            out.append(job_id)
        if len(out) >= limit:
            break
    return out


def now() -> datetime:
    return datetime.now(UTC)
