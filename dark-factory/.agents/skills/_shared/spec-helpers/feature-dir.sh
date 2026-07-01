#!/usr/bin/env bash
# feature-dir.sh — resolve the active feature directory for the downstream chain.
#
# In the feature-directory model, every phase after `specification` (clarify, plan,
# tasks, analyze, implementor, converge) locates the feature the same way: it reads
# `.specify/feature.json` { "feature_directory": "specs/NNN-<slug>" }. This replaces
# git-branch / NNN-scan detection. Resolution order:
#   1. $SPECIFY_FEATURE_DIRECTORY (explicit override), if set and non-empty
#   2. .specify/feature.json -> feature_directory
#
# Usage:
#   feature-dir.sh                 # prints the resolved feature directory path
#   feature-dir.sh --require-file spec.md   # also assert <dir>/spec.md exists
#
# Exit codes: 0 ok (prints path to stdout); 1 unresolved / missing required file.
set -euo pipefail

require_file=""
if [[ "${1:-}" == "--require-file" ]]; then
  require_file="${2:?--require-file needs a filename}"
fi

dir="${SPECIFY_FEATURE_DIRECTORY:-}"
if [[ -z "$dir" ]]; then
  json=".specify/feature.json"
  if [[ ! -f "$json" ]]; then
    echo "error: no .specify/feature.json and \$SPECIFY_FEATURE_DIRECTORY unset — run specification first" >&2
    exit 1
  fi
  dir="$(grep -o '"feature_directory"[[:space:]]*:[[:space:]]*"[^"]*"' "$json" \
    | sed 's/.*:[[:space:]]*"\([^"]*\)".*/\1/' | head -n1)"
fi

if [[ -z "$dir" ]]; then
  echo "error: feature_directory could not be resolved" >&2
  exit 1
fi
if [[ ! -d "$dir" ]]; then
  echo "error: resolved feature directory does not exist: $dir" >&2
  exit 1
fi
if [[ -n "$require_file" && ! -f "$dir/$require_file" ]]; then
  echo "error: $dir/$require_file not found (prerequisite missing)" >&2
  exit 1
fi

printf '%s\n' "$dir"
