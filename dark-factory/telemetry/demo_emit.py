#!/usr/bin/env python3
"""demo_emit.py — emit one labelled custom span + log event through the telemetry stack.

A minimal, repeatable smoke test that the local telemetry pipeline (OTel collector ->
Tempo/Loki -> Grafana) is actually ingesting and that labels propagate. One run emits
exactly one OpenTelemetry span (destined for Tempo) and one matching log event
(destined for Loki), both carrying a user-supplied --label under the stable key
`demo.label`, then prints what it emitted and where so the developer knows what to
search for in Grafana.

Reuses `.agents/skills/_shared/telemetry/emit.py`'s `send_span` / `send_logs` rather
than re-implementing OTLP/HTTP; endpoint resolution (incl. the
FEATURE_OTLP_HTTP_ENDPOINT override) stays owned by emit.py. Zero third-party runtime
deps, consistent with emit.py's zero-dependency design.

Run: `python -m telemetry.demo_emit --label <name>`
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Reuse the real emitter — insert its dir onto sys.path idempotently, then import it.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EMIT_DIR = str(_REPO_ROOT / ".agents" / "skills" / "_shared" / "telemetry")
if _EMIT_DIR not in sys.path:
    sys.path.insert(0, _EMIT_DIR)
import emit  # noqa: E402 — import follows the sys.path insert above, by design

SPAN_NAME = "demo.emit"
DEFAULT_LABEL = "demo-emit"
LABEL_KEY = "demo.label"
EVENT_TYPE = "demo"


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m telemetry.demo_emit",
        description="Emit one labelled span (Tempo) + event (Loki) through emit.py.",
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help="Searchable label stamped on both signals under demo.label "
        f"(default: {DEFAULT_LABEL}).",
    )
    args = parser.parse_args(argv)
    if not args.label.strip():
        parser.error("--label must not be empty or whitespace-only")
    return args


def _resolve_ids():
    """Use the active feature-run's ids if present, else mint our own non-empty ones.

    A non-empty trace_id is mandatory: emit.send_span returns False on an empty one,
    which would look like an emission failure (FR-008) when none occurred. The minted
    run_id is shaped `demo-<hex>` — a space-free, valid Loki label value.
    """
    ctx = emit.current_context()
    trace_id = ctx.get("trace_id") or os.urandom(16).hex()
    run_id = ctx.get("run_id") or f"demo-{os.urandom(4).hex()}"
    span_id = os.urandom(8).hex()
    return trace_id, run_id, span_id


def main(argv=None):
    args = _parse_args(argv)
    label = args.label

    trace_id, run_id, span_id = _resolve_ids()
    now = time.time_ns()
    event_body = f"demo emit: {label}"

    # Each send is wrapped in its OWN try/except so a partial failure (one signal
    # accepted, the other not) is attributed to the right signal (FR-008, E2).
    failures = []

    try:
        span_ok = emit.send_span(
            trace_id=trace_id,
            run_id=run_id,
            name=SPAN_NAME,
            span_id=span_id,
            start_ns=now,
            end_ns=now,
            attrs=[(LABEL_KEY, label)],
            strict=True,
        )
        if not span_ok:
            failures.append("span (Tempo)")
    except Exception as exc:  # noqa: BLE001 — any send error is an emission failure to report
        failures.append(f"span (Tempo): {exc}")

    try:
        logs_ok = emit.send_logs(
            trace_id=trace_id,
            run_id=run_id,
            records=[
                {
                    "body": event_body,
                    "severity": "INFO",
                    "attrs": [("event_type", EVENT_TYPE), (LABEL_KEY, label)],
                }
            ],
            strict=True,
        )
        if not logs_ok:
            failures.append("event (Loki)")
    except Exception as exc:  # noqa: BLE001 — any send error is an emission failure to report
        failures.append(f"event (Loki): {exc}")

    if failures:
        print(
            f"demo_emit: emission failed for {', '.join(failures)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f'demo_emit: emitted span "{SPAN_NAME}" -> Tempo and event "{event_body}" -> Loki')
    print(f'  label: {label}   (search by {LABEL_KEY}="{label}")')
    print(f"  trace_id: {trace_id}   run_id: {run_id}")
    sys.exit(0)


if __name__ == "__main__":
    main()
