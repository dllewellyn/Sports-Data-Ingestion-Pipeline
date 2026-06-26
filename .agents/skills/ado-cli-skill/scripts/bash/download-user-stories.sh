#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/.ado-cli-config"
OUTPUT_DIR="${PWD}/user_stories"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

load_config() {
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Configuration not found at ${CONFIG_FILE}" >&2
    echo "Please run: ado-ticket.sh init" >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${CONFIG_FILE}"
}

require_cmd az
require_cmd jq
load_config

mkdir -p "${OUTPUT_DIR}"

echo "Fetching work item IDs from ${PROJECT}..." >&2

WIQL="Select [System.Id] From WorkItems Order By [System.ChangedDate] Desc"

# Use a temp file to store IDs (mapfile not available on macOS bash 3.x)
IDS_TEMP=$(mktemp)
trap "rm -f ${IDS_TEMP}" EXIT

az boards query \
  --wiql "${WIQL}" \
  --organization "${ORG}" \
  --project "${PROJECT}" \
  --output json \
| jq -r '.[].id' > "${IDS_TEMP}"

if [[ ! -s "${IDS_TEMP}" ]]; then
  echo "No user stories found." >&2
  exit 0
fi

# Count the IDs
COUNT_TOTAL=$(wc -l < "${IDS_TEMP}")
echo "Found ${COUNT_TOTAL} user stories." >&2

# Prompt if more than 10
if [[ ${COUNT_TOTAL} -gt 10 ]]; then
  read -p "Download ${COUNT_TOTAL} tickets? (y/n) " -n 1 -r </dev/tty
  echo  # new line
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled." >&2
    exit 0
  fi
fi

echo "Downloading..." >&2

COUNT=0
while IFS= read -r id; do
  if [[ -n "${id}" ]]; then
    az boards work-item show \
      --id "${id}" \
      --organization "${ORG}" \
      --output json > "${OUTPUT_DIR}/${id}.json"
    echo "  ✓ ${id} → user_stories/${id}.json" >&2
    ((COUNT++))
  fi
done < "${IDS_TEMP}"

echo "" >&2
echo "✓ Downloaded ${COUNT} user stories to ${OUTPUT_DIR}" >&2
