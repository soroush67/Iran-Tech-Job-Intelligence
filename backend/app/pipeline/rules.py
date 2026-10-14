"""Deterministic, explainable analysis. Always available - the LLM layer refines it.

Every function returns evidence (the snippet that triggered the decision) so the UI
can show *why*, and nothing is invented: unknown stays unknown.
"""
from __future__ import annotations

import re

from app.pipeline import taxonomy as tx
from app.pipeline.normalize import normalize_text, parse_experience_years
from app.schemas_ai import (
    AnalysisResult,
    CategoryVerdict,
    QualityCriterion,
    QualityScore,
    RedFlag,
    SeniorityVerdict,
    SkillItem,
)

SENIORITY_LEVELS = ("junior", "mid", "senior", "staff", "principal", "unknown")

# Bump when the rules change: existing jobs are re-analysed in the background.
RULES_VERSION = "2026-10-14.3"

# --- text sections --------------------------------------------------------------

_OPTIONAL_HEADING = re.compile(
    r"nice to have|is a plus|are a plus|bonus|preferred|امتیاز|مزیت محسوب|ترجیح|آشنایی با .* مزیت|اولویت با", re.I
)
_REQUIRED_HEADING = re.compile(
    r"requirements|qualifications|must have|what you need|skills|الزامات|شرایط احراز|نیازمندی|مهارت(\s|‌)?های (مورد نیاز|لازم|ضروری)|"
    r"شرایط (مورد نیاز|لازم)|توانایی(\s|‌)?ها|تسلط",
    re.I,
)
_RESP_HEADING = re.compile(r"responsibilit|what you will do|duties|role|شرح وظایف|وظایف|مسئولیت|شرح شغل|شرح موقعیت", re.I)
_BENEFIT_WORDS = {
    "بیمه": "بیمه", "بیمه تکمیلی": "بیمه تکمیلی", "وام": "وام", "ناهار": "ناهار", "پاداش": "پاداش",
    "بن": "بن", "سرویس": "سرویس رفت و آمد", "دورکاری": "امکان دورکاری", "ساعت کاری منعطف": "ساعت کاری منعطف",
    "آموزش": "دوره‌های آموزشی", "health insurance": "بیمه", "bonus": "پاداش", "flexible": "ساعت کاری منعطف",
    "remote": "امکان دورکاری", "lunch": "ناهار", "training": "دوره‌های آموزشی",
}


def split_skill_sections(text: str) -> tuple[str, str]:
    """Split description into (required-ish text, optional-ish text) by headings/markers."""
    req, opt = [], []
    mode = "req"
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) < 80 and _OPTIONAL_HEADING.search(stripped) and not re.search(r"[.:].{20,}", stripped):
            mode = "opt"
            continue
        if len(stripped) < 60 and (_REQUIRED_HEADING.search(stripped) or _RESP_HEADING.search(stripped)):
            mode = "req"
        if _OPTIONAL_HEADING.search(stripped):
            opt.append(stripped)  # single line "... is a plus"
            continue
        (opt if mode == "opt" else req).append(stripped)
    return "\n".join(req), "\n".join(opt)


def extract_skills(title: str, description: str, structured: list[str], structured_optional: list[str]) -> list[SkillItem]:
    items: dict[str, SkillItem] = {}
    for raw in structured:
        name = tx.canonical_skill(raw) or normalize_text(raw)
        if name and name not in items:
            items[name] = SkillItem(name=name, required=True, evidence=raw, origin="structured")
    for raw in structured_optional:
        name = tx.canonical_skill(raw) or normalize_text(raw)
        if name and name not in items:
            items[name] = SkillItem(name=name, required=False, evidence=raw, origin="structured")
    req_text, opt_text = split_skill_sections(description)
    for name, snippet in tx.find_skills(title + "\n" + req_text).items():
        items.setdefault(name, SkillItem(name=name, required=True, evidence=snippet, origin="extracted"))
    for name, snippet in tx.find_skills(opt_text).items():
        items.setdefault(name, SkillItem(name=name, required=False, evidence=snippet, origin="extracted"))
    return list(items.values())


def detect_work_mode(raw_mode: str | None, text: str) -> tuple[str | None, str | None]:
    if raw_mode:
        return raw_mode, "source field"
    t = text.lower()
    if m := re.search(r"هیبریدی|هیبرید|ترکیبی از حضوری و دورکاری|hybrid|نیمه\s?حضوری|دورکاری (پاره|بخشی)", t):
        return "hybrid", m.group(0)
    if m := re.search(r"(امکان )?دورکاری( کامل)?|remote|telecommut|کاملا غیرحضوری", t):
        if "امکان" in m.group(0):
            return "hybrid", m.group(0)
        return "remote", m.group(0)
    if m := re.search(r"حضوری|on[\s-]?site|in[\s-]office", t):
        return "onsite", m.group(0)
    return None, None


def extract_benefits(source_benefits: list[str], text: str) -> list[str]:
    if source_benefits:
        return source_benefits
    found = []
    low = text.lower()
    for word, label in _BENEFIT_WORDS.items():
        if re.search(rf"(?<![\w؀-ۿ]){re.escape(word)}(?![\w؀-ۿ])", low) and label not in found:
            found.append(label)
    return found


# --- classification ---------------------------------------------------------------

def classify(title: str, skills: list[SkillItem], description: str) -> list[CategoryVerdict]:
    t = normalize_text(title).lower().replace("‌", " ")
    verdicts: dict[str, CategoryVerdict] = {}
    negative = bool(tx.NEGATIVE_TITLE.search(t))
    for cat, sub, pattern, conf in tx.TITLE_RULES:
        m = re.search(pattern, t, re.I)
        if not m:
            continue
        c = conf * (0.4 if negative else 1.0)
        if cat not in verdicts or verdicts[cat].confidence < c:
            verdicts[cat] = CategoryVerdict(
                category=cat, subcategory=sub, confidence=round(c, 2),
                evidence=[f"عنوان: «{m.group(0)}»"] + (["عنوان شامل نقش غیرفنی است"] if negative else []),
            )

    # Description evidence: per-family skill counts (required skills weigh double).
    fam_score: dict[str, float] = {}
    fam_names: dict[str, list[str]] = {}
    for s in skills:
        fam = tx.SKILL_FAMILY.get(s.name)
        if fam in tx.DESCRIPTION_RULES:
            fam_score[fam] = fam_score.get(fam, 0) + (1.0 if s.required else 0.5)
            fam_names.setdefault(fam, []).append(s.name)
    # SRE tooling also counts toward DevOps and vice versa (they share most of the stack).
    if "sre" in fam_score:
        fam_score["devops"] = fam_score.get("devops", 0) + 0.5 * fam_score["sre"]

    generic = bool(tx.GENERIC_TECH_TITLE.search(t)) and not negative
    title_primary = any(v.confidence >= 0.5 for v in verdicts.values())
    for cat, (sub, need) in tx.DESCRIPTION_RULES.items():
        if cat in verdicts:
            continue
        score = fam_score.get(cat, 0)
        names = fam_names.get(cat, [])
        if title_primary:
            need += tx.SECONDARY_EXTRA  # a secondary category needs clearly more evidence
        if cat == "python":
            # Python as a *tool* of another role does not make the job a Python-development role.
            py_required = any(s.name == "Python" and s.required for s in skills)
            strong = py_required and generic and not verdicts and (score >= need or "Python" in names)
        elif cat == "sre":
            # Monitoring tools alone are everyday DevOps work; SRE needs a reliability practice signal.
            practice = {"SLO/SLI", "Incident Management"} & set(names) or re.search(
                r"site reliability|\bsre\b|reliability engineering|قابلیت اطمینان|error budget", description, re.I)
            strong = bool(practice) and score >= need and (generic or title_primary)
        else:
            strong = score >= need and (generic or title_primary)
        if strong:
            verdicts[cat] = CategoryVerdict(
                category=cat, subcategory=sub, confidence=0.5 if title_primary else 0.55,
                evidence=[f"مهارت‌های شرح شغل: {', '.join(names[:6])}"],
            )
    out = [v for v in verdicts.values() if v.confidence >= 0.45]
    out.sort(key=lambda v: v.confidence, reverse=True)
    if out:
        out[0].primary = True
    return out


# --- seniority ----------------------------------------------------------------------

_SENIORITY_TITLE = [
    ("principal", r"principal|distinguished"),
    ("staff", r"\bstaff\b"),
    ("senior", r"senior|\bsr\.?\b|ارشد|سنیور|lead|سرپرست|team lead|tech lead"),
    ("mid", r"mid[\s-]?level|\bmid\b|میانی|intermediate"),
    ("junior", r"junior|\bjr\.?\b|جونیور|تازه\s?کار|کارآموز|intern|entry level|مبتدی"),
]
_SOURCE_HINT = {
    "intern": "junior", "internship": "junior", "junior": "junior", "employee": "mid", "specialist": "mid",
    "senior specialist": "senior", "expert": "senior", "senior": "senior", "manager": "senior",
    "senior manager": "staff", "director": "principal",
}


def years_to_level(years: float) -> str:
    if years < 2:
        return "junior"
    if years < 5:
        return "mid"
    if years < 8:
        return "senior"
    return "staff"


def detect_seniority(title: str, experience: str | None, source_hint: str | None, description: str) -> SeniorityVerdict:
    t = normalize_text(title).lower()
    evidence: list[str] = []
    level = None
    conf = 0.0
    for lvl, pat in _SENIORITY_TITLE:
        m = re.search(pat, t, re.I)
        if m:
            level, conf = lvl, 0.85
            evidence.append(f"عنوان: «{m.group(0)}»")
            break
    years = parse_experience_years(experience)
    if years is None:
        m = re.search(r"(\d+)\+?\s*(?:years?|سال)\s*(?:of )?(?:experience|سابقه)|(?:حداقل|at least)\s*(\d+)\s*(?:سال|years?)", description, re.I)
        if m:
            years = float(m.group(1) or m.group(2))
            evidence.append(f"شرح: «{m.group(0)}»")
    elif experience:
        evidence.append(f"سابقه: «{experience}»")
    if years is not None:
        by_years = years_to_level(years)
        if level is None:
            level, conf = by_years, 0.6
        elif by_years == level:
            conf = 0.95
    hint = (source_hint or "").strip().lower()
    if level is None and hint in _SOURCE_HINT:
        level, conf = _SOURCE_HINT[hint], 0.5
        evidence.append(f"سطح اعلام‌شده منبع: «{source_hint}»")
    return SeniorityVerdict(level=level or "unknown", confidence=round(conf, 2), evidence=evidence, years_min=years)


# --- quality score -------------------------------------------------------------------

def quality_score(
    *, salary_min: int | None, salary_max: int | None, salary_original: str | None, description: str,
    benefits: list[str], employment_type: str | None, work_mode: str | None, work_hours: str | None,
    seniority: SeniorityVerdict, experience_required: str | None, skills: list[SkillItem],
    company_website: str | None, company_size: str | None, company_industry: str | None,
    company_description: str | None, red_flags: list[RedFlag],
) -> QualityScore:
    crit: list[QualityCriterion] = []

    # 1. salary transparency (25)
    if salary_min and salary_max and salary_max != salary_min:
        crit.append(QualityCriterion(key="salary", label="شفافیت حقوق", score=25, max=25, reason="بازه حقوق اعلام شده"))
    elif salary_min:
        crit.append(QualityCriterion(key="salary", label="شفافیت حقوق", score=20, max=25, reason="یک رقم حقوق اعلام شده"))
    else:
        why = "حقوق «توافقی» است" if salary_original else "حقوق اعلام نشده"
        crit.append(QualityCriterion(key="salary", label="شفافیت حقوق", score=0, max=25, reason=why))

    # 2. description clarity (20)
    n = len(description)
    base = 10 if n >= 1200 else 7 if n >= 600 else 4 if n >= 250 else 0
    has_resp = bool(_RESP_HEADING.search(description))
    has_req = bool(_REQUIRED_HEADING.search(description))
    score = min(20, base + (6 if has_resp else 0) + (4 if has_req else 0))
    crit.append(QualityCriterion(
        key="description", label="وضوح شرح وظایف", score=score, max=20,
        reason=f"{n} نویسه؛ بخش وظایف: {'دارد' if has_resp else 'ندارد'}؛ بخش الزامات: {'دارد' if has_req else 'ندارد'}",
    ))

    # 3. benefits & terms (15)
    s3 = (7 if len(benefits) >= 3 else 4 if benefits else 0) + (3 if employment_type else 0) + (2 if work_mode else 0) + (3 if work_hours else 0)
    crit.append(QualityCriterion(
        key="terms", label="شفافیت مزایا و شرایط همکاری", score=min(15, s3), max=15,
        reason=f"{len(benefits)} مزیت؛ نوع همکاری: {'مشخص' if employment_type else 'نامشخص'}؛ "
               f"شیوه کار: {'مشخص' if work_mode else 'نامشخص'}؛ ساعت کاری: {'مشخص' if work_hours else 'نامشخص'}",
    ))

    # 4. experience vs expectations (15)
    mismatch = any(f.code == "seniority_mismatch" for f in red_flags)
    s4 = (7 if (experience_required or seniority.years_min is not None) else 0)
    s4 += 0 if mismatch else (8 if seniority.level != "unknown" else 3)
    crit.append(QualityCriterion(
        key="experience", label="سازگاری سطح تجربه با انتظارات", score=s4, max=15,
        reason="ناسازگاری بین سطح و سابقه" if mismatch else
        f"سابقه: {experience_required or ('%g سال' % seniority.years_min if seniority.years_min is not None else 'نامشخص')}؛ سطح: {seniority.level}",
    ))

    # 5. technical skills (15)
    k = len({s.name for s in skills})
    s5 = 15 if k >= 6 else 11 if k >= 4 else 7 if k >= 2 else 3 if k == 1 else 0
    crit.append(QualityCriterion(key="skills", label="مشخص بودن مهارت‌های فنی", score=s5, max=15, reason=f"{k} مهارت مشخص"))

    # 6. employer info (10)
    s6 = (4 if company_website else 0) + (2 if company_size else 0) + (2 if company_industry else 0) + (
        2 if company_description and len(company_description) > 60 else 0)
    crit.append(QualityCriterion(
        key="employer", label="اطلاعات قابل بررسی درباره کارفرما", score=s6, max=10,
        reason=f"وب‌سایت: {'دارد' if company_website else 'ندارد'}؛ اندازه: {'دارد' if company_size else 'ندارد'}؛ "
               f"حوزه فعالیت: {'دارد' if company_industry else 'ندارد'}",
    ))
    return QualityScore(total=sum(c.score for c in crit), criteria=crit)


# --- red flags ------------------------------------------------------------------------

def red_flags(
    *, title: str, description: str, skills: list[SkillItem], seniority: SeniorityVerdict,
    employment_type: str | None, salary_min: int | None, benefits: list[str], categories: list[CategoryVerdict],
) -> list[RedFlag]:
    flags: list[RedFlag] = []
    if len(description) < 250:
        flags.append(RedFlag(code="vague_description", message="شرح شغل بسیار کوتاه یا مبهم است",
                             evidence=f"طول شرح: {len(description)} نویسه"))
    fams = {tx.SKILL_FAMILY.get(s.name) for s in skills if s.required} - {None, "general"}
    if len(fams) >= 5 or len(skills) >= 22:
        flags.append(RedFlag(code="skill_sprawl", message="مجموعه مهارت‌های درخواستی بیش از حد گسترده یا نامتناسب است",
                             evidence=f"{len(skills)} مهارت از {len(fams)} حوزه: {', '.join(sorted(fams))}"))
    if not employment_type and not salary_min and not benefits:
        flags.append(RedFlag(code="missing_terms", message="شرایط استخدام (نوع همکاری، حقوق، مزایا) مشخص نشده",
                             evidence="هیچ‌کدام از نوع همکاری/حقوق/مزایا در آگهی نیست"))
    y = seniority.years_min
    t = normalize_text(title).lower()
    if y is not None:
        if re.search(r"junior|جونیور|کارآموز|intern|تازه\s?کار", t) and y >= 4:
            flags.append(RedFlag(code="seniority_mismatch", message="عنوان سطح پایه است ولی سابقه زیاد خواسته شده",
                                 evidence=f"عنوان «{title}» با {y:g} سال سابقه"))
        if re.search(r"senior|ارشد|lead|سرپرست|principal|staff", t) and y <= 1:
            flags.append(RedFlag(code="seniority_mismatch", message="عنوان ارشد است ولی سابقه بسیار کم خواسته شده",
                                 evidence=f"عنوان «{title}» با {y:g} سال سابقه"))
    if m := re.search(r"بدون حقوق|دوره آزمایشی (رایگان|بدون حقوق)|unpaid|پروژه آزمایشی رایگان|حقوق پس از", description, re.I):
        flags.append(RedFlag(code="unpaid_work", message="اشاره به کار یا دوره آزمایشی بدون پرداخت",
                             evidence=f"«{m.group(0)}»"))
    cat_keys = {c.category for c in categories}
    if cat_keys & {"devops", "sre"}:
        if m := re.search(r"دوربین مدار\s?بسته|پرینتر|printer|پشتیبانی کاربران|helpdesk|help desk|تعمیر سخت\s?افزار|کابل\s?کشی", description, re.I):
            flags.append(RedFlag(code="unrelated_duties", message="مسئولیت‌هایی خارج از حوزه DevOps/SRE در شرح وظایف آمده",
                                 evidence=f"«{m.group(0)}»"))
    return flags


def summary_fa(categories: list[CategoryVerdict], seniority: SeniorityVerdict, skills: list[SkillItem]) -> str:
    cats = "، ".join(tx.CATEGORY_LABELS_FA[c.category] + (f" ({c.subcategory})" if c.subcategory else "") for c in categories) or "خارج از دسته‌های هدف"
    lvl = {"junior": "Junior", "mid": "Mid-Level", "senior": "Senior", "staff": "Staff", "principal": "Principal"}.get(seniority.level, "نامشخص")
    top = ", ".join([s.name for s in skills if s.required][:8])
    return f"دسته: {cats} | سطح: {lvl}" + (f" | مهارت‌های اصلی: {top}" if top else "")


def analyze(job) -> AnalysisResult:
    """job: a Job ORM row (or anything with the same attributes)."""
    text = job.description or ""
    skills = extract_skills(job.title, text, list(job.required_skills or []), list(job.optional_skills or []))
    categories = classify(job.title, skills, text)
    seniority = detect_seniority(job.title, job.experience_required, (job.extra or {}).get("seniority_hint"), text)
    flags = red_flags(
        title=job.title, description=text, skills=skills, seniority=seniority, employment_type=job.employment_type,
        salary_min=job.salary_min, benefits=list(job.benefits or []), categories=categories,
    )
    company = job.company
    quality = quality_score(
        salary_min=job.salary_min, salary_max=job.salary_max, salary_original=job.salary_original, description=text,
        benefits=list(job.benefits or []), employment_type=job.employment_type, work_mode=job.work_mode,
        work_hours=(job.extra or {}).get("work_days"), seniority=seniority, experience_required=job.experience_required,
        skills=skills, company_website=company.website if company else None,
        company_size=company.size if company else None, company_industry=company.industry if company else None,
        company_description=company.description if company else None, red_flags=flags,
    )
    return AnalysisResult(
        categories=categories, skills=skills, seniority=seniority, quality=quality, red_flags=flags,
        summary_fa=summary_fa(categories, seniority, skills), engine="rules",
    )
