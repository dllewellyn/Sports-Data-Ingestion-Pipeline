---
title: "Phase 0 Research — Code-Defined Audit Trail Checks"
---

# Phase 0 Research — Code-Defined Audit Trail Checks

**Feature directory**: `specs/003-audit-trail-checks/`
**Date**: 2026-06-30

Each unknown the spec left open (or that the build must settle before Phase 1) is resolved below with
a **Decision**, **Rationale**, and **Alternatives considered**. The spec's Open Questions = None; the
unknowns here are the two thresholds the spec deliberately deferred to the plan, plus the technical
choices the build needs nailed down (query transport, config convention, role attribution, decorator
shape, discovery). Substrate facts were verified against the live stack and the source files.

---

## R1 — Max-size bound for captured tool-input values (FR-010 / Edge E5)

**Decision.** Bound each captured tool-input value to **512 characters** (measured on the string form
of the value), truncating longer values to the first 512 chars and appending a marker. The captured
record carries a boolean-style attribute `value_truncated="true"` and the original length
`value_len="<n>"` when truncation occurs. The bound is a module-level constant
`MAX_TOOL_INPUT_VALUE = 512` so it is documented in one place and adjustable.

**Rationale.** File paths and Grep/Glob patterns — the only values FR-009 requires — are virtually
always far under 512 chars (POSIX `PATH_MAX` is 4096, but real repo paths run tens of chars). 512
comfortably fits any realistic path/pattern while capping a pathological value (e.g. a giant inlined
string accidentally passed as a path) well below the existing per-record `MAX_BODY = 6000` ceiling in
`subagent_stop.py`, so one record can hold several captured values without bloating Loki. Marking
truncation (not silently cutting) satisfies Edge E5's "observable rather than silently dropping data"
and Constitution IV (honesty). A small, named constant keeps the policy auditable.

**Alternatives considered.** (a) Reuse `MAX_BODY = 6000` — rejected: that is the whole-record body
cap, not a per-value cap; a 6 KB path is meaningless and inflates index. (b) 256 chars — rejected:
deep monorepo paths plus a long Glob pattern can plausibly exceed 256, risking false truncation of
legitimate paths. (c) Unbounded with secret-scrubbing only — rejected: violates FR-010's explicit
"bounded to a recorded maximum size".

---

## R2 — Verdict → exit-status mapping (FR-014)

**Decision.** The runner's process exit status is:

| Aggregate condition over all discovered audits | Exit status |
|--------------------------------------------------|-------------|
| At least one `fail` **or** at least one `error`  | `1` |
| Only `pass` and/or `warn` verdicts (no fail/error) | `0` |
| No `@audit` functions discovered at all          | `2` |

`warn`-only runs exit `0` (warnings inform, they do not gate). "No audits discovered" gets a distinct
non-zero-but-not-failure code `2`, so a CI step can tell "nothing ran" apart from "something failed"
(`1`) and "all good" (`0`).

**Rationale.** Matches the spec's stated default (Assumptions: any `fail`/`error` → non-zero;
`warn`-only → zero) and Edge E1's requirement that "no audits discovered" be "a non-error status
distinct from 'all passed'". Exit `2` is the conventional "usage/setup problem" code (argparse itself
uses `2`), reads naturally as "the runner ran but found nothing to do", and is distinct from both `0`
and `1`. `error` is grouped with `fail` for exit purposes (both are non-zero) because an audit that
could not evaluate is not a green result — but the two remain distinct *verdicts* in the output and in
telemetry (FR-004), so the distinction is preserved where it matters.

**Alternatives considered.** (a) `error` → its own exit code `3` — rejected as over-engineered for the
gate use case; FR-014 only asks that fail/error drive non-zero and that "no audits" be distinct. The
verdict-level distinction already lives in the result records. (b) "No audits" → `0` — rejected:
indistinguishable from "all passed", which Edge E1 forbids. (c) `warn` → non-zero — rejected:
contradicts the spec default and would make warnings un-ignorable, defeating their purpose.

---

## R3 — Query transport to telemetry (the read side, US3 / FR-008)

**Decision.** The query client reads recorded telemetry from the **Loki HTTP API**
`GET /loki/api/v1/query_range` on **host port 3100** (mapped in `telemetry/docker-compose.yml`
`loki: ports: "3100:3100"`), using LogQL stream selectors on the index labels
(`{run_id="…"}` / `{feature="…"}`) plus structured-metadata line filters
(`| event_type="transcript" | role="…"`). Transport is **stdlib `urllib`** (no third-party HTTP
client), mirroring `emit.py`. The endpoint is overridable via an environment variable
`FEATURE_LOKI_HTTP_ENDPOINT` (default `http://localhost:3100`), matching the `emit.py`
`FEATURE_OTLP_HTTP_ENDPOINT` pattern.

**Rationale.** Verified live: `GET /loki/api/v1/query_range` returns `resultType: streams` and the
index labels are exactly `feature`, `run_id`, `service_name`; a structured-metadata filter
(`| event_type="commit"`) works and commit records carry `git_files` as a comma-joined string — so
`all_diffs_for_feature()` has its data today and `get_all_reads_from_code_review_agent()` will have its
data once FR-009 lands. Reusing `urllib` keeps the zero-third-party-dep convention emit.py
established (no new runtime dependency, no `uv.lock` churn beyond what tests need). Going through Loki
(not Tempo) is correct because the read paths are *log records* (transcript ingestion + commit events),
which live in Loki, not the span store.

**Alternatives considered.** (a) `requests`/`httpx` — rejected: introduces a runtime dependency the
repo does not have (only `pytest` is declared); `emit.py` proves `urllib` is sufficient. (b) Query
Tempo via TraceQL — rejected: the read data (tool-read paths, commit `git_files`) are log records in
Loki, not span attributes. (c) Read the on-disk `temp/telemetry/<run_id>/` queue files directly —
rejected: those are transient pairing/queue artifacts, not the persisted audit substrate; the spec's
intent ("query the recorded telemetry") is the durable Loki store, and a run may be audited after the
queue dir is cleaned.

---

## R4 — Configuration convention (NOT pydantic-settings)

**Decision.** Configure the runner and query client through **environment variables read at the edge**
(`FEATURE_LOKI_HTTP_ENDPOINT`, `FEATURE_OTLP_HTTP_ENDPOINT`, the existing run-context env), exactly as
`emit.py` does — **not** via `pydantic-settings`.

**Rationale.** **Contradiction surfaced and resolved against the repo's reality.** The planning brief
and the architecture-linter's generic advice string mention `pydantic-settings` for config, but the
repo does **not** depend on pydantic or pydantic-settings — `pyproject.toml`/`uv.lock` declare only
`pytest`, and a repo-wide grep finds `pydantic` only inside a string literal in
`arch-helpers/arch-lint.py` (advice text from a data-platform template, not this repo's practice). The
telemetry substrate's actual, established convention is stdlib env-var reads with sensible defaults
(`emit.py._endpoint()`). Adopting `pydantic-settings` here would be introducing a new runtime
dependency for a handful of endpoint strings — a tooling addition the constitution's "use the repo's
own package manager/runtime — no swaps" guidance counsels against absent a real need. Recorded so it
can be challenged.

**Alternatives considered.** (a) Add `pydantic-settings` — rejected: new dependency for trivial
config; contradicts the in-repo convention and adds `uv.lock` surface. (b) A hand-rolled config class
— rejected: over-engineered vs. the one-liner `os.environ.get(..., default)` the substrate already
uses. If config grows materially later, `pydantic-settings` can be revisited as its own change.

---

## R5 — Resolving "the code-review agent" by telemetry `role`

**Decision.** `get_all_reads_from_code_review_agent()` resolves the agent by the telemetry **`role`
attribute** recorded on sub-agent records (e.g. records whose `role` matches the code-review role),
**not** by `agent_id`. The query selects `{run_id="…"} | event_type="transcript"` and filters records
to those whose `role` is the code-review role, then extracts the captured read-path values.

**Rationale.** Carry-forward #4 from the gate, and it matches the substrate: `role` is already attached
to every transcript record (`subagent_stop.py` `_transcript_records` adds `("role", role)`) and to the
spans (`posttool_emit.py`). `agent_id` is an opaque per-spawn id, unstable and not human-meaningful;
`role` is the durable, queryable identity of *what kind of* agent acted. Edge E6 ("read by a different
agent, not the code-review agent → fail") falls out naturally because the filter is on `role`.

**Alternatives considered.** (a) Filter by `agent_id` — rejected: opaque, per-spawn, and the spec
(Assumptions) explicitly chooses `role`. (b) Filter by `agent_type` — rejected: `agent_type` is the
sub-agent *type* (e.g. `general-purpose`) which is coarser than the semantic role and not guaranteed to
identify the review function; `role` is the right grain.

---

## R6 — `@audit` decorator + runner discovery shape

**Decision.** `@audit` is a decorator that (a) accepts author metadata
(`@audit(name="…", severity="…", category="…", owner="…", **extra)`) and bare-call usage (`@audit`),
(b) registers the wrapped function in a **module-level registry** (a list/dict the runner reads), and
(c) lets the body signal failure explicitly via a raised `AuditFailure(evidence=…)` (the
`fail_audit_check()`-style mechanism, FR-001) and a non-fatal `AuditWarning`. A clean return (no raise)
is `pass`; an `AuditFailure` is `fail` (carrying evidence); an `AuditWarning` is `warn`; any *other*
exception is `error` (carrying the traceback summary). The runner discovers audits by **importing the
configured Python module(s)/path** so the decorator's import-time registration populates the registry,
then iterates the registry. Duplicate names (Edge E4) are refused at registration time with a clear
collision error.

**Rationale.** FR-001 requires failure signalled explicitly "rather than relying on the function's
return value alone" — a raised sentinel exception is the idiomatic Python way and lets evidence ride on
the exception. The four-way verdict (FR-004 `pass`/`fail`/`error`/`warn`) maps cleanly onto
{clean return, `AuditFailure`, other exception, `AuditWarning`}, and FR-007 (one audit's error must not
stop the rest) is satisfied by running each audit in its own try/except inside the runner loop.
Import-time registration via a decorator registry is the standard discovery pattern (pytest, click,
Flask all use it) and avoids fragile source parsing. Refusing duplicate names at registration makes
Edge E4 deterministic.

**Alternatives considered.** (a) Return-value verdicts (`return True/False`) — rejected by FR-001. (b)
AST/source scanning to discover `@audit` — rejected: brittle vs. import-time registration, and cannot
capture metadata reliably. (c) Subclass-a-base-class instead of a decorator — rejected: the spec's
headline example is explicitly a decorated *function*, and a decorator is lighter for authors (SC-001:
"a single decorated Python function").

---

## R7 — Where the audit-result emission rides in the existing label model

**Decision.** Each audit result is emitted with `emit.send_logs(...)` as one log record per audit, with
`run_id`/`feature` carried as the **resource attributes** `send_logs` already promotes to Loki index
labels, and the **audit name + every declared metadata key + verdict + evidence** carried as per-record
`attrs` (Loki **structured metadata**), e.g.
`attrs=[("event_type","audit_result"), ("audit", name), ("verdict", verdict), ("severity", …),
("category", …), ("evidence", …)]`. No change to `loki-config.yaml` `attributes_config`; no new index
label.

**Rationale.** FR-011/FR-013 and the clarify session fix this: index labels are exactly
`feature`/`run_id`/`service.name` (verified live: `data: ["feature","run_id","service_name"]`), and
Loki only allows `index_label` on *resource* attributes anyway. `send_logs` already does exactly this
split — resource attrs → labels, per-record `attrs` → structured metadata filterable with `| key="…"`.
So audit results reuse the existing emit path verbatim; the new `event_type="audit_result"` value
slots alongside the existing `commit`/`gate`/`subagent_stop` event types. Fire-and-forget (FR-012) is
inherited from `emit.py` (short timeout, swallow errors, exit 0).

**Alternatives considered.** (a) Add `audit` as a third index label — rejected explicitly by the spec
(cardinality/Loki-config change, out of scope) and impossible without editing `loki-config.yaml`. (b)
Emit results as a Prometheus metric — rejected: audit results are low-volume, evidence-bearing events
that fit Loki's log+structured-metadata model (spec Assumptions); a metric cannot carry the evidence
string.

---

## R8 — Testing the hook enrichment (US3 / capability provisioning awareness)

**Decision.** The capture enrichment in `subagent_stop.py._summarize_content` is tested two ways, both
under `tests/` with the existing `uv`+`pytest` harness: (1) a **direct unit test** that calls
`_summarize_content` with a synthetic Anthropic `tool_use` block for `Read`/`Edit`/`Write`/`Grep`/
`Glob` and asserts the captured path/pattern **value** (bounded, truncation-marked) appears
attributable to the role — extending the existing `tests/test_telemetry_hooks.py` monkeypatch-the-emit
pattern; and (2) a **fixture-driven integration test** that feeds a recorded transcript line through
`_transcript_records` and asserts the read path is in the emitted record's attrs. The "drive a real
sub-agent through a Read and assert the recorded value" end-to-end check is captured as a
**quickstart.md** runnable scenario (it needs a live harness + collector, so it is a manual/quickstart
proof, not a unit test). A **fake-telemetry pytest fixture** (records `send_logs`/`send_span` kwargs;
already exists as `recorders` in `test_telemetry_hooks.py`) and a **Loki-query test harness** (a fixture
that either points the query client at a stub HTTP server returning canned `query_range` JSON, or skips
when no Loki is reachable) are the guardrails to establish before the query-client tests.

**Rationale.** Mirrors the established hook-test convention (`test_telemetry_hooks.py` imports the hook
module, monkeypatches the `emit` boundary, points the queue dir at `tmp_path`). Constitution III
(test-first) and II (no reward-hacking, real failing-first tests) require the value-capture to be
proven by a test that fails before the enrichment lands. The Loki-query harness must use a stub HTTP
response (not the live stack) so the test is deterministic and order-independent (the constitution's
"each test builds its own seed state" principle), with the live-stack path reserved for quickstart.

**Alternatives considered.** (a) Only an end-to-end live-stack test — rejected: non-deterministic,
needs Docker + a real sub-agent, can't be a red/green unit test. (b) Mock the whole hook — rejected:
the enrichment logic in `_summarize_content` is exactly what must be exercised, so it is called for
real with synthetic input.

---

## R9 — Capability/skill gaps flagged for the downstream B2 provisioning gate

**Decision.** Two capability items the build depends on have **no existing skill**, surfaced here so
the downstream provisioning gate can decide:

- **`@audit` framework rule** — there is no project rule for an audit-decorator/registry convention
  (the repo has no `.claude/rules/` or `.agents/rules/` dir; conventions live in the constitution +
  `CLAUDE.md`/`AGENTS.md`). A new project rule should be drafted (via `create-rule`) for how `@audit`
  functions are authored/registered/named — see the convention audit (`created-pending-approval`).
- **Grafana dashboard-as-code / Loki-query test harness** — no skill covers extending a dashboard JSON
  or a Loki-query test fixture; both are done by hand against the existing `feature-runs.json` pattern
  and a stub-HTTP fixture. Not worth a new skill yet (single use); flagged so `self-learn` can codify
  the pattern after the build if it recurs.

The hook-capture enrichment **edits an existing Claude Code hook** (`subagent_stop.py`) rather than
adding a new hook — no new hook registration is needed; the test is driving a sub-agent through a Read
and asserting the recorded value (R8).

**Rationale.** Carry-forward from the planning brief's "skill-discovery + capability provisioning
awareness": name what is missing before the build relies on it. The `@audit` rule is the one genuine
convention gap and is handled by the convention-audit hard gate (drafted, approval-pending). The
dashboard/harness work has a clear existing pattern to mirror, so it is a step, not a skill gap.

**Alternatives considered.** (a) Create an `observability-dashboards` skill now — rejected: single
use, premature; `self-learn` after the build is the right time. (b) Add the `@audit` convention
silently in code — rejected: the convention audit is a hard gate; a missing governing convention must
be drafted and approved, not assumed (non-interactive mode: drafted + recorded as a blocker needing
approval).

---

## R10 — How FR-010 secret-safety is concretely satisfied (the masker)

**Decision.** FR-010 ("MUST NOT emit secrets/credentials unmasked") is satisfied by **two concrete,
tested mechanisms**, replacing the earlier hand-wavy "secret-shaped value masked" helper:

1. **Capture-scope.** The enrichment only ever captures the path/pattern keys (`file_path` for
   Read/Edit/Write; `pattern`/`path` for Grep/Glob) — never an arbitrary tool-input value. Arbitrary
   secret-bearing input (e.g. a Bash command, an env var) is never read by the capture path at all.
2. **A named redaction rule for the one realistic leak vector** — a `Grep`/`Glob` `pattern` that *is*
   a secret being searched for. A captured value matching a high-entropy / secret-prefix regex is
   masked to **first 4 + `…` + last 4 chars** and flagged `value_redacted="true"`. The regex
   (`subagent_stop.py` module constant) matches: `sk-…` (OpenAI), `ghp_…` (GitHub PAT), `AKIA…` (AWS
   key id), `xox[baprs]-…` (Slack), JWTs (`eyJ….….…`), and any unbroken ≥40-char base64-ish blob.
   Masking is applied **before** the 512-char bound.

**Rationale.** FR-010 is a hard MUST and an undefined masker is a reward-hacking risk (Constitution
II) — so the rule is pinned precisely and backed by a **positive** unit test (a `Grep`
`pattern="sk-ABCD1234EFGH5678IJKL"` is masked to `sk-A…IJKL`, `value_redacted="true"`) and a
**negative** unit test (a real path `src/services/auth_secret_loader.py` containing the word "secret"
is NOT masked — full path verbatim, no flag). The conservative prefix/entropy shape means ordinary
repo paths and globs (`**/*.py`, `src/foo.py`) never false-positive, so the required values survive
intact while a genuinely secret pattern is neutralised.

**Alternatives considered.** (a) Mask anything containing the substrings "secret"/"token"/"key" —
rejected: rampant false positives (`auth_secret_loader.py`, `tokens.py`, `keymap/`) would corrupt the
very path values FR-009 requires. (b) No masker, rely on capture-scope alone — rejected: a Grep for a
literal secret string is a real, demonstrable leak vector; FR-010 says MUST NOT, so a concrete rule is
required, not an argument that it "probably won't happen". (c) A full entropy-scoring scrubber —
rejected: over-engineered for path/pattern capture; the named-prefix + ≥40-char-blob regex covers the
realistic shapes deterministically and is unit-testable.
