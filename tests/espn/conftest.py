"""ESPN test isolation (F1).

The repo-wide ``_silence_otel`` fixture only patches the football engine's
``get_tracer``; ESPN tests would otherwise hit a real tracer/exporter. This
autouse fixture defaults the ESPN ingest engine to a no-op tracer. Tests that
assert on spans override this target with their own monkeypatch.
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
def _silence_espn_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("data_platform.espn.ingest.get_tracer", lambda *a, **k: _NoOpTracer())
