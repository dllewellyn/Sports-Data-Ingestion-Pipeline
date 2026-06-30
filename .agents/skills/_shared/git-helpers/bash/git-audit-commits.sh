#!/usr/bin/env bash
# Read-only commit auditor — shared by feature's adherence meta-reviewer.
#
# Deterministically checks the mechanical parts of "commits are clean": each
# commit on this branch since base is a Conventional Commit, none are merges,
# and flags likely non-atomic commits (touch many files / span unrelated
# top-level dirs). The *semantic* checks (one-per-task, message traces to the
# plan step) stay with the reviewing agent — this just hands it the facts.
#
# STRICTLY READ-ONLY. Only runs: rev-parse, symbolic-ref, merge-base, log,
# show, rev-list. Never mutates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null \
  || git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${GIT_ROOT}" ]]; then
  echo "Not inside a git repository." >&2
  exit 1
fi
G() { git -C "${GIT_ROOT}" "$@"; }

CONV_RE='^(feat|fix|refactor|build|ci|chore|docs|style|perf|test)(\([a-zA-Z0-9._/-]+\))?!?: .+'
BASE_OVERRIDE=""
FILE_WARN=15   # commits touching more than this many files are flagged as possibly non-atomic

usage() {
  cat >&2 <<EOF
Usage: git-audit-commits.sh [options]

Audits commits on the current branch since the base for mechanical commit hygiene.

Options:
  --base <ref>      Audit base..HEAD (default: auto-detected default branch).
  --file-warn <n>   Flag commits touching > n files as possibly non-atomic (default: 15).
  -h | --help

Output: one block per commit (sha, subject, PASS/FAIL conventional, merge?, file
count, top-level dirs touched) then a summary (total, conventional fails, merges,
fat commits). Exit code is non-zero if any commit fails the conventional gate or
is a merge — so it doubles as a gate.
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)      BASE_OVERRIDE="$2"; shift 2 ;;
    --file-warn) FILE_WARN="$2"; shift 2 ;;
    -h|--help)   usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

BASE_REF="${BASE_OVERRIDE}"
if [[ -z "${BASE_REF}" ]]; then
  BASE_REF="$(G symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null \
    | sed 's@^refs/remotes/origin/@@')" || true
  if [[ -n "${BASE_REF}" ]]; then BASE_REF="origin/${BASE_REF}"; fi
  if [[ -z "${BASE_REF}" ]]; then
    for c in main master develop trunk; do
      if G rev-parse --verify --quiet "refs/heads/${c}" >/dev/null 2>&1; then BASE_REF="${c}"; break; fi
    done
  fi
fi
if [[ -z "${BASE_REF}" ]] || ! G rev-parse --verify --quiet "${BASE_REF}" >/dev/null 2>&1; then
  echo "Could not resolve a base branch; pass --base <ref>." >&2
  exit 1
fi

MERGE_BASE="$(G merge-base "${BASE_REF}" HEAD 2>/dev/null || true)"
if [[ -z "${MERGE_BASE}" ]]; then
  echo "No common ancestor with ${BASE_REF}." >&2
  exit 1
fi

COMMITS=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && COMMITS+=("${line}")
done < <(G rev-list --reverse "${MERGE_BASE}..HEAD")
echo "# Commit audit  (base: ${BASE_REF}, range: ${MERGE_BASE:0:8}..HEAD, ${#COMMITS[@]} commit(s))"
echo ""

total=0; conv_fail=0; merges=0; fat=0
for sha in "${COMMITS[@]}"; do
  [[ -z "${sha}" ]] && continue
  total=$((total + 1))
  subject="$(G log -1 --format='%s' "${sha}")"
  parents="$(G log -1 --format='%P' "${sha}")"
  nparents=$(wc -w <<<"${parents}")
  files="$(G show --no-commit-id -r --name-only --format='' "${sha}" | sed '/^$/d')"
  fcount=$(printf '%s\n' "${files}" | sed '/^$/d' | wc -l | tr -d ' ')
  topdirs="$(printf '%s\n' "${files}" | sed '/^$/d' | awk -F/ '{print $1}' | sort -u | paste -sd',' -)"

  conv="PASS"; [[ "${subject}" =~ ${CONV_RE} ]] || { conv="FAIL"; conv_fail=$((conv_fail + 1)); }
  is_merge="no"; [[ "${nparents}" -gt 1 ]] && { is_merge="yes"; merges=$((merges + 1)); }
  fatflag=""; [[ "${fcount}" -gt "${FILE_WARN}" ]] && { fatflag=" (possibly non-atomic)"; fat=$((fat + 1)); }

  echo "- ${sha:0:8}  conventional:${conv}  merge:${is_merge}  files:${fcount}${fatflag}"
  echo "    subject:  ${subject}"
  echo "    topdirs:  ${topdirs:-<none>}"
done

echo ""
echo "## Summary"
echo "commits:            ${total}"
echo "conventional fails: ${conv_fail}"
echo "merge commits:      ${merges}"
echo "fat (> ${FILE_WARN} files):    ${fat}"
echo ""
echo "Note: 'one commit per task' and 'message traces to the plan step' are semantic —"
echo "the reviewing agent judges those against the plan; this tool checks only mechanics."

if [[ "${conv_fail}" -gt 0 || "${merges}" -gt 0 ]]; then
  exit 1
fi
