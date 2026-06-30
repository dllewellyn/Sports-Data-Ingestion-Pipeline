---
title: "Feature Specification: Telemetry Emit Demo"
---

# Feature Specification: Telemetry Emit Demo

**Feature directory**: `specs/001-telemetry-emit-demo/`
**Created**: 2026-06-30
**Status**: Draft
**Input**: "A custom test-span emitter for the local telemetry stack: a small, real, pytest-tested Python module `telemetry/demo_emit.py` (runnable as `python -m telemetry.demo_emit --label <name>`) that emits one clearly-labelled custom OpenTelemetry span AND one matching log event through the existing `.agents/skills/_shared/telemetry/emit.py` machinery, so a developer can watch a single, deliberately-labelled data point flow end-to-end into Tempo (the span) and Loki (the event) and find it in Grafana. Purpose: a minimal, repeatable way to validate that the telemetry pipeline (OTel collector → Tempo/Loki → Grafana) is actually ingesting and that labels propagate — distinct from a full feature-run trace. It must reuse the existing emit.py OTLP/HTTP emission rather than reinventing it, accept a user-supplied --label (with a sensible default) so the emitted span/event are easy to find by label in Grafana, print to stdout exactly what it emitted and where (span name → Tempo, event → Loki) so the user knows what to search for, and exit non-zero if emission fails. Keep it minimal and dependency-free, consistent with emit.py (zero-dep OTLP/HTTP)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Emit a labelled span and event and learn where to find them (Priority: P1)

A developer who has the local telemetry stack running wants to confirm the pipeline is actually
ingesting. They run `python -m telemetry.demo_emit --label smoke-2026-06-30`. The tool emits exactly
one span (destined for Tempo) and exactly one matching log event (destined for Loki), both stamped
with the label they supplied, and prints to stdout the span name, the event body, the label, and the
destination of each ("span → Tempo", "event → Loki") so they know precisely what to search for in
Grafana. The process exits 0.

**Why this priority**: This is the whole feature — a single deliberately-labelled data point pushed
through the real OTLP/HTTP path so a human can verify ingestion and label propagation end-to-end.
Without it there is nothing.

**Independent Test**: With the stack up, run the module with a unique `--label`, observe the printed
span name / event body / label / destinations and a 0 exit, then find both the span (Tempo) and the
event (Loki) in Grafana by that label. The slice is independently valuable: it proves the pipeline
ingests and that labels propagate.

**Acceptance Scenarios**:

1. **Given** the telemetry collector is reachable at its OTLP/HTTP endpoint, **When** the developer
   runs `python -m telemetry.demo_emit --label smoke-1`, **Then** exactly one span and exactly one log
   event are emitted via the existing `emit.py` send functions, both carrying the label value
   `smoke-1`, and the process exits 0.
2. **Given** a successful run, **When** the developer reads stdout, **Then** it states the emitted
   span name, the emitted event body, the label value, and that the span goes to Tempo and the event
   goes to Loki — enough to locate both in Grafana without reading the source.
3. **Given** the same label is searched in Grafana after a successful run, **When** the developer
   queries Tempo for the span and Loki for the event, **Then** both the span and the event are found
   and both carry the supplied label.

---

### User Story 2 - Default label when none is supplied (Priority: P2)

A developer wants the quickest possible smoke check and runs `python -m telemetry.demo_emit` with no
arguments. The tool applies a sensible, recognisable default label, emits the span and event under
it, and prints what it used so the developer still knows what to search for.

**Why this priority**: Lowers friction for the common "just check it works" case, but the labelled
path (P1) already delivers the core value, so this ranks below it.

**Independent Test**: Run the module with no `--label`; confirm a documented default label is applied,
both signals are emitted under it, the default is printed to stdout, and the process exits 0.

**Acceptance Scenarios**:

1. **Given** no `--label` argument, **When** the developer runs `python -m telemetry.demo_emit`,
   **Then** a sensible default label is used and printed to stdout, and one span and one event are
   emitted under it.

---

### User Story 3 - Fail loudly when emission does not succeed (Priority: P2)

A developer runs the tool while the collector is unreachable (stack down, wrong endpoint). The tool
must not silently report success: it surfaces that emission failed and exits non-zero, so the
developer can tell a real ingestion problem from a successful smoke test.

**Why this priority**: Distinguishing a genuine pipeline failure from a pass is the point of a
validation tool — a false "OK" would defeat the feature — but it builds on the P1 happy path.

**Independent Test**: Point the OTLP/HTTP endpoint at an unreachable address, run the module, and
confirm it reports the failure on stderr and exits non-zero.

**Acceptance Scenarios**:

1. **Given** the configured OTLP/HTTP endpoint is unreachable, **When** the developer runs the
   module, **Then** the tool reports that emission failed and exits with a non-zero status.
2. **Given** the span emits successfully but the event emission fails (or vice versa), **When** the
   run completes, **Then** the tool reports the partial failure and exits non-zero.

---

### Edge Cases

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | Collector / OTLP-HTTP endpoint unreachable | Tool reports emission failure on stderr and exits non-zero (does not print a success line). |
| E2 | Only one of the two signals (span or event) is accepted | Treated as failure: report which signal failed and exit non-zero. |
| E3 | No `--label` supplied | Apply the documented default label, print it, proceed normally. |
| E4 | Empty or whitespace-only `--label` value | Reject with a clear message and exit non-zero, rather than emitting an unfindable blank label. |
| E5 | Endpoint overridden via the existing `FEATURE_OTLP_HTTP_ENDPOINT` environment variable | Honour the override (reuse `emit.py`'s endpoint resolution); do not hardcode a second endpoint. |
| E6 | Run with no active feature-run context (`temp/telemetry/current.json` absent) | Still succeeds: the demo mints its own trace id rather than depending on an active feature run, so it is usable standalone. |

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a Python module runnable as `python -m telemetry.demo_emit`.
- **FR-002**: On a run, the system MUST emit exactly one OpenTelemetry span (destined for Tempo) and
  exactly one log event (destined for Loki).
- **FR-003**: The system MUST perform that emission by calling the existing
  `.agents/skills/_shared/telemetry/emit.py` send functions (`send_span` / `send_logs`), NOT by
  re-implementing OTLP wire encoding or HTTP transport.
- **FR-004**: The span and the event MUST both carry the user-supplied label value in a way that is
  searchable in Grafana (the span findable in Tempo by label, the event findable in Loki by label).
- **FR-005**: Users MUST be able to supply the label via a `--label <name>` argument; when omitted,
  the system MUST apply a documented, recognisable default label and proceed.
- **FR-006**: The system MUST reject an empty or whitespace-only `--label` value with a clear message
  and a non-zero exit.
- **FR-007**: On success, the system MUST print to stdout the emitted span name, the emitted event
  body, the label used, and the destination of each signal (span → Tempo, event → Loki) — enough for
  a developer to locate both in Grafana without reading the source.
- **FR-008**: The system MUST exit 0 only when BOTH the span and the event were emitted successfully;
  if either fails it MUST report the failure (on stderr) and exit non-zero.
- **FR-009**: The system MUST reuse `emit.py`'s endpoint resolution (including the
  `FEATURE_OTLP_HTTP_ENDPOINT` override) rather than introducing its own endpoint configuration.
- **FR-010**: The system MUST add no third-party runtime dependencies, consistent with `emit.py`'s
  zero-dependency OTLP/HTTP design.
- **FR-011**: The system MUST be covered by pytest tests that verify, without requiring a live
  collector, that a run with a given label invokes the span and event emission with that label, that
  the default label applies when none is given, and that a failed emission yields a non-zero exit.

### Key Entities *(include only if the feature involves data)*

- **Demo span**: the single trace span pushed to Tempo for a run. Key attributes: a recognisable span
  name, the run's trace id, and the user-supplied label as a searchable attribute.
- **Demo event**: the single log record pushed to Loki for a run. Key attributes: a human-readable
  body referencing the label, and the user-supplied label as searchable structured metadata.
- **Label**: the user-supplied (or default) string that ties the span and the event together and
  makes the data point findable in Grafana.

## Success Criteria *(mandatory)*

- **SC-001**: After one run with a unique label and the stack up, a developer finds exactly one
  matching span (Tempo) and one matching event (Loki) in Grafana, both carrying that label.
- **SC-002**: A run that successfully emits both signals exits 0 and prints a stdout line naming the
  span, the event, the label, and each signal's destination.
- **SC-003**: A run where emission cannot reach the collector exits non-zero and does not print a
  success line.
- **SC-004**: The feature adds zero third-party runtime dependencies.
- **SC-005**: The pytest suite for the module passes and includes at least one test that fails if the
  label is not propagated to both signals and at least one that fails if a failed emission still
  exited 0.

## Constraints & things to be aware of *(mandatory)*

- **Reuse, do not reinvent** (constitution II — No Reward Hacking; the description's explicit
  requirement): emission MUST go through `emit.py`'s `send_span` / `send_logs`; no duplicated OTLP
  JSON or HTTP code, and no stubbed/faked emission outside test fixtures — the tool must really emit.
- **`emit.py` is fire-and-forget by design**: its CLI always exits 0 and its send functions return a
  boolean (True on a 2xx POST, False on any error) and only re-raise under `--strict`. This feature's
  non-zero-on-failure requirement (FR-008) therefore depends on inspecting those return values (or the
  strict path), since the default `emit.py` behaviour is the opposite — surfaced as a known tension,
  see Open Questions.
- **Endpoint**: the demo targets the collector's OTLP/HTTP receiver on host port `14318` (the default
  in `emit.py`), overridable via `FEATURE_OTLP_HTTP_ENDPOINT` — distinct from the gRPC `14317`
  endpoint `claude-otel.env` points Claude Code at. Do not introduce a new endpoint variable.
- **`service.name`**: emitted signals will carry `service.name=feature-orchestrator` (emit.py's
  constant), so in Grafana they appear under that service, not `claude-code`. The README documents
  these never collide.
- **Loki label model**: per `emit.py`, `run_id` is the Loki *index* label and `service.name` is the
  other selector; everything else (including this feature's demo label) rides as filterable structured
  metadata. The demo label must be placed where it is actually findable under that model.
- **Test-First** (constitution III): the pytest coverage in FR-011 must be genuinely red-able before
  the code exists; tests must not be narrowed to pass.
- **No backward compatibility** (constitution I): this is a new, standalone module; it does not need
  to preserve any legacy emit path.
- **Scope discipline**: this is a deliberately minimal telemetry smoke test, distinct from the
  feature-run trace tree. It is not an observability tool — resist adding metrics, dashboards,
  multi-span trees, or configuration beyond `--label`.

## Assumptions *(mandatory)*

- The module lives at `telemetry/demo_emit.py` and `telemetry/` is (or becomes) an importable package
  so `python -m telemetry.demo_emit` works; if `telemetry/__init__.py` is absent, the implementer adds
  an empty one. (Default chosen because the description fixes the run command and module path.)
- The default label (when `--label` is omitted) is a recognisable constant such as `demo-emit`
  optionally suffixed for uniqueness; the exact string is an implementation choice recorded at build
  time. (Default chosen: friction-free smoke check.)
- The span name is a fixed, recognisable constant (e.g. `demo.emit`) so it is easy to find in Tempo,
  independent of the label. (Default chosen: searchability.)
- The demo mints its own `trace_id`/`run_id` (via `emit.py`'s id helpers) when no active feature-run
  context exists, so it works standalone without a `feature` run in progress. (Default chosen: the
  stated purpose is a standalone pipeline check distinct from a feature-run trace.)
- "Find it in Grafana" is verified by the developer manually in this minimal feature; automated
  end-to-end query-back against live Tempo/Loki is out of scope (pytest covers emission behaviour, not
  a running stack). (Default chosen: minimalism; keeps tests collector-free.)
- The label is propagated as a span attribute and as event structured metadata under a single, stable
  key (e.g. `demo.label`); the exact key is an implementation detail recorded at build time. (Default
  chosen so both signals are findable by the same label.)

## Open Questions *(mandatory)*

- To satisfy FR-008 (exit non-zero on emission failure) the module must observe `emit.py`'s
  boolean return values (or use its `strict=True` path) rather than its fire-and-forget CLI, which
  always exits 0. **Best-guess answer**: call the importable `send_span` / `send_logs` directly and
  treat a `False` return from either as failure (exit non-zero), reserving `strict=True` for surfacing
  the underlying exception on stderr. *Rationale*: the importable API already returns success/failure
  booleans, so no change to `emit.py` is needed and the reuse constraint is honoured. Not a build
  blocker — the chosen approach is implementable as-is.
