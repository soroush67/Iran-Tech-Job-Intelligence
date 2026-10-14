"""Synthetic pages that reproduce the *structure* of the real sources (verified
against live pages on 2026-10-14) with invented companies and ads. Test data
only - never presented as real job ads."""
from __future__ import annotations

import html
import json

JOBINJA_ROBOTS = "User-agent: *\nDisallow:\nDisallow: /style_guide/\n"
JOBVISION_ROBOTS = (
    "user-agent: *\ndisallow: *?*\ndisallow: *utm_*\ndisallow: */Login/*\nAllow: *.js\nAllow: *.css\n\n"
    "Sitemap: https://jobvision.ir/sitemap.xml\n"
)


def jobinja_search(links: list[tuple[str, str, str]], total: int) -> str:
    """links: (company_slug, code, title)"""
    items = "".join(
        f'<li class="o-listView__item c-jobListView__item"><a class="c-jobListView__titleLink" '
        f'href="https://jobinja.ir/companies/{c}/jobs/{code}/%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85-x?_ref=16&amp;_t=abc">'
        f"{html.escape(t)}</a></li>"
        for c, code, t in links
    )
    return (f'<html><body><div class="c-jobSearchState__numberOfResultsEcho"> {total:,} فرصت ‌شغلی </div>'
            f'<ul class="o-listView">{items}</ul></body></html>')


def jobinja_job(*, code="tAbC", company_slug="sample-co", title="مهندس DevOps (DevOps Engineer)",
                company="شرکت نمونه آزمایشی", description_html="<p>شرح وظایف</p>", location="تهران ، تهران",
                employment="تمام وقت", experience="سه تا شش سال", salary="توافقی",
                skills=("Docker", "Kubernetes", "Linux"), website="sample-test.example", size="۵۱ - ۲۰۰ نفر",
                industry="فناوری اطلاعات", telecommute=False, ld_salary=5000000, expired=False) -> str:
    ld = {
        "@context": "http://schema.org", "@type": "JobPosting", "datePosted": "2026-10-01",
        "description": description_html, "title": title,
        "hiringOrganization": {"@type": "Organization", "name": company, "sameAs": f"http://{website}"},
        # the real site fills baseSalary even when the info box says توافقی
        "baseSalary": {"@type": "MonetaryAmount", "currency": "IRT", "value": ld_salary, "unitText": "MONTH"},
        "employmentType": "FULL_TIME", "jobLocationType": "TELECOMMUTE" if telecommute else "",
    }
    skill_tags = "".join(f'<span class="black">{html.escape(s)}</span>' for s in skills)
    box = [("دسته‌بندی شغلی", '<span class="black">وب،&zwnj; برنامه&zwnj;نویسی و نرم&zwnj;افزار</span>'),
           ("موقعیت مکانی", f'<span class="black">{location}</span>'),
           ("نوع همکاری", f'<span class="black">{employment}</span>'),
           ("حداقل سابقه کار", f'<span class="black">{experience}</span>'),
           ("حقوق", f'<span class="black">{salary}</span>'),
           ("مهارت‌های مورد نیاز", skill_tags)]
    lis = "".join(f'<li class="c-infoBox__item"><h4 class="c-infoBox__itemTitle">{t}</h4><div class="tags">{v}</div></li>'
                  for t, v in box)
    exp = '<div class="c-jobView__expired">این آگهی منقضی شده است</div>' if expired else ""
    return f"""<!DOCTYPE html><html><head>
<link rel="canonical" href="https://jobinja.ir/companies/{company_slug}/jobs/{code}/x"/>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head><body>
<div class="c-companyHeader__meta">
<span class="c-companyHeader__metaItem"><a class="c-companyHeader__metaLink" href="https://jobinja.ir/company/list/it">{industry}</a></span>
<span class="c-companyHeader__metaItem">{size}</span>
<span class="c-companyHeader__metaItem"><a class="c-companyHeader__metaLink" href="http://{website}">{website}</a></span>
</div>{exp}
<ul class="c-jobView__firstInfoBox c-infoBox">{lis}</ul></body></html>"""


def jobvision_sitemap_index() -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<sitemap><loc>https://jobvision.ir/sitemap/jobposts.xml</loc></sitemap></sitemapindex>")


def jobvision_sitemap(entries: list[tuple[int, str, str]]) -> str:
    """entries: (id, slug, lastmod ISO)"""
    urls = "".join(f"<url><loc>https://jobvision.ir/jobs/{i}/{s}</loc><lastmod>{lm}</lastmod></url>" for i, s, lm in entries)
    return f'<?xml version="1.0" encoding="utf-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def jobvision_job(*, job_id=900001, title="Senior DevOps Engineer", company="شرکت نمونه آزمایشی دو",
                  company_en="Sample Test Co 2", description_html="<p>Responsibilities</p>", province="تهران",
                  city="تهران", salary=None, software=("Docker", "Kubernetes", "Terraform"), is_remote=False,
                  seniority="Senior Specialist", expired=False, benefits=("بیمه تکمیلی", "وام")) -> str:
    detail = {
        "id": job_id, "title": title, "description": description_html, "isPersian": False,
        "company": {"id": "77", "name": {"titleFa": company, "titleEn": company_en}, "website": "sample2-test.example",
                    "companyLink": f"/companies/77/sample", "logoUrl": None,
                    "size": {"titleFa": "۵۱ تا ۲۰۰ نفر", "titleEn": "51 - 200 employees"},
                    "industries": [{"titleFa": "فناوری اطلاعات", "titleEn": "IT"}],
                    "description": {"titleFa": "شرکت نمونه برای آزمون نرم‌افزار؛ محصولات و خدمات ابری آزمایشی ارائه می‌دهد و هیچ ارتباطی با شرکت واقعی ندارد.", "titleEn": ""},
                    "establishmentYear": 1395, "companyType": None, "isGovernmentalCompany": False},
        "location": {"province": {"titleFa": province, "titleEn": "Tehran"}, "city": {"titleFa": city, "titleEn": "Tehran"}},
        "jobCategories": [{"titleFa": "شبکه / DevOps", "titleEn": "Network / DevOps / IT admin"}],
        "workType": {"titleFa": "تمام وقت", "titleEn": "Full Time"},
        "seniorityLevel": {"titleFa": "کارشناس ارشد", "titleEn": seniority},
        "salary": ({"titleFa": f"{salary[0]} - {salary[1]} میلیون تومان", "min": salary[0], "max": salary[1]} if salary else None),
        "benefits": [{"titleFa": b, "titleEn": b} for b in benefits],
        "softwareRequirements": [{"software": {"titleFa": s, "titleEn": s}, "skill": {"titleEn": "Advanced"}} for s in software],
        "skills": [], "workDays": "Saturday-Wednesday 9-18", "requiredRelatedExperienceYears": None,
        "isInternship": False, "isRemote": is_remote, "isUrgent": False,
        "firstActivationTime": {"date": "2026-10-10T10:00:00"}, "expireTime": {"date": "2026-12-10T10:00:00"},
        "isExpired": expired,
    }
    state = {f"https://candidateapi.jobvision.ir/api/v1/JobPost/Detail?jobPostId={job_id}": detail, "transfer-translate-fa": {}}
    ld = {"@context": "http://schema.org", "@type": "JobPosting", "title": title, "baseSalary": 12000}
    return (f'<html><head><script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head><body>'
            f'<script id="ng-state" type="application/json">{json.dumps(state, ensure_ascii=False)}</script></body></html>')


DEVOPS_DESCRIPTION = """<div dir="ltr"><strong>Responsibilities</strong><br>
Build and maintain CI/CD pipelines with GitLab CI.<br>Operate Kubernetes clusters and Docker images.<br>
Automate infrastructure with Terraform and Ansible.<br>Run monitoring with Prometheus and Grafana.<br><br>
<strong>Requirements</strong><br>At least 4 years of experience in DevOps.<br>Strong Linux and Bash skills.<br><br>
<strong>Nice to have</strong><br>Experience with ArgoCD and Helm.<br></div>"""
