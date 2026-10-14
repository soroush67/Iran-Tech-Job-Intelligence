"""5. Job classification (incl. superficial-mention negatives and multi-category)."""
import pytest

from app.pipeline import rules


def classify(title, description="", structured=()):
    skills = rules.extract_skills(title, description, list(structured), [])
    return {c.category: c for c in rules.classify(title, skills, description)}


@pytest.mark.parametrize("title,expected", [
    ("Senior DevOps Engineer", {"devops"}),
    ("کارشناس دواپس", {"devops"}),
    ("مهندس دوآپس (DevOps Engineer)", {"devops"}),
    ("Platform Engineer", {"devops"}),
    ("Kubernetes Engineer", {"devops"}),
    ("Linux Administrator", {"devops"}),
    ("Site Reliability Engineer", {"sre"}),
    ("SRE", {"sre"}),
    ("Observability Engineer", {"sre"}),
    ("DevOps / SRE Engineer", {"devops", "sre"}),
    ("Senior DevSecOps Engineer", {"devops"}),
    ("برنامه نویس پایتون", {"python"}),
    ("Django Developer", {"python"}),
    ("FastAPI Backend Developer", {"python"}),
    ("Backend Developer (Python)", {"python"}),
    ("Machine Learning Engineer", {"ai_ml"}),
    ("متخصص هوش مصنوعی", {"ai_ml"}),
    ("LLM Engineer", {"ai_ml"}),
    ("Computer Vision Engineer", {"ai_ml"}),
    ("کارشناس پردازش زبان طبیعی (NLP)", {"ai_ml"}),
    ("MLOps Engineer", {"mlops_data"}),
    ("Data Engineer", {"mlops_data"}),
    ("مهندس داده", {"mlops_data"}),
])
def test_titles(title, expected):
    assert set(classify(title)) == expected


@pytest.mark.parametrize("title,description", [
    ("حسابدار", "آشنایی با Python و اکسل مزیت محسوب می‌شود"),
    ("کارشناس فروش محصولات هوش مصنوعی", "فروش راهکارهای AI و machine learning به مشتریان سازمانی"),
    ("مدیر محصول هوش مصنوعی (AI Product Manager)", "تعریف نقشه راه محصول"),
    ("مدرس پایتون", "تدریس دوره‌های Python مقدماتی"),
    ("کارشناس زیرساخت شبکه", "پیکربندی سوییچ‌های Cisco و MikroTik"),
    ("Frontend Developer", "React, TypeScript. Familiarity with Python is a plus"),
])
def test_superficial_mentions_are_not_categorised(title, description):
    assert classify(title, description) == {}


def test_generic_title_with_strong_python_evidence():
    desc = "Requirements\nStrong Python and Django experience\nREST API design with PostgreSQL and Celery"
    cats = classify("Backend Developer", desc)
    assert "python" in cats
    assert cats["python"].confidence < 0.9  # weaker than a title match


def test_generic_title_with_devops_evidence():
    desc = "Requirements\nDocker, Kubernetes, Terraform, Ansible and GitLab CI\nLinux administration"
    assert "devops" in classify("Software Engineer", desc)


def test_seniority_detection():
    s = rules.detect_seniority("Senior DevOps Engineer", "5 سال", None, "")
    assert s.level == "senior" and s.confidence >= 0.85
    assert rules.detect_seniority("Junior Python Developer", None, None, "").level == "junior"
    assert rules.detect_seniority("DevOps Engineer", None, None, "at least 3 years of experience").level == "mid"
    assert rules.detect_seniority("DevOps Engineer", None, None, "").level == "unknown"


def test_skill_sections_required_vs_optional():
    from tests.fixtures.pages import DEVOPS_DESCRIPTION
    from app.pipeline.normalize import html_to_text
    skills = {s.name: s for s in rules.extract_skills("DevOps Engineer", html_to_text(DEVOPS_DESCRIPTION), [], [])}
    assert skills["Kubernetes"].required
    assert skills["ArgoCD"].required is False and skills["Helm"].required is False


def test_monitoring_tools_alone_do_not_make_sre():
    desc = "Requirements\nDocker, Kubernetes\nPrometheus, Grafana, Loki, Elasticsearch, Zabbix monitoring"
    assert set(classify("DevOps Engineer", desc)) == {"devops"}
    desc_sre = desc + "\nDefine SLOs and own the on-call incident response"
    assert set(classify("DevOps Engineer", desc_sre)) == {"devops", "sre"}


def test_python_tool_in_other_role_and_secondary_threshold():
    desc = "Requirements\nPython scripting\nDocker, Kubernetes, Terraform, Ansible, GitLab CI, Linux"
    assert set(classify("Senior DevSecOps Engineer", desc, ["Python"])) == {"devops"}
    data = "Requirements\nSpark, Kafka, Airflow, ETL pipelines\nDocker and Kubernetes"
    assert set(classify("Senior Data Engineer", data)) == {"mlops_data"}
