#!/usr/bin/env bash
# Discovery and status helper for the story-synchronizer agent skill.
# Synthesis is performed by the agent (Claude) — this script handles file-system queries only.
# It never reads, edits, or deletes findings, user stories, or the changeset; it only reports state.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}")"
TEMP_BASE="${GIT_ROOT}/temp"
STORIES_DIR="${GIT_ROOT}/user_stories"
CHANGESET="${TEMP_BASE}/story_changeset.json"
ACTION="${1:-status}"
shift || true

usage() {
  cat >&2 <<EOF
Usage: $0 <status|findings|stories> [options]

Commands:
  status     Summary: counts of findings, user stories, and whether a changeset exists
  findings   List every extracted finding (tab-separated: sha  type  finding_file)
             type is "transcript" (extracted_*.json) or "architecture" (arch_extracted_*.json)
  stories    Report the user_stories dir state: "missing", "empty", or one line per story
             (tab-separated: id  filename)

Options:
  --temp <dir>      Temp base dir holding the processors' output (default: <repo_root>/temp)
  --stories <dir>   User stories dir (default: <repo_root>/user_stories)
  --help | -h
EOF
  exit 1
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --temp)    TEMP_BASE="$2"; CHANGESET="${TEMP_BASE}/story_changeset.json"; shift 2 ;;
      --stories) STORIES_DIR="$2"; shift 2 ;;
      --help|-h) usage ;;
      *) echo "Unknown option: $1" >&2; usage ;;
    esac
  done
}

# Print all finding files across temp/<sha>/ as: sha \t type \t finding_file
emit_findings() {
  [[ ! -d "${TEMP_BASE}" ]] && return 0
  while IFS= read -r commit_dir; do
    [[ -z "${commit_dir}" ]] && continue
    local short_sha
    short_sha="$(basename "${commit_dir}")"
    while IFS= read -r -d '' f; do
      printf '%s\t%s\t%s\n' "${short_sha}" "transcript" "${f}"
    done < <(find "${commit_dir}" -maxdepth 1 -name "extracted_*.json" -print0 2>/dev/null)
    while IFS= read -r -d '' f; do
      printf '%s\t%s\t%s\n' "${short_sha}" "architecture" "${f}"
    done < <(find "${commit_dir}" -maxdepth 1 -name "arch_extracted_*.json" -print0 2>/dev/null)
  done < <(find "${TEMP_BASE}" -maxdepth 1 -mindepth 1 -type d | sort)
}

cmd_findings() {
  parse_args "$@"
  local out
  out="$(emit_findings)"
  if [[ -z "${out}" ]]; then
    echo "No findings. Run transcript-processor / architecture-processor first." >&2
    return 0
  fi
  printf '%s\n' "${out}"
}

cmd_stories() {
  parse_args "$@"
  if [[ ! -d "${STORIES_DIR}" ]]; then
    echo "missing"
    return 0
  fi
  local found=0
  while IFS= read -r f; do
    [[ -z "${f}" ]] && continue
    local id
    id="$(basename "${f}" .json)"
    printf '%s\t%s\n' "${id}" "$(basename "${f}")"
    found=$((found + 1))
  done < <(find "${STORIES_DIR}" -maxdepth 1 -name '*.json' | sort)
  if [[ "${found}" -eq 0 ]]; then
    echo "empty"
  fi
}

cmd_status() {
  parse_args "$@"

  local transcript_n=0 arch_n=0
  if [[ -d "${TEMP_BASE}" ]]; then
    transcript_n="$(find "${TEMP_BASE}" -maxdepth 2 -name 'extracted_*.json' 2>/dev/null | wc -l | tr -d ' ')"
    arch_n="$(find "${TEMP_BASE}" -maxdepth 2 -name 'arch_extracted_*.json' 2>/dev/null | wc -l | tr -d ' ')"
  fi

  local stories_state stories_n=0
  if [[ ! -d "${STORIES_DIR}" ]]; then
    stories_state="missing (greenfield: propose new stories)"
  else
    stories_n="$(find "${STORIES_DIR}" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "${stories_n}" -eq 0 ]]; then
      stories_state="empty (greenfield: propose new stories)"
    else
      stories_state="${stories_n} story file(s) (update mode)"
    fi
  fi

  echo "Findings"
  echo "  transcript (extracted_*.json):    ${transcript_n}"
  echo "  architecture (arch_extracted_*):  ${arch_n}"
  echo ""
  echo "User stories"
  echo "  dir:    ${STORIES_DIR}"
  echo "  state:  ${stories_state}"
  echo ""
  if [[ -f "${CHANGESET}" ]]; then
    echo "Changeset: EXISTS at ${CHANGESET} (will be overwritten unless you intend otherwise)"
  else
    echo "Changeset: not yet generated (target: ${CHANGESET})"
  fi
}

case "${ACTION}" in
  status)    cmd_status "$@" ;;
  findings)  cmd_findings "$@" ;;
  stories)   cmd_stories "$@" ;;
  --help|-h) usage ;;
  *)
    echo "Unknown command: ${ACTION}" >&2
    usage
    ;;
esac
