#!/usr/bin/env bash
# Deterministic helpers for the ticket-formatter agent skill.
# The agent (Claude) authors ticket bodies and writes the agreed content into the
# local user_stories/ backlog plus derived output. This script does discovery +
# mechanical work only: it validates a spec, prints the canonical spec template, and
# diffs two files. It NEVER calls az, never mutates the spec, and never pushes anywhere.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}")"
STORIES_DIR="${GIT_ROOT}/user_stories"
OUT_DIR="${GIT_ROOT}/temp/ticket_formatter"

ACTION="${1:-}"
shift || true

usage() {
  cat >&2 <<EOF
Usage: $0 <validate|diff|template|status> [options]

Commands:
  validate <spec.json>      Check the spec parses and carries the required fields;
                            print a dry-run plan (create vs update per work item).
  diff <before> <after>     Unified diff of two files (markdown bodies). Exit 0 whether
                            or not they differ; non-diff errors still fail.
  template                  Print the canonical ticket-spec JSON template to stdout.
  status [--stories <dir>]  Report the user_stories dir and the output dir state.

Options:
  --stories <dir>   user_stories dir (default: <repo_root>/user_stories)
  --out <dir>       derived-output dir (default: <repo_root>/temp/ticket_formatter)
  --help | -h
EOF
  exit 1
}

# Shared option parsing for commands that accept --stories/--out after positionals.
STORIES_OVERRIDE=""
OUT_OVERRIDE=""
POSITIONAL=()
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --stories) STORIES_OVERRIDE="$2"; shift 2 ;;
      --out)     OUT_OVERRIDE="$2"; shift 2 ;;
      --help|-h) usage ;;
      *) POSITIONAL+=("$1"); shift ;;
    esac
  done
  [[ -n "${STORIES_OVERRIDE}" ]] && STORIES_DIR="${STORIES_OVERRIDE}"
  [[ -n "${OUT_OVERRIDE}" ]] && OUT_DIR="${OUT_OVERRIDE}"
  return 0
}

cmd_template() {
  cat <<'EOF'
{
  "epic": {
    "id": null,
    "work_item_type": "Epic",
    "title": "<epic title>",
    "state": null,
    "parent": null,
    "sections": {
      "overview": "## Overview\n\n<plain-language epic narrative>",
      "glossary": "## Glossary\n\n| Term | Definition |\n| --- | --- |\n| <term> | <definition from source material> |",
      "component_architecture": "## Component Architecture Overview\n\n<components, responsibilities, data flows>",
      "definition_of_ready": "## Definition of Ready\n\n- [ ] <DOR item>",
      "definition_of_done": "## Definition of Done\n\n- [ ] <DOD item>"
    }
  },
  "stories": [
    {
      "id": null,
      "work_item_type": "User Story",
      "title": "<story title>",
      "state": null,
      "sections": {
        "user_story": "As a <role>, I want <capability>, so that <benefit>.",
        "description": "## Description\n\n<full detail>",
        "acceptance_criteria": "## Acceptance Criteria\n\n- [ ] Given <context>, when <action>, then <outcome>",
        "dependencies": "## Dependencies\n\n- <other story / external dependency>",
        "notes": "## Notes\n\n<implementation notes, evidence references>"
      }
    }
  ]
}
EOF
}

cmd_validate() {
  parse_args "$@"
  local spec="${POSITIONAL[0]:-}"
  if [[ -z "${spec}" ]]; then
    echo "validate requires a spec path. See: $0 template" >&2
    exit 1
  fi
  if [[ ! -f "${spec}" ]]; then
    echo "Spec not found: ${spec}" >&2
    exit 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to validate the spec JSON." >&2
    exit 1
  fi
  python3 - "${spec}" <<'PY'
import json, sys

spec_path = sys.argv[1]
try:
    with open(spec_path) as fh:
        spec = json.load(fh)
except json.JSONDecodeError as e:
    print(f"Invalid JSON: {e}", file=sys.stderr)
    sys.exit(1)

errors = []
epic = spec.get("epic")
if not isinstance(epic, dict):
    errors.append("missing top-level 'epic' object")
    epic = {}

REQUIRED_EPIC_SECTIONS = [
    "overview", "glossary", "component_architecture",
    "definition_of_ready", "definition_of_done",
]
if not epic.get("title"):
    errors.append("epic.title is required")
if not epic.get("work_item_type"):
    errors.append("epic.work_item_type is required")
sections = epic.get("sections") or {}
for key in REQUIRED_EPIC_SECTIONS:
    if not sections.get(key):
        errors.append(f"epic.sections.{key} is required")

stories = spec.get("stories")
if stories is None:
    stories = []
if not isinstance(stories, list):
    errors.append("'stories' must be a list")
    stories = []

REQUIRED_STORY_SECTIONS = ["user_story", "acceptance_criteria"]
for i, s in enumerate(stories):
    if not isinstance(s, dict):
        errors.append(f"stories[{i}] must be an object")
        continue
    if not s.get("title"):
        errors.append(f"stories[{i}].title is required")
    if not s.get("work_item_type"):
        errors.append(f"stories[{i}].work_item_type is required")
    ss = s.get("sections") or {}
    for key in REQUIRED_STORY_SECTIONS:
        if not ss.get(key):
            errors.append(f"stories[{i}].sections.{key} is required")

if errors:
    print("Spec INVALID:", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)

def verb(item):
    return "UPDATE id=%s" % item.get("id") if item.get("id") else "CREATE (new)"

print("Spec OK.")
print(f"Plan:")
print(f"  Epic: {verb(epic)}  — \"{epic.get('title')}\"")
for s in stories:
    print(f"  Story: {verb(s)}  — \"{s.get('title')}\" (link → epic)")
print(f"  {len(stories)} story/stories total.")
PY
}

cmd_diff() {
  parse_args "$@"
  local before="${POSITIONAL[0]:-}"
  local after="${POSITIONAL[1]:-}"
  if [[ -z "${before}" || -z "${after}" ]]; then
    echo "diff requires two file paths: <before> <after>" >&2
    exit 1
  fi
  # /dev/null stands in for a missing side (e.g. a brand-new ticket has no before).
  [[ -f "${before}" ]] || before=/dev/null
  [[ -f "${after}" ]] || after=/dev/null
  # diff exits 1 when files differ — that is success for us; only >1 is a real error.
  diff -u "${before}" "${after}" || [[ $? -eq 1 ]]
}

cmd_status() {
  parse_args "$@"
  echo "user_stories dir: ${STORIES_DIR}"
  if [[ -d "${STORIES_DIR}" ]]; then
    local n
    n="$(find "${STORIES_DIR}" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
    echo "  state: ${n} story file(s)"
  else
    echo "  state: missing"
  fi
  echo "output dir: ${OUT_DIR}"
  if [[ -d "${OUT_DIR}" ]]; then
    echo "  bodies/diffs present:"
    find "${OUT_DIR}" -maxdepth 1 -type f 2>/dev/null | sort | sed 's/^/    /' || true
  else
    echo "  state: not yet created (regenerated on apply)"
  fi
}

case "${ACTION}" in
  validate) cmd_validate "$@" ;;
  diff)     cmd_diff "$@" ;;
  template) cmd_template ;;
  status)   cmd_status "$@" ;;
  --help|-h|"") usage ;;
  *) echo "Unknown command: ${ACTION}" >&2; usage ;;
esac
