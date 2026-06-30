"""S13 — Guard: no `from __future__ import annotations` in assets/*.py.

Dagster introspects context/return annotations at runtime; stringized
annotations (PEP 563 / __future__ annotations) cause
DagsterInvalidDefinitionError. This AST scan prevents accidental
re-introduction (CLAUDE.md non-obvious constraint).
"""

import ast
from pathlib import Path

ASSETS_DIR = Path(__file__).parents[1] / "src" / "data_platform" / "assets"


def _has_future_annotations(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(alias.name == "annotations" for alias in node.names)
        ):
            return True
    return False


def test_no_future_annotations_in_assets() -> None:
    """No asset module may use 'from __future__ import annotations'."""
    offenders = [p.name for p in sorted(ASSETS_DIR.glob("*.py")) if _has_future_annotations(p)]
    assert not offenders, (
        f"Assets with 'from __future__ import annotations' (breaks Dagster runtime "
        f"annotation introspection): {offenders}"
    )
