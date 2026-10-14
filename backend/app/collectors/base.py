"""Source adapter contract. A new job board = one module implementing SourceAdapter
and one line in registry.py."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field

from app.collectors.http import FetchResult, PoliteClient


class RawJob(BaseModel):
    """What an adapter extracts from one job page - before enrichment/AI."""

    source_job_id: str
    canonical_url: str
    title: str
    company_name: str | None = None
    company_profile_url: str | None = None
    company_website: str | None = None
    company_size: str | None = None
    company_industry: str | None = None
    company_description: str | None = None
    company_logo_url: str | None = None
    city: str | None = None
    province: str | None = None
    work_mode: str | None = None  # onsite | hybrid | remote
    employment_type: str | None = None  # full_time | part_time | contract | internship
    seniority_hint: str | None = None
    experience_required: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    description: str = ""
    benefits: list[str] = Field(default_factory=list)
    salary_original: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    source_categories: list[str] = Field(default_factory=list)
    is_expired: bool = False
    extra: dict = Field(default_factory=dict)


@dataclass
class Candidate:
    source_job_id: str
    url: str
    lastmod: datetime | None = None
    hint_title: str | None = None


@dataclass
class Discovery:
    candidates: list[Candidate]
    listed_total: int  # how many ads the listing exposed before our relevance filter
    coverage_note: str
    errors: list[str] = field(default_factory=list)
    # Every ad id the listing exposes (before our relevance filter), when known.
    all_listed_ids: set[str] | None = None


@dataclass
class PageOutcome:
    status: str  # active | expired | gone | not_job
    job: RawJob | None = None


class SourceAdapter(ABC):
    key: str
    name: str
    host: str
    base_url: str
    access_method: str
    limitations: str
    default_config: dict = {}
    min_interval_minutes: int = 60
    # True when discovery sees every live ad (sitemap); absence then means removal.
    complete_listing: bool = False

    def client(self) -> PoliteClient:
        return PoliteClient(host=self.host)

    @abstractmethod
    def discover(self, client: PoliteClient, config: dict, state: dict) -> Discovery: ...

    @abstractmethod
    def parse_job(self, page: FetchResult) -> PageOutcome: ...

    @abstractmethod
    def job_url(self, source_job_id: str, canonical_url: str) -> str: ...
