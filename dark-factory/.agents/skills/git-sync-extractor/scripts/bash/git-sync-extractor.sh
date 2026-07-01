#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}")"
LAST_SYNC_FILE="${GIT_ROOT}/.last-sync"
TEMP_BASE="${GIT_ROOT}/temp"
PATTERNS=()
ACTION="${1:-run}"
shift || true

usage() {
  cat >&2 <<EOF
Usage: $0 [run|reset|status] [options]

Commands:
  run     Extract diffs for commits since last sync (default)
  reset   Clear .last-sync so next run reprocesses all commits
  status  Show current sync state without processing

Options:
  --pattern <prefix>   Path prefix to match (repeatable)
                       Default: architecture transcripts
  --temp <dir>         Output directory (default: <repo_root>/temp)
  --last-sync <file>   .last-sync file path (default: <repo_root>/.last-sync)
  --from <commit>      Override starting commit (skips .last-sync prompt)
EOF
  exit 1
}

FROM_COMMIT_OVERRIDE=""

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pattern)
        PATTERNS+=("$2")
        shift 2
        ;;
      --temp)
        TEMP_BASE="$2"
        shift 2
        ;;
      --last-sync)
        LAST_SYNC_FILE="$2"
        shift 2
        ;;
      --from)
        FROM_COMMIT_OVERRIDE="$2"
        shift 2
        ;;
      --help|-h)
        usage
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage
        ;;
    esac
  done

  if [[ ${#PATTERNS[@]} -eq 0 ]]; then
    PATTERNS=("architecture" "transcripts")
  fi
}

matches_pattern() {
  local file="$1"
  for pattern in "${PATTERNS[@]}"; do
    # Strip trailing slash from pattern for consistent matching
    pattern="${pattern%/}"
    if [[ "${file}" == "${pattern}"/* || "${file}" == "${pattern}" ]]; then
      return 0
    fi
  done
  return 1
}

# Converts a file path to a safe flat filename segment
# architecture/foo/bar.puml -> architecture__foo__bar.puml
path_to_flat() {
  echo "${1//\//__}"
}

read_last_sync() {
  if [[ -f "${LAST_SYNC_FILE}" ]]; then
    tr -d '[:space:]' < "${LAST_SYNC_FILE}"
  else
    echo ""
  fi
}

write_last_sync() {
  echo "$1" > "${LAST_SYNC_FILE}"
}

resolve_start_commit() {
  local last_sync="$1"

  if [[ -n "${FROM_COMMIT_OVERRIDE}" ]]; then
    echo "${FROM_COMMIT_OVERRIDE}"
    return
  fi

  if [[ -n "${last_sync}" ]]; then
    # Validate the commit still exists
    if git -C "${GIT_ROOT}" cat-file -t "${last_sync}" >/dev/null 2>&1; then
      echo "${last_sync}"
      return
    else
      echo "Warning: .last-sync commit '${last_sync}' not found in repo, ignoring." >&2
    fi
  fi

  # No usable last-sync — ask user
  echo "" >&2
  echo "No previous sync point found." >&2
  echo "Options:" >&2
  echo "  1) Start from the very beginning (first commit)" >&2
  echo "  2) Start from a specific commit or ref" >&2
  read -rp "Choice [1/2]: " choice </dev/tty

  if [[ "${choice}" == "2" ]]; then
    read -rp "Enter commit hash or ref: " ref </dev/tty
    if [[ -z "${ref}" ]]; then
      echo "No commit provided, aborting." >&2
      exit 1
    fi
    if ! git -C "${GIT_ROOT}" cat-file -t "${ref}" >/dev/null 2>&1; then
      echo "Commit/ref '${ref}' not found in repository." >&2
      exit 1
    fi
    echo "${ref}"
  else
    echo ""
  fi
}

get_commits_since() {
  local start="$1"
  if [[ -z "${start}" ]]; then
    git -C "${GIT_ROOT}" log --format="%H" --reverse
  else
    git -C "${GIT_ROOT}" log --format="%H" --reverse "${start}..HEAD"
  fi
}

get_commit_meta() {
  local commit="$1"
  git -C "${GIT_ROOT}" log -1 --format="%H%n%h%n%an%n%ae%n%aI%n%s" "${commit}"
}

get_changed_files() {
  local commit="$1"
  # Returns lines of: STATUS<tab>PATH
  # Status: A=added, M=modified, D=deleted, R=renamed, C=copied
  git -C "${GIT_ROOT}" diff-tree --no-commit-id -r --name-status "${commit}"
}

get_file_diff() {
  local commit="$1"
  local filepath="$2"
  git -C "${GIT_ROOT}" diff "${commit}^" "${commit}" -- "${filepath}" 2>/dev/null || \
    git -C "${GIT_ROOT}" show "${commit}:${filepath}" | \
      diff /dev/null - 2>/dev/null | sed "s|^--- /dev/null|--- /dev/null|" || true
}

get_file_content() {
  local commit="$1"
  local filepath="$2"
  git -C "${GIT_ROOT}" show "${commit}:${filepath}"
}

process_commit() {
  local commit="$1"

  # Read commit metadata
  local meta_raw
  meta_raw="$(get_commit_meta "${commit}")"
  local full_sha short_sha author_name author_email timestamp subject
  full_sha="$(  echo "${meta_raw}" | sed -n '1p')"
  short_sha="$( echo "${meta_raw}" | sed -n '2p')"
  author_name="$(echo "${meta_raw}" | sed -n '3p')"
  author_email="$(echo "${meta_raw}" | sed -n '4p')"
  timestamp="$(  echo "${meta_raw}" | sed -n '5p')"
  subject="$(    echo "${meta_raw}" | sed -n '6p')"

  local commit_dir="${TEMP_BASE}/${short_sha}"

  # Collect matching files
  local matched_lines=()
  while IFS=$'\t' read -r status filepath; do
    [[ -z "${filepath}" ]] && continue
    if matches_pattern "${filepath}"; then
      matched_lines+=("${status}	${filepath}")
    fi
  done < <(get_changed_files "${commit}")

  if [[ ${#matched_lines[@]} -eq 0 ]]; then
    return 0
  fi

  mkdir -p "${commit_dir}"

  local json_files="[]"
  local json_array=()

  for entry in "${matched_lines[@]}"; do
    local status="${entry%%$'\t'*}"
    local filepath="${entry#*$'\t'}"
    local flat_path
    flat_path="$(path_to_flat "${filepath}")"

    case "${status}" in
      A)
        # New file — write full content
        local out_file="${commit_dir}/new_${flat_path}"
        if get_file_content "${commit}" "${filepath}" > "${out_file}" 2>/dev/null; then
          json_array+=("{\"path\":\"${filepath}\",\"status\":\"added\",\"output\":\"new_${flat_path}\"}")
        else
          echo "  Warning: could not read new file content for ${filepath}" >&2
          rm -f "${out_file}"
        fi
        ;;
      M|C|R*)
        # Modified/renamed/copied — write diff
        local out_file="${commit_dir}/changed_${flat_path}.diff"
        if get_file_diff "${commit}" "${filepath}" > "${out_file}" 2>/dev/null; then
          # If diff is empty (e.g. no parent), fall back to full content
          if [[ ! -s "${out_file}" ]]; then
            get_file_content "${commit}" "${filepath}" > "${out_file}" 2>/dev/null || true
          fi
          json_array+=("{\"path\":\"${filepath}\",\"status\":\"modified\",\"output\":\"changed_${flat_path}.diff\"}")
        else
          echo "  Warning: could not produce diff for ${filepath}" >&2
          rm -f "${out_file}"
        fi
        ;;
      D)
        # Deleted — record in JSON but no output file
        json_array+=("{\"path\":\"${filepath}\",\"status\":\"deleted\",\"output\":null}")
        ;;
    esac
  done

  # Build JSON array string
  local joined=""
  for item in "${json_array[@]}"; do
    if [[ -z "${joined}" ]]; then
      joined="${item}"
    else
      joined="${joined},${item}"
    fi
  done

  cat > "${commit_dir}/changed_files.json" <<JSON
{
  "commit": "${full_sha}",
  "short_commit": "${short_sha}",
  "author": "${author_name}",
  "author_email": "${author_email}",
  "timestamp": "${timestamp}",
  "message": $(printf '%s' "${subject}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo "\"${subject}\""),
  "patterns": $(printf '%s\n' "${PATTERNS[@]}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().splitlines()))' 2>/dev/null || echo "[]"),
  "files": [${joined}]
}
JSON

  echo "  → ${#matched_lines[@]} file(s) in ${commit_dir}"
}

cmd_run() {
  parse_args "$@"

  local last_sync
  last_sync="$(read_last_sync)"

  local start_commit
  start_commit="$(resolve_start_commit "${last_sync}")"

  echo "Scanning commits..." >&2
  local commit_count=0
  local processed_count=0
  local latest_commit=""

  while IFS= read -r commit; do
    [[ -z "${commit}" ]] && continue
    commit_count=$((commit_count + 1))
    latest_commit="${commit}"
    echo "Processing ${commit:0:8}: $(git -C "${GIT_ROOT}" log -1 --format="%s" "${commit}")" >&2
    process_commit "${commit}"
    processed_count=$((processed_count + 1))
  done < <(get_commits_since "${start_commit}")

  if [[ -z "${latest_commit}" ]]; then
    echo "No new commits to process since last sync." >&2
    exit 0
  fi

  write_last_sync "${latest_commit}"
  echo "" >&2
  echo "Done. Processed ${processed_count} commit(s)." >&2
  echo "Updated .last-sync to ${latest_commit:0:8}" >&2
  echo "Output in: ${TEMP_BASE}" >&2
}

cmd_reset() {
  if [[ -f "${LAST_SYNC_FILE}" ]]; then
    rm "${LAST_SYNC_FILE}"
    echo "Cleared .last-sync" >&2
  else
    echo ".last-sync does not exist, nothing to clear." >&2
  fi
}

cmd_status() {
  local last_sync
  last_sync="$(read_last_sync)"
  if [[ -z "${last_sync}" ]]; then
    echo "No sync point recorded (.last-sync is absent or empty)." >&2
  else
    local commit_msg
    commit_msg="$(git -C "${GIT_ROOT}" log -1 --format="%s (%aI)" "${last_sync}" 2>/dev/null || echo "unknown")"
    echo "Last sync: ${last_sync:0:8} — ${commit_msg}" >&2
    local pending
    pending="$(git -C "${GIT_ROOT}" log --oneline "${last_sync}..HEAD" | wc -l | tr -d ' ')"
    echo "Commits pending: ${pending}" >&2
  fi
}

case "${ACTION}" in
  run)
    cmd_run "$@"
    ;;
  reset)
    cmd_reset
    ;;
  status)
    cmd_status
    ;;
  --help|-h)
    usage
    ;;
  *)
    echo "Unknown command: ${ACTION}" >&2
    usage
    ;;
esac
