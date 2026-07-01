"""runner.py — discover, evaluate, print, and emit code-defined audit checks.

The path-invoked entry point for the ``@audit`` framework (contracts/audit-api.md
§Runner). Invoked BY PATH, mirroring ``emit.py`` (the repo's ``pyproject.toml`` sets
``[tool.uv] package = false`` — there is no console script)::

    uv run python .agents/skills/_shared/telemetry/audit/runner.py \\
        --run-id RUN --feature FEAT --path AUDIT_FILE [--loki-endpoint URL]

It prepends ``.agents/skills/_shared/telemetry`` (this package's parent dir) onto
``sys.path`` so an audit file's bare ``from audit import audit, AuditFailure`` resolves,
imports the configured ``--path`` audit file so its ``@audit`` decorations populate the
registry, then evaluates EVERY discovered audit (plus the built-in flagship
``all_changed_files_code_reviewed``). Each audit runs ISOLATED in its own try/except
(FR-007 — one audit raising ``error`` never stops the rest); the per-audit verdict +
evidence prints locally (US1 — readable without Grafana) and each result is emitted
fire-and-forget into Loki (FR-011/FR-012, via ``audit.result.emit_result``).

Exit status (FR-014 / R2): any ``fail`` OR ``error`` ⇒ ``1``; only ``pass``/``warn`` ⇒
``0``; NO audits discovered ⇒ ``2`` (distinct from "all passed" — Edge E1).
"""

import argparse
import importlib.util
import os
import sys
from pathlib import Path

# --- sys.path injection (before importing the framework) ------------------- #
# This module lives at .agents/skills/_shared/telemetry/audit/runner.py; its
# grandparent (.agents/skills/_shared/telemetry) is the dir an audit file's bare
# `from audit import …` and this module's `import audit`/`import emit` resolve from —
# exactly as the hooks insert the shared telemetry dir. Insert it FIRST so a
# subprocess launched by path (with no PYTHONPATH) can still import the framework.
_TELEMETRY_DIR = Path(__file__).resolve().parent.parent
if str(_TELEMETRY_DIR) not in sys.path:
    sys.path.insert(0, str(_TELEMETRY_DIR))

import audit as audit_framework  # noqa: E402 — must follow the sys.path injection above
from audit import AuditFailure, audit  # noqa: E402
from audit.query import FeatureRunQuery  # noqa: E402
from audit.result import emit_result  # noqa: E402

# Exit codes (R2 / FR-014).
EXIT_OK = 0
EXIT_VERDICT_FAILED = 1
EXIT_NO_AUDITS = 2

# Verdicts that make the runner exit non-zero.
_FAILING_VERDICTS = frozenset({"fail", "error"})


@audit(name="all_changed_files_code_reviewed", severity="high", category="review-integrity")
def all_changed_files_code_reviewed(run):
    """Flagship: every file changed across the run's diffs was read by the code-review agent.

    Diff-minus-reviewed (SC-002). An empty change set is a vacuous ``pass`` (Edge E3 —
    nothing left unreviewed). An UNKNOWN run makes the query helpers raise
    ``UnknownRunError``, which the runner isolates into the distinct ``error`` verdict
    (Edge E2) — deliberately NOT caught here, so it is never a false ``pass``.
    """
    reviewed = run.get_all_reads_from_code_review_agent()
    unreviewed = sorted(f for f in run.all_diffs_for_feature() if f not in reviewed)
    if unreviewed:
        raise AuditFailure(evidence={"unreviewed_files": unreviewed})


# Audits the runner ships itself (registered above at import time). ``--no-builtins``
# excludes these from discovery so "no audits discovered" (Edge E1) is testable
# independently of the always-on flagship.
_BUILTIN_AUDIT_NAMES = frozenset({"all_changed_files_code_reviewed"})


def _import_audit_file(path):
    """Import the audit file at ``path`` so its ``@audit`` decorations register.

    Loaded under a throwaway module name via importlib so any filename works; the
    framework's sys.path entry is already set, so the file's ``from audit import …``
    resolves. Registration happens as a side effect of import.
    """
    resolved = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("_audit_under_test", resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load audit file: {resolved}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _format_verdict(result):
    """One human-readable line per audit verdict (+ evidence/detail), for local output."""
    line = f"audit {result.audit_name} -> {result.verdict.upper()}"
    if result.verdict == "fail" and result.evidence is not None:
        line += f"  evidence={result.evidence}"
    elif result.verdict == "warn" and result.evidence is not None:
        line += f"  note={result.evidence}"
    elif result.verdict == "error" and result.error_detail:
        line += f"  error={result.error_detail}"
    return line


def run_audits(run_id, feature, audit_path, endpoint, include_builtins=True):
    """Discover, evaluate, print, and emit every audit; return the exit code (R2).

    ``include_builtins`` (default True) keeps the runner's built-in audits (the flagship);
    ``--no-builtins`` sets it False so only the ``--path`` file's audits are discovered.
    """
    if audit_path:
        _import_audit_file(audit_path)

    checks = [
        check
        for check in audit_framework.registry
        if include_builtins or check.name not in _BUILTIN_AUDIT_NAMES
    ]
    if not checks:
        print("no audits discovered")
        return EXIT_NO_AUDITS

    run = FeatureRunQuery(run_id=run_id, feature=feature, endpoint=endpoint)

    exit_code = EXIT_OK
    for check in checks:
        result = audit_framework.evaluate(check, run)
        print(_format_verdict(result))
        # Fire-and-forget emission (S5/T017) — swallows all errors, so a telemetry
        # outage never changes the verdict or the verdict-driven exit status (FR-012).
        emit_result(result, endpoint=endpoint)
        if result.verdict in _FAILING_VERDICTS:
            exit_code = EXIT_VERDICT_FAILED
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run code-defined @audit checks over a feature run."
    )
    parser.add_argument("--run-id", dest="run_id", default="")
    parser.add_argument("--feature", dest="feature", default="")
    parser.add_argument("--path", dest="path", default="")
    parser.add_argument("--loki-endpoint", dest="loki_endpoint", default="")
    parser.add_argument(
        "--no-builtins",
        dest="include_builtins",
        action="store_false",
        help="do not register the runner's built-in audits (e.g. the flagship)",
    )
    args = parser.parse_args(argv)

    run_id = args.run_id or os.environ.get("FEATURE_RUN_ID") or None
    feature = args.feature or None
    endpoint = args.loki_endpoint or os.environ.get("FEATURE_LOKI_HTTP_ENDPOINT") or None

    exit_code = run_audits(
        run_id, feature, args.path, endpoint, include_builtins=args.include_builtins
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
