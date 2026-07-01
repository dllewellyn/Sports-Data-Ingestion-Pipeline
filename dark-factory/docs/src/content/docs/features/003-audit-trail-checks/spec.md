---
title: "Feature Specification: Code-Defined Audit Trail Checks"
---

# Feature Specification: Code-Defined Audit Trail Checks

**Feature directory**: `specs/003-audit-trail-checks/`
**Created**: 2026-06-30
**Status**: Draft
**Input**: "Improve our telemetry logging / audit trail — make it so that we can code the audit-trail in a python file. For example the logic might be: `@audit def all_changed_files_code_reviewed(): code_reviewed_read_files = get_all_reads_from_code_review_agent(); for diff in all_diffs_for_feature(): for file_changed in diff: if file_changed not in code_review_read_files: fail_audit_check()`. I accept it'll be a comprehensive audit-trail logging, but I want these to then show up in Grafana with some metadata assigned to each `@audit` tag (or however is best to do this). We'll need clear and understandable documentation for this as well."

> **Domain note.** The domain vocabulary here is the existing feature-run telemetry substrate —
> `run_id`, `feature`, spans, log records, `event_type`, tool-input values, Loki/Grafana. That
> vocabulary IS the requirement (an audit asserts over what telemetry recorded), so it is used
> directly. Internal code design (query-client module, decorator internals, library choices) is left
> to the plan.

## Clarifications

### Session 2026-06-30

- Q: How should the audit name and per-audit `@audit` metadata be surfaced in Loki/Grafana — as new
  index labels or as structured metadata? → A: Structured metadata only. The substrate promotes only
  `feature`, `run_id`, and default `service.name` to Loki index labels (`loki-config.yaml`
  `otlp_config`; `emit.py send_logs`); audit name + metadata ride as per-record log attributes,
  LogQL-filterable via `| audit="…"`. No new index label is added. (Encoded into FR-011, FR-013, and
  Assumptions.)
- Q: When a feature run changed no files, what verdict should the flagship "all changed files
  reviewed" audit return? → A: `pass` (vacuous truth — nothing left unreviewed), not `error`/`fail`.
  Defensible default for a universally-quantified rule; reversible, an author can add a separate
  "must change ≥1 file" audit. (Encoded into US1 acceptance scenario 5 and Assumptions; already in
  Edge case E3.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Author and run a code-defined audit over a feature run (Priority: P1)

An audit author writes a plain Python function decorated `@audit` that expresses a rule about a
feature run — for example, "every file changed across the feature's diffs was read by the
code-review agent". They run the audit runner against a completed (or in-progress) feature run,
identified by its `run_id` (or by the feature it is bound to). The runner discovers every `@audit`
function, executes each one against that run's recorded telemetry, and produces a per-audit verdict
(pass / fail) plus, on failure, the concrete evidence that explains the verdict (e.g. the changed
files that were never read). The author can read the outcome from the runner's own output without
opening Grafana.

**Why this priority**: This is the core of the feature — without authorable, runnable, code-defined
audit checks producing pass/fail verdicts there is nothing to surface anywhere. It delivers value on
its own: a developer can assert governance properties of a feature run from a Python file.

**Independent Test**: Author a trivial `@audit` that must pass and one that must fail against a
fixture feature run with known telemetry, run the runner, and assert that the first reports `pass`,
the second reports `fail`, and the failing one carries the offending evidence. No Grafana required.

**Acceptance Scenarios**:

1. **Given** a feature run whose telemetry records that the code-review agent read every file that
   appears in the run's diffs, **When** the `all_changed_files_code_reviewed` audit runs against that
   run, **Then** the runner reports that audit as `pass`.
2. **Given** a feature run whose diffs include a changed file that the code-review agent never read,
   **When** the same audit runs, **Then** the runner reports it as `fail` and the result names the
   unread changed file(s) as evidence.
3. **Given** a Python file containing two `@audit` functions, **When** the runner executes against a
   run, **Then** both functions are discovered and each produces its own independent verdict.
4. **Given** an `@audit` function that raises an unexpected error while evaluating, **When** the
   runner executes it, **Then** that audit is reported as `error` (distinct from `fail`) with the
   error detail, and the other audits still run and report.
5. **Given** a feature run whose diffs changed no files at all (empty change set), **When** the
   `all_changed_files_code_reviewed` audit runs, **Then** the runner reports it as `pass` (vacuously
   true — nothing was left unreviewed), not `error` or `fail`.

---

### User Story 2 - Audit results appear in Grafana keyed by audit name and metadata (Priority: P2)

After (or as part of) a run, each audit's verdict is emitted into the existing telemetry stack so it
is visible in Grafana alongside the feature run it describes. Each result carries the audit's name,
the `run_id` and `feature` it was evaluated against, the verdict, and any author-declared metadata
attached to the `@audit` decorator (e.g. category, severity, owner). A viewer filtering the Feature
runs dashboard to a given feature/run can see which audits passed and which failed for that run, and
read the failure evidence.

**Why this priority**: The user explicitly wants results "to then show up in Grafana with some
metadata assigned to each `@audit` tag". It depends on US1 (there must be verdicts before they can be
surfaced) but is independently demonstrable once US1 exists.

**Independent Test**: Run the runner against a fixture run with one passing and one failing audit,
then query Loki/Grafana for that `run_id` and assert two audit-result records exist, each carrying
the audit name, verdict, feature, and declared metadata, and that the failing one carries its
evidence.

**Acceptance Scenarios**:

1. **Given** the telemetry stack is up and the runner has executed audits for a run, **When** a
   viewer queries Grafana/Loki for that `run_id`, **Then** one audit-result record per executed audit
   is present, each labelled with the audit name, verdict, `feature`, and `run_id`.
2. **Given** an `@audit` declares metadata (e.g. `severity="high"`, `category="review-integrity"`),
   **When** its result is surfaced, **Then** that metadata is attached to the result and is
   filterable/visible in Grafana.
3. **Given** a failing audit, **When** its result is viewed in Grafana, **Then** the failure evidence
   recorded by the runner is readable from the result.
4. **Given** the telemetry stack is down when the runner executes, **When** audits run, **Then** the
   runner still produces and reports verdicts locally and emission failure does not change any
   verdict or fail the run (fire-and-forget, consistent with the existing emitter).

---

### User Story 3 - Audit authors can query what each agent did during the run (Priority: P1)

For an audit to assert "every changed file was read by the code-review agent", the audit code needs
two queries over the run's telemetry: the set of file paths each agent (by role) read, and the set of
files changed across the feature's diffs. A documented query surface is available to audit authors so
they can write `get_all_reads_from_code_review_agent()`-style helpers without hand-rolling Loki
queries, and the underlying telemetry actually records the file paths an agent read — not merely that
a `Read`/`Edit`/`Write`/`Grep`/`Glob` tool was called.

**Why this priority**: This is a hard prerequisite for the flagship example and a known gap (see
Constraints): today the transcript-ingest hook records only the *keys* of a tool call's input
(e.g. `file_path`), never the *value* (the path). Without capturing the values, no audit can know
*what* an agent read or changed, so the headline audit is impossible. It is P1 because US1's flagship
scenario cannot pass without it.

**Independent Test**: Drive a sub-agent through a `Read` of a known path under an instrumented run,
then assert (a) the recorded telemetry for that run contains the read path attributable to that
agent's role, and (b) the query helper returns that path when asked for the agent's reads.

**Acceptance Scenarios**:

1. **Given** an instrumented feature run in which the code-review agent reads `src/foo.py` and
   `src/bar.py`, **When** an audit calls the "reads by the code-review agent" query, **Then** it
   receives a set containing exactly those two paths.
2. **Given** a feature run with commits recording changed files, **When** an audit calls the
   "files changed across the feature's diffs" query, **Then** it receives the union of files from the
   run's commit records.
3. **Given** a sub-agent that performs `Edit`, `Write`, `Grep`, and `Glob` calls, **When** the run's
   telemetry is recorded, **Then** the relevant path/pattern value for each of those tool calls is
   captured and attributable to the agent's role (not just the tool name).
4. **Given** a tool call whose input contains a value that should not be persisted in full (oversized
   or sensitive), **When** the value is captured, **Then** it is bounded/handled per the recorded
   capture policy rather than emitted unbounded or as a secret.

---

### Edge Cases

| # | Edge case / failure | Expected behaviour |
|---|---------------------|--------------------|
| E1 | No `@audit` functions are found in the target Python file/path | Runner reports zero audits executed with a clear "no audits discovered" message and exits with a non-error status distinct from "all passed". |
| E2 | The target `run_id` has no telemetry (unknown/empty run) | Runner reports that the run could not be resolved / has no data; audits depending on that data report `error`, not a false `pass`. |
| E3 | A query helper returns an empty set legitimately (agent read nothing) | Audits relying on it evaluate over the empty set deterministically; "no files changed" yields `pass` for the flagship audit (nothing left unreviewed), not `error`. |
| E4 | Two `@audit` functions share the same name | Runner refuses the duplicate (or disambiguates deterministically) and reports the collision rather than silently surfacing one verdict under a name that maps to two checks. |
| E5 | Telemetry records a tool-input value larger than the capture bound | The value is truncated to the bound and marked truncated, so the audit sees a bounded value and the truncation is observable rather than silently dropping data. |
| E6 | A changed file was read by a *different* agent but not the code-review agent | The flagship audit fails for that file — the rule is "read by the code-review agent", so reads by other roles do not satisfy it. |
| E7 | Audit emission to the telemetry stack fails (stack down, timeout) | Verdicts are unaffected and reported locally; the emission failure is non-fatal and does not alter exit status driven by verdicts (consistent with fire-and-forget emit). |
| E8 | An audit returns a non-fatal warning condition rather than a hard pass/fail | A `warn` verdict is recorded and surfaced distinctly from `pass`/`fail`/`error`. |

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let an author define an audit check as a Python function decorated with
  an `@audit` decorator, where the function body expresses the rule and signals failure explicitly
  (e.g. a `fail_audit_check()`-style call or equivalent) rather than relying on the function's return
  value alone.
- **FR-002**: The `@audit` decorator MUST accept author-declared metadata (at minimum a name and an
  open set of key/value attributes such as category, severity, owner) and associate it with that
  audit's results.
- **FR-003**: The system MUST provide a runner that discovers every `@audit` function in a configured
  location, executes each against a specified feature run, and produces one verdict per audit.
- **FR-004**: Each audit verdict MUST be one of a fixed set: `pass`, `fail`, `error` (the audit itself
  raised), or `warn`; `fail` and `error` MUST be distinguishable.
- **FR-005**: On a `fail` (and where applicable `warn`), the runner MUST capture concrete evidence
  explaining the verdict (e.g. the specific changed files that were not reviewed) and include it in
  the result.
- **FR-006**: The runner MUST identify the target feature run by `run_id`, and MUST resolve it via the
  active run context / feature binding when not given explicitly, consistent with how the existing
  telemetry establishes run identity.
- **FR-007**: One audit raising an error MUST NOT prevent the remaining audits from running; the
  runner MUST execute all discovered audits and report all verdicts.
- **FR-008**: The system MUST provide audit authors a documented query surface over a run's telemetry
  sufficient to write the flagship example, including at minimum: the set of file paths read by a
  given agent role (e.g. the code-review agent), and the set of files changed across the feature's
  diffs for that run.
- **FR-009**: Telemetry capture MUST record the relevant tool-input *value* for file-touching tool
  calls — at minimum the path for `Read`, `Edit`, and `Write`, and the path/pattern for `Grep` and
  `Glob` — attributable to the acting agent's role and the run, not merely the input *keys* or the
  tool name. *(This closes the known gap where only input keys are captured today.)*
- **FR-010**: Captured tool-input values MUST be bounded to a recorded maximum size and MUST NOT emit
  secrets/credentials unmasked; values exceeding the bound MUST be truncated and marked as truncated.
- **FR-011**: Each audit result MUST be emitted into the existing telemetry stack so it is queryable
  in Grafana/Loki, carrying the audit name, verdict, `run_id`, `feature`, the author-declared
  metadata, and (on failure) the evidence. The result MUST be correlated to its run via the existing
  `run_id`/`feature` resource attributes (the only feature-run Loki index labels); the audit name and
  all author-declared metadata MUST travel as per-record log attributes (Loki structured metadata),
  NOT as new Loki index labels — promoting a new index label is out of scope and MUST NOT be required.
- **FR-012**: Audit-result emission MUST be fire-and-forget: a telemetry outage MUST NOT change any
  verdict, MUST NOT raise, and MUST NOT alter the runner's verdict-driven exit status (consistent with
  the existing `emit.py` contract).
- **FR-013**: Audit results MUST be viewable in Grafana grouped/filterable by `feature` and `run_id`
  and by audit name, so a viewer can see which audits passed/failed for a given run and read the
  failure evidence. Filtering by `feature`/`run_id` uses the existing Loki index labels (template
  dropdowns); filtering by audit name (and any metadata) is achieved with LogQL structured-metadata
  line/label filters (`| audit="…"`), not by adding a new Loki index label.
- **FR-014**: The runner's exit status MUST reflect the aggregate verdict (e.g. non-zero when any
  audit `fail`s or `error`s) so it can gate automated workflows, with "no audits discovered"
  distinguishable from "all passed".
- **FR-015**: The feature MUST ship clear, understandable end-user documentation covering how to write
  an `@audit` function, what query helpers are available, how metadata is declared and where it
  appears, how to run the runner, and how to find results in Grafana — with at least the flagship
  example reproduced and runnable.

### Key Entities *(include only if the feature involves data)*

- **Audit check**: A named, code-defined rule (a decorated Python function) with author-declared
  metadata; evaluates against one feature run and yields a verdict.
- **Audit result**: The outcome of evaluating one audit against one run — audit name, verdict
  (`pass`/`fail`/`error`/`warn`), `run_id`, `feature`, declared metadata, timestamp, and evidence on
  failure.
- **Feature run**: The existing telemetry run identity (`run_id`, `trace_id`, bound `feature`) that an
  audit is evaluated against; the substrate the queries read.
- **Agent tool-read record**: The enriched telemetry record capturing which file path/pattern an agent
  (by role) read/edited/wrote/searched during the run — the data `get_all_reads_from_code_review_agent`
  reads.
- **Diff/commit record**: The existing per-run commit record carrying the changed files (`git_files`)
  that `all_diffs_for_feature()` reads.

## Success Criteria *(mandatory)*

- **SC-001**: An author can express a working audit check in a single decorated Python function and
  see its pass/fail verdict from the runner, with no telemetry-query plumbing written by hand.
- **SC-002**: The flagship audit ("every changed file was reviewed by the code-review agent") returns
  `pass` on a run where it holds and `fail` (naming the unreviewed files) on a run where it does not.
- **SC-003**: For an instrumented run, the recorded telemetry exposes the actual file paths read by
  each agent role — verifiable by querying the run and finding the known read paths — closing the
  current "keys-only" gap.
- **SC-004**: Every executed audit produces exactly one result discoverable in Grafana for its
  `run_id`, carrying its name, verdict, declared metadata, and (on failure) its evidence.
- **SC-005**: With the telemetry stack stopped, the runner still produces and reports all verdicts and
  its verdict-driven exit status is unchanged — zero verdicts are lost to a telemetry outage.
- **SC-006**: A developer who has never seen the framework can, using only the shipped documentation,
  author a new passing audit and locate its result in Grafana without further guidance.

## Constraints & things to be aware of *(mandatory)*

- **Build on the existing telemetry substrate, do not reinvent it.** Audits query the existing
  feature-run telemetry (`run_id`/`feature` index labels, spans in Tempo, log records in Loki via the
  collector at host ports 14317/14318) and emit results through the existing `emit.py` OTLP/HTTP path
  and `run-context.sh` run identity. Grafana surfacing extends the existing `feature-runs` dashboard
  rather than standing up a parallel stack.
- **Known gap / first-class dependency:** the transcript-ingest hook (`subagent_stop.py`,
  `_summarize_content`) currently records only tool-input *keys* (`",".join(sorted(input.keys()))`),
  not their values — so today telemetry knows an agent called `Read` but not *what* it read.
  FR-009 exists specifically to close this; the flagship audit cannot work until it is closed. Note
  `git_files` IS already captured on `commit` events, so `all_diffs_for_feature()` has its data today.
- **Fire-and-forget telemetry (Principle of harmless absence):** emission must never block, fail, or
  alter a run/verdict when the collector is down — mirror the existing `emit.py` contract (short
  timeout, swallow errors, exit 0).
- **No backward compatibility (Constitution I):** enriching the capture replaces the keys-only
  behaviour; do not keep a keys-only legacy path alongside the value-capturing one.
- **No reward hacking / Test-First (Constitution II & III):** audits, the runner, and the enriched
  capture must be backed by real, genuinely-failing-first tests (pytest under `tests/`, invoking
  shell scripts via `subprocess` where shell is involved); no stubbed verdicts, no test narrowed to
  pass. A failing audit must fail honestly.
- **Security (Constitution Security Requirements):** captured tool-input values must not leak secrets
  unmasked; bound the captured value and mask/omit sensitive content (show first/last 4 chars only if
  display is required).
- **Tooling & conventions:** use the repo's `uv`+`pytest` harness and `pathlib.Path`; shell touched
  must follow the shell/installer conventions (`set -euo pipefail`, quoted expansions); Conventional
  Commits.
- **Honesty (Constitution IV):** an `error` verdict (the audit couldn't evaluate) must be reported as
  such and never silently coerced into `pass`.

## Assumptions *(mandatory)*

- Audits are evaluated against telemetry already persisted for a run (post-hoc or against an
  in-progress run's recorded-so-far data); the runner reads telemetry, it does not re-execute the
  feature. *(Default chosen; the description implies querying recorded reads/diffs.)*
- The runner is a developer/CI-invoked Python entry point run from the repo root (consistent with the
  existing feature-run hooks requiring repo-root launch), not an always-on service.
- "Show up in Grafana with metadata per `@audit` tag" is satisfied by emitting audit results as log
  records carrying the audit name + verdict + metadata, surfaced on the existing Feature runs
  dashboard — chosen as "the best way" over standing up a separate metrics pipeline, because audit
  results are low-volume, evidence-bearing events that fit Loki's log+structured-metadata model and
  the existing `feature`/`run_id` index labels.
- **Loki label model (resolved from the substrate, not a new index label).** The substrate promotes
  ONLY `feature`, `run_id`, and the default `service.name` to Loki index labels (see
  `telemetry/loki/loki-config.yaml` `otlp_config.resource_attributes.attributes_config`, and
  `emit.py` `send_logs` which sets those as resource attributes while per-record `attrs` ride as
  structured metadata). Therefore the audit name and all `@audit` metadata are emitted as per-record
  log attributes (Loki structured metadata, LogQL-filterable via `| audit="…"` / `| severity="…"`),
  NOT as new index labels. The plan MUST NOT add a third feature-run index label or change
  `loki-config.yaml`'s `attributes_config` — doing so is a cardinality/Loki-config change outside this
  feature's scope. (Loki only allows `index_label` on resource attributes anyway.)
- `@audit` decorator metadata is an open key/value set; a small recommended vocabulary (name,
  category, severity, owner) is documented but authors may add their own keys.
- The flagship `get_all_reads_from_code_review_agent()` resolves "the code-review agent" by the
  telemetry `role` attribute already recorded on sub-agent spans/records (e.g. the code-review
  role), rather than by agent_id.
- Default verdict-to-exit mapping: any `fail` or `error` → non-zero; `warn`-only → zero (configurable
  later if needed). Recorded so it can be challenged.
- Documentation lives with the other developer docs (Starlight site / repo docs) so it is picked up
  by the existing docs-sync flow.
- **Empty-diff verdict (default chosen, low-stakes, reversible).** When a run changed no files, the
  flagship "every changed file was reviewed" audit evaluates over the empty set and returns `pass`
  (vacuous truth: there is nothing left unreviewed), per Edge case E3 and US1 scenario 5 — not `error`
  or `fail`. This is a defensible default for a universally-quantified rule; an author who wants
  "a run must change at least one file" can express that as a separate audit. Recorded explicitly so
  it can be challenged without forking the build.

## Open Questions *(mandatory)*

- None.
