"""Shared throttled, cache-aware HTTP client for football-data.co.uk ingestion.

Two layers:

* ``ThrottledFetcher`` — the testable core. It enforces 0.4 s pacing between
  consecutive GETs, a within-run cache for immutable historical files,
  unconditional re-fetch for current-season/extra files, artifact-presence
  skip-existing, and bounded polite retry. The monotonic clock and sleep are
  injected so pacing is deterministic in tests (no real wall-clock sleeps).
* ``ThrottledHttpClient`` — a thin Dagster ``ConfigurableResource`` that builds a
  ``ThrottledFetcher`` over a real ``requests.Session`` (auto-instrumented by
  ``otel.py``). Build one per run so its pacing + cache are shared across that
  run's discovery page GETs and file GETs.

Cache/skip policy is keyed purely on **bronze-artifact presence** for historical
files (A-plan-2 / Q-refresh-keying) — no ETag/Last-Modified/content-hash.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

import requests
from dagster import ConfigurableResource

from ..config import settings
from .registry import Family
from .season import should_refetch


class FootballFetchError(RuntimeError):
    """A source file could not be retrieved within the bounded retry budget."""

    def __init__(self, url: str, attempts: int) -> None:
        super().__init__(f"failed to fetch {url} after {attempts} attempt(s)")
        self.url = url
        self.attempts = attempts


class ThrottledFetcher:
    """Polite, cache-aware GET layer with deterministic (injectable) pacing."""

    def __init__(
        self,
        *,
        session: requests.Session,
        throttle_seconds: float,
        max_retries: int,
        timeout: float,
        user_agent: str,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._throttle = throttle_seconds
        self._max_retries = max(1, max_retries)
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._cache: dict[str, bytes] = {}

    def _pace(self) -> None:
        """Block until at least ``throttle`` seconds have passed since the last GET."""
        if self._last_request_at is not None:
            wait = self._throttle - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def get_bytes(self, url: str) -> bytes:
        """Paced, bounded-retry GET. Raises FootballFetchError on persistent failure."""
        last_exc: Exception | None = None
        for _ in range(self._max_retries):
            self._pace()
            try:
                resp = self._session.get(url, timeout=self._timeout, headers=self._headers)
                resp.raise_for_status()
                return resp.content
            except requests.RequestException as exc:  # transient: retry within limits
                last_exc = exc
        raise FootballFetchError(url, self._max_retries) from last_exc

    def get_text(self, url: str) -> str:
        """Fetch a discovery page as text (HTML hrefs are ASCII; decode leniently)."""
        return self.get_bytes(url).decode("utf-8", errors="replace")

    def fetch_source(
        self,
        *,
        url: str,
        family: Family,
        season_token: str | None,
        run_date: date,
        artifact_path: Path | None,
    ) -> bytes | None:
        """Fetch a source CSV honouring cache + skip-existing policy.

        Returns the file bytes, or ``None`` when an already-landed immutable
        historical file should be skipped (no network call made).
        """
        if should_refetch(family, season_token, run_date):
            # Current-season / extra: always fetch fresh; never cache or skip.
            return self.get_bytes(url)

        # Historical / immutable.
        if artifact_path is not None and artifact_path.exists():
            return None  # skip-existing: artifact already landed
        if url in self._cache:
            return self._cache[url]  # within-run reuse
        content = self.get_bytes(url)
        self._cache[url] = content
        return content


class ThrottledHttpClient(ConfigurableResource):
    """Dagster resource exposing a freshly-built ThrottledFetcher per run."""

    base_url: str = settings.football_base_url
    throttle_seconds: float = settings.football_throttle_seconds
    max_retries: int = settings.football_max_retries
    timeout: float = settings.football_request_timeout
    user_agent: str = settings.football_user_agent

    def build_fetcher(self) -> ThrottledFetcher:
        return ThrottledFetcher(
            session=requests.Session(),
            throttle_seconds=self.throttle_seconds,
            max_retries=self.max_retries,
            timeout=self.timeout,
            user_agent=self.user_agent,
        )


__all__ = ["ThrottledFetcher", "ThrottledHttpClient", "FootballFetchError"]
