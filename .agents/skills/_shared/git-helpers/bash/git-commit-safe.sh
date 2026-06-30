#!/usr/bin/env bash
# Guarded atomic commit — shared by implementor (and self-learn's optional commit).
#
# Encodes the repo's commit rules STRUCTURALLY so a skill can't get them wrong:
#   * stages ONLY the paths you name (never sweeps unrelated working-tree changes);
#   * refuses to run if the index already has unrelated staged changes;
#   * enforces a Conventional Commits subject;
#   * appends the Claude co-author trailer;
#   * lets pre-commit run — NEVER passes --no-verify / --skip;
#   * exposes NONE of the forbidden verbs (no push / checkout / switch /
#     reset --hard / clean / restore / rm / rebase). It can only add + commit.
#
# If a hook fails (or modifies files and aborts the commit) the script exits
# non-zero and leaves the tree as git left it — fix and re-review; do not bypass.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null \
  || git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${GIT_ROOT}" ]]; then
  echo "Not inside a git repository." >&2
  exit 1
fi
G() { git -C "${GIT_ROOT}" "$@"; }

TRAILER="Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
CONV_RE='^(feat|fix|refactor|build|ci|chore|docs|style|perf|test)(\([a-zA-Z0-9._/-]+\))?!?: .+'

MESSAGE=""
PATHS=()
ALLOW_DEFAULT_BRANCH=0
NO_TRAILER=0
DRY_RUN=0

usage() {
  cat >&2 <<EOF
Usage: git-commit-safe.sh -m "<conventional message>" [options] <path> [<path> ...]

Stages exactly the given paths and makes ONE atomic Conventional Commit.

Required:
  -m, --message <msg>      Commit message. First line must be Conventional Commits:
                           feat|fix|refactor|build|ci|chore|docs|style|perf|test(scope): summary
  <path> ...               The task's footprint — only these paths are staged.

Options:
  --allow-default-branch   Permit committing while HEAD is the default branch
                           (otherwise the script refuses, so you raise the branch
                           question with the user first — it never switches branches).
  --no-trailer             Do not append the Claude co-author trailer.
  --dry-run                Show what would be staged/committed; make no changes.
  -h | --help

Refuses (exit non-zero) if: not a git repo; no message/paths; message isn't
Conventional; the index already has staged changes outside your paths; the paths
match nothing changed; or on the default branch without --allow-default-branch.
NEVER bypasses hooks.
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)          MESSAGE="$2"; shift 2 ;;
    --allow-default-branch) ALLOW_DEFAULT_BRANCH=1; shift ;;
    --no-trailer)          NO_TRAILER=1; shift ;;
    --dry-run)             DRY_RUN=1; shift ;;
    -h|--help)             usage ;;
    --) shift; while [[ $# -gt 0 ]]; do PATHS+=("$1"); shift; done ;;
    -*) echo "Unknown option: $1" >&2; usage ;;
    *)  PATHS+=("$1"); shift ;;
  esac
done

[[ -z "${MESSAGE}" ]] && { echo "Error: -m/--message is required." >&2; usage; }
[[ ${#PATHS[@]} -eq 0 ]] && { echo "Error: at least one path to stage is required." >&2; usage; }

# 1. Conventional Commits gate (first line only)
SUBJECT="${MESSAGE%%$'\n'*}"
if [[ ! "${SUBJECT}" =~ ${CONV_RE} ]]; then
  echo "Error: subject is not a Conventional Commit:" >&2
  echo "  ${SUBJECT}" >&2
  echo "Expected: <type>(<scope>): <summary>  (type ∈ feat|fix|refactor|build|ci|chore|docs|style|perf|test)" >&2
  exit 1
fi

# 2. Refuse to sweep in staged changes OUTSIDE the named paths. Changes already
#    staged *within* the footprint are fine (that's what we're committing). We
#    can't unstage the rest — reset/restore are forbidden — so we abort & report.
PRE_STAGED="$(G diff --cached --name-only)"
if [[ -n "${PRE_STAGED}" ]]; then
  OUT_OF_SCOPE=""
  while IFS= read -r f; do
    [[ -z "${f}" ]] && continue
    covered=0
    for p in "${PATHS[@]}"; do
      pp="${p%/}"
      if [[ "${f}" == "${pp}" || "${f}" == "${pp}"/* ]]; then covered=1; break; fi
    done
    [[ ${covered} -eq 0 ]] && OUT_OF_SCOPE+="  ${f}"$'\n'
  done <<< "${PRE_STAGED}"
  if [[ -n "${OUT_OF_SCOPE}" ]]; then
    echo "Error: the index has staged changes outside the paths you named:" >&2
    printf '%s' "${OUT_OF_SCOPE}" >&2
    echo "Refusing to fold them into this commit. Commit/handle them separately first." >&2
    exit 1
  fi
fi

# 3. Default-branch guard (the branch decision is the user's; we never switch).
CUR_BRANCH="$(G rev-parse --abbrev-ref HEAD 2>/dev/null || echo "DETACHED")"
DEFAULT_BRANCH="$(G symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null \
  | sed 's@^refs/remotes/origin/@@')" || true
if [[ -z "${DEFAULT_BRANCH}" ]]; then
  for c in main master; do
    if G rev-parse --verify --quiet "refs/heads/${c}" >/dev/null 2>&1; then DEFAULT_BRANCH="${c}"; break; fi
  done
fi
if [[ -n "${DEFAULT_BRANCH}" && "${CUR_BRANCH}" == "${DEFAULT_BRANCH}" && "${ALLOW_DEFAULT_BRANCH}" -eq 0 ]]; then
  echo "Error: HEAD is on the default branch '${DEFAULT_BRANCH}'." >&2
  echo "Raise the feature-branch question with the user (this script never switches branches)." >&2
  echo "Re-run with --allow-default-branch to commit here intentionally." >&2
  exit 1
fi

# 4. Stage exactly the named paths.
G add -- "${PATHS[@]}"

STAGED="$(G diff --cached --name-only)"
if [[ -z "${STAGED}" ]]; then
  echo "Nothing to commit — the given paths have no staged changes." >&2
  exit 1
fi

# 5. Assemble the final message. Trailers (one contiguous block): the Claude
#    co-author trailer, plus a Feature-Run trailer tying the commit to the active
#    feature run so `git log` <-> the trace cross-reference both ways. Best-effort;
#    no active run -> no Feature-Run trailer.
RUN_ID="$(grep -o '"run_id"[[:space:]]*:[[:space:]]*"[^"]*"' "${GIT_ROOT}/temp/telemetry/current.json" 2>/dev/null \
  | sed 's/.*:[[:space:]]*"\([^"]*\)".*/\1/' | head -n1 || true)"
TRAILERS=""
if [[ "${NO_TRAILER}" -eq 0 && "${MESSAGE}" != *"Co-Authored-By: Claude"* ]]; then
  TRAILERS="${TRAILER}"
fi
if [[ -n "${RUN_ID}" && "${MESSAGE}" != *"Feature-Run:"* ]]; then
  if [[ -n "${TRAILERS}" ]]; then TRAILERS="${TRAILERS}"$'\n'"Feature-Run: ${RUN_ID}"
  else TRAILERS="Feature-Run: ${RUN_ID}"; fi
fi
FINAL_MSG="${MESSAGE}"
if [[ -n "${TRAILERS}" ]]; then
  FINAL_MSG="${MESSAGE}"$'\n\n'"${TRAILERS}"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] would commit on branch '${CUR_BRANCH}' with subject:"
  echo "  ${SUBJECT}"
  echo "[dry-run] staged files:"
  echo "${STAGED}" | sed 's/^/  /'
  echo "[dry-run] no changes made (index left staged)."
  exit 0
fi

# 6. Commit — hooks run (pre-commit/ruff). No --no-verify, ever.
MSG_FILE="$(mktemp)"
trap 'rm -f "${MSG_FILE}"' EXIT
printf '%s\n' "${FINAL_MSG}" > "${MSG_FILE}"

if ! G commit -F "${MSG_FILE}"; then
  echo "" >&2
  echo "Commit failed (a hook rejected it or modified files). The task is NOT green." >&2
  echo "Fix the cause and re-review — do NOT retry with --no-verify/--skip." >&2
  exit 1
fi

echo "Committed: $(G log -1 --format='%h %s')"

# Emit a commit event tying this sha to the active feature run (trace -> commit).
# Best-effort: no run / no collector -> silent no-op, never affects the commit.
TEL_EMIT="${SCRIPT_DIR}/../../telemetry/emit.py"
if [[ -n "${RUN_ID}" && -f "${TEL_EMIT}" ]]; then
  python3 "${TEL_EMIT}" commit \
    --sha "$(G log -1 --format='%H')" \
    --subject "$(G log -1 --format='%s')" \
    --phase "${FEATURE_GATE_PHASE:-implementor}" \
    --files "$(IFS=,; echo "${PATHS[*]}")" >/dev/null 2>&1 || true
fi
