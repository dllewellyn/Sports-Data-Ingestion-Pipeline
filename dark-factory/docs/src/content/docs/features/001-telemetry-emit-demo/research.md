---
title: "Research — Telemetry Emit Demo (Phase 0)"
---

# Research — Telemetry Emit Demo (Phase 0)

Resolves the unknowns and technology choices behind the plan. The feature is a deliberately minimal,
standalone CLI smoke-test module; most "unknowns" are really *how to reuse `emit.py` correctly*, so
each decision is grounded in the verified source of `.agents/skills/_shared/telemetry/emit.py`.

## D1 — How to emit without re-implementing OTLP (FR-003, Constitution II)

- **Decision**: Import `emit.py` as a module and call its keyword-only `send_span(...)` and
  `send_logs(...)` functions directly. Do not shell out to the CLI and do not duplicate any OTLP JSON
  or HTTP code.
- **Rationale**: `emit.py` exposes an importable API (`send_span`, `send_logs`) precisely for in-process
  callers (the hooks batch through it). The CLI (`cmd_span`/`cmd_event`) always `sys.exit(0)` and
  swallows the boolean, so it cannot satisfy FR-008. The importable functions *return the bool* we need.
- **Import mechanics**: `telemetry/demo_emit.py` is not a sibling of `emit.py` (which lives under
  `.agents/skills/_shared/telemetry/`). The module must add that directory to `sys.path` at runtime and
  `import emit`, OR import by file location via `importlib`. Chosen: compute the repo root from the
  module file and insert `<root>/.agents/skills/_shared/telemetry` onto `sys.path`, then `import emit`.
  This keeps the dependency a real import of the real module (no copy), stdlib-only.
- **Alternatives considered**: (a) `subprocess` to `emit.py span|event` — rejected: the CLI exits 0 and
  hides success/failure, defeating FR-008. (b) Copy the send functions locally — rejected: duplicates
  OTLP code, violates FR-003 / Constitution II.

## D2 — Exit-non-zero-on-failure given fire-and-forget design (FR-008, SC-003, Open Question)

- **Decision**: Call `send_span` and `send_logs` and treat a `False` return from **either** as failure;
  on any failure, print a failure line to **stderr** and `sys.exit(1)`. Exit 0 only when both returned
  `True`. Pass `strict=True` so the underlying transport exception is raised and can be surfaced on
  stderr (caught at the top level, reported, non-zero exit) rather than silently swallowed.
- **Rationale**: This is the spec's recorded Open-Questions resolution and matches the verified source:
  `_post` returns `True` only on a 2xx, `False` on any error, and re-raises under `strict=True`
  (emit.py L92–108). `send_span` also returns `False` immediately on an empty `trace_id` (L128–129) and
  `send_logs` returns `False` on empty records (L174–175). Inspecting the booleans is the only
  reuse-respecting way to get FR-008 — no change to `emit.py` is needed or wanted.
- **Note on `strict`**: with `strict=True`, an unreachable endpoint raises inside `send_*`. The module
  wraps each call so it can report *which* signal failed (E2 partial-failure) and still exit non-zero.
- **Alternatives considered**: patching `emit.py` to exit non-zero — rejected: breaks its fire-and-forget
  contract that protects real feature runs, and violates "reuse, do not reinvent".

## D3 — Minting a non-empty trace id before the span call (FR-002, FR-008, Edge E6)

- **Decision**: Resolve ids via `emit.current_context()` first; if it returns `{}` (no active feature
  run), mint a fresh `trace_id = os.urandom(16).hex()` (32 hex chars / W3C 16-byte) and a
  `run_id` for the demo, and a `span_id = os.urandom(8).hex()` (8-byte). Always pass a **non-empty**
  `trace_id` into `send_span`/`send_logs`.
- **Rationale**: Verified — there is **no importable `new_trace_id()`**; emit.py's `new-trace-id`/
  `new-span-id` are CLI-only lambdas (`print(os.urandom(16).hex())` L355, `os.urandom(8).hex()` L356).
  And `send_span` returns `False` on empty `trace_id` (L128). If we left the trace id empty, FR-008
  would trip on a *false* failure even when the collector is healthy. So the module mints ids itself
  with the same `os.urandom` widths, or reuses the active run's ids when present (E6: works standalone).
- **`run_id` choice**: when standalone, derive a recognisable run id for the demo (e.g. the label plus a
  short random suffix) so the Loki index label is meaningful. Reuse `ctx["run_id"]`/`ctx["trace_id"]`
  when a feature run is active so the demo joins that run's trace.
- **Alternatives considered**: calling the CLI `new-trace-id` via subprocess — rejected: adds a process
  hop and parsing for something `os.urandom` does in one line; same primitive, no reuse benefit.

## D4 — Endpoint resolution (FR-009, Edge E5)

- **Decision**: Do **not** read or set any endpoint in `demo_emit.py`. Endpoint selection is entirely
  `emit.py`'s job via its `_endpoint()` (`FEATURE_OTLP_HTTP_ENDPOINT` or `DEFAULT_ENDPOINT`).
- **Rationale**: Verified `DEFAULT_ENDPOINT = "http://localhost:14318"` (L39) — the collector's OTLP
  **HTTP** receiver mapped to host port `14318` (docker-compose L22–24: `14318:4318`). This is emit.py's
  own default and deliberately differs from the README *component table*'s container port `4318`. Reusing
  `emit.py`'s resolution honours `FEATURE_OTLP_HTTP_ENDPOINT` for free (E5) and means there is exactly
  one endpoint source of truth.
- **Alternatives considered**: hardcoding `14318` or `4318` in the demo — rejected: a second endpoint
  source, contradicts FR-009, and `4318` would be wrong for the host.

## D5 — Where the label is searchable, per the Loki label model (FR-004, SC-001)

- **Decision**: Put the label in **both** places it is findable: as a **span attribute** (`demo.label`)
  on the Tempo span, and as **per-record structured metadata** (`("demo.label", <value>)` in the log
  record's `attrs`) on the Loki event. Also embed the label in the human-readable event body.
- **Rationale**: Verified — `send_logs` promotes only `run_id` (resource attr) and `service.name` to Loki
  *index labels* (L177–187, docstring L153–160); a record's `attrs` become flat **structured metadata**
  filterable with `| key="…"`, NOT a label selector. So the demo label cannot be a Loki label-selector;
  it must ride as structured metadata on the event and as an attribute on the span. The quickstart's
  Grafana step therefore filters Loki by structured metadata (`| demo_label="…"`), not by a label
  selector that doesn't exist.
- **Alternatives considered**: trying to make the label a Loki index label — rejected: `send_logs` does
  not promote arbitrary keys, and the spec scopes this minimal (no emit.py changes).

## D6 — Pinned deferred values (Constitution-V note; SC-001/SC-005 checkability)

Pinned now as decisions so they are objectively checkable downstream and not lingering assumptions:

| Value | Pinned to | Why |
|-------|-----------|-----|
| Span name (fixed) | `demo.emit` | Spec-suggested; constant so it is findable in Tempo independent of the label. |
| Default `--label` | `demo-emit` | Spec-suggested recognisable constant; friction-free smoke check. |
| Label key (span attr + log structured metadata) | `demo.label` | Spec-suggested single stable key so one search finds both signals. |
| Event body shape | `demo emit: <label>` (e.g. `demo emit: smoke-1`) | Human-readable, references the label, FR-007. |
| Event `event_type` attr | `demo` | Distinguishes the demo event in Loki from gate/commit/feature events. |

## D7 — Test facility & collector-free strategy (FR-011, SC-005, Constitution III)

- **Decision**: **pytest** with `monkeypatch` to replace `emit.send_span`/`emit.send_logs` with recording
  fakes (test-fixture context only — allowed by Constitution II). Tests assert: (a) one span + one event
  emitted with the label propagated to both (span attr + event structured metadata); (b) default label
  applied when `--label` omitted; (c) empty/whitespace label rejected non-zero; (d) a fake returning
  `False` (or raising) yields a non-zero exit and a stderr report; (e) partial failure (span ok, event
  fails) exits non-zero. No live collector required.
- **Rationale**: FR-011 mandates collector-free pytest. Monkeypatching the *boundary* (emit.py's send
  functions) keeps the real module logic under test while avoiding network — the fakes record call
  kwargs so propagation is asserted on real arguments, not mocked behaviour of `demo_emit` itself.
- **Harness**: the repo has **no** pytest/lint config, no `tests/` dir, no `pyproject.toml`. Establishing
  a minimal harness is a real Phase-2 convention + S0 setup step (see plan §3, §6). The interpreter is
  the system `python3` (3.14); the module and tests are stdlib-only, so no version pin is imposed.
- **Alternatives considered**: pushing logic into Pydantic/Pandera/dbt — rejected: this is CLI control
  flow, not a data contract; pytest is the right facility. A live-collector e2e test — rejected: out of
  scope (SC-001 is verified manually in Grafana per spec Assumptions).

## D8 — Zero third-party runtime dependencies (FR-010, SC-004)

- **Decision**: `demo_emit.py` imports only the stdlib (`argparse`, `os`, `sys`, `time`) plus the repo's
  own `emit.py`. pytest is a **dev/test** dependency only, not a runtime dependency.
- **Rationale**: Verified — `emit.py` is itself zero-dep (urllib only). SC-004 counts *runtime* deps;
  pytest does not ship in the runtime path. Confirmed by `python3 -c "import telemetry.demo_emit"` needing
  nothing installed.
