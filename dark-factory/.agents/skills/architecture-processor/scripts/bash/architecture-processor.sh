#!/usr/bin/env bash
# Discovery and status helper for the architecture-processor agent skill.
# Extraction is performed by the agent (Claude) — this script handles file-system queries only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}")"
TEMP_BASE="${GIT_ROOT}/temp"
COMMIT_FILTER=""
PATH_FILTER="architecture"   # default: only architecture files
ACTION="${1:-list}"
shift || true

# Output prefix — distinct from transcript-processor's "extracted_" so both skills coexist
OUT_PREFIX="arch_extracted_"

usage() {
  cat >&2 <<EOF
Usage: $0 <list|status> [options]

Commands:
  list     Print pending new_* files (tab-separated: sha  flat_path  source_path)
  status   Show done vs pending counts per commit

Options:
  --commit <short_sha>   Scope to a single commit dir
  --filter <substring>   Override the default "architecture" filter
  --temp <dir>           Temp base dir (default: <repo_root>/temp)
  --help | -h
EOF
  exit 1
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --commit)  COMMIT_FILTER="$2"; shift 2 ;;
      --filter)  PATH_FILTER="$2"; shift 2 ;;
      --temp)    TEMP_BASE="$2"; shift 2 ;;
      --help|-h) usage ;;
      *) echo "Unknown option: $1" >&2; usage ;;
    esac
  done
}

# For a new_* file, compute its arch_extracted_*.json sibling path
extracted_for() {
  local new_file="$1"
  local dir base stem
  dir="$(dirname "${new_file}")"
  base="$(basename "${new_file}")"
  stem="${base#new_}"
  echo "${dir}/${OUT_PREFIX}${stem}.json"
}

# Convert flat filename back to original path for display (architecture__foo.puml -> architecture/foo.puml)
original_path() {
  echo "${1#new_}" | sed 's|__|/|g'
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

find_new_files() {
  local commit_dir="$1"
  while IFS= read -r -d '' f; do
    local base
    base="$(basename "${f}")"
    if [[ -n "${PATH_FILTER}" && "${base}" != *"${PATH_FILTER}"* ]]; then
      continue
    fi
    echo "${f}"
  done < <(find "${commit_dir}" -maxdepth 1 -name "new_*" -not -name "*.json" -print0 2>/dev/null)
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
    local short_sha
    short_sha="$(basename "${commit_dir}")"

    # Only consider commits that have a manifest (produced by git-sync-extractor)
    [[ ! -f "${commit_dir}/changed_files.json" ]] && continue

    while IFS= read -r new_file; do
      [[ -z "${new_file}" ]] && continue
      local out
      out="$(extracted_for "${new_file}")"
      if [[ ! -f "${out}" ]]; then
        local flat_base orig
        flat_base="$(basename "${new_file}")"
        orig="$(original_path "${flat_base}")"
        printf '%s\t%s\t%s\n' "${short_sha}" "${flat_base}" "${orig}"
        found=$((found + 1))
      fi
    done < <(find_new_files "${commit_dir}")
  done < <(find_commit_dirs)

  if [[ "${found}" -eq 0 ]]; then
    echo "No pending files." >&2
  fi
}

cmd_status() {
  parse_args "$@"

  if [[ ! -d "${TEMP_BASE}" ]]; then
    echo "Temp directory not found: ${TEMP_BASE}" >&2
    exit 1
  fi

  local total_pending=0
  local total_done=0

  while IFS= read -r commit_dir; do
    [[ -z "${commit_dir}" ]] && continue
    local short_sha
    short_sha="$(basename "${commit_dir}")"
    [[ ! -f "${commit_dir}/changed_files.json" ]] && continue

    local commit_pending=0
    local commit_done=0

    while IFS= read -r new_file; do
      [[ -z "${new_file}" ]] && continue
      local out flat_base orig
      out="$(extracted_for "${new_file}")"
      flat_base="$(basename "${new_file}")"
      orig="$(original_path "${flat_base}")"
      if [[ -f "${out}" ]]; then
        commit_done=$((commit_done + 1))
        printf '  ✓ %s\n' "${orig}"
      else
        commit_pending=$((commit_pending + 1))
        printf '  ○ %s\n' "${orig}"
      fi
    done < <(find_new_files "${commit_dir}")

    if [[ $((commit_pending + commit_done)) -gt 0 ]]; then
      echo "${short_sha}  (${commit_done} done, ${commit_pending} pending)"
    fi

    total_pending=$((total_pending + commit_pending))
    total_done=$((total_done + commit_done))
  done < <(find_commit_dirs)

  echo ""
  echo "Total: ${total_done} done, ${total_pending} pending"
}

case "${ACTION}" in
  list)    cmd_list "$@" ;;
  status)  cmd_status "$@" ;;
  --help|-h) usage ;;
  *)
    echo "Unknown command: ${ACTION}" >&2
    usage
    ;;
esac
