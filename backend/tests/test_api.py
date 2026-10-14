"""11. API integration tests."""
from sqlalchemy import select

from app.models import AuditLog, Job
from tests.fixtures import pages
from tests.helpers import jobinja_raw, jobvision_raw, put


def seed_jobs(db):
    put(db, "jobinja", jobinja_raw(code="a1", title="Senior DevOps Engineer", salary="50 - 70 میلیون تومان",
                                   experience="پنج تا ده سال", description_html=pages.DEVOPS_DESCRIPTION))
    put(db, "jobinja", jobinja_raw(code="a2", title="برنامه نویس پایتون (Django)", skills=("Python", "Django"),
                                   location="اصفهان ، اصفهان", telecommute=True, description_html="<p>Django REST</p>"))
    put(db, "jobvision", jobvision_raw(job_id=900010, title="Machine Learning Engineer", software=("Python", "PyTorch"),
                                       description_html="<p>Train PyTorch models</p>"))
    put(db, "jobinja", jobinja_raw(code="a4", title="حسابدار", skills=("Excel",), description_html="<p>حسابداری</p>"))


def test_health_and_openapi(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"
    spec = client.get("/api/openapi.json").json()
    for path in ["/api/v1/jobs", "/api/v1/jobs/{job_id}", "/api/v1/companies", "/api/v1/companies/{company_id}",
                 "/api/v1/insights", "/api/v1/events", "/api/v1/sources/health", "/api/v1/saved-searches",
                 "/api/v1/notifications/test", "/api/v1/telegram/connect", "/api/v1/admin/collection/run",
                 "/api/v1/health"]:
        assert path in spec["paths"], path


def test_auth_required(client):
    assert client.get("/api/v1/jobs").status_code == 401
    assert client.post("/api/v1/admin/collection/run", json={}).status_code == 401


def test_login_and_me(admin_client):
    me = admin_client.get("/api/v1/auth/me").json()
    assert me["role"] == "admin"


def test_bad_login_is_audited(client, db):
    r = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    assert db.scalar(select(AuditLog.action)) == "auth.login_failed"


def test_jobs_list_filters_sort_pagination(user_client, db):
    seed_jobs(db)
    r = user_client.get("/api/v1/jobs").json()
    assert r["total"] == 3  # the accountant ad is not relevant
    assert {i["title"] for i in r["items"]} >= {"Senior DevOps Engineer"}
    r = user_client.get("/api/v1/jobs", params={"categories": "python"}).json()
    assert [i["title"] for i in r["items"]] == ["برنامه نویس پایتون (Django)"]
    r = user_client.get("/api/v1/jobs", params={"work_modes": "remote"}).json()
    assert r["total"] == 1
    r = user_client.get("/api/v1/jobs", params={"salary_status": "reported"}).json()
    assert [i["title"] for i in r["items"]] == ["Senior DevOps Engineer"]
    r = user_client.get("/api/v1/jobs", params={"salary_min": 60_000_000}).json()
    assert r["total"] == 1
    r = user_client.get("/api/v1/jobs", params={"sources": "jobvision"}).json()
    assert [i["source"] for i in r["items"]] == ["jobvision"]
    r = user_client.get("/api/v1/jobs", params={"skills": "PyTorch"}).json()
    assert r["total"] == 1
    r = user_client.get("/api/v1/jobs", params={"q": "django"}).json()
    assert r["total"] == 1
    r = user_client.get("/api/v1/jobs", params={"provinces": "اصفهان"}).json()
    assert r["total"] == 1
    r = user_client.get("/api/v1/jobs", params={"seniority": "senior"}).json()
    assert r["total"] >= 1 and all(i["seniority"] == "senior" for i in r["items"])
    r = user_client.get("/api/v1/jobs", params={"page_size": 2, "page": 2, "sort": "title"}).json()
    assert r["total"] == 3 and len(r["items"]) == 1
    r = user_client.get("/api/v1/jobs", params={"relevant_only": "false"}).json()
    assert r["total"] == 4
    # SQL-ish input is just data
    r = user_client.get("/api/v1/jobs", params={"q": "'; drop table jobs; --"})
    assert r.status_code == 200 and r.json()["total"] == 0
    assert user_client.get("/api/v1/jobs", params={"sort": "evil"}).status_code == 422


def test_job_detail_and_history(user_client, db):
    seed_jobs(db)
    put(db, "jobinja", jobinja_raw(code="a1", title="Senior DevOps Engineer", salary="60 - 80 میلیون تومان",
                                   experience="پنج تا ده سال", description_html=pages.DEVOPS_DESCRIPTION))
    jid = db.scalar(select(Job.id).where(Job.source_job_id == "a1"))
    d = user_client.get(f"/api/v1/jobs/{jid}").json()
    assert d["analysis"]["engine"] == "rules"
    assert d["analysis"]["quality"]["total"] == sum(c["score"] for c in d["analysis"]["quality"]["criteria"])
    assert [e["type"] for e in d["events"]][:1] == ["SALARY_CHANGED"]
    assert len(d["history"]) == 2
    assert d["salary_estimate"]["status"] == "reported"
    assert user_client.get(f"/api/v1/jobs/{jid}/snapshots/1").json()["data"]["salary_min"] == 50_000_000
    assert user_client.get("/api/v1/jobs/999999").status_code == 404


def test_match_score_with_profile(user_client, db):
    seed_jobs(db)
    user_client.put("/api/v1/auth/me/profile", json={"skills": ["Docker", "Kubernetes", "Linux", "Terraform"],
                                                     "preferred_skills": ["ArgoCD"], "years_experience": 6,
                                                     "cities": ["تهران"], "work_modes": ["onsite", "hybrid"]})
    items = user_client.get("/api/v1/jobs").json()["items"]
    scores = {i["title"]: i["match_score"] for i in items}
    assert scores["Senior DevOps Engineer"] > scores["Machine Learning Engineer"]
    jid = next(i["id"] for i in items if i["title"] == "Senior DevOps Engineer")
    m = user_client.get(f"/api/v1/jobs/{jid}").json()["match"]
    assert {p["key"] for p in m["breakdown"]} == {"required", "preferred", "experience", "city", "work_mode"}


def test_csv_export(user_client, db):
    seed_jobs(db)
    r = user_client.get("/api/v1/jobs/export.csv", params={"categories": "devops"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.content.decode("utf-8-sig").strip().splitlines()
    assert lines[0].startswith("id,source,title") and len(lines) == 2


def test_companies_insights_events_sources(user_client, db):
    seed_jobs(db)
    comps = user_client.get("/api/v1/companies").json()
    assert comps["total"] >= 1
    cid = comps["items"][0]["id"]
    c = user_client.get(f"/api/v1/companies/{cid}").json()
    assert "note" in c["transparency"] and c["transparency_level"] in ("unknown", "low", "medium", "high")
    ins = user_client.get("/api/v1/insights").json()
    assert ins["total_active"] == 3 and ins["top_skills"]
    assert all(g.get("insufficient") for g in ins["salary"]["groups"])  # 1 sample < minimum
    ev = user_client.get("/api/v1/events").json()
    assert ev["total"] == 3 and {e["type"] for e in ev["items"]} == {"NEW_JOB"}
    src = user_client.get("/api/v1/sources/health").json()["sources"]
    assert {s["key"] for s in src} == {"jobinja", "jobvision"}
    assert all(s["access_method"] and s["limitations"] for s in src)
    dash = user_client.get("/api/v1/dashboard").json()
    assert dash["total_relevant_active"] == 3 and dash["by_category"]["devops"] >= 1


def test_saved_searches_and_subscriptions(user_client):
    r = user_client.post("/api/v1/saved-searches", json={"name": "DevOps Tehran",
                                                         "filters": {"categories": ["devops"], "cities": ["تهران"]}})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert user_client.post("/api/v1/saved-searches", json={"name": "DevOps Tehran", "filters": {}}).status_code == 409
    r = user_client.post("/api/v1/subscriptions", json={"saved_search_id": sid, "channel": "email",
                                                        "event_types": ["NEW_JOB", "SALARY_CHANGED"], "frequency": "daily",
                                                        "min_match_score": 60})
    assert r.status_code == 201
    lst = user_client.get("/api/v1/saved-searches").json()
    assert lst["items"][0]["subscriptions"][0]["frequency"] == "daily"
    assert user_client.post("/api/v1/subscriptions", json={"channel": "email", "event_types": ["BOGUS"]}).status_code == 422
    assert user_client.delete(f"/api/v1/saved-searches/{sid}").json()["ok"]


def test_saved_search_isolation(user_client, admin_client):
    sid = user_client.post("/api/v1/saved-searches", json={"name": "mine", "filters": {}}).json()["id"]
    assert admin_client.delete(f"/api/v1/saved-searches/{sid}").status_code == 404


def test_notification_test_email(user_client, db, smtp_server):
    from app.models import User
    r = user_client.post("/api/v1/notifications/test", json={"channel": "email"})
    assert r.status_code == 400  # no verified address yet
    r = user_client.post("/api/v1/notifications/email", json={"email": "me@example.com"})
    assert r.status_code == 200 and len(smtp_server.messages) == 1
    import email
    import re
    msg = email.message_from_string(smtp_server.messages[0]["data"])
    html = next(p.get_payload(decode=True).decode() for p in msg.walk() if p.get_content_type() == "text/html")
    token = re.search(r"/email/verify/([A-Za-z0-9_-]+)", html).group(1)
    assert user_client.get(f"/api/v1/notifications/email/verify/{token}").status_code == 200
    assert db.scalar(select(User.notify_email_verified_at).where(User.email == "user@example.com")) is not None
    assert "نامعتبر" in user_client.get(f"/api/v1/notifications/email/verify/{token}").text  # single use
    r = user_client.post("/api/v1/notifications/test", json={"channel": "email"})
    assert r.status_code == 200 and len(smtp_server.messages) == 2


def test_admin_only_endpoints(user_client, admin_client, monkeypatch):
    assert user_client.post("/api/v1/admin/collection/run", json={}).status_code == 403
    assert user_client.get("/api/v1/admin/ai").status_code == 403
    queued = []

    class FakeJob:
        id = "job-1"

    monkeypatch.setattr("app.api.admin._enqueue", lambda name, *a, **kw: queued.append((name, a)) or FakeJob())
    r = admin_client.post("/api/v1/admin/collection/run", json={"source": "jobinja"})
    assert r.status_code == 200 and queued == [("collect_source", ("jobinja", "manual"))]


def test_admin_ai_settings_never_return_key(admin_client):
    r = admin_client.put("/api/v1/admin/ai", json={"enabled": True, "provider": "claude", "model": "claude-opus-5-5",
                                                   "effort": "low", "anthropic_api_key": "sk-ant-secret-value-1234"})
    assert r.status_code == 200
    body = r.text
    assert "sk-ant-secret" not in body and r.json()["anthropic_api_key_configured"] is True
    assert "sk-ant-secret" not in admin_client.get("/api/v1/admin/ai").text
    assert admin_client.put("/api/v1/admin/ai", json={"enabled": True, "model": "gpt-4"}).status_code == 400


def test_admin_smtp_password_masked(admin_client):
    r = admin_client.put("/api/v1/admin/smtp", json={"host": "smtp.example.com", "port": 587, "username": "u",
                                                     "password": "smtp-pass-xyz", "from": "a@example.com"})
    assert r.status_code == 200 and "smtp-pass-xyz" not in r.text and r.json()["password_configured"]


def test_salary_dataset_upload_and_versioning(admin_client, db):
    csv_ok = ("category,seniority,city,salary_min,salary_max,salary_median,sample_size\n"
              "devops,senior,تهران,60000000,90000000,75000000,40\n")
    form = {"name": "test-ds", "source_name": "آزمایشی", "data_year": "1405"}
    r = admin_client.post("/api/v1/admin/salary/datasets", data=form, files={"file": ("s.csv", csv_ok.encode(), "text/csv")})
    assert r.status_code == 201 and r.json()["version"] == 1
    r = admin_client.post("/api/v1/admin/salary/datasets", data=form, files={"file": ("s.csv", csv_ok.encode(), "text/csv")})
    assert r.json()["version"] == 2
    items = admin_client.get("/api/v1/admin/salary/datasets").json()["items"]
    assert [(d["version"], d["is_active"]) for d in items] == [(2, True), (1, False)]
    bad = "category,salary_min,salary_max\nmarketing,1,2\n"
    r = admin_client.post("/api/v1/admin/salary/datasets", data=form, files={"file": ("b.csv", bad.encode(), "text/csv")})
    assert r.status_code == 400 and "category" in r.text


def test_cross_origin_post_refused(admin_client):
    r = admin_client.post("/api/v1/saved-searches", json={"name": "x", "filters": {}},
                          headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_login_rate_limited(client):
    codes = [client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "wrong-pass"}).status_code
             for _ in range(12)]
    assert 429 in codes
