#!/usr/bin/env bash
# run-context.sh — own the per-feature-run correlation identity (the trace).
#
# The `feature` flow spawns every stage and sub-agent as separate agents; to draw
# the whole run as one trace in Grafana they must share a stable trace id. This
# helper mints that identity ONCE per run and persists it so every later phase,
# the Claude Code hooks, and the shared helpers can pick it up — and reuses it on
# resume so a restarted run continues the SAME trace instead of forking a new one.
#
# Source of truth (well-known, does NOT depend on .specify/feature.json existing,
# because specification writes feature.json only in phase A — after §0 intake):
#   temp/telemetry/current.json            { run_id, trace_id, root_span_id, ... }
#   temp/telemetry/<run_id>/context.json   per-run copy (survives a new run)
# When .specify/feature.json exists it ALSO gets a mirrored `telemetry` block for
# the git ↔ trace audit story.
#
# Commands:
#   init [--feature-dir <dir>]   mint-or-reuse the run; prints run_id to stdout
#   current [--field <k>]        print current.json (or one field)
#   attach                       re-mirror the telemetry block into feature.json
#   close [--status ok|error]    emit the root feature span (start..now) and mark ended
#
# Like emit.py this is best-effort: telemetry must never break a feature run.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMIT="${SCRIPT_DIR}/emit.py"

ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null \
  || git rev-parse --show-toplevel 2>/dev/null \
  || pwd)"
TEL_DIR="${ROOT}/temp/telemetry"
CURRENT="${TEL_DIR}/current.json"

py() { python3 "$@"; }

cmd="${1:-}"; shift || true

case "${cmd}" in
  init)
    feature_dir=""
    if [[ "${1:-}" == "--feature-dir" ]]; then feature_dir="${2:-}"; shift 2 || true; fi

    # Reuse an active run when the pointer exists, is not closed, and either no
    # feature dir was supplied or it matches the recorded one (resume).
    if [[ -f "${CURRENT}" ]]; then
      reuse_id="$(py - "$CURRENT" "$feature_dir" <<'PY'
import json, sys
cur, want = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(cur, encoding="utf-8"))
except Exception:
    sys.exit(0)
if d.get("status") == "ended":
    sys.exit(0)
if want and d.get("feature_dir") and d["feature_dir"] != want:
    sys.exit(0)
print(d.get("run_id", ""))
PY
)"
      if [[ -n "${reuse_id}" ]]; then
        # Late-binding the feature dir on resume if we now know it.
        if [[ -n "${feature_dir}" ]]; then
          py - "$CURRENT" "$feature_dir" <<'PY'
import json, sys
cur, fd = sys.argv[1], sys.argv[2]
d = json.load(open(cur, encoding="utf-8"))
d["feature_dir"] = fd
json.dump(d, open(cur, "w", encoding="utf-8"), indent=2)
PY
        fi
        printf '%s\n' "${reuse_id}"
        exit 0
      fi
    fi

    mkdir -p "${TEL_DIR}"
    run_id="$(date -u +%Y%m%dT%H%M%SZ)-$(py "${EMIT}" new-span-id | cut -c1-6)"
    trace_id="$(py "${EMIT}" new-trace-id)"
    root_span_id="$(py "${EMIT}" new-span-id)"
    started_ns="$(py "${EMIT}" now-ns)"
    branch="$(git -C "${ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

    py - "$CURRENT" "$run_id" "$trace_id" "$root_span_id" "$started_ns" "$branch" "$feature_dir" <<'PY'
import json, os, sys
cur, run_id, trace_id, root, started, branch, fd = sys.argv[1:8]
data = {
    "run_id": run_id, "trace_id": trace_id, "root_span_id": root,
    "started_at_ns": int(started), "branch": branch,
    "feature_dir": fd, "status": "running",
}
json.dump(data, open(cur, "w", encoding="utf-8"), indent=2)
os.makedirs(os.path.join(os.path.dirname(cur), run_id), exist_ok=True)
json.dump(data, open(os.path.join(os.path.dirname(cur), run_id, "context.json"), "w", encoding="utf-8"), indent=2)
PY
    "${0}" attach >/dev/null 2>&1 || true
    printf '%s\n' "${run_id}"
    ;;

  current)
    [[ -f "${CURRENT}" ]] || { echo "error: no active run (temp/telemetry/current.json)" >&2; exit 1; }
    if [[ "${1:-}" == "--field" ]]; then
      py - "$CURRENT" "${2:?--field needs a key}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
v = d.get(sys.argv[2], "")
print(v if v is not None else "")
PY
    else
      cat "${CURRENT}"
    fi
    ;;

  attach)
    # Mirror the telemetry identity into .specify/feature.json when it exists.
    fj="${ROOT}/.specify/feature.json"
    [[ -f "${fj}" && -f "${CURRENT}" ]] || exit 0
    py - "$fj" "$CURRENT" <<'PY'
import json, sys
fj, cur = sys.argv[1], sys.argv[2]
try:
    f = json.load(open(fj, encoding="utf-8"))
    c = json.load(open(cur, encoding="utf-8"))
except Exception:
    sys.exit(0)
f["telemetry"] = {k: c.get(k) for k in ("run_id", "trace_id", "started_at_ns")}
json.dump(f, open(fj, "w", encoding="utf-8"), indent=2)
PY
    ;;

  close)
    status="ok"
    if [[ "${1:-}" == "--status" ]]; then status="${2:-ok}"; shift 2 || true; fi
    [[ -f "${CURRENT}" ]] || exit 0
    read -r trace_id run_id root_span_id started_ns <<<"$(py - "$CURRENT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print(d.get("trace_id",""), d.get("run_id",""), d.get("root_span_id",""), d.get("started_at_ns",""))
PY
)"
    end_ns="$(py "${EMIT}" now-ns)"
    py "${EMIT}" --trace-id "${trace_id}" --run-id "${run_id}" span \
      --name "feature-run" --role "feature-run" \
      --span-id "${root_span_id}" \
      --start-ns "${started_ns}" --end-ns "${end_ns}" \
      --status "${status}" >/dev/null 2>&1 || true
    py - "$CURRENT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
d["status"] = "ended"
json.dump(d, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
    ;;

  *)
    echo "usage: run-context.sh {init [--feature-dir <dir>]|current [--field <k>]|attach|close [--status ok|error]}" >&2
    exit 2
    ;;
esac
