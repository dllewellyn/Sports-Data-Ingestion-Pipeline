"""S4 — throttled, cache-aware HTTP fetcher.

Targets the testable core (`ThrottledFetcher`) with an injected fake session,
monotonic clock, and sleep, so pacing/cache/skip/retry are deterministic with no
real wall-clock sleeps. The Dagster `ThrottledHttpClient` resource is a thin wrapper
that builds this core with a real requests.Session.
"""

from datetime import date

import pytest
import requests

from data_platform.football.http_client import FootballFetchError, ThrottledFetcher
from data_platform.football.registry import Family

RUN_DATE = date(2026, 6, 26)  # current main season token = "2526"
CURRENT_URL = "https://www.football-data.co.uk/mmz4281/2526/E0.csv"
HISTORICAL_URL = "https://www.football-data.co.uk/mmz4281/9394/E0.csv"
EXTRA_URL = "https://www.football-data.co.uk/new/ARG.csv"


class FakeClock:
    """Monotonic clock that only advances when sleep() is called."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.content = content
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeSession:
    """Records GET calls; can be scripted to fail then succeed."""

    def __init__(self, *, content: bytes = b"data", fail_times: int = 0) -> None:
        self.content = content
        self.fail_times = fail_times
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(url)
        if len(self.calls) <= self.fail_times:
            raise requests.ConnectionError("transient boom")
        return FakeResponse(self.content)


def _fetcher(session: FakeSession, clock: FakeClock, *, max_retries: int = 3) -> ThrottledFetcher:
    return ThrottledFetcher(
        session=session,
        throttle_seconds=0.4,
        max_retries=max_retries,
        timeout=30.0,
        user_agent="test-agent",
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_pacing_enforced_between_requests() -> None:
    session, clock = FakeSession(), FakeClock()
    fetcher = _fetcher(session, clock)
    fetcher.get_bytes(HISTORICAL_URL)
    fetcher.get_bytes(CURRENT_URL)
    assert len(session.calls) == 2
    assert sum(clock.slept) >= 0.4, "a >=0.4s budget must elapse between consecutive GETs"


def test_within_run_cache_reuses_historical(tmp_path) -> None:
    session, clock = FakeSession(content=b"hist"), FakeClock()
    fetcher = _fetcher(session, clock)
    artifact = tmp_path / "9394_E0.parquet"  # not present → must fetch once
    kwargs = {
        "family": Family.MAIN,
        "season_token": "9394",
        "run_date": RUN_DATE,
        "artifact_path": artifact,
    }
    a = fetcher.fetch_source(url=HISTORICAL_URL, **kwargs)
    b = fetcher.fetch_source(url=HISTORICAL_URL, **kwargs)
    assert a == b == b"hist"
    assert len(session.calls) == 1, "historical file cached within the run"


def test_current_season_never_cached() -> None:
    session, clock = FakeSession(), FakeClock()
    fetcher = _fetcher(session, clock)
    kwargs = {
        "family": Family.MAIN,
        "season_token": "2526",
        "run_date": RUN_DATE,
        "artifact_path": None,
    }
    fetcher.fetch_source(url=CURRENT_URL, **kwargs)
    fetcher.fetch_source(url=CURRENT_URL, **kwargs)
    assert len(session.calls) == 2, "current-season files bypass the cache"


def test_skip_existing_historical_artifact(tmp_path) -> None:
    session, clock = FakeSession(), FakeClock()
    fetcher = _fetcher(session, clock)
    artifact = tmp_path / "9394_E0.parquet"
    artifact.write_bytes(b"already-landed")
    result = fetcher.fetch_source(
        url=HISTORICAL_URL,
        family=Family.MAIN,
        season_token="9394",
        run_date=RUN_DATE,
        artifact_path=artifact,
    )
    assert result is None, "already-landed historical file is skipped"
    assert session.calls == [], "no GET for a skipped historical file"


def test_current_season_not_skipped_even_if_artifact_exists(tmp_path) -> None:
    session, clock = FakeSession(), FakeClock()
    fetcher = _fetcher(session, clock)
    artifact = tmp_path / "2526_E0.parquet"
    artifact.write_bytes(b"stale")
    result = fetcher.fetch_source(
        url=CURRENT_URL,
        family=Family.MAIN,
        season_token="2526",
        run_date=RUN_DATE,
        artifact_path=artifact,
    )
    assert result == b"data", "current-season file is always re-fetched"
    assert len(session.calls) == 1


def test_extra_family_always_fetched_never_skipped(tmp_path) -> None:
    session, clock = FakeSession(), FakeClock()
    fetcher = _fetcher(session, clock)
    artifact = tmp_path / "ARG.parquet"
    artifact.write_bytes(b"old")
    kwargs = {
        "family": Family.EXTRA,
        "season_token": None,
        "run_date": RUN_DATE,
        "artifact_path": artifact,
    }
    fetcher.fetch_source(url=EXTRA_URL, **kwargs)
    fetcher.fetch_source(url=EXTRA_URL, **kwargs)
    assert len(session.calls) == 2, "extra files always re-fetched, never cached/skipped"


def test_transient_error_retried_then_succeeds() -> None:
    session, clock = FakeSession(fail_times=1), FakeClock()
    fetcher = _fetcher(session, clock, max_retries=3)
    assert fetcher.get_bytes(HISTORICAL_URL) == b"data"
    assert len(session.calls) == 2, "one transient failure then success"


def test_persistent_failure_raises_after_bounded_retries() -> None:
    session, clock = FakeSession(fail_times=99), FakeClock()
    fetcher = _fetcher(session, clock, max_retries=3)
    with pytest.raises(FootballFetchError):
        fetcher.get_bytes(HISTORICAL_URL)
    assert len(session.calls) == 3, "retry is bounded by max_retries (no infinite loop)"
