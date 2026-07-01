"""Audit-trail check framework — the ``@audit`` decorator, registry, and evaluator.

Audit authors import this package as ``from audit import audit, AuditFailure,
AuditWarning`` (the runner prepends ``.agents/skills/_shared/telemetry`` onto
``sys.path`` before importing a configured audit file, exactly as the hooks do for
``import emit``; contracts/audit-api.md §Importability). Stdlib-only, module-docstring
house style mirrors ``emit.py`` — no third-party deps, no pydantic.

Surface (contracts/audit-api.md §Decorator / §Failure signalling; data-model.md §1/§2):

  * ``audit(_func=None, *, name=None, **metadata)`` — usable bare (``@audit``) or called
    (``@audit(name=..., severity=...)``). ``name`` defaults to ``func.__name__``; a
    duplicate ``name`` raises :class:`AuditNameCollision` at decoration time (Edge E4).
    All ``metadata`` values are coerced to ``str`` (data-model §1). The decorator returns
    the original function unchanged (it stays callable) and registers an :class:`AuditCheck`.
  * ``registry`` — a module-level :class:`AuditRegistry` that iterates over the registered
    :class:`AuditCheck` objects (not names), and exposes ``get(name)`` and ``clear()``.
  * :class:`AuditFailure` / :class:`AuditWarning` — the failure-signalling exceptions
    carrying ``.evidence``; :class:`AuditNameCollision` — the duplicate-name registration error.
  * ``evaluate(check, run=None)`` — evaluate ONE :class:`AuditCheck` against a run handle
    and derive an :class:`AuditResult` per the data-model §2 verdict table.

This module stays free of heavy imports (no ``query.py`` import at top level) so
``from audit.query import FeatureRunQuery`` keeps resolving without a circular import or
forcing any Loki config at package-import time — the decorator/registry/verdicts are pure
Python and independent of ``query.py``.
"""

import time
from dataclasses import dataclass, field

# error_detail is bounded (data-model §2 — "Bounded in size") so a huge traceback-shaped
# exception string can never blow up the emitted record.
MAX_ERROR_DETAIL = 500


class AuditFailure(Exception):
    """Raised by an audit body to signal a deterministic ``fail`` (FR-001/FR-004).

    Carries ``.evidence`` — the concrete explanation (e.g. ``{"unreviewed_files": [...]}``)
    surfaced on the resulting :class:`AuditResult` (FR-005).
    """

    def __init__(self, evidence=None):
        super().__init__(evidence)
        self.evidence = evidence


class AuditWarning(Exception):
    """Raised by an audit body to signal a non-fatal ``warn`` (Edge E8).

    Distinct from pass/fail/error. ``.evidence`` is optional (may be ``None``).
    """

    def __init__(self, evidence=None):
        super().__init__(evidence)
        self.evidence = evidence


class AuditNameCollision(Exception):
    """Raised at decoration time when a second audit reuses an existing name (Edge E4)."""


@dataclass
class AuditCheck:
    """A registered audit: the decorated function plus its metadata (data-model §1)."""

    name: str
    func: object
    metadata: dict


@dataclass
class AuditResult:
    """The outcome of evaluating one :class:`AuditCheck` against one run (data-model §2)."""

    audit_name: str
    verdict: str
    evidence: object = None
    error_detail: object = None
    run_id: str = ""
    feature: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp_ns: int = field(default_factory=time.time_ns)


class AuditRegistry:
    """Module-level registry of :class:`AuditCheck` objects.

    Iterates over the registered checks (NOT their names — a bare dict would iterate keys),
    so ``{check.name for check in registry}`` works. Exposes ``get(name)`` and ``clear()``.
    """

    def __init__(self):
        self._checks = {}

    def register(self, check):
        """Register ``check``; refuse a duplicate name deterministically (Edge E4)."""
        if check.name in self._checks:
            raise AuditNameCollision(check.name)
        self._checks[check.name] = check

    def get(self, name):
        return self._checks.get(name)

    def clear(self):
        self._checks.clear()

    def __iter__(self):
        return iter(self._checks.values())

    def __len__(self):
        return len(self._checks)


registry = AuditRegistry()


def audit(_func=None, *, name=None, **metadata):
    """Register an audit check. Usable bare (``@audit``) or called (``@audit(name=...)``).

    ``name`` defaults to the wrapped function's ``__name__``. ``metadata`` is an open
    key/value set (FR-002) whose values are all coerced to ``str`` (data-model §1). A
    duplicate ``name`` raises :class:`AuditNameCollision` at decoration time (Edge E4).
    Returns the original function unchanged so it stays directly callable.
    """
    coerced_metadata = {key: str(value) for key, value in metadata.items()}

    def _decorate(func):
        check_name = name if name is not None else func.__name__
        registry.register(AuditCheck(name=check_name, func=func, metadata=coerced_metadata))
        return func

    if _func is not None:
        # Bare usage: @audit (the function is passed positionally, no metadata/name).
        return _decorate(_func)
    return _decorate


def evaluate(check, run=None):
    """Evaluate one :class:`AuditCheck` against ``run`` and derive an :class:`AuditResult`.

    Maps the body's outcome per data-model §2:
      * returns cleanly            ⇒ ``pass``  (evidence=None)
      * raises :class:`AuditFailure` ⇒ ``fail``  (evidence = exception's evidence)
      * raises :class:`AuditWarning` ⇒ ``warn``  (evidence = exception's evidence, may be None)
      * raises any other Exception ⇒ ``error`` (error_detail = bounded exception summary)

    An unexpected exception is NEVER coerced to pass/fail (Constitution IV / Edge E2).
    """
    common = {
        "audit_name": check.name,
        "metadata": dict(check.metadata),
        "run_id": getattr(run, "run_id", "") or "",
        "feature": getattr(run, "feature", "") or "",
    }
    try:
        check.func(run)
    except AuditFailure as exc:
        return AuditResult(verdict="fail", evidence=exc.evidence, **common)
    except AuditWarning as exc:
        return AuditResult(verdict="warn", evidence=exc.evidence, **common)
    except Exception as exc:  # the whole point: never coerce to pass/fail (Edge E2).
        detail = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_DETAIL]
        return AuditResult(verdict="error", error_detail=detail, **common)
    return AuditResult(verdict="pass", evidence=None, **common)
