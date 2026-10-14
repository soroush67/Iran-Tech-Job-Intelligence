"""SQLAlchemy models. The Alembic migration in alembic/versions mirrors this file."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

CATEGORIES = ("devops", "sre", "python", "ai_ml", "mlops_data")
JOB_STATUSES = ("active", "expired", "unknown")
EVENT_TYPES = (
    "NEW_JOB",
    "SALARY_CHANGED",
    "DESCRIPTION_CHANGED",
    "REQUIREMENTS_CHANGED",
    "WORK_MODE_CHANGED",
    "JOB_EXPIRED",
    "JOB_REOPENED",
)
SOURCE_STATUSES = ("healthy", "degraded", "blocked", "disabled", "unknown")


def _now_col(**kw):
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kw)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Matching profile: {"skills": [...], "preferred_skills": [...], "years_experience": 4,
    # "cities": [...], "work_modes": [...]}
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    notify_email: Mapped[str | None] = mapped_column(String(320))
    notify_email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_email_token_hash: Mapped[str | None] = mapped_column(String(128))
    notify_email_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now_col()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    interval_minutes: Mapped[int] = mapped_column(Integer, default=240)
    # Lower bound imposed by what we know about the source (robots crawl-delay, ToS).
    min_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    access_method: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    robots_summary: Mapped[str | None] = mapped_column(Text)
    robots_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    baseline_done: Mapped[bool] = mapped_column(Boolean, default=False)
    # Persisted crawl cursor (e.g. which sitemap URLs are still to fetch).
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now_col()


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="schedule")
    status: Mapped[str] = mapped_column(String(16), default="running")
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = _now_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    parsed: Mapped[int] = mapped_column(Integer, default=0)
    relevant: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, default=0)
    changed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    expired_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    http_status_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    coverage_note: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship()


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)
    website: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str | None] = mapped_column(String(80))
    industry: Mapped[str | None] = mapped_column(String(200))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(120))
    # [{"source": "jobinja", "url": "...", "fetched_at": "..."}]
    profiles: Mapped[list] = mapped_column(JSONB, default=list)
    profile_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transparency: Mapped[dict | None] = mapped_column(JSONB)
    transparency_score: Mapped[int | None] = mapped_column(Integer)
    transparency_level: Mapped[str] = mapped_column(String(16), default="unknown")
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now_col()
    updated_at: Mapped[datetime] = _now_col(onupdate=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_jobs_source_job_id"),
        UniqueConstraint("source_id", "canonical_url", name="uq_jobs_source_url"),
        Index("ix_jobs_status_relevant", "status", "is_relevant"),
        Index("ix_jobs_first_seen", "first_seen_at"),
        Index("ix_jobs_last_changed", "last_changed_at"),
        Index("ix_jobs_dedup_key", "dedup_key"),
        Index("ix_jobs_city", "city"),
        Index("ix_jobs_province", "province"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"), index=True)
    source_job_id: Mapped[str] = mapped_column(String(64))
    canonical_url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    company_name: Mapped[str | None] = mapped_column(String(255))
    company_profile_url: Mapped[str | None] = mapped_column(String(1000))
    city: Mapped[str | None] = mapped_column(String(120))
    province: Mapped[str | None] = mapped_column(String(120))
    work_mode: Mapped[str | None] = mapped_column(String(16))  # onsite | hybrid | remote
    employment_type: Mapped[str | None] = mapped_column(String(32))
    seniority: Mapped[str] = mapped_column(String(16), default="unknown")
    experience_required: Mapped[str | None] = mapped_column(String(120))
    experience_min_years: Mapped[float | None] = mapped_column(Float)
    required_skills: Mapped[list] = mapped_column(ARRAY(String), default=list)
    optional_skills: Mapped[list] = mapped_column(ARRAY(String), default=list)
    description: Mapped[str | None] = mapped_column(Text)
    benefits: Mapped[list] = mapped_column(ARRAY(String), default=list)
    salary_original: Mapped[str | None] = mapped_column(String(255))
    salary_min: Mapped[int | None] = mapped_column(BigInteger)
    salary_max: Mapped[int | None] = mapped_column(BigInteger)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(16))
    # reported | estimated | unknown, plus the range used for filtering
    salary_status: Mapped[str] = mapped_column(String(16), default="unknown")
    salary_estimate: Mapped[dict | None] = mapped_column(JSONB)
    effective_salary_min: Mapped[int | None] = mapped_column(BigInteger)
    effective_salary_max: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = _now_col()
    last_seen_at: Mapped[datetime] = _now_col()
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="active")
    content_hash: Mapped[str] = mapped_column(String(64))
    is_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    # Normalised company+title+city: same job posted on two sites shares it.
    dedup_key: Mapped[str | None] = mapped_column(String(128))
    missing_checks: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    search_text: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship()
    company: Mapped[Company | None] = relationship()
    categories: Mapped[list["JobCategory"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
    skills: Mapped[list["JobSkill"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )


class JobCategory(Base):
    __tablename__ = "job_categories"
    __table_args__ = (Index("ix_job_categories_category", "category", "subcategory"),)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    subcategory: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    method: Mapped[str] = mapped_column(String(16), default="rules")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    job: Mapped[Job] = relationship(back_populates="categories")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (Index("ix_job_skills_skill", "skill"),)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    skill: Mapped[str] = mapped_column(String(80), primary_key=True)
    skill_type: Mapped[str] = mapped_column(String(16), default="required")  # required | optional
    origin: Mapped[str] = mapped_column(String(16), default="extracted")  # structured | extracted | llm
    job: Mapped[Job] = relationship(back_populates="skills")


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = _now_col()
    source_run_id: Mapped[int | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"))


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_type_created", "event_type", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    diff: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Baseline events (first crawl of a source) are recorded but never notified.
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    source_run_id: Mapped[int | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _now_col(index=True)
    job: Mapped[Job] = relationship()


class JobAnalysis(Base):
    __tablename__ = "job_analyses"
    __table_args__ = (Index("ix_job_analyses_current", "job_id", "is_current"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    engine: Mapped[str] = mapped_column(String(16))  # rules | claude | ollama
    model: Mapped[str | None] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    seniority: Mapped[str | None] = mapped_column(String(16))
    seniority_confidence: Mapped[float | None] = mapped_column(Float)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_col()


class SalaryDataset(Base):
    __tablename__ = "salary_datasets"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_salary_dataset_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    data_year: Mapped[int] = mapped_column(Integer)  # Solar Hijri year, e.g. 1405
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = _now_col()


class SalaryBenchmark(Base):
    __tablename__ = "salary_benchmarks"
    __table_args__ = (Index("ix_salary_bench_lookup", "category", "seniority", "city"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("salary_datasets.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    role_title: Mapped[str | None] = mapped_column(String(200))
    seniority: Mapped[str | None] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(String(120))
    employment_type: Mapped[str | None] = mapped_column(String(32))
    min_years: Mapped[float | None] = mapped_column(Float)
    max_years: Mapped[float | None] = mapped_column(Float)
    salary_min: Mapped[int] = mapped_column(BigInteger)  # monthly, toman
    salary_max: Mapped[int] = mapped_column(BigInteger)
    salary_median: Mapped[int | None] = mapped_column(BigInteger)
    sample_size: Mapped[int | None] = mapped_column(Integer)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_saved_search_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now_col()
    updated_at: Mapped[datetime] = _now_col(onupdate=func.now())


class NotificationSubscription(Base):
    __tablename__ = "notification_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    saved_search_id: Mapped[int | None] = mapped_column(
        ForeignKey("saved_searches.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(16))  # email | telegram
    event_types: Mapped[list] = mapped_column(ARRAY(String), default=lambda: ["NEW_JOB"])
    frequency: Mapped[str] = mapped_column(String(16), default="instant")  # instant | daily
    categories: Mapped[list] = mapped_column(ARRAY(String), default=list)
    min_match_score: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = _now_col()


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        # One message per user, channel and event - however many subscriptions match.
        UniqueConstraint("user_id", "channel", "job_event_id", name="uq_delivery_event"),
        UniqueConstraint("user_id", "channel", "digest_key", name="uq_delivery_digest"),
        Index("ix_deliveries_status", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_subscriptions.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(16))
    job_event_id: Mapped[int | None] = mapped_column(ForeignKey("job_events.id", ondelete="CASCADE"))
    digest_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|sent|failed|skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now_col()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramConnection(Base):
    __tablename__ = "telegram_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | active | revoked
    code_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now_col()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now_col(index=True)


class AppSetting(Base):
    """Runtime settings editable from the admin UI. Secrets live in encrypted_value."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONB)
    encrypted_value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _now_col(onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
