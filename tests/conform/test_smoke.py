"""Smoke test proving the new tests/conform/ directory is collected by pytest.

Written RED first (asserting False) to confirm collection, then flipped green.
"""


def test_placeholder_fails() -> None:
    assert True
