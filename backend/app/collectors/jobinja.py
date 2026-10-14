"""jobinja.ir adapter.

Access (checked 2026-10-14, re-checked at the start of every run):
* robots.txt: `User-agent: *` / `Disallow:` (empty) / `Disallow: /style_guide/` -
  public pages may be crawled. No public API or feed is published; no sitemap.
* Discovery = the public keyword search `/jobs?filters[keywords][0]=<kw>&page=N`
  (the page states the total result count, used for coverage).
* Job pages carry schema.org JobPosting JSON-LD + an info box (location, contract
  type, experience, salary, skills). JSON-LD `baseSalary` is NOT trusted - it is
  filled even when the ad says "توافقی"; salary comes from the info box only.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import quote

from selectolax.parser import HTMLParser

from app.collectors.base import Candidate, Discovery, PageOutcome, RawJob, SourceAdapter
from app.collectors.http import FetchResult, PoliteClient
from app.pipeline.normalize import (
    canonical_url,
    html_to_text,
    normalize_text,
    parse_salary_text,
    split_location,
    to_ascii_digits,
)

SEARCH_URL = "https://jobinja.ir/jobs?filters%5Bkeywords%5D%5B0%5D={kw}&page={page}"
_JOB_LINK = re.compile(r'href="(https://jobinja\.ir/companies/([^/"]+)/jobs/([A-Za-z0-9]+)/[^"?]*)')
_TOTAL = re.compile(r"([\d۰-۹,٬]+)\s*فرصت\s*‌?\s*شغلی")

DEFAULT_KEYWORDS = [
    "devops", "دواپس", "sre", "kubernetes", "linux", "platform engineer", "cloud engineer", "observability",
    "python", "پایتون", "django", "fastapi", "machine learning", "یادگیری ماشین", "هوش مصنوعی", "deep learning",
    "llm", "nlp", "computer vision", "mlops", "data engineer", "مهندس داده",
]

EMPLOYMENT = {
    "تمام وقت": "full_time", "پاره وقت": "part_time", "قراردادی": "contract", "پروژه ای": "contract",
    "کارآموزی": "internship", "FULL_TIME": "full_time", "PART_TIME": "part_time", "CONTRACTOR": "contract",
    "INTERN": "internship",
}
EXPIRED_MARKERS = ("این آگهی منقضی شده", "آگهی منقضی شده است", "مهلت ارسال رزومه", "c-jobView__expired",
                   "این آگهی غیرفعال")


def _total(html: str) -> int | None:
    m = _TOTAL.search(html)
    if not m:
        return None
    try:
        return int(to_ascii_digits(m.group(1)).replace(",", "").replace("٬", ""))
    except ValueError:
        return None


class JobinjaAdapter(SourceAdapter):
    key = "jobinja"
    name = "Jobinja (جابینجا)"
    host = "jobinja.ir"
    base_url = "https://jobinja.ir"
    min_interval_minutes = 120
    access_method = (
        "Public keyword search pages (robots.txt allows all paths except /style_guide/) + public job pages "
        "with schema.org JobPosting JSON-LD and the info box. No official API/feed is published."
    )
    limitations = (
        "No sitemap: coverage = the configured search keywords x pages per keyword. Ads that match none of the "
        "keywords are not seen. Salary is taken from the info box only (JSON-LD baseSalary is unreliable)."
    )
    default_config = {"keywords": DEFAULT_KEYWORDS, "max_pages_per_keyword": 5}

    def job_url(self, source_job_id: str, canonical_url: str) -> str:
        return canonical_url

    def discover(self, client: PoliteClient, config: dict, state: dict) -> Discovery:
        cfg = {**self.default_config, **(config or {})}
        seen: dict[str, Candidate] = {}
        errors: list[str] = []
        totals: list[str] = []
        listed_total = 0
        for kw in cfg["keywords"]:
            kw_total = None
            for page in range(1, int(cfg["max_pages_per_keyword"]) + 1):
                url = SEARCH_URL.format(kw=quote(kw), page=page)
                try:
                    res = client.get(url)
                except Exception as exc:
                    errors.append(f"search '{kw}' p{page}: {exc}")
                    break
                if res.status >= 400:
                    errors.append(f"search '{kw}' p{page}: HTTP {res.status}")
                    break
                if kw_total is None:
                    kw_total = _total(res.text)
                links = _JOB_LINK.findall(res.text)
                if not links:
                    break
                for full, _company, code in links:
                    seen.setdefault(code, Candidate(code, canonical_url(full)))
                if kw_total is not None and page * 20 >= kw_total:
                    break
            if kw_total is not None:
                listed_total += kw_total
                totals.append(f"{kw}: {kw_total}")
        note = (
            f"search results reported by jobinja (sum over keywords, overlapping): {listed_total}; "
            f"unique ads collected from up to {cfg['max_pages_per_keyword']} pages/keyword: {len(seen)}. "
            + "; ".join(totals)
        )
        return Discovery(list(seen.values()), listed_total, note, errors)

    def parse_job(self, page: FetchResult) -> PageOutcome:
        if page.status in (404, 410):
            return PageOutcome("gone")
        if page.status >= 400:
            raise RuntimeError(f"HTTP {page.status}")
        tree = HTMLParser(page.text)
        ld = None
        for node in tree.css('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.text())
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                ld = data
                break
        m = re.search(r"/companies/([^/]+)/jobs/([A-Za-z0-9]+)", page.final_url or page.url)
        if ld is None or not m:
            return PageOutcome("not_job")
        company_slug, code = m.group(1), m.group(2)

        info: dict[str, list[str]] = {}
        for item in tree.css("li.c-infoBox__item"):
            title_node = item.css_first(".c-infoBox__itemTitle")
            if title_node is None:
                continue
            title = normalize_text(title_node.text())
            values = [normalize_text(t.text()) for t in item.css(".tags span")]
            info[title] = [v for v in values if v]

        def first(key: str) -> str | None:
            vals = info.get(key) or []
            return vals[0] if vals else None

        province, city = split_location(first("موقعیت مکانی"))
        employment_raw = first("نوع همکاری")
        employment = EMPLOYMENT.get(employment_raw or "") or EMPLOYMENT.get(str(ld.get("employmentType", "")))
        work_mode = "remote" if ld.get("jobLocationType") == "TELECOMMUTE" or (
            employment_raw and "دورکاری" in employment_raw) else None

        salary_text = first("حقوق")
        salary = parse_salary_text(salary_text)

        header = tree.css_first(".c-companyHeader__meta")
        industry = size = website = None
        if header is not None:
            for span in header.css(".c-companyHeader__metaItem"):
                txt = normalize_text(span.text())
                if not txt:
                    continue
                if span.css_first("a.c-companyHeader__metaLink") and "company/list" in (
                    span.css_first("a").attributes.get("href") or ""
                ):
                    industry = txt
                elif re.search(r"نفر", txt):
                    size = txt
                elif re.search(r"\.[a-z]{2,}", txt, re.I):
                    website = txt
        org = ld.get("hiringOrganization") or {}
        published = None
        if ld.get("datePosted"):
            try:
                published = datetime.fromisoformat(ld["datePosted"]).replace(tzinfo=UTC)
            except ValueError:
                published = None

        expired = any(mk in page.text for mk in EXPIRED_MARKERS)
        job = RawJob(
            source_job_id=code,
            canonical_url=canonical_url(page.final_url or page.url),
            title=normalize_text(ld.get("title")),
            company_name=normalize_text(org.get("name")) or None,
            company_profile_url=f"https://jobinja.ir/companies/{company_slug}",
            company_website=website or org.get("sameAs") or None,
            company_size=size,
            company_industry=industry,
            company_logo_url=org.get("logo"),
            city=city,
            province=province,
            work_mode=work_mode,
            employment_type=employment,
            experience_required=first("حداقل سابقه کار"),
            required_skills=info.get("مهارت‌های مورد نیاز", []),
            description=html_to_text(ld.get("description")),
            benefits=info.get("مزایا", []),
            salary_original=salary_text,
            salary_min=salary["min"] if salary else None,
            salary_max=salary["max"] if salary else None,
            salary_currency=salary["currency"] if salary else None,
            salary_period=salary["period"] if salary else None,
            published_at=published,
            source_categories=info.get("دسته‌بندی شغلی", []),
            is_expired=expired,
            extra={
                "gender": first("جنسیت"),
                "military": first("وضعیت نظام وظیفه"),
                "education": first("حداقل مدرک تحصیلی"),
                "parser": "json-ld+infobox",
            },
        )
        return PageOutcome("expired" if expired else "active", job)
