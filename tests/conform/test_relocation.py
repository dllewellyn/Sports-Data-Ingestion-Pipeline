"""Relocation guard (T008): the Matchbook conform engine moved to the neutral
`data_platform.conform` package. The old `data_platform.matchbook.conform` must
no longer exist (constitution I — no backward-compat shim), and the engine's
public surface must import from its new home.
"""

import pytest


def test_old_matchbook_conform_module_gone() -> None:
    """The old package is deleted outright — no shim, no re-export, no alias."""
    with pytest.raises(ModuleNotFoundError):
        import data_platform.matchbook.conform  # noqa: F401


def test_conform_engine_importable_from_neutral_package() -> None:
    """`run_conform` is importable from the relocated neutral package."""
    from data_platform.conform.matchbook import run_conform

    assert callable(run_conform)
