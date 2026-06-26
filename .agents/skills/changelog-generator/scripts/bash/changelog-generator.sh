#!/usr/bin/env bash
# Discovery and status helper for the changelog-generator agent skill.
# Authoring of CHANGELOG.md is performed by the agent (Claude) — this script
# handles file-system queries only: which commits in temp/ are not yet logged.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}")"
TEMP_BASE="${GIT_ROOT}/temp"
CHANGELOG="${GIT_ROOT}/CHANGELOG.md"
COMMIT_FILTER=""
ACTION="${1:-list}"
shift || true

usage() {
  cat >&2 <<EOF
Usage: $0 <list|status> [options]

Commands:
  list     Print commits present in temp/ that are NOT yet in CHANGELOG.md
           (tab-separated: short_sha  manifest_path)
  status   Show logged vs pending commits

Detection: a commit is "logged" when CHANGELOG.md contains the marker
  <!-- okf:commit=<short_sha> -->
which the agent writes once per commit entry.

Options:
  --commit <short_sha>   Scope to a single commit dir
  --changelog <path>     CHANGELOG file (default: <repo_root>/CHANGELOG.md)
  --temp <dir>           Temp base dir (default: <repo_root>/temp)
  --help | -h
EOF
  exit 1
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --commit)    COMMIT_FILTER="$2"; shift 2 ;;
      --changelog) CHANGELOG="$2"; shift 2 ;;
      --temp)      TEMP_BASE="$2"; shift 2 ;;
      --help|-h)   usage ;;
      *) echo "Unknown option: $1" >&2; usage ;;
    esac
  done
}

# Is this short_sha already present in the changelog?
is_logged() {
  local short_sha="$1"
  [[ -f "${CHANGELOG}" ]] || return 1
  grep -q "okf:commit=${short_sha}" "${CHANGELOG}"
}

find_commit_dirs() {
  if [[ -n "${COMMIT_FILTER}" ]]; then
    local target="${TEMP_BASE}/${COMMIT_FILTER}"
    if [[ ! -d "${target}" ]]; then
      echo "Commit dir not found: ${target}" >&2
      exit 1
    fi
    echo "${target}"
  else
    find "${TEMP_BASE}" -maxdepth 1 -mindepth 1 -type d | sort
  fi
}

cmd_list() {
  parse_args "$@"

  if [[ ! -d "${TEMP_BASE}" ]]; then
    echo "Temp directory not found: ${TEMP_BASE}" >&2
    exit 1
  fi

  local found=0
  while IFS= read -r commit_dir; do
    [[ -z "${commit_dir}" ]] && continue
    local short_sha manifest
    short_sha="$(basename "${commit_dir}")"
    manifest="${commit_dir}/changed_files.json"

    # Only consider commits that have a manifest (produced by git-sync-extractor)
    [[ ! -f "${manifest}" ]] && continue

    if ! is_logged "${short_sha}"; then
      printf '%s\t%s\n' "${short_sha}" "${manifest}"
      found=$((found + 1))
    fi
  done < <(find_commit_dirs)

  if [[ "${found}" -eq 0 ]]; then
    echo "No pending commits — CHANGELOG.md is up to date." >&2
  fi
}

cmd_status() {
  parse_args "$@"

  if [[ ! -d "${TEMP_BASE}" ]]; then
    echo "Temp directory not found: ${TEMP_BASE}" >&2
    exit 1
  fi

  local total_pending=0
  local total_logged=0

  while IFS= read -r commit_dir; do
    [[ -z "${commit_dir}" ]] && continue
    local short_sha manifest
    short_sha="$(basename "${commit_dir}")"
    manifest="${commit_dir}/changed_files.json"
    [[ ! -f "${manifest}" ]] && continue

    if is_logged "${short_sha}"; then
      total_logged=$((total_logged + 1))
      printf '  ✓ %s\n' "${short_sha}"
    else
      total_pending=$((total_pending + 1))
      printf '  ○ %s\n' "${short_sha}"
    fi
  done < <(find_commit_dirs)

  echo ""
  echo "Changelog: ${CHANGELOG}"
  echo "Total: ${total_logged} logged, ${total_pending} pending"
}

case "${ACTION}" in
  list)      cmd_list "$@" ;;
  status)    cmd_status "$@" ;;
  --help|-h) usage ;;
  *)
    echo "Unknown command: ${ACTION}" >&2
    usage
    ;;
esac
