---
title: "Quickstart — Telemetry Emit Demo"
---

# Quickstart — Telemetry Emit Demo

Runnable validation that the feature works end-to-end. Two layers: the **collector-free pytest** layer
(proves the module's behaviour, no stack needed) and the **live Grafana** layer (proves real ingestion
and label propagation — SC-001, verified manually per spec Assumptions).

## Prerequisites

- Python 3 (system `python3`; the module is stdlib-only).
- `pytest` available for the test layer (dev dependency, established by plan step S0).
- For the live layer only: the telemetry stack up (`cd telemetry && docker compose up -d`).

## Layer 1 — collector-free pytest (no stack required) — FR-011, SC-005

```bash
cd /Users/danielllewellyn/dark-factory
uv run pytest tests/test_demo_emit.py -v     # or: pytest tests/test_demo_emit.py -v
```

**Expected**: all tests pass, including the two SC-005 anchors — a test that fails if the label is not
propagated to **both** signals, and a test that fails if a failed emission still exited 0.

## Layer 2 — live emit + find it in Grafana (SC-001, SC-002)

1. Bring the stack up and confirm receivers:
   ```bash
   cd /Users/danielllewellyn/dark-factory/telemetry
   docker compose up -d
   curl -s localhost:3200/ready                 # Tempo ready (traces)
   curl -s "localhost:3100/loki/api/v1/labels"  # Loki receiving
   ```
2. Emit one labelled data point (the endpoint is `emit.py`'s default `http://localhost:14318` — the
   collector's OTLP **HTTP** host port; no endpoint flag needed):
   ```bash
   cd /Users/danielllewellyn/dark-factory
   python -m telemetry.demo_emit --label smoke-$(date +%Y%m%d-%H%M%S)
   ```
   **Expected**: a stdout line naming the span (`demo.emit` → Tempo), the event body (→ Loki), the label,
   and the `demo.label` search key; exit status `0` (`echo $?`).
3. Find it in Grafana (`http://localhost:3000`, signals are under `service.name=feature-orchestrator`):
   - **Tempo (the span)**: search traces for span name `demo.emit`, or filter by the attribute
     `demo.label = <your label>`.
   - **Loki (the event)**: select `{service_name="feature-orchestrator"}` (optionally also the
     `run_id`), then filter on the **structured metadata** with `| demo_label="<your label>"`. The label
     is structured metadata, **not** a label selector — do not write `{demo_label="…"}`.

   **Expected (SC-001)**: exactly one matching span in Tempo and exactly one matching event in Loki,
   both carrying your label.

## Layer 3 — failure path (SC-003, E1)

```bash
cd /Users/danielllewellyn/dark-factory
FEATURE_OTLP_HTTP_ENDPOINT=http://localhost:1 python -m telemetry.demo_emit --label down-test
echo $?    # expect non-zero
```

**Expected**: a stderr line reporting the emission failed; **no** success line on stdout; non-zero exit
(proves FR-008 / SC-003 and the `FEATURE_OTLP_HTTP_ENDPOINT` override path E5).
