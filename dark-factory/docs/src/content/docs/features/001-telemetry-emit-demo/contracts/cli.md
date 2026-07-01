---
title: "Contract — `python -m telemetry.demo_emit` CLI grammar"
---

# Contract — `python -m telemetry.demo_emit` CLI grammar

The feature exposes one interface: a CLI invoked via `python -m telemetry.demo_emit`. This is its
contract — the grammar, the stdout/stderr shape, and the exit-code semantics that tests and the
quickstart assert against. (The OTLP wire contract is owned by `emit.py` and is NOT redefined here.)

## Invocation

```
python -m telemetry.demo_emit [--label <name>]
```

| Argument | Required | Default | Rule |
|----------|----------|---------|------|
| `--label <name>` | no | `demo-emit` | Value used as the searchable label on both signals. Empty/whitespace-only is rejected (FR-006, E4). |

No other arguments are accepted (scope discipline: no config beyond `--label`).

## Exit codes (FR-008, SC-002, SC-003)

| Exit | Condition |
|------|-----------|
| `0` | BOTH `send_span` and `send_logs` returned `True` (both signals emitted). |
| non-zero (`1`) | Either send returned `False` / raised (collector unreachable, partial failure E1/E2), OR the `--label` was empty/whitespace (E4). |

## stdout — success path only (FR-007, SC-002)

On exit 0, print a human-readable report that names, at minimum:
- the **span name** (`demo.emit`) and that it goes to **Tempo**;
- the **event body** and that it goes to **Loki**;
- the **label** used (so the developer searches the right value);
- the **label key** (`demo.label`) used as the Tempo attribute / Loki structured-metadata field.

Illustrative (exact wording is an implementation choice; the four facts above are the contract):

```
demo_emit: emitted span "demo.emit" -> Tempo and event "demo emit: smoke-1" -> Loki
  label: smoke-1   (search by demo.label="smoke-1")
  trace_id: <hex>  run_id: <id>
```

On any failure, stdout MUST NOT print a success line (SC-003).

## stderr — failure path (FR-008, E1, E2)

On failure, print to **stderr** which signal(s) failed and exit non-zero. The default-label notice
(E3) is allowed on stdout (it is not a failure).

## Behavioural contract (asserted by pytest, collector-free — FR-011, SC-005)

| # | Given | Then |
|---|-------|------|
| C1 | `--label smoke-1`, both sends succeed | `send_span` called once and `send_logs` called once; both carry `demo.label=smoke-1` (span attr + event structured metadata); exit 0; stdout names span/event/label/destinations. |
| C2 | no `--label`, both sends succeed | label `demo-emit` used on both signals and printed; exit 0. |
| C3 | `--label "   "` (whitespace) | no send attempted; clear stderr message; exit non-zero. |
| C4 | `send_logs` (or `send_span`) returns `False`/raises | stderr names the failed signal; exit non-zero; no success line on stdout. |
| C5 | no active feature-run context | module mints its own non-empty `trace_id`/`run_id`; both sends still invoked with a non-empty `trace_id`; exit 0 when sends succeed. |
