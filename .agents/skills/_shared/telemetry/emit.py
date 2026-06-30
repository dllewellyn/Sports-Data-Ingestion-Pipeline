#!/usr/bin/env python3
"""emit.py — fire-and-forget OTLP/HTTP JSON emitter for the feature-run telemetry.

The `feature` flow is driven by prose that spawns sub-agents; this helper lets the
orchestrator, the shared validators, the commit helper, and the Claude Code hooks
drop **spans** (the graph) and **log records** (gate verdicts, commit ties, live
progress, sub-agent transcripts) onto the existing OpenTelemetry collector so a
whole run can be reconstructed in Grafana.

Two faces:
  * importable — `import emit; emit.send_span(...) / emit.send_logs(...)` (hooks
    batch many transcript lines through one POST this way).
  * CLI — `emit.py span|event|gate|commit|label-next|new-*-id|now-ns` for shell
    callers (validators, git-commit-safe.sh, the orchestrator).

Design constraints (mirrors the `otel.py` guardrail convention — "absence of a
collector is harmless"):
  * Zero third-party deps — raw OTLP/HTTP JSON over urllib, no OTEL SDK.
  * Fire-and-forget — short timeout, swallows every error, ALWAYS exits 0 from the
    CLI so a telemetry outage can never block or fail a feature run. --strict
    re-raises (debugging only).
  * Stdout stays clean on the happy path; diagnostics go to stderr on --debug.

Endpoint: the collector's OTLP **HTTP** receiver — the 14318 port, NOT the gRPC
14317 that `claude-otel.env` points Claude Code at. Override via
FEATURE_OTLP_HTTP_ENDPOINT.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

SCOPE_NAME = "feature-telemetry"
SERVICE_NAME = "feature-orchestrator"
DEFAULT_ENDPOINT = "http://localhost:14318"
TIMEOUT_S = 2.0

SEVERITY = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _endpoint():
    return os.environ.get("FEATURE_OTLP_HTTP_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def _repo_root():
    cur = os.path.abspath(os.environ.get("FEATURE_REPO_ROOT", os.getcwd()))
    while True:
        if os.path.isdir(os.path.join(cur, ".specify")) or os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(os.environ.get("FEATURE_REPO_ROOT", os.getcwd()))
        cur = parent


def current_context():
    """Active-run pointer written by run-context.sh; {} if no run is active."""
    path = os.path.join(_repo_root(), "temp", "telemetry", "current.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def derive_span_id(trace_id, agent_id):
    """Stable 16-hex span id for an agent — lets a child resolve its parent's span
    id by computation alone, sidestepping the fact that a parent sub-agent's span
    is only emitted AFTER its children stop (so a registry lookup would miss it)."""
    h = hashlib.sha256(f"{trace_id}:{agent_id}".encode()).hexdigest()
    return h[:16]


def _attrs(pairs):
    out = []
    for k, v in pairs:
        if k is None or v is None or v == "":
            continue
        out.append({"key": str(k), "value": {"stringValue": str(v)}})
    return out


def _post(path, payload, debug=False, strict=False):
    url = f"{_endpoint()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            if debug:
                print(f"emit.py: POST {path} -> {resp.status}", file=sys.stderr)
            return True
    except Exception as exc:  # noqa: BLE001 — fire-and-forget by design
        if debug:
            print(f"emit.py: POST {path} failed: {exc!r}", file=sys.stderr)
        if strict:
            raise
        return False


# --------------------------------------------------------------------------- #
# Importable API
# --------------------------------------------------------------------------- #
def send_span(
    *,
    trace_id,
    run_id,
    name,
    span_id,
    parent_span_id="",
    start_ns,
    end_ns,
    status_ok=True,
    attrs=(),
    debug=False,
    strict=False,
):
    if not trace_id:
        return False
    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 1,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": _attrs([("feature.run_id", run_id)] + list(attrs)),
        "status": {"code": 1 if status_ok else 2},
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": _attrs([("service.name", SERVICE_NAME)])},
                "scopeSpans": [{"scope": {"name": SCOPE_NAME}, "spans": [span]}],
            }
        ]
    }
    return _post("/v1/traces", payload, debug, strict)


def send_logs(*, trace_id, run_id, records, debug=False, strict=False):
    """records: iterable of dicts {body, severity, attrs: [(k, v)]}.

    Label model: `run_id` is a RESOURCE attribute (constant per run) promoted to a
    Loki index label (Loki only allows index_label on resource attrs) so the
    dashboard can offer a run dropdown; `service.name` is the other selector label.
    Everything else (event_type, agent_id, role, phase, git_*) rides as flat
    structured metadata, filterable with `| key="…"`."""
    log_records = []
    for r in records:
        sev = (r.get("severity") or "INFO").upper()
        rec = {
            "timeUnixNano": str(r.get("ts_ns") or time.time_ns()),
            "severityNumber": SEVERITY.get(sev, 9),
            "severityText": sev,
            "body": {"stringValue": str(r.get("body", ""))},
            "attributes": _attrs(list(r.get("attrs", []))),
        }
        if trace_id:
            rec["traceId"] = trace_id
        log_records.append(rec)
    if not log_records:
        return False
    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": _attrs([("service.name", SERVICE_NAME), ("run_id", run_id)])
                },
                "scopeLogs": [{"scope": {"name": SCOPE_NAME}, "logRecords": log_records}],
            }
        ]
    }
    return _post("/v1/logs", payload, debug, strict)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _ids(args):
    ctx = current_context()
    trace_id = args.trace_id or os.environ.get("FEATURE_TRACE_ID") or ctx.get("trace_id")
    run_id = args.run_id or os.environ.get("FEATURE_RUN_ID") or ctx.get("run_id")
    return trace_id, run_id


def _kv_list(items):
    out = []
    for item in items or []:
        if "=" in item:
            k, v = item.split("=", 1)
            out.append((k, v))
    return out


def cmd_span(args):
    trace_id, run_id = _ids(args)
    send_span(
        trace_id=trace_id,
        run_id=run_id,
        name=args.name,
        span_id=args.span_id or os.urandom(8).hex(),
        parent_span_id=args.parent_span_id,
        start_ns=args.start_ns or time.time_ns(),
        end_ns=args.end_ns or time.time_ns(),
        status_ok=(args.status != "error"),
        attrs=[("role", args.role), ("phase", args.phase), ("agent_type", args.agent_type)]
        + _kv_list(args.attr),
        debug=args.debug,
        strict=args.strict,
    )


def cmd_event(args):
    trace_id, run_id = _ids(args)
    send_logs(
        trace_id=trace_id,
        run_id=run_id,
        records=[
            {
                "body": args.body,
                "severity": args.severity,
                "attrs": [("event_type", args.type), ("phase", args.phase)] + _kv_list(args.attr),
            }
        ],
        debug=args.debug,
        strict=args.strict,
    )


def cmd_gate(args):
    trace_id, run_id = _ids(args)
    ok = args.verdict.upper() == "PASS"
    body = f"gate {args.phase or ''} {args.artifact} -> {args.verdict.upper()}".strip()
    send_logs(
        trace_id=trace_id,
        run_id=run_id,
        records=[
            {
                "body": body,
                "severity": "INFO" if ok else "ERROR",
                "attrs": [
                    ("event_type", "gate"),
                    ("phase", args.phase),
                    ("artifact", args.artifact),
                    ("verdict", args.verdict.upper()),
                ],
            }
        ],
        debug=args.debug,
        strict=args.strict,
    )


def cmd_commit(args):
    trace_id, run_id = _ids(args)
    send_logs(
        trace_id=trace_id,
        run_id=run_id,
        records=[
            {
                "body": f"commit {args.sha} {args.subject}".strip(),
                "severity": "INFO",
                "attrs": [
                    ("event_type", "commit"),
                    ("phase", args.phase),
                    ("task", args.task),
                    ("git_sha", args.sha),
                    ("git_subject", args.subject),
                    ("git_files", args.files),
                ],
            }
        ],
        debug=args.debug,
        strict=args.strict,
    )


def cmd_label_next(args):
    _, run_id = _ids(args)
    if not run_id:
        return
    queue_dir = os.path.join(_repo_root(), "temp", "telemetry", run_id)
    try:
        os.makedirs(queue_dir, exist_ok=True)
        with open(os.path.join(queue_dir, "pending-roles.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps({"role": args.role, "phase": args.phase, "ts_ns": time.time_ns()}) + "\n"
            )
    except OSError as exc:
        if args.debug:
            print(f"emit.py: label-next failed: {exc!r}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--trace-id", dest="trace_id", default="")
    p.add_argument("--run-id", dest="run_id", default="")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("span")
    sp.add_argument("--name", required=True)
    sp.add_argument("--role", default="")
    sp.add_argument("--phase", default="")
    sp.add_argument("--agent-type", dest="agent_type", default="")
    sp.add_argument("--span-id", dest="span_id", default="")
    sp.add_argument("--parent-span-id", dest="parent_span_id", default="")
    sp.add_argument("--start-ns", dest="start_ns", type=int, default=0)
    sp.add_argument("--end-ns", dest="end_ns", type=int, default=0)
    sp.add_argument("--status", choices=["ok", "error"], default="ok")
    sp.add_argument("--attr", action="append")
    sp.set_defaults(func=cmd_span)

    ev = sub.add_parser("event")
    ev.add_argument("--body", required=True)
    ev.add_argument("--type", default="event")
    ev.add_argument("--phase", default="")
    ev.add_argument("--severity", default="info")
    ev.add_argument("--attr", action="append")
    ev.set_defaults(func=cmd_event)

    ga = sub.add_parser("gate")
    ga.add_argument("--artifact", required=True)
    ga.add_argument("--verdict", required=True)
    ga.add_argument("--phase", default="")
    ga.set_defaults(func=cmd_gate)

    co = sub.add_parser("commit")
    co.add_argument("--sha", required=True)
    co.add_argument("--subject", default="")
    co.add_argument("--phase", default="")
    co.add_argument("--task", default="")
    co.add_argument("--files", default="")
    co.set_defaults(func=cmd_commit)

    ln = sub.add_parser("label-next")
    ln.add_argument("--role", required=True)
    ln.add_argument("--phase", default="")
    ln.set_defaults(func=cmd_label_next)

    sub.add_parser("new-trace-id").set_defaults(func=lambda a: print(os.urandom(16).hex()))
    sub.add_parser("new-span-id").set_defaults(func=lambda a: print(os.urandom(8).hex()))
    sub.add_parser("now-ns").set_defaults(func=lambda a: print(time.time_ns()))

    args = p.parse_args()
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001 — never fail the caller
        if args.debug:
            print(f"emit.py: unhandled {exc!r}", file=sys.stderr)
        if args.strict:
            raise
    sys.exit(0)


if __name__ == "__main__":
    main()
