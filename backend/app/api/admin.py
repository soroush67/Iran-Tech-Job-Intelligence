import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import settings_store
from app.ai.engine import get_provider, pending_llm_jobs
from app.ai.providers import ClaudeProvider, OllamaProvider, ProviderError
from app.api.deps import audit, redis, require_admin
from app.api.insights import _run_out
from app.db import get_db
from app.models import (
    CATEGORIES,
    AuditLog,
    Job,
    NotificationDelivery,
    SalaryBenchmark,
    SalaryDataset,
    Source,
    SourceRun,
    User,
)
from app.pipeline.salary import apply_salary

router = APIRouter(prefix="/admin", tags=["admin"])

AI_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]


def _enqueue(func_name: str, *args, queue_name: str, **kw):
    from app import tasks
    return tasks.queue(queue_name).enqueue(getattr(tasks, func_name), *args, **kw)


# ---- collection -------------------------------------------------------------------------

class RunIn(BaseModel):
    source: str | None = None  # None = all enabled sources


@router.post("/collection/run")
def run_collection(body: RunIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    q = select(Source).where(Source.enabled)
    if body.source:
        q = select(Source).where(Source.key == body.source)
    sources = db.scalars(q).all()
    if not sources:
        raise HTTPException(404, "no matching enabled source")
    jobs = []
    for s in sources:
        if not s.enabled:
            raise HTTPException(400, f"source {s.key} is disabled")
        j = _enqueue("collect_source", s.key, "manual", queue_name="collect", job_timeout=3 * 3600)
        jobs.append({"source": s.key, "job_id": j.id})
    audit(db, request, admin, "collection.run", ",".join(s.key for s in sources))
    db.commit()
    return {"queued": jobs}


@router.get("/collection/runs")
def runs(source: str | None = None, page: int = Query(1, ge=1), db: Session = Depends(get_db),
         admin: User = Depends(require_admin)):
    stmt = select(SourceRun, Source.key).join(Source)
    if source:
        stmt = stmt.where(Source.key == source)
    rows = db.execute(stmt.order_by(SourceRun.started_at.desc()).offset((page - 1) * 50).limit(50)).all()
    return {"items": [_run_out(r, k) | {"errors": r.errors} for r, k in rows]}


class SourceIn(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=30, le=7 * 24 * 60)
    config: dict | None = None


@router.put("/sources/{key}")
def update_source(key: str, body: SourceIn, request: Request, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    s = db.scalar(select(Source).where(Source.key == key))
    if s is None:
        raise HTTPException(404, "source not found")
    if body.interval_minutes < s.min_interval_minutes:
        raise HTTPException(400, f"interval must be >= {s.min_interval_minutes} minutes for this source")
    s.enabled = body.enabled
    s.interval_minutes = body.interval_minutes
    if body.config is not None:
        allowed = {"jobinja": {"keywords", "max_pages_per_keyword"}, "jobvision": {"slug_keywords", "max_age_days"}}.get(key, set())
        bad = set(body.config) - allowed
        if bad:
            raise HTTPException(400, f"unknown config keys: {', '.join(sorted(bad))}")
        s.config = body.config
    s.status = "disabled" if not s.enabled else (s.status if s.status != "disabled" else "unknown")
    audit(db, request, admin, "source.update", key, body.model_dump())
    db.commit()
    return {"ok": True}


@router.get("/collector/settings")
def collector_settings(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from app.collectors.registry import ADAPTERS
    return {"paused": settings_store.get(db, "collector.paused"),
            "sources": [{"key": s.key, "enabled": s.enabled, "interval_minutes": s.interval_minutes,
                         "min_interval_minutes": s.min_interval_minutes,
                         "config": {**ADAPTERS[s.key].default_config, **(s.config or {})}}
                        for s in db.scalars(select(Source).order_by(Source.id))]}


class PausedIn(BaseModel):
    paused: bool


@router.put("/collector/paused")
def set_paused(body: PausedIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    settings_store.set_value(db, "collector.paused", body.paused, admin.id)
    audit(db, request, admin, "collector.paused", str(body.paused))
    db.commit()
    return {"ok": True}


# ---- AI ------------------------------------------------------------------------------------

class AISettingsIn(BaseModel):
    enabled: bool
    provider: Literal["claude", "ollama"] = "claude"
    model: str = Field(default="claude-opus-5-5", max_length=80)
    effort: Literal["low", "medium", "high"] = "low"
    anthropic_api_key: str | None = Field(default=None, max_length=300)  # None = keep current
    clear_api_key: bool = False
    ollama_base_url: str | None = Field(default=None, max_length=300)
    ollama_model: str | None = Field(default=None, max_length=120)
    auto_analyze_new: bool = True


@router.get("/ai")
def ai_settings(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    view = settings_store.public_view(db, "ai")
    try:
        status = (redis().get("ai:sync:status") or b"").decode()
    except Exception:
        status = ""
    relevant = db.scalar(select(func.count()).select_from(Job).where(Job.is_relevant))
    return {**view, "models": AI_MODELS, "pending": len(pending_llm_jobs(db, 100000)) if get_provider(db) else None,
            "relevant_jobs": relevant, "sync_status": status or None}


@router.put("/ai")
def update_ai(body: AISettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if body.provider == "claude" and body.model not in AI_MODELS:
        raise HTTPException(400, f"model must be one of {AI_MODELS}")
    settings_store.set_value(db, "ai.enabled", body.enabled, admin.id)
    settings_store.set_value(db, "ai.provider", body.provider, admin.id)
    settings_store.set_value(db, "ai.model", body.model, admin.id)
    settings_store.set_value(db, "ai.effort", body.effort, admin.id)
    settings_store.set_value(db, "ai.auto_analyze_new", body.auto_analyze_new, admin.id)
    if body.clear_api_key:
        settings_store.set_value(db, "ai.anthropic_api_key", "", admin.id)
    elif body.anthropic_api_key:
        settings_store.set_value(db, "ai.anthropic_api_key", body.anthropic_api_key.strip(), admin.id)
    if body.ollama_base_url:
        if not body.ollama_base_url.startswith(("http://", "https://")):
            raise HTTPException(400, "ollama_base_url must be http(s)")
        settings_store.set_value(db, "ai.ollama_base_url", body.ollama_base_url, admin.id)
    if body.ollama_model:
        settings_store.set_value(db, "ai.ollama_model", body.ollama_model, admin.id)
    audit(db, request, admin, "ai.settings", None, body.model_dump(exclude={"anthropic_api_key"}) |
          {"api_key_changed": bool(body.anthropic_api_key) or body.clear_api_key})
    db.commit()
    return ai_settings(db, admin)


@router.post("/ai/test")
def ai_test(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    provider = settings_store.get(db, "ai.provider")
    try:
        if provider == "ollama":
            p = OllamaProvider(settings_store.get(db, "ai.ollama_base_url"), settings_store.get(db, "ai.ollama_model"))
        else:
            p = ClaudeProvider(settings_store.get(db, "ai.anthropic_api_key"), settings_store.get(db, "ai.model"))
        name = p.ping()
    except ProviderError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "model": name}


class SyncIn(BaseModel):
    limit: int = Field(default=200, ge=1, le=5000)


@router.post("/ai/sync")
def ai_sync(body: SyncIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if get_provider(db) is None:
        raise HTTPException(400, "AI is disabled or not configured - enable it and set the API key first")
    j = _enqueue("sync_llm", body.limit, True, queue_name="analyze", job_timeout=6 * 3600)
    redis().set("ai:sync:status", "queued")
    audit(db, request, admin, "ai.sync", None, {"limit": body.limit})
    db.commit()
    return {"queued": j.id, "pending": len(pending_llm_jobs(db, body.limit))}


@router.post("/ai/reanalyze/{job_id}")
def reanalyze(job_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.get(Job, job_id) is None:
        raise HTTPException(404, "job not found")
    j = _enqueue("analyze_jobs", [job_id], True, True, queue_name="analyze")
    return {"queued": j.id}


# ---- SMTP -------------------------------------------------------------------------------

class SMTPIn(BaseModel):
    host: str = Field(default="", max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    password: str | None = Field(default=None, max_length=500)  # None = keep
    from_: str = Field(default="", alias="from", max_length=255)
    starttls: bool = True
    ssl: bool = False


@router.get("/smtp")
def smtp_get(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return settings_store.public_view(db, "smtp")


@router.put("/smtp")
def smtp_put(body: SMTPIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    for k, v in (("host", body.host), ("port", body.port), ("username", body.username), ("from", body.from_),
                 ("starttls", body.starttls), ("ssl", body.ssl)):
        settings_store.set_value(db, f"smtp.{k}", v, admin.id)
    if body.password is not None:
        settings_store.set_value(db, "smtp.password", body.password, admin.id)
    audit(db, request, admin, "smtp.settings", None, {"host": body.host, "port": body.port,
                                                      "password_changed": body.password is not None})
    db.commit()
    return settings_store.public_view(db, "smtp")


class NotifySettingsIn(BaseModel):
    daily_digest_hour: int = Field(ge=0, le=23)
    max_per_user_per_hour: int = Field(ge=1, le=500)


@router.put("/notify")
def notify_put(body: NotifySettingsIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    settings_store.set_value(db, "notify.daily_digest_hour", body.daily_digest_hour, admin.id)
    settings_store.set_value(db, "notify.max_per_user_per_hour", body.max_per_user_per_hour, admin.id)
    db.commit()
    return {"daily_digest_hour": body.daily_digest_hour, "max_per_user_per_hour": body.max_per_user_per_hour}


@router.get("/notify")
def notify_get(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    counts = dict(db.execute(select(NotificationDelivery.status, func.count()).group_by(NotificationDelivery.status)).all())
    return {"daily_digest_hour": settings_store.get(db, "notify.daily_digest_hour"),
            "max_per_user_per_hour": settings_store.get(db, "notify.max_per_user_per_hour"),
            "deliveries": counts}


# ---- salary datasets ------------------------------------------------------------------------

SALARY_COLUMNS = ["category", "role_title", "seniority", "city", "employment_type", "min_years", "max_years",
                  "salary_min", "salary_max", "salary_median", "sample_size"]


def _num(v: str, kind=int):
    v = (v or "").strip().replace(",", "")
    return kind(float(v)) if v else None


@router.get("/salary/datasets")
def datasets(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.scalars(select(SalaryDataset).order_by(SalaryDataset.name, SalaryDataset.version.desc())).all()
    return {"items": [{"id": d.id, "name": d.name, "version": d.version, "source_name": d.source_name,
                       "source_url": d.source_url, "data_year": d.data_year, "is_active": d.is_active,
                       "row_count": d.row_count, "uploaded_at": d.uploaded_at, "notes": d.notes} for d in rows],
            "csv_columns": SALARY_COLUMNS}


@router.post("/salary/datasets", status_code=201)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(..., min_length=2, max_length=200),
    source_name: str = Form(..., min_length=2, max_length=255),
    source_url: str | None = Form(None),
    data_year: int = Form(..., ge=1390, le=1500),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 5 MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "file must be UTF-8 CSV") from None
    reader = csv.DictReader(io.StringIO(text))
    missing = {"category", "salary_min", "salary_max"} - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(400, f"missing columns: {', '.join(sorted(missing))}; expected {SALARY_COLUMNS}")
    rows, errors = [], []
    for i, r in enumerate(reader, start=2):
        try:
            cat = (r.get("category") or "").strip()
            if cat not in CATEGORIES:
                raise ValueError(f"category must be one of {CATEGORIES}")
            sen = (r.get("seniority") or "").strip() or None
            if sen and sen not in ("junior", "mid", "senior", "staff", "principal"):
                raise ValueError("bad seniority")
            lo, hi = _num(r.get("salary_min")), _num(r.get("salary_max"))
            if not lo or not hi or lo <= 0 or hi < lo:
                raise ValueError("salary_min/salary_max must be positive and min <= max (monthly toman)")
            if hi > 10_000_000_000:
                raise ValueError("salary looks wrong (expects monthly toman)")
            rows.append(SalaryBenchmark(
                category=cat, role_title=(r.get("role_title") or "").strip() or None, seniority=sen,
                city=(r.get("city") or "").strip() or None,
                employment_type=(r.get("employment_type") or "").strip() or None,
                min_years=_num(r.get("min_years"), float), max_years=_num(r.get("max_years"), float),
                salary_min=lo, salary_max=hi, salary_median=_num(r.get("salary_median")),
                sample_size=_num(r.get("sample_size"))))
        except (ValueError, TypeError) as exc:
            errors.append(f"line {i}: {exc}")
    if errors:
        raise HTTPException(400, {"message": "CSV validation failed", "errors": errors[:50]})
    if not rows:
        raise HTTPException(400, "CSV has no data rows")
    version = (db.scalar(select(func.max(SalaryDataset.version)).where(SalaryDataset.name == name)) or 0) + 1
    db.execute(update(SalaryDataset).where(SalaryDataset.name == name).values(is_active=False))
    ds = SalaryDataset(name=name, version=version, source_name=source_name, source_url=source_url, data_year=data_year,
                       notes=notes, is_active=True, row_count=len(rows), uploaded_by=admin.id)
    db.add(ds)
    db.flush()
    for r in rows:
        r.dataset_id = ds.id
        db.add(r)
    audit(db, request, admin, "salary.dataset_upload", f"{name} v{version}", {"rows": len(rows)})
    db.commit()
    _enqueue_salary_refresh()
    return {"id": ds.id, "name": name, "version": version, "rows": len(rows)}


class ActiveIn(BaseModel):
    is_active: bool


@router.put("/salary/datasets/{ds_id}")
def set_dataset_active(ds_id: int, body: ActiveIn, request: Request, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    ds = db.get(SalaryDataset, ds_id)
    if ds is None:
        raise HTTPException(404, "dataset not found")
    if body.is_active:
        db.execute(update(SalaryDataset).where(SalaryDataset.name == ds.name).values(is_active=False))
    ds.is_active = body.is_active
    audit(db, request, admin, "salary.dataset_active", f"{ds.name} v{ds.version}", body.model_dump())
    db.commit()
    _enqueue_salary_refresh()
    return {"ok": True}


def _enqueue_salary_refresh():
    try:
        from app import tasks
        tasks.queue("analyze").enqueue(tasks.refresh_salaries)
    except Exception:
        pass


@router.post("/salary/recompute")
def recompute(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    n = 0
    for job in db.scalars(select(Job).where(Job.is_relevant)):
        apply_salary(db, job)
        n += 1
    db.commit()
    return {"recomputed": n}


# ---- users & audit --------------------------------------------------------------------------

@router.get("/users")
def users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return {"items": [{"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role,
                       "is_active": u.is_active, "created_at": u.created_at, "last_login_at": u.last_login_at}
                      for u in db.scalars(select(User).order_by(User.id))]}


class UserAdminIn(BaseModel):
    role: Literal["admin", "user"]
    is_active: bool


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserAdminIn, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    if u.id == admin.id and (body.role != "admin" or not body.is_active):
        raise HTTPException(400, "you cannot demote or disable yourself")
    u.role, u.is_active = body.role, body.is_active
    audit(db, request, admin, "user.update", u.email, body.model_dump())
    db.commit()
    return {"ok": True}


@router.get("/audit")
def audit_logs(page: int = Query(1, ge=1), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.execute(select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.user_id)
                      .order_by(AuditLog.created_at.desc()).offset((page - 1) * 100).limit(100)).all()
    return {"items": [{"id": a.id, "action": a.action, "target": a.target, "details": a.details, "ip": a.ip,
                       "user": email, "created_at": a.created_at} for a, email in rows]}
