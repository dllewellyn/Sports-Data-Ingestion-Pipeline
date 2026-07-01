"""result.py — emit one audit result into telemetry, fire-and-forget (FR-011 / FR-012).

Maps an :class:`audit.AuditResult` onto a single ``emit.send_logs`` log record
(data-model.md §5). ``run_id``/``feature`` travel as RESOURCE attrs (the existing Loki
index labels, set by ``send_logs``); ``event_type="audit_result"``, the ``audit`` name,
the ``verdict``, every declared metadata key, and (on fail/warn) the ``evidence`` ride as
PER-RECORD attrs (Loki structured metadata, LogQL-filterable via ``| audit="…"``). No new
index label is added — ``loki-config.yaml`` is untouched (clarify Q1 / Assumptions).

Emission is FIRE-AND-FORGET (FR-012 / Edge E7 / SC-005): any failure — a collector outage,
a missing run context — is swallowed so it can never change a verdict or the runner's
verdict-driven exit status (mirrors ``emit.py``'s own harmless-absence contract).
"""

import contextlib
import json

import emit

# Bound the emitted evidence string so a large evidence dict cannot bloat the record.
MAX_EVIDENCE_LEN = 2000


def _evidence_str(evidence):
    """Render evidence to a bounded, readable string (data-model §5 — bounded string form)."""
    if evidence is None:
        return None
    try:
        text = json.dumps(evidence, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(evidence)
    return text[:MAX_EVIDENCE_LEN]


def _record_attrs(result):
    """Per-record structured-metadata attrs for one AuditResult (data-model §5)."""
    attrs = [
        ("event_type", "audit_result"),
        ("audit", result.audit_name),
        ("verdict", result.verdict),
    ]
    # Author-declared metadata (severity/category/owner/…) — each its own attr.
    for key, value in (result.metadata or {}).items():
        attrs.append((key, str(value)))
    evidence = _evidence_str(result.evidence)
    if evidence is not None:
        attrs.append(("evidence", evidence))
    if result.error_detail:
        attrs.append(("error_detail", result.error_detail))
    return attrs


def emit_result(result, endpoint=None):
    """Emit one AuditResult into Loki via ``emit.send_logs`` — fire-and-forget.

    ``run_id``/``feature`` become resource attrs (index labels); the audit name, verdict,
    metadata, and evidence become per-record structured metadata. Every error is swallowed
    (FR-012) so emission can never alter a verdict or the runner's exit status. ``endpoint``
    is accepted for signature parity with the runner's call site; the emit collector is
    configured through ``emit.py``'s own env, so it is intentionally unused here.
    """
    with contextlib.suppress(Exception):
        ctx = emit.current_context()
        trace_id = result.__dict__.get("trace_id") or ctx.get("trace_id") or ""
        run_id = result.run_id or ctx.get("run_id") or ""
        emit.send_logs(
            trace_id=trace_id,
            run_id=run_id,
            feature=result.feature or None,
            records=[
                {
                    "body": f"audit {result.audit_name} -> {result.verdict.upper()}",
                    "severity": "ERROR" if result.verdict in ("fail", "error") else "INFO",
                    "attrs": _record_attrs(result),
                }
            ],
        )
