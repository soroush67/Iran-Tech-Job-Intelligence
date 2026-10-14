"""Polite HTTP client for collectors.

* robots.txt is fetched once per run and every URL is checked against it
  (urllib.robotparser) before any request - a disallowed URL is never fetched.
* One request at a time per source with a minimum delay (and the robots
  Crawl-delay if larger).
* Retries with exponential backoff on 5xx / timeouts; 429 honours Retry-After.
* 403 / 429 storms and CAPTCHA pages mark the run as *blocked* - we stop,
  we never try to get around it.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from app.config import get_settings

log = structlog.get_logger()

ALLOWED_HOSTS = {"jobinja.ir", "jobvision.ir"}

CAPTCHA_MARKERS = ("g-recaptcha", "hcaptcha", "cf-challenge", "captcha-container", "arvancloud challenge",
                   "لطفا کد امنیتی")


class BlockedError(Exception):
    """The source refused us (403/429 storm or CAPTCHA). Stop the run."""


class DisallowedError(Exception):
    """robots.txt disallows the URL."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    headers: dict
    content: bytes = b""


@dataclass
class PoliteClient:
    host: str
    delay: float | None = None
    timeout: float | None = None
    max_retries: int = 3
    status_counts: dict = field(default_factory=dict)
    _robots: RobotFileParser | None = None
    _last: float = 0.0
    _blocked_hits: int = 0

    def __post_init__(self):
        s = get_settings()
        if self.host not in ALLOWED_HOSTS:
            raise ValueError(f"host {self.host!r} is not an allowed source host")
        self.delay = s.collector_request_delay_seconds if self.delay is None else self.delay
        self.timeout = s.collector_timeout_seconds if self.timeout is None else self.timeout
        self.user_agent = s.collector_user_agent
        self.backoff_factor = s.collector_backoff_factor
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.6"},
            timeout=self.timeout,
            follow_redirects=True,
            proxy=s.collector_proxy or None,
        )

    def close(self):
        self._client.close()

    # -- robots -------------------------------------------------------------
    def load_robots(self) -> str:
        url = f"https://{self.host}/robots.txt"
        resp = self._client.get(url)
        self._count(resp.status_code)
        rp = RobotFileParser()
        rp.set_url(url)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        elif resp.status_code in (401, 403):
            rp.disallow_all = True
        else:
            rp.allow_all = True
        self._robots = rp
        cd = rp.crawl_delay(self.user_agent) or rp.crawl_delay("*")
        if cd and float(cd) > (self.delay or 0):
            self.delay = float(cd)
        self._last = time.monotonic()
        return resp.text if resp.status_code == 200 else f"HTTP {resp.status_code}"

    def allowed(self, url: str) -> bool:
        if self._robots is None:
            self.load_robots()
        assert self._robots is not None
        return self._robots.can_fetch(self.user_agent, url) and self._robots.can_fetch("*", url)

    # -- fetching -----------------------------------------------------------
    def _count(self, status: int) -> None:
        self.status_counts[str(status)] = self.status_counts.get(str(status), 0) + 1

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last
        wait = (self.delay or 0) - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.3))

    def get(self, url: str, *, check_robots: bool = True, extra_headers: dict | None = None) -> FetchResult:
        if urlsplit(url).hostname not in {self.host, f"www.{self.host}"}:
            raise ValueError(f"refusing to fetch off-source URL {url}")
        if check_robots and not self.allowed(url):
            raise DisallowedError(url)
        attempt = 0
        while True:
            self._wait()
            attempt += 1
            try:
                resp = self._client.get(url, headers=extra_headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                self._last = time.monotonic()
                self._count(0)
                if attempt > self.max_retries:
                    raise
                backoff = min(60, 2 ** attempt) * self.backoff_factor
                log.warning("fetch_retry", url=url, error=str(exc), backoff=backoff)
                time.sleep(backoff)
                continue
            self._last = time.monotonic()
            self._count(resp.status_code)
            if resp.status_code == 429 or resp.status_code == 403:
                self._blocked_hits += 1
                if self._blocked_hits >= 3:
                    raise BlockedError(f"HTTP {resp.status_code} repeatedly from {self.host}")
                retry_after = resp.headers.get("Retry-After", "")
                backoff = (int(retry_after) if retry_after.isdigit() else min(120, 10 * 2 ** attempt)) * self.backoff_factor
                if attempt > self.max_retries:
                    raise BlockedError(f"HTTP {resp.status_code} from {self.host}")
                log.warning("fetch_throttled", url=url, status=resp.status_code, backoff=backoff)
                time.sleep(backoff)
                continue
            if resp.status_code >= 500 and attempt <= self.max_retries:
                time.sleep(min(60, 2 ** attempt) * self.backoff_factor)
                continue
            body = resp.text if resp.status_code < 400 or resp.status_code in (404, 410) else ""
            low = body[:20000].lower()
            if any(m in low for m in CAPTCHA_MARKERS):
                raise BlockedError(f"CAPTCHA/anti-bot page served by {self.host}")
            self._blocked_hits = 0
            return FetchResult(url, str(resp.url), resp.status_code, body, dict(resp.headers), resp.content)
