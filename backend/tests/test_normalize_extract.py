"""1. Extraction & normalisation with valid sample data."""
from app.collectors.http import FetchResult
from app.collectors.jobinja import JobinjaAdapter
from app.collectors.jobvision import JobvisionAdapter
from app.pipeline.normalize import (
    canonical_url,
    compare_key,
    normalize_text,
    parse_experience_years,
    parse_salary_text,
    split_location,
)
from tests.fixtures import pages


def page(url, body, status=200):
    return FetchResult(url, url, status, body, {}, body.encode())


def test_persian_normalisation():
    raw = "برنامه‌‌نويس  پايتون  با ۵ سال سابقه‌ و كار تيمي"
    out = normalize_text(raw)
    assert "ي" not in out and "ك" not in out
    assert "5 سال" in out
    assert "‌‌" not in out
    assert "  " not in out
    # ZWNJ next to a space is dropped, inside a word kept
    assert normalize_text("می‌خواهیم") == "می‌خواهیم"
    assert normalize_text("سابقه‌ و") == "سابقه و"


def test_compare_key_ignores_layout():
    a = "<p>شرح   وظایف</p>\n\nکار با  Docker"
    b = "شرح وظایف کار با docker"
    assert compare_key(normalize_text(a.replace("<p>", "").replace("</p>", ""))) == compare_key(b)


def test_canonical_url_strips_tracking():
    u = "https://jobinja.ir/companies/x/jobs/AbC1/%D8%A7%D8%B3%D8%AA?_ref=16&_t=abc#top"
    assert canonical_url(u) == "https://jobinja.ir/companies/x/jobs/AbC1/است"


def test_salary_parsing():
    assert parse_salary_text("توافقی") is None
    assert parse_salary_text("۲۰ تا ۳۰ میلیون تومان") == {"min": 20_000_000, "max": 30_000_000, "currency": "IRT", "period": "monthly"}
    assert parse_salary_text("25,000,000 - 40,000,000 تومان")["max"] == 40_000_000
    assert parse_salary_text("۳۵۰,۰۰۰,۰۰۰ ریال")["min"] == 35_000_000
    assert parse_salary_text("25") is None  # a bare number is not a monthly salary


def test_experience_and_location():
    assert parse_experience_years("سه تا شش سال") == 3
    assert parse_experience_years("کمتر از سه سال") == 0
    assert parse_experience_years("5+ years") == 5
    assert split_location("تهران ، تهران") == ("تهران", "تهران")
    assert split_location("اصفهان، کاشان") == ("اصفهان", "کاشان")


def test_jobinja_parse_uses_infobox_salary_not_jsonld():
    html = pages.jobinja_job(description_html=pages.DEVOPS_DESCRIPTION, salary="توافقی", ld_salary=5000000)
    out = JobinjaAdapter().parse_job(page("https://jobinja.ir/companies/sample-co/jobs/tAbC/x", html))
    j = out.job
    assert out.status == "active"
    assert j.source_job_id == "tAbC"
    assert j.salary_original == "توافقی" and j.salary_min is None  # JSON-LD 5,000,000 ignored
    assert (j.province, j.city) == ("تهران", "تهران")
    assert j.employment_type == "full_time"
    assert j.required_skills == ["Docker", "Kubernetes", "Linux"]
    assert j.company_website == "sample-test.example"
    assert j.company_industry == "فناوری اطلاعات"
    assert "Kubernetes" in j.description


def test_jobinja_reported_salary_and_remote():
    html = pages.jobinja_job(salary="۴۰ - ۶۰ میلیون تومان", telecommute=True)
    j = JobinjaAdapter().parse_job(page("https://jobinja.ir/companies/sample-co/jobs/tAbC/x", html)).job
    assert (j.salary_min, j.salary_max) == (40_000_000, 60_000_000)
    assert j.work_mode == "remote"


def test_jobvision_parse_ng_state():
    html = pages.jobvision_job(salary=(45, 60), description_html=pages.DEVOPS_DESCRIPTION)
    out = JobvisionAdapter().parse_job(page("https://jobvision.ir/jobs/900001/senior-devops", html))
    j = out.job
    assert j.source_job_id == "900001"
    assert (j.salary_min, j.salary_max) == (45_000_000, 60_000_000)
    assert j.required_skills == ["Docker", "Kubernetes", "Terraform"]
    assert j.employment_type == "full_time"
    assert j.seniority_hint == "Senior Specialist"
    assert j.published_at is not None and j.expires_at is not None
    assert j.benefits == ["بیمه تکمیلی", "وام"]


def test_jobvision_jsonld_salary_placeholder_ignored():
    html = pages.jobvision_job(salary=None)
    j = JobvisionAdapter().parse_job(page("https://jobvision.ir/jobs/900001/x", html)).job
    assert j.salary_min is None and j.salary_original is None  # baseSalary 12000 in JSON-LD ignored


def test_gone_and_expired_pages():
    assert JobvisionAdapter().parse_job(page("https://jobvision.ir/jobs/1/x", "", 404)).status == "gone"
    html = pages.jobvision_job(expired=True)
    assert JobvisionAdapter().parse_job(page("https://jobvision.ir/jobs/900001/x", html)).status == "expired"
    html = pages.jobinja_job(expired=True)
    assert JobinjaAdapter().parse_job(page("https://jobinja.ir/companies/s/jobs/tAbC/x", html)).status == "expired"
