"""Shared pytest configuration.

Tests import the code location from ``src/`` (the project is not installed as a
wheel — ``[tool.uv] package = false``). ``pyproject.toml`` sets
``pythonpath = ["src"]`` so ``uv run pytest`` works without an env var; we also
honour the documented ``PYTHONPATH=src uv run pytest`` invocation.
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
def _silence_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default unit tests to a no-op tracer so they never configure a real OTLP
    exporter or attempt network export. Tests that assert on spans override this
    with their own monkeypatch of the same target."""
    monkeypatch.setattr("data_platform.football.ingest.get_tracer", lambda *a, **k: _NoOpTracer())
