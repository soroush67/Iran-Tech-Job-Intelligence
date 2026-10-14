"""Collector runs with mocked HTTP (respx): robots compliance, baseline, expiry,
8. one source failing while the other keeps working."""
import httpx
import respx
from sqlalchemy import func, select

from app.collectors.runner import run_source
from app.models import Job, JobEvent, Source
from tests.fixtures import pages

JV = "https://jobvision.ir"
JB = "https://jobinja.ir"


def mock_jobvision(router, entries, jobs, *, gone=()):
    router.get(f"{JV}/robots.txt").respond(200, text=pages.JOBVISION_ROBOTS)
    router.get(f"{JV}/sitemap.xml").respond(200, text=pages.jobvision_sitemap_index())
    router.get(f"{JV}/sitemap/jobposts.xml").respond(200, text=pages.jobvision_sitemap(entries))
    for jid, html in jobs.items():
        router.get(url__regex=rf"^{JV}/jobs/{jid}/.*").respond(200, text=html)
    for jid in gone:
        router.get(url__regex=rf"^{JV}/jobs/{jid}(/.*)?$").respond(404, text="not found")


def mock_jobinja(router, links, jobs, total=None):
    router.get(f"{JB}/robots.txt").respond(200, text=pages.JOBINJA_ROBOTS)
    router.get(url__regex=rf"^{JB}/jobs\?.*page=1$").respond(200, text=pages.jobinja_search(links, total or len(links)))
    router.get(url__regex=rf"^{JB}/jobs\?.*page=\d+$").respond(200, text=pages.jobinja_search([], 0))
    for code, html in jobs.items():
        router.get(url__regex=rf"^{JB}/companies/[^/]+/jobs/{code}/.*").respond(200, text=html)


def config_single_keyword(db):
    s = db.scalar(select(Source).where(Source.key == "jobinja"))
    s.config = {"keywords": ["devops"], "max_pages_per_keyword": 2}
    db.commit()


def recent():
    return "2026-10-13T10:00:00Z"


def test_jobvision_run_respects_robots_and_filters(db):
    entries = [(900001, "استخدام-senior-devops-engineer", recent()), (900002, "استخدام-حسابدار", recent())]
    with respx.mock(assert_all_called=False) as router:
        mock_jobvision(router, entries, {900001: pages.jobvision_job(description_html=pages.DEVOPS_DESCRIPTION)})
        run = run_source(db, "jobvision", "manual")
        requested = [str(c.request.url) for c in router.calls]
    assert run.status == "success", run.errors
    assert run.discovered == 1  # the accountant ad is filtered out by its slug, never fetched
    assert not any("?" in u for u in requested)  # robots: disallow *?*
    assert not any("candidateapi" in u for u in requested)  # the disallowed API host is never used
    assert run.new_jobs == 1 and run.is_baseline
    assert db.scalar(select(Source.status).where(Source.key == "jobvision")) == "healthy"
    ev = db.scalar(select(JobEvent))
    assert ev.event_type == "NEW_JOB" and ev.is_baseline  # first crawl: no notification storm


def test_second_run_is_not_baseline_and_unchanged_ads_not_refetched(db):
    entries = [(900001, "استخدام-senior-devops-engineer", recent())]
    job_html = pages.jobvision_job(description_html=pages.DEVOPS_DESCRIPTION)
    with respx.mock(assert_all_called=False) as router:
        mock_jobvision(router, entries, {900001: job_html})
        run_source(db, "jobvision", "manual")
    entries.append((900003, "استخدام-python-developer", recent()))
    with respx.mock(assert_all_called=False) as router:
        mock_jobvision(router, entries, {900003: pages.jobvision_job(job_id=900003, title="Python Developer",
                                                                     software=("Python", "Django"))})
        run2 = run_source(db, "jobvision", "manual")
        fetched = [str(c.request.url) for c in router.calls if "/jobs/" in str(c.request.url)]
    assert not run2.is_baseline and run2.new_jobs == 1
    assert len(fetched) == 1 and "900003" in fetched[0]  # 900001 unchanged (lastmod) -> not fetched
    ev = db.scalars(select(JobEvent).order_by(JobEvent.id)).all()[-1]
    assert ev.event_type == "NEW_JOB" and not ev.is_baseline


def test_removed_from_sitemap_and_404_marks_expired(db):
    entries = [(900001, "استخدام-senior-devops-engineer", recent())]
    with respx.mock(assert_all_called=False) as router:
        mock_jobvision(router, entries, {900001: pages.jobvision_job(description_html=pages.DEVOPS_DESCRIPTION)})
        run_source(db, "jobvision", "manual")
    with respx.mock(assert_all_called=False) as router:
        mock_jobvision(router, [], {}, gone=(900001,))
        run = run_source(db, "jobvision", "manual")
    assert run.expired_jobs == 1
    assert db.scalar(select(Job.status)) == "expired"


def test_blocked_source_does_not_stop_other_source(db):
    config_single_keyword(db)
    with respx.mock(assert_all_called=False) as router:
        # jobvision answers 403 to everything -> blocked
        router.get(f"{JV}/robots.txt").respond(200, text=pages.JOBVISION_ROBOTS)
        router.get(url__regex=rf"^{JV}/.*").respond(403, text="forbidden")
        mock_jobinja(router, [("sample-co", "tAbC", "DevOps")],
                     {"tAbC": pages.jobinja_job(description_html=pages.DEVOPS_DESCRIPTION)})
        r_jv = run_source(db, "jobvision", "manual")
        r_jb = run_source(db, "jobinja", "manual")
    assert r_jv.status == "blocked"
    assert db.scalar(select(Source.status).where(Source.key == "jobvision")) == "blocked"
    assert r_jb.status == "success" and r_jb.new_jobs == 1
    assert db.scalar(select(Source.status).where(Source.key == "jobinja")) == "healthy"


def test_network_errors_and_bad_pages_degrade_but_continue(db):
    config_single_keyword(db)
    with respx.mock(assert_all_called=False) as router:
        mock_jobinja(router, [("sample-co", "good", "DevOps"), ("sample-co", "boom", "DevOps")],
                     {"good": pages.jobinja_job(code="good", description_html=pages.DEVOPS_DESCRIPTION)})
        router.get(url__regex=rf"^{JB}/companies/[^/]+/jobs/boom/.*").mock(side_effect=httpx.ConnectError("reset"))
        run = run_source(db, "jobinja", "manual")
    assert run.new_jobs == 1 and run.failed == 1
    assert run.status == "partial"  # 50% failures -> degraded, not success
    assert db.scalar(select(Source.status).where(Source.key == "jobinja")) == "degraded"
    assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_robots_disallow_is_honoured(db):
    config_single_keyword(db)
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{JB}/robots.txt").respond(200, text="User-agent: *\nDisallow: /companies/\n")
        router.get(url__regex=rf"^{JB}/jobs\?.*page=1$").respond(200, text=pages.jobinja_search([("sample-co", "tAbC", "x")], 1))
        job_route = router.get(url__regex=rf"^{JB}/companies/.*").respond(200, text="should not be fetched")
        run = run_source(db, "jobinja", "manual")
    assert not job_route.called
    assert run.skipped == 1 and any("robots.txt disallows" in e for e in run.errors)


def test_disabled_source_is_skipped(db):
    s = db.scalar(select(Source).where(Source.key == "jobinja"))
    s.enabled = False
    db.commit()
    run = run_source(db, "jobinja", "manual")
    assert run.status == "skipped" and s.status == "disabled"
