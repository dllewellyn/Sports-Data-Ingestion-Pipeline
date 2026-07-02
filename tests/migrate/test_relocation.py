"""Relocation guard: the Postgres migration engines moved to the neutral
`data_platform.migrate` package. The old provider-scoped modules
(`data_platform.espn.migrate_from_postgres`,
`data_platform.matchbook.migrate_from_postgres`) must no longer exist
(constitution I — no backward-compat shim), and each engine's `run_*` entry
point must import from its new home.
"""

import pytest


def test_old_espn_migration_module_gone() -> None:
    """The old ESPN migration module is deleted outright — no shim, no alias."""
    with pytest.raises(ModuleNotFoundError):
        import data_platform.espn.migrate_from_postgres  # noqa: F401


def test_old_matchbook_migration_module_gone() -> None:
    """The old Matchbook migration module is deleted outright — no shim, no alias."""
    with pytest.raises(ModuleNotFoundError):
        import data_platform.matchbook.migrate_from_postgres  # noqa: F401


def test_espn_migration_importable_from_neutral_package() -> None:
    """`run_espn_postgres_migration` is importable from the relocated package."""
    from data_platform.migrate.espn import run_espn_postgres_migration

    assert callable(run_espn_postgres_migration)


def test_matchbook_migration_importable_from_neutral_package() -> None:
    """`run_matchbook_postgres_migration` is importable from the relocated package."""
    from data_platform.migrate.matchbook import run_matchbook_postgres_migration

    assert callable(run_matchbook_postgres_migration)
