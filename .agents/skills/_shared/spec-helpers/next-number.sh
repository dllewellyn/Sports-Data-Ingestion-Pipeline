#!/usr/bin/env bash
# next-number.sh — print the next zero-padded NNN for a numbered-doc directory.
#
# Deterministic replacement for "list the dir, eyeball the highest NNN, add one"
# used by specification, missing-specification and feature. In the feature-directory
# model a feature is the directory `specs/NNN-<slug>/`, so this scans for NNN-prefixed
# directories (and, for robustness, files). Collision-free: with --count it
# pre-allocates a block of consecutive numbers, which is what missing-specification
# needs when several spec-writer sub-agents run in parallel.
#
# Usage:
#   next-number.sh <dir>              # next number, e.g. 004
#   next-number.sh <dir> --count 3   # next 3 numbers, one per line (parallel alloc)
#
# Scans entries (dirs or files) whose basename starts with digits ("NNN-..."). A
# missing/empty dir yields 001. Never reuses a number even if entries were deleted
# is the CALLER's rule — this only ever returns highest+1.
set -euo pipefail

dir="${1:-}"
if [[ -z "$dir" ]]; then
  echo "usage: next-number.sh <dir> [--count N]" >&2
  exit 2
fi

count=1
if [[ "${2:-}" == "--count" ]]; then
  count="${3:?--count needs a value}"
  [[ "$count" =~ ^[0-9]+$ ]] || { echo "error: --count must be a positive integer" >&2; exit 2; }
fi

max=0
if [[ -d "$dir" ]]; then
  while IFS= read -r f; do
    base="$(basename "$f")"
    if [[ "$base" =~ ^([0-9]+)- ]]; then
      n=$((10#${BASH_REMATCH[1]}))
      (( n > max )) && max=$n
    fi
  done < <(find "$dir" -maxdepth 1 -mindepth 1 \( -type d -o -type f \) 2>/dev/null)
fi

for ((i = 1; i <= count; i++)); do
  printf '%03d\n' $((max + i))
done
