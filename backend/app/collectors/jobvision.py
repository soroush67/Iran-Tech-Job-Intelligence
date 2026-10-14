"""jobvision.ir adapter.

Access (checked 2026-10-14, re-checked at the start of every run):
* robots.txt: `disallow: *?*`, `*utm_*`, `*/Login/*`; sitemaps advertised.
* candidateapi.jobvision.ir (the JSON API the site uses) has `Disallow: /` -> NOT used.
* Discovery = the advertised sitemap (`/sitemap/jobposts.xml`, URL + lastmod for
  every live ad). Job pages `/jobs/<id>/<slug>` are allowed; they are server-side
  rendered and embed the job (Angular `ng-state` transfer state) which we parse.
* JSON-LD `baseSalary` is NOT trusted (a placeholder on ads without salary).
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

from selectolax.parser import HTMLParser

from app.collectors.base import Candidate, Discovery, PageOutcome, RawJob, SourceAdapter
from app.collectors.http import FetchResult, PoliteClient
from app.pipeline.normalize import canonical_url, html_to_text, normalize_text

SITEMAP_INDEX = "https://jobvision.ir/sitemap.xml"
_URL_RE = re.compile(
    r"<url>\s*<loc>(https://jobvision\.ir/jobs/(\d+)/[^<]*)</loc>\s*(?:<lastmod>([^<]+)</lastmod>)?"
)

DEFAULT_SLUG_KEYWORDS = [
    "devops", "دواپس", "دوآپس", "sre", "site-reliability", "reliability", "platform-engineer", "kubernetes",
    "کوبرنتیز", "cloud", "کلاد", "linux", "لینوکس", "زیرساخت", "infrastructure", "observability", "monitoring",
    "مانیتورینگ", "python", "پایتون", "django", "جنگو", "fastapi", "flask", "backend", "بک-اند", "بکند",
    "machine-learning", "یادگیری-ماشین", "یادگیری-عمیق", "deep-learning", "هوش-مصنوعی", "ai-", "-ai",
    "llm", "nlp", "پردازش-زبان", "computer-vision", "بینایی-ماشین", "mlops", "llmops", "data-engineer",
    "مهندس-داده", "data-scientist", "دانشمند-داده", "علم-داده", "داده-کاوی", "big-data", "automation",
    "اتوماسیون", "gitops", "ansible", "terraform",
]

WORK_TYPES = {
    "full time": "full_time", "part time": "part_time", "contractual": "contract", "project based": "contract",
    "internship": "internship", "تمام وقت": "full_time", "پاره وقت": "part_time", "قراردادی": "contract",
    "پروژه ای": "contract", "کارآموزی": "internship",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _t(obj, lang="titleFa") -> str | None:
    if not isinstance(obj, dict):
        return None
    val = obj.get(lang) or obj.get("titleEn" if lang == "titleFa" else "titleFa") or obj.get("title")
    val = normalize_text(val) if isinstance(val, str) else None
    return val or None


def _find_job(state) -> dict | None:
    if isinstance(state, dict):
        for key, val in state.items():
            if "JobPost/Detail" in key:
                node = val
                for _ in range(3):
                    if isinstance(node, dict) and "workType" in node and "title" in node:
                        return node
                    if isinstance(node, dict):
                        node = node.get("b") or node.get("body") or node.get("data") or node.get("result")
                return None
    return None


class JobvisionAdapter(SourceAdapter):
    key = "jobvision"
    name = "JobVision (جاب‌ویژن)"
    host = "jobvision.ir"
    base_url = "https://jobvision.ir"
    min_interval_minutes = 120
    complete_listing = True
    access_method = (
        "Sitemap (/sitemap/jobposts.xml, advertised in robots.txt) + public job pages /jobs/<id>/<slug>, "
        "parsing the job data the server embeds in the page. The JSON API host candidateapi.jobvision.ir "
        "is disallowed by its robots.txt and is not used."
    )
    limitations = (
        "Coverage = sitemap entries whose URL slug matches tech keywords, within the age window, capped per run. "
        "Ads whose title (slug) does not contain any keyword are not fetched. URLs with '?' are disallowed, "
        "so search/filter pages are never used. JSON-LD baseSalary is a placeholder and is ignored."
    )
    default_config = {"max_age_days": 45, "slug_keywords": DEFAULT_SLUG_KEYWORDS}

    def job_url(self, source_job_id: str, canonical_url: str) -> str:
        return canonical_url or f"https://jobvision.ir/jobs/{source_job_id}"

    def discover(self, client: PoliteClient, config: dict, state: dict) -> Discovery:
        cfg = {**self.default_config, **(config or {})}
        errors: list[str] = []
        index = client.get(SITEMAP_INDEX)
        text = _decode(index)
        maps = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
        job_maps = [m for m in maps if "jobposts" in m] or ["https://jobvision.ir/sitemap/jobposts.xml"]
        cutoff = datetime.now(UTC) - timedelta(days=int(cfg["max_age_days"]))
        kw = [k.lower() for k in cfg["slug_keywords"]]
        listed = 0
        seen: dict[str, Candidate] = {}
        all_ids: set[str] = set()
        for sm in job_maps:
            try:
                page = client.get(sm)
            except Exception as exc:  # one sitemap failing must not kill the run
                errors.append(f"sitemap {sm}: {exc}")
                continue
            for url, job_id, lastmod in _URL_RE.findall(_decode(page)):
                all_ids.add(job_id)
                lm = _parse_dt(lastmod)
                if lm and lm < cutoff:
                    continue
                listed += 1
                slug = unquote(url.split("/", 5)[-1]).lower()
                if not any(k in slug for k in kw):
                    continue
                if job_id not in seen or (lm and seen[job_id].lastmod and lm > seen[job_id].lastmod):
                    seen[job_id] = Candidate(job_id, url, lm, slug.replace("-", " "))
        cands = sorted(seen.values(), key=lambda c: c.lastmod or datetime.min.replace(tzinfo=UTC), reverse=True)
        note = (
            f"sitemap: {listed} ads updated in the last {cfg['max_age_days']} days; "
            f"{len(cands)} match the tech keyword filter on the URL slug"
        )
        return Discovery(cands, listed, note, errors, all_ids if not errors else None)

    def parse_job(self, page: FetchResult) -> PageOutcome:
        if page.status in (404, 410):
            return PageOutcome("gone")
        if page.status >= 400:
            raise RuntimeError(f"HTTP {page.status}")
        tree = HTMLParser(page.text)
        state_node = tree.css_first("script#ng-state")
        job = None
        if state_node is not None:
            try:
                job = _find_job(json.loads(state_node.text()))
            except json.JSONDecodeError:
                job = None
        if job is None:
            return self._from_jsonld(tree, page)
        return PageOutcome("expired" if job.get("isExpired") else "active", self._from_state(job, page))

    def _from_state(self, j: dict, page: FetchResult) -> RawJob:
        company = j.get("company") or {}
        loc = j.get("location") or {}
        salary = j.get("salary") or None
        smin = smax = None
        sal_text = None
        if isinstance(salary, dict) and (salary.get("min") or salary.get("max")):
            sal_text = _t(salary)
            unit = 1_000_000  # jobvision ranges are "N - M میلیون تومان"
            smin = int(float(salary.get("min") or salary.get("max")) * unit)
            smax = int(float(salary.get("max") or salary.get("min")) * unit)
        req, opt = [], []
        for item in j.get("softwareRequirements") or []:
            name = _t(item.get("software"), "titleEn")
            if name:
                req.append(name)
        for item in j.get("skills") or []:
            name = _t(item.get("skill") if isinstance(item.get("skill"), dict) else item, "titleEn")
            if name:
                opt.append(name)
        work_type = (_t(j.get("workType"), "titleEn") or "").lower()
        exp = j.get("requiredRelatedExperienceYears")
        industries = company.get("industries") or []
        url = canonical_url(page.final_url or page.url)
        profile = company.get("companyLink")
        return RawJob(
            source_job_id=str(j.get("id")),
            canonical_url=url,
            title=normalize_text(j.get("title")),
            company_name=_t(company.get("name")),
            company_profile_url=f"https://jobvision.ir{profile}" if profile else None,
            company_website=company.get("website") or None,
            company_size=_t(company.get("size")),
            company_industry=_t(industries[0]) if industries else None,
            company_description=_t(company.get("description")),
            company_logo_url=company.get("logoUrl"),
            city=_t(loc.get("city")),
            province=_t(loc.get("province")),
            work_mode="remote" if j.get("isRemote") else None,
            employment_type="internship" if j.get("isInternship") else WORK_TYPES.get(work_type),
            seniority_hint=_t(j.get("seniorityLevel"), "titleEn"),
            experience_required=f"{exp} سال" if exp else None,
            required_skills=req,
            optional_skills=opt,
            description=html_to_text(j.get("description")),
            benefits=[b for b in (_t(x) for x in j.get("benefits") or []) if b],
            salary_original=sal_text,
            salary_min=smin,
            salary_max=smax,
            salary_currency="IRT" if smin else None,
            salary_period="monthly" if smin else None,
            published_at=_parse_dt((j.get("firstActivationTime") or {}).get("date")),
            expires_at=_parse_dt((j.get("expireTime") or {}).get("date")),
            source_categories=[c for c in (_t(x, "titleEn") for x in j.get("jobCategories") or []) if c],
            is_expired=bool(j.get("isExpired")),
            extra={
                "work_days": j.get("workDays"),
                "is_urgent": j.get("isUrgent"),
                "company_establishment_year": company.get("establishmentYear"),
                "company_type": _t(company.get("companyType")),
                "company_is_governmental": company.get("isGovernmentalCompany"),
                "parser": "ng-state",
            },
        )

    def _from_jsonld(self, tree: HTMLParser, page: FetchResult) -> PageOutcome:
        node = tree.css_first('script[type="application/ld+json"]')
        if node is None:
            return PageOutcome("not_job")
        try:
            d = json.loads(node.text())
        except json.JSONDecodeError:
            return PageOutcome("not_job")
        if d.get("@type") != "JobPosting":
            return PageOutcome("not_job")
        m = re.search(r"/jobs/(\d+)", page.final_url or page.url)
        if not m:
            return PageOutcome("not_job")
        addr = ((d.get("jobLocation") or {}).get("address")) or {}
        org = d.get("hiringOrganization") or {}
        expires = _parse_dt(d.get("validThrough"))
        job = RawJob(
            source_job_id=m.group(1),
            canonical_url=canonical_url(page.final_url or page.url),
            title=normalize_text(d.get("title")),
            company_name=normalize_text(org.get("name")) or None,
            company_website=org.get("sameAs") or None,
            province=normalize_text(addr.get("addressRegion")) or None,
            employment_type=WORK_TYPES.get(str(d.get("employmentType", "")).replace("-", " ").lower()),
            description=html_to_text(d.get("description")),
            benefits=[b.strip() for b in str(d.get("jobBenefits") or "").split(",") if b.strip()],
            published_at=_parse_dt(d.get("datePosted")),
            expires_at=expires,
            extra={"parser": "json-ld"},
        )
        expired = bool(expires and expires < datetime.now(UTC))
        return PageOutcome("expired" if expired else "active", job)


def _decode(page: FetchResult) -> str:
    raw = page.content
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")
