from sqlalchemy import select

from app.collectors.http import FetchResult
from app.collectors.jobinja import JobinjaAdapter
from app.collectors.jobvision import JobvisionAdapter
from app.models import Source
from app.pipeline.ingest import ingest
from tests.fixtures import pages


def page(url, body, status=200):
    return FetchResult(url, url, status, body, {}, body.encode())


def jobinja_raw(**kw):
    code = kw.get("code", "tAbC")
    html = pages.jobinja_job(**kw)
    return JobinjaAdapter().parse_job(page(f"https://jobinja.ir/companies/sample-co/jobs/{code}/x", html)).job


def jobvision_raw(**kw):
    jid = kw.get("job_id", 900001)
    html = pages.jobvision_job(**kw)
    return JobvisionAdapter().parse_job(page(f"https://jobvision.ir/jobs/{jid}/x", html)).job


def source(db, key):
    return db.scalar(select(Source).where(Source.key == key))


def put(db, key, raw, baseline=False):
    s = source(db, key)
    res = ingest(db, s.id, key, raw, run_id=None, baseline=baseline)
    db.commit()
    return res
