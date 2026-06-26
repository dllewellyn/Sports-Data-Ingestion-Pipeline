"""Shared pytest configuration.

Tests import the code location from ``src/`` (the project is not installed as a
wheel — ``[tool.uv] package = false``). ``pyproject.toml`` sets
``pythonpath = ["src"]`` so ``uv run pytest`` works without an env var; we also
honour the documented ``PYTHONPATH=src uv run pytest`` invocation.
"""
