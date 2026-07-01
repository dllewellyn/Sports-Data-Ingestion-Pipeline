---
title: "Data Model — Telemetry Emit Demo (Phase 1)"
---

# Data Model — Telemetry Emit Demo (Phase 1)

This feature has no persistent storage and no warehouse layer. Its "entities" are the two telemetry
signals it emits and the label that ties them together. They are described here as the data contracts
the module produces (the wire shapes are owned by `emit.py`; this module only chooses the values).

## Entity: Label

The user-supplied (or default) string that ties the span and the event together and makes the data
point findable in Grafana.

| Field | Type | Source | Validation |
|-------|------|--------|------------|
| value | str | `--label <name>` arg, or default | MUST be non-empty after `.strip()`; whitespace-only is rejected (FR-006, E4). |

- **Default**: `demo-emit` (pinned, research D6) when `--label` is omitted (FR-005, E3).
- **Validation rule**: `label.strip() == ""` → print a clear message to stderr, exit non-zero. Do **not**
  emit an unfindable blank label.

## Entity: Demo span (→ Tempo)

The single trace span pushed to Tempo per run. Produced by `emit.send_span(...)`.

| Field | Value | Notes |
|-------|-------|-------|
| name | `demo.emit` (pinned constant) | Fixed so it is findable in Tempo independent of the label (D6). |
| trace_id | active run's `trace_id`, else `os.urandom(16).hex()` | Non-empty guaranteed before the call (D3, FR-008). |
| span_id | `os.urandom(8).hex()` | 8-byte, matching emit.py's CLI width. |
| run_id | active run's `run_id`, else demo-minted | Resource-level; also the Loki index label on the event. |
| start_ns / end_ns | `time.time_ns()` bracketing the call | Single point-in-time span (no children). |
| status_ok | True | A successful emit is a healthy span. |
| attrs | `[("demo.label", <label value>)]` | The label as a **span attribute** → findable in Tempo (FR-004, D5). |

- **Cardinality**: exactly one span per run (FR-002). No span tree, no children (scope discipline).

## Entity: Demo event (→ Loki)

The single log record pushed to Loki per run. Produced by `emit.send_logs(..., records=[one record])`.

| Field | Value | Notes |
|-------|-------|-------|
| body | `demo emit: <label>` | Human-readable, references the label (FR-007). |
| severity | `INFO` | Normal smoke-test event. |
| attrs (structured metadata) | `[("event_type", "demo"), ("demo.label", <label value>)]` | The label rides as **structured metadata** (`\| demo_label="…"` in Grafana), the only place it is findable under Loki's model (D5, FR-004). `event_type=demo` distinguishes it from gate/commit/feature events. |
| run_id | same as the span's run_id | Promoted by `emit.py` to the Loki **index label**. |
| trace_id | same as the span's trace_id | Lets the event link to the span's trace. |

- **Cardinality**: exactly one event per run (FR-002).

## Relationships & invariants

- The **same** `label` value MUST appear on both the span (attribute) and the event (structured
  metadata) — this is the propagation invariant SC-005 asserts in a test.
- The **same** `trace_id`/`run_id` MUST be used for both signals in a run, so they correlate in Grafana.
- A run emits **both or it fails**: exit 0 iff both `send_span` and `send_logs` returned `True`;
  otherwise stderr report + non-zero exit (FR-008, E2). No partial "success" is reported.

## State transitions

Single, stateless invocation — no persisted state, no idempotency concern (each run is an independent
emit; re-running simply emits another labelled data point, which is the intended smoke-test behaviour).
