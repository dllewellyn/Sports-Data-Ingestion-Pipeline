#!/usr/bin/env bash
# Read-only git history walker — shared by missing-specification (retro-spec backfill).
#
# Two operations:
#   list            Enumerate the history oldest -> newest as: <sha>\t<iso-date>\t<subject>
#   show <sha>      Print one commit's metadata + --stat (and full diff with --diff)
#
# STRICTLY READ-ONLY. Only runs: rev-parse, log, show, diff-tree. Never mutates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null \
  || git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${GIT_ROOT}" ]]; then
  echo "Not inside a git repository." >&2
  exit 1
fi
G() { git -C "${GIT_ROOT}" "$@"; }

ACTION="${1:-list}"
shift || true

SINCE=""
WITH_DIFF=0

usage() {
  cat >&2 <<EOF
Usage: git-history.sh <list|show> [options]

Commands:
  list                 Enumerate commits oldest -> newest, one per line:
                         <full_sha>\t<iso_date>\t<subject>
  show <sha>           Print <sha>'s metadata + name-status + --stat.

Options:
  --since <ref>        list: only commits after <ref> (exclusive). Default: all history.
  --diff               show: also print the full patch (default: --stat only).
  -h | --help
EOF
  exit 1
}

case "${ACTION}" in
  list)
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --since) SINCE="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; usage ;;
      esac
    done
    if [[ -n "${SINCE}" ]]; then
      if ! G rev-parse --verify --quiet "${SINCE}" >/dev/null 2>&1; then
        echo "Ref not found: ${SINCE}" >&2; exit 1
      fi
      G log --reverse --format='%H%x09%aI%x09%s' "${SINCE}..HEAD"
    else
      G log --reverse --format='%H%x09%aI%x09%s'
    fi
    ;;

  show)
    SHA="${1:-}"
    [[ -z "${SHA}" ]] && { echo "show requires a <sha>" >&2; usage; }
    shift || true
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --diff) WITH_DIFF=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; usage ;;
      esac
    done
    if ! G cat-file -e "${SHA}^{commit}" 2>/dev/null; then
      echo "Commit not found: ${SHA}" >&2; exit 1
    fi
    echo "## COMMIT $(G rev-parse --short "${SHA}")"
    G log -1 --format='sha:     %H%nauthor:  %an <%ae>%ndate:    %aI%nsubject: %s%n%nbody:%n%b' "${SHA}"
    echo ""
    echo "## FILES (name-status)"
    G diff-tree --no-commit-id -r --name-status "${SHA}" || true
    echo ""
    echo "## STAT"
    G show --stat --format='' "${SHA}" || true
    if [[ "${WITH_DIFF}" == "1" ]]; then
      echo ""
      echo "## DIFF"
      G show --format='' "${SHA}" || true
    fi
    ;;

  -h|--help) usage ;;
  *) echo "Unknown command: ${ACTION}" >&2; usage ;;
esac
