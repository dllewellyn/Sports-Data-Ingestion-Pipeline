"""Throttled HTTP client for ESPN soccer ingestion (mirrors the football client).

Two layers:

* ``ThrottledFetcher`` — the testable core. It enforces polite pacing between
  consecutive GETs and a bounded retry budget, decoding each response as JSON. The
  monotonic clock and sleep are injected so pacing is deterministic in tests (no
  real wall-clock sleeps). ESPN requires a browser ``User-Agent`` or it
  rejects/throttles requests, so one is always sent.
* ``ThrottledHttpClient`` — a thin Dagster ``ConfigurableResource`` that builds a
  ``ThrottledFetcher`` over a real ``requests.Session`` (auto-instrumented by
  ``otel.py``). Build one per run so its pacing is shared across that run's GETs.

ESPN scoreboard payloads are always re-fetched (the unit is overwritten with the
latest scoreboard each run), so there is no cache/skip-existing layer here.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import requests
from dagster import ConfigurableResource

from ..config import settings


class EspnFetchError(RuntimeError):
    """An ESPN endpoint could not be retrieved within the bounded retry budget."""

    def __init__(self, url: str, attempts: int) -> None:
        super().__init__(f"failed to fetch {url} after {attempts} attempt(s)")
        self.url = url
        self.attempts = attempts


class ThrottledFetcher:
    """Polite, bounded-retry JSON GET layer with deterministic (injectable) pacing."""

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

    def _pace(self) -> None:
        """Block until at least ``throttle`` seconds have passed since the last GET."""
        if self._last_request_at is not None:
            wait = self._throttle - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def get_json(self, url: str) -> dict:
        """Paced, bounded-retry GET decoded as JSON. Raises EspnFetchError on failure."""
        last_exc: Exception | None = None
        for _ in range(self._max_retries):
            self._pace()
            try:
                resp = self._session.get(url, timeout=self._timeout, headers=self._headers)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:  # transient / bad body
                last_exc = exc
        raise EspnFetchError(url, self._max_retries) from last_exc


class ThrottledHttpClient(ConfigurableResource):
    """Dagster resource exposing a freshly-built ThrottledFetcher per run."""

    core_base_url: str = settings.espn_core_base_url
    site_base_url: str = settings.espn_site_base_url
    throttle_seconds: float = settings.espn_throttle_seconds
    max_retries: int = settings.espn_max_retries
    timeout: float = settings.espn_request_timeout
    user_agent: str = settings.espn_user_agent

    def build_fetcher(self) -> ThrottledFetcher:
        return ThrottledFetcher(
            session=requests.Session(),
            throttle_seconds=self.throttle_seconds,
            max_retries=self.max_retries,
            timeout=self.timeout,
            user_agent=self.user_agent,
        )


__all__ = ["ThrottledFetcher", "ThrottledHttpClient", "EspnFetchError"]
