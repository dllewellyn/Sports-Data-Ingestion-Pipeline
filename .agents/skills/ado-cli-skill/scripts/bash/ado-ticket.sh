#!/usr/bin/env bash
set -euo pipefail

# Configuration file location (relative to script directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/.ado-cli-config"

ACTION="${1:-}"
if [[ -z "${ACTION}" ]]; then
  echo "Usage: $0 <init|get|list|create|update> [options]" >&2
  exit 1
fi
shift || true

ORG=""
PROJECT=""
OUTPUT="json"
REMAINING_ARGS=()
SCOPE_ARGS=()

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

ensure_azdo_extension() {
  if ! az extension show --name azure-devops >/dev/null 2>&1; then
    echo "Installing Azure DevOps extension..." >&2
    az extension add --name azure-devops >/dev/null
  fi
}

load_config() {
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Configuration not found at ${CONFIG_FILE}" >&2
    echo "Please run: $0 init" >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${CONFIG_FILE}"
}

init_config() {
  echo "=== Azure DevOps CLI Initialization ===" >&2
  read -p "Enter your Azure DevOps organization URL (e.g., https://dev.azure.com/myorg): " ORG </dev/tty
  read -p "Enter your project name: " PROJECT </dev/tty

  # Validate that org and project are not empty
  if [[ -z "${ORG}" ]] || [[ -z "${PROJECT}" ]]; then
    echo "Error: Organization and project are required" >&2
    exit 1
  fi

  # Save configuration
  cat > "${CONFIG_FILE}" << EOF
# Azure DevOps CLI Configuration
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
ORG="${ORG}"
PROJECT="${PROJECT}"
EOF
  chmod 600 "${CONFIG_FILE}"
  echo "✓ Configuration saved to ${CONFIG_FILE}" >&2
}

preflight_check() {
  require_cmd az

  if ! az account show >/dev/null 2>&1; then
    echo "Error: Not logged in to Azure CLI. Run: az login" >&2
    exit 1
  fi

  echo "✓ Azure CLI found and authenticated" >&2
}

init_action() {
  preflight_check
  init_config
}

validate_config() {
  if [[ -z "${ORG}" ]] || [[ -z "${PROJECT}" ]]; then
    echo "Error: Organization and project must be configured" >&2
    echo "Run: $0 init" >&2
    exit 1
  fi
}

parse_common_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --org)
        ORG="$2"
        shift 2
        ;;
      --project)
        PROJECT="$2"
        shift 2
        ;;
      --output)
        OUTPUT="$2"
        shift 2
        ;;
      *)
        break
        ;;
    esac
  done

  REMAINING_ARGS=("$@")
}

build_scope_args() {
  SCOPE_ARGS=()
  if [[ -n "${ORG}" ]]; then
    SCOPE_ARGS+=(--organization "${ORG}")
  fi
  if [[ -n "${PROJECT}" ]]; then
    SCOPE_ARGS+=(--project "${PROJECT}")
  fi
}

get_ticket() {
  local id=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id)
        id="$2"
        shift 2
        ;;
      *)
        echo "Unknown argument for get: $1" >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${id}" ]]; then
    echo "Missing required argument: --id" >&2
    exit 1
  fi

  az boards work-item show --id "${id}" "${SCOPE_ARGS[@]:-}" --output "${OUTPUT}"
}

list_tickets() {
  local wiql="Select [System.Id], [System.Title], [System.State] From WorkItems Where [System.TeamProject] = @project Order By [System.ChangedDate] Desc"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --wiql)
        wiql="$2"
        shift 2
        ;;
      *)
        echo "Unknown argument for list: $1" >&2
        exit 1
        ;;
    esac
  done

  az boards query --wiql "${wiql}" "${SCOPE_ARGS[@]:-}" --output "${OUTPUT}"
}

create_ticket() {
  local type=""
  local title=""
  local description=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --type)
        type="$2"
        shift 2
        ;;
      --title)
        title="$2"
        shift 2
        ;;
      --description)
        description="$2"
        shift 2
        ;;
      *)
        echo "Unknown argument for create: $1" >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${type}" || -z "${title}" ]]; then
    echo "Missing required arguments: --type and --title" >&2
    exit 1
  fi

  local args=(boards work-item create --type "${type}" --title "${title}")
  if [[ -n "${description}" ]]; then
    args+=(--description "${description}")
  fi
  args+=("${SCOPE_ARGS[@]}" --output "${OUTPUT}")

  az "${args[@]}"
}

update_ticket() {
  local id=""
  local -a fields=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id)
        id="$2"
        shift 2
        ;;
      --field)
        fields+=("$2")
        shift 2
        ;;
      *)
        echo "Unknown argument for update: $1" >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${id}" ]]; then
    echo "Missing required argument: --id" >&2
    exit 1
  fi

  if [[ ${#fields[@]} -eq 0 ]]; then
    echo "At least one --field key=value is required" >&2
    exit 1
  fi

  local args=(boards work-item update --id "${id}")
  for field in "${fields[@]}"; do
    args+=(--fields "${field}")
  done
  args+=("${SCOPE_ARGS[@]}" --output "${OUTPUT}")

  az "${args[@]}"
}

require_cmd az
ensure_azdo_extension

# Handle init action separately (doesn't need config)
if [[ "${ACTION}" == "init" ]]; then
  init_action
  exit 0
fi

# For all other actions, load and validate config
load_config
parse_common_args "$@"

# Allow org/project override via CLI args, otherwise use config
if [[ -z "${ORG}" ]]; then
  ORG="${ORG:-}"
fi
if [[ -z "${PROJECT}" ]]; then
  PROJECT="${PROJECT:-}"
fi

validate_config
build_scope_args

case "${ACTION}" in
  get)
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
      get_ticket "${REMAINING_ARGS[@]}"
    else
      get_ticket
    fi
    ;;
  list)
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
      list_tickets "${REMAINING_ARGS[@]}"
    else
      list_tickets
    fi
    ;;
  create)
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
      create_ticket "${REMAINING_ARGS[@]}"
    else
      create_ticket
    fi
    ;;
  update)
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
      update_ticket "${REMAINING_ARGS[@]}"
    else
      update_ticket
    fi
    ;;
  *)
    echo "Unsupported action: ${ACTION}" >&2
    echo "Supported actions: init, get, list, create, update" >&2
    exit 1
    ;;
esac
