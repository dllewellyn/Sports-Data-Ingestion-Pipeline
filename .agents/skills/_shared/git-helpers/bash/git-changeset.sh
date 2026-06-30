#!/usr/bin/env bash
# Read-only changeset inspector — shared by the review / learning skills.
#
# Emits the "what changed" context (branch/base header, status, commit log,
# uncommitted diff, committed branch-vs-base diff) deterministically. It
# resolves the repo's default branch and the merge-base itself, so skills
# never hardcode `main` (which breaks on master/develop/detached HEAD).
#
# STRICTLY READ-ONLY. It only ever runs: rev-parse, symbolic-ref, for-each-ref,
# status, log, diff, merge-base. It never stages, commits, or mutates anything.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null \
  || git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${GIT_ROOT}" ]]; then
  echo "Not inside a git repository." >&2
  exit 1
fi
G() { git -C "${GIT_ROOT}" "$@"; }

BASE_OVERRIDE=""
SECTION="all"        # all | log | status | diff
DIFF_STYLE="full"    # full | stat
LOG_LIMIT=20

usage() {
  cat >&2 <<EOF
Usage: git-changeset.sh [options]

Read-only inspector for "what changed on this branch / in the working tree".

Options:
  --base <ref>     Compare against <ref> instead of the auto-detected default branch.
  --section <s>    Limit output to: all (default) | log | status | diff
  --stat           Use --stat for diffs (compact) instead of full patches.
  --log-limit <n>  Max commits to show in the log section (default: 20; 0 = all in range).
  -h | --help

Output sections (in 'all'): header (branch/base/merge-base/worktree state),
STATUS (porcelain), LOG (base..HEAD), DIFF — UNCOMMITTED, DIFF — COMMITTED (base..HEAD).
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)      BASE_OVERRIDE="$2"; shift 2 ;;
    --section)   SECTION="$2"; shift 2 ;;
    --stat)      DIFF_STYLE="stat"; shift ;;
    --log-limit) LOG_LIMIT="$2"; shift 2 ;;
    -h|--help)   usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

detect_default_branch() {
  local d
  # 1. origin/HEAD symbolic ref (most reliable when a remote exists)
  d="$(G symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null \
        | sed 's@^refs/remotes/origin/@@')" || true
  if [[ -n "${d}" ]] && G rev-parse --verify --quiet "origin/${d}" >/dev/null 2>&1; then
    echo "origin/${d}"; return
  fi
  # 2. common local/remote names
  local c
  for c in main master develop trunk; do
    if G rev-parse --verify --quiet "refs/heads/${c}" >/dev/null 2>&1; then echo "${c}"; return; fi
  done
  for c in main master develop trunk; do
    if G rev-parse --verify --quiet "refs/remotes/origin/${c}" >/dev/null 2>&1; then echo "origin/${c}"; return; fi
  done
  echo ""
}

CUR_BRANCH="$(G rev-parse --abbrev-ref HEAD 2>/dev/null || echo "DETACHED")"
BASE_REF="${BASE_OVERRIDE}"
[[ -z "${BASE_REF}" ]] && BASE_REF="$(detect_default_branch)"

# Compute merge-base if base is usable and is not HEAD itself
MERGE_BASE=""
BASE_NOTE=""
if [[ -n "${BASE_REF}" ]] && G rev-parse --verify --quiet "${BASE_REF}" >/dev/null 2>&1; then
  if [[ "$(G rev-parse "${BASE_REF}")" == "$(G rev-parse HEAD)" ]]; then
    BASE_NOTE="HEAD is at the base ref — no committed branch delta."
  else
    MERGE_BASE="$(G merge-base "${BASE_REF}" HEAD 2>/dev/null || true)"
    [[ -z "${MERGE_BASE}" ]] && BASE_NOTE="No common ancestor with ${BASE_REF}; committed-diff section skipped."
  fi
else
  BASE_NOTE="Could not resolve a base/default branch; showing uncommitted changes only."
fi

if [[ -n "$(G status --porcelain)" ]]; then WORKTREE="dirty"; else WORKTREE="clean"; fi

diff_args() { [[ "${DIFF_STYLE}" == "stat" ]] && echo "--stat" || echo "--patch"; }

print_header() {
  echo "# Changeset"
  echo "repo:        ${GIT_ROOT}"
  echo "branch:      ${CUR_BRANCH}"
  echo "base:        ${BASE_REF:-<none>}"
  echo "merge-base:  ${MERGE_BASE:-<none>}"
  echo "worktree:    ${WORKTREE}"
  [[ -n "${BASE_NOTE}" ]] && echo "note:        ${BASE_NOTE}"
  echo ""
}

print_status() {
  echo "## STATUS (git status --short)"
  G status --short || true
  echo ""
}

print_log() {
  echo "## LOG (commits on this branch since base)"
  if [[ -n "${MERGE_BASE}" ]]; then
    local lim=()
    [[ "${LOG_LIMIT}" != "0" ]] && lim=(-n "${LOG_LIMIT}")
    G log --oneline "${lim[@]}" "${MERGE_BASE}..HEAD" || true
  else
    echo "(no base delta — showing recent history instead)"
    G log --oneline -n "${LOG_LIMIT}" || true
  fi
  echo ""
}

print_diff() {
  echo "## DIFF — UNCOMMITTED (working tree + index)"
  G diff "$(diff_args)" HEAD || true
  echo ""
  if [[ -n "${MERGE_BASE}" ]]; then
    echo "## DIFF — COMMITTED (base..HEAD)"
    G diff "$(diff_args)" "${MERGE_BASE}..HEAD" || true
    echo ""
  fi
}

case "${SECTION}" in
  all)    print_header; print_status; print_log; print_diff ;;
  status) print_header; print_status ;;
  log)    print_header; print_log ;;
  diff)   print_header; print_diff ;;
  *) echo "Unknown section: ${SECTION}" >&2; usage ;;
esac
