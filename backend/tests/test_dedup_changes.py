"""2. Duplicate detection, 3. real-change detection (and no false changes)."""
from sqlalchemy import func, select

from app.models import Job, JobEvent, JobSnapshot
from app.pipeline.ingest import mark_expired
from tests.fixtures import pages
from tests.helpers import jobinja_raw, jobvision_raw, put


def events(db, job_id):
    return [e.event_type for e in db.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id))]


def test_same_source_id_is_one_row(db):
    r1 = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    r2 = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    assert r1.created and not r2.created and not r2.changed
    assert db.scalar(select(func.count()).select_from(Job)) == 1
    assert db.scalar(select(func.count()).select_from(JobSnapshot)) == 1
    assert events(db, r1.job.id) == ["NEW_JOB"]


def test_same_job_on_two_sources_is_grouped_not_merged(db):
    a = put(db, "jobinja", jobinja_raw(title="Senior DevOps Engineer", company="شرکت نمونه آزمایشی",
                                       description_html=pages.DEVOPS_DESCRIPTION))
    b = put(db, "jobvision", jobvision_raw(title="Senior DevOps Engineer", company="شركت  نمونه آزمایشی",
                                           description_html=pages.DEVOPS_DESCRIPTION))
    assert a.job.id != b.job.id  # both source records are kept
    assert a.job.dedup_key == b.job.dedup_key  # ...and linked as the same posting
    assert a.job.company_id == b.job.company_id  # company names normalised (ك/ی, spaces, "شرکت")


def test_layout_only_change_is_not_a_change(db):
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    reflowed = pages.DEVOPS_DESCRIPTION.replace("<br>", "<br>\n\n  ").replace("CI/CD", "CI/CD ")
    r = put(db, "jobinja", jobinja_raw(description_html=f"<div class='new-wrapper'>{reflowed}</div>"))
    assert not r.changed
    assert events(db, r.job.id) == ["NEW_JOB"]


def test_salary_change_event_with_diff(db):
    r = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION, salary="توافقی"))
    r2 = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION, salary="۴۰ - ۶۰ میلیون تومان"))
    assert r2.changed and "SALARY_CHANGED" in r2.events
    ev = db.scalar(select(JobEvent).where(JobEvent.event_type == "SALARY_CHANGED"))
    assert ev.diff["salary_original"] == {"old": "توافقی", "new": "40 - 60 میلیون تومان"}  # digits normalised
    assert ev.diff["salary_min"]["new"] == 40_000_000
    assert db.scalar(select(func.count()).select_from(JobSnapshot).where(JobSnapshot.job_id == r.job.id)) == 2


def test_requirements_and_work_mode_changes(db):
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    r = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION, telecommute=True,
                                       skills=("Docker", "Kubernetes", "Linux", "Terraform")))
    assert set(r.events) == {"REQUIREMENTS_CHANGED", "WORK_MODE_CHANGED"}
    ev = db.scalar(select(JobEvent).where(JobEvent.event_type == "REQUIREMENTS_CHANGED"))
    assert ev.diff["required_skills"]["added"] == ["Terraform"]


def test_description_change(db):
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    new = pages.DEVOPS_DESCRIPTION + "<p>You will also own the on-call rotation and lead the migration to a new cloud provider.</p>"
    r = put(db, "jobinja", jobinja_raw(description_html=new))
    assert "DESCRIPTION_CHANGED" in r.events
    ev = db.scalar(select(JobEvent).where(JobEvent.event_type == "DESCRIPTION_CHANGED"))
    assert ev.diff["similarity"] < 0.97 and any("on-call" in line for line in ev.diff["diff"])


def test_expire_and_reopen(db):
    r = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    assert mark_expired(db, r.job, reason="page returned HTTP 404", run_id=None, baseline=False)
    db.commit()
    assert not mark_expired(db, r.job, reason="again", run_id=None, baseline=False)  # idempotent
    r2 = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    assert r2.job.status == "active"
    assert events(db, r.job.id) == ["NEW_JOB", "JOB_EXPIRED", "JOB_REOPENED"]


def test_baseline_events_are_flagged(db):
    r = put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION), baseline=True)
    ev = db.scalar(select(JobEvent).where(JobEvent.job_id == r.job.id))
    assert ev.is_baseline


def test_irrelevant_job_stored_without_events(db):
    r = put(db, "jobinja", jobinja_raw(title="حسابدار ارشد", skills=("Excel",),
                                       description_html="<p>آشنایی با Python مزیت است</p>"))
    assert not r.job.is_relevant
    assert events(db, r.job.id) == []


def test_published_at_not_invented(db):
    raw = jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION)
    raw.published_at = None
    r = put(db, "jobinja", raw)
    assert r.job.published_at is None and r.job.first_seen_at is not None
