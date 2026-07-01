# Claude Code Telemetry Stack

A self-contained OpenTelemetry stack that ingests [Claude Code's telemetry](https://code.claude.com/docs/en/monitoring-usage) and visualises usage, cost, and chat/activity logs.

```
Claude Code ──OTLP/gRPC:4317──▶ OTel Collector ──┬─▶ Prometheus  (metrics)
                                                  ├─▶ Loki        (logs/events)
                                                  └─▶ Tempo       (traces)
                                                                   └─▶ Grafana (dashboards)
```

## Components

| Service | Image | Role | Host port |
| --- | --- | --- | --- |
| `otel-collector` | `otel/opentelemetry-collector-contrib` | OTLP ingestor; fans metrics→Prometheus, logs→Loki | 4317 (gRPC), 4318 (HTTP), 8889/8888 |
| `prometheus` | `prom/prometheus` | Metrics store, scrapes the collector | 9090 |
| `loki` | `grafana/loki` | Logs/events store (native OTLP ingestion) | 3100 |
| `tempo` | `grafana/tempo` | Trace store for the feature-run span tree | 3200 |
| `grafana` | `grafana/grafana` | Dashboards (pre-provisioned) | 3000 |

## Quick start

```bash
cd telemetry
docker compose up -d
source ./claude-otel.env   # env vars persist across the cd below

# IMPORTANT: launch Claude Code from the REPO ROOT, not from telemetry/.
cd ..                      # repo root — where .claude/settings.json (the
                           # feature-run hooks) and .agents/ live
claude
```

> **The feature-run sub-agent hooks are PROJECT hooks** (defined in the repo-root
> `.claude/settings.json`), and Claude Code only executes project hooks when **two
> conditions hold**, or the per-sub-agent spans / transcript drill-down silently
> never emit (you'll still get gate/commit/intake events, which come from `emit.py`
> directly, but the **Feature Runs waterfall will be empty**):
>
> 1. **Launch from the repo root** so the project directory — and therefore
>    `$CLAUDE_PROJECT_DIR`, which every hook command interpolates — resolves to the
>    repo root. Starting `claude` inside `telemetry/` roots the session there, so the
>    repo-root project settings (and thus the hooks) are never loaded.
> 2. **Accept the "trust the files in this folder" dialog** on first run. Claude Code
>    will not run project-defined hooks for an untrusted folder (global hooks still
>    run, which is why other tooling can appear to work while these hooks do not).
>    Check with `jq '.projects["<repo-root>"].hasTrustDialogAccepted' ~/.claude.json`.

Then open Grafana at **http://localhost:3000** (`admin` / `admin`). Two dashboards
are provisioned under the **Claude Code** folder:

- **Claude Code — Overview**: cost, token usage by type, sessions, commits/PRs,
  lines of code, tool-decision accept/reject, active time. Filterable by model and user.
- **Claude Code — Chat & Activity Logs**: user prompts, tool calls/results,
  API errors/refusals, and a raw event stream — backed by Loki.
- **Feature Runs**: one view per `feature`-skill run — the full stage/sub-agent
  trace waterfall (Tempo), gate verdicts, commits, and the initial prompt. See below.

> Note on Grafana login: the admin password is set on the **first** start only and
> then lives in the `grafana-data` volume. If `admin`/`admin` is rejected, use the
> password you set previously (or reset it: `docker compose exec grafana grafana cli
> admin reset-admin-password <new>`).

## About "chat logs"

Claude Code's logs/events protocol emits **prompts and activity, not a full transcript**:

- `user_prompt` — prompt text only when `OTEL_LOG_USER_PROMPTS=1` (set in `claude-otel.env`), otherwise `<REDACTED>`.
- `tool_result`, `tool_decision`, `api_request`, `api_error`, `api_refusal`, etc.
- **Assistant replies are not logged by default.** To capture the full
  conversation (request + response bodies, including history), enable
  `OTEL_LOG_RAW_API_BODIES` — see the commented block in `claude-otel.env`.
  This logs the entire conversation; treat it as sensitive data.

## Feature-run tracing (the `feature` skill)

The `feature` orchestrator runs each stage (specification → … → implementor) and its
nested sub-agents (per-task implementer + **independent reviewer**, plan self-review)
as separate agents. This stack reconstructs a whole run as one trace so you can see —
and audit — exactly what happened.

**How it's wired** (all under `.agents/skills/_shared/telemetry/`):

- `run-context.sh` mints a `run_id` + W3C `trace_id` at run start (Phase 0), persisted
  to `temp/telemetry/current.json`. Each NEW feature mints a fresh run (so it's its own
  entry in the dashboard); a resume (`init --feature-dir <dir>`) reuses the same ids, so
  the trace continues rather than forking. The `specification` phase binds the run to its
  feature dir the moment it writes `.specify/feature.json` — stamping the `feature` slug
  (e.g. `002-subdir-install-layout`) onto every span/log and mirroring the ids back into
  `feature.json`. Binding lives in `specification` so it can't be skipped.
- **Claude Code hooks** (`.claude/settings.json` → `hooks/*.py`) fire on every
  sub-agent spawn/stop — deterministically, regardless of what the model says — and
  emit one **span per sub-agent**, nested correctly (a child's parent span id is
  derived from the parent's `agent_id`, so reverse-order stops under nesting still
  nest right). `SubagentStop` also ingests that sub-agent's **own transcript**
  (prompt, tool calls, reasoning) into Loki tagged with `run_id` + `agent_id`.
- `emit.py` (zero-dep OTLP/HTTP) adds the meaning hooks can't know: phase/role labels,
  **gate** PASS/FAIL from the validators, and **commit** events from
  `git-commit-safe.sh` (which also stamps a `Feature-Run: <run_id>` git trailer).

**Using it:** open the **Feature Runs** dashboard, pick a `feature` from the dropdown,
then a `run_id` (the dropdown lists only that feature's runs). The trace panel
shows feature → stages → sub-agents → nested implementer/reviewer. **Click any span**
to jump to that sub-agent's activity in Loki (its prompt, tool calls, reasoning).
Gate and commit panels prove required files were validated before the next phase and
which commit each task produced. All telemetry is **best-effort**: with the stack
down, the `feature` run proceeds normally and emits nothing.

### First-run verification (do this once)

The hook + native-log behaviour can only be confirmed in a live session, so the very
first run doubles as a spike:

1. In a fresh shell: `cd telemetry && docker compose up -d && source ./claude-otel.env`,
   then start `claude` (so it loads `.claude/settings.json` with telemetry enabled).
2. Run a `feature` on a tiny throwaway feature (or just spawn a couple of sub-agents).
3. Open **Feature Runs** → confirm: the waterfall shows the stage/sub-agent tree; an
   **independent reviewer** span exists per implemented task; gate events precede the
   next phase; clicking an implementer span shows its transcript; the commits panel
   lists shas and `git log` shows the `Feature-Run:` trailer.
4. **Spike check:** in Loki, see whether Claude Code's *native* events
   (`api_request_body_event`, `tool_result_event`) carry an `agent_id`. If they do,
   you can set `FEATURE_TELEMETRY_INGEST_TRANSCRIPTS=0` and rely on native logs for
   click-through instead of transcript ingestion. If not, leave ingestion on (the
   default) — it's what makes per-sub-agent drill-down deterministic.

## Verifying it works

```bash
docker compose ps                                   # all services Up
curl -s localhost:18889/metrics | grep claude_code  # collector re-exporting metrics
curl -s "localhost:3100/loki/api/v1/labels"         # Loki receiving logs
curl -s localhost:3200/ready                         # Tempo ready (traces)
curl -s "localhost:3100/loki/api/v1/label/feature/values"  # features seen so far
curl -s "localhost:3100/loki/api/v1/label/run_id/values"   # feature runs seen so far
```

If no `claude_code_*` metrics appear, confirm you `source`d `claude-otel.env` in the
same shell as `claude`, and that nothing else is bound to ports 4317/4318.

## Notes & caveats

- **Temporality**: Prometheus needs cumulative metrics; `claude-otel.env` sets
  `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` accordingly.
- **Metric names**: the collector's Prometheus exporter runs with
  `add_metric_suffixes: false`, so names map predictably
  (`claude_code.token.usage` → `claude_code_token_usage`). Dashboards rely on this.
- **`service.name`**: a `resource` processor stamps `service.name=claude-code` so
  Loki queries can use `{service_name="claude-code"}`.
- **Default credentials** (`admin`/`admin`) and open ports are fine for local use.
  Lock these down before exposing anywhere shared.
- **Persistence**: Prometheus, Loki, Tempo, and Grafana data live in named Docker
  volumes (`prometheus-data`, `loki-data`, `tempo-data`, `grafana-data`).
  `docker compose down -v` wipes them.
- **Feature spans vs Claude Code logs**: feature-run spans/events carry
  `service.name=feature-orchestrator` (vs `claude-code`), so the two never collide;
  `feature` and `run_id` are Loki index labels, everything else is structured metadata.
```
