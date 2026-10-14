from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import admin, alerts, auth, companies, insights, jobs, telegram
from app.api.deps import redis
from app.config import get_settings
from app.db import get_engine
from app.logging_setup import setup_logging

setup_logging()

app = FastAPI(
    title="Iran Tech Job Intelligence API",
    version="1.0.0",
    description="Collection, analysis and monitoring of Iranian IT job ads (DevOps, SRE, Python, AI/ML, MLOps/Data).",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
# Endpoints reached by links in e-mails / mail clients (no browser Origin check possible).
ORIGIN_EXEMPT = ("/api/v1/notifications/unsubscribe/",)


@app.middleware("http")
async def security(request: Request, call_next):
    # CSRF defence for cookie auth: a state-changing request carrying an Origin must
    # come from our own public origin (SameSite=Lax already blocks most cases).
    if request.method in UNSAFE and not request.url.path.startswith(ORIGIN_EXEMPT):
        origin = request.headers.get("origin")
        if origin and request.cookies:
            allowed = urlsplit(get_settings().public_base_url)
            o = urlsplit(origin)
            if (o.scheme, o.netloc) != (allowed.scheme, allowed.netloc):
                return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/") and not request.url.path.startswith(("/api/docs", "/api/redoc")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


api = APIRouter(prefix="/api/v1")


@api.get("/health", tags=["health"])
def health():
    checks = {}
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        redis().ping()
        hb = redis().get("heartbeat:scheduler")
        checks["redis"] = "ok"
        checks["scheduler_heartbeat"] = int(hb) if hb else None
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
    ok = checks.get("database") == "ok" and checks.get("redis") == "ok"
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


for r in (auth.router, jobs.router, companies.router, insights.router, alerts.router, telegram.router, admin.router):
    api.include_router(r)
app.include_router(api)
