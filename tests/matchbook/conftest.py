"""Matchbook test isolation.

Silences the matchbook ingest OTel tracer so tests don't need a live collector.
Tests that assert on spans override this target with their own monkeypatch.
"""

import pytest


class _NoOpSpan:
    def set_attribute(self, *args, **kwargs) -> None: ...

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args) -> bool:
        return False


class _NoOpTracer:
    def start_as_current_span(self, *args, **kwargs) -> _NoOpSpan:
        return _NoOpSpan()


@pytest.fixture(autouse=True)
def _silence_matchbook_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        monkeypatch.setattr(
            "data_platform.matchbook.ingest.get_tracer", lambda *a, **k: _NoOpTracer()
        )
    except (ImportError, AttributeError):
        # ingest module not yet present (e.g. during S1 contract tests before S2)
        pass
