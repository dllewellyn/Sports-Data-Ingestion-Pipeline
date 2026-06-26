"""Shared fakes for football asset/integration tests.

`fetcher_factory` builds a REAL ThrottledFetcher (so cache/skip-existing/retry are
exercised for real) over a fake session that serves a URL→bytes map and counts
GETs. Pacing uses a fake clock, so there are no real sleeps.
"""

import pytest
import requests

from data_platform.football.http_client import ThrottledFetcher


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class MapSession:
    """Serves a URL→bytes map; records every GET; 404s unknown URLs."""

    def __init__(self, content_by_url: dict[str, bytes]) -> None:
        self.content_by_url = content_by_url
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append(url)
        try:
            return _Response(self.content_by_url[url])
        except KeyError as exc:
            raise requests.HTTPError(f"404 {url}") from exc


@pytest.fixture
def fetcher_factory():
    def make(content_by_url: dict[str, bytes], *, max_retries: int = 1):
        session = MapSession(content_by_url)
        clock = _Clock()
        fetcher = ThrottledFetcher(
            session=session,
            throttle_seconds=0.0,
            max_retries=max_retries,
            timeout=5.0,
            user_agent="test-agent",
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
        return fetcher, session

    return make
