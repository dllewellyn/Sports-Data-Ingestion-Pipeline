#!/usr/bin/env bash
# classify-commits.sh — PRE-FILTER (not a verdict) for missing-specification §2.
#
# Walks history oldest -> newest and tags each commit by its CHANGED-PATH FOOTPRINT
# only, to lift the obviously-non-substantive commits out of the agent's
# classification load. It deliberately does NOT decide "covered vs unspecified" —
# that needs the diff and stays the agent's judgement.
#
#   AUTO-NONSUBSTANTIVE  every changed path is docs/skills/CI/meta — safe to skip,
#                        no spec needed (records, does not get a spec)
#   DEP                  only dependency manifests/locks changed — likely a bump;
#                        the agent confirms there is no behavioural change
#   CANDIDATE            touches code/data/schema/config — the agent must make the
#                        covered/unspecified call from the diff
#   MERGE / EMPTY        merge commit or no file changes — agent decides
#
# Read-only (only `git log` / `git diff-tree`). Prints `<sha>\t<class>\t<subject>`
# oldest-first, and a per-class summary to stderr.
#
# Usage: classify-commits.sh [--since <ref>]
set -euo pipefail

since=""
if [[ "${1:-}" == "--since" ]]; then
  since="${2:?--since needs a ref}"
fi
range="HEAD"
[[ -n "$since" ]] && range="${since}..HEAD"

classify_footprint() {
  # paths on stdin (newline-separated) -> class on stdout
  local has_code=0 has_dep=0 has_meta=0 any=0 p
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    any=1
    case "$p" in
      uv.lock|poetry.lock|Pipfile.lock|Pipfile|package-lock.json|pnpm-lock.yaml|yarn.lock|\
      requirements*.txt|requirements*.in|pyproject.toml|setup.cfg|setup.py|package.json)
        has_dep=1 ;;
      .agents/*|.github/*|.gitignore|.gitattributes|.editorconfig|.pre-commit-config.yaml|\
      LICENSE|docs/*|*.md|.vscode/*|.idea/*)
        has_meta=1 ;;
      *)
        has_code=1 ;;
    esac
  done
  if (( any == 0 )); then echo "EMPTY"; return; fi
  if (( has_code == 1 )); then echo "CANDIDATE"; return; fi
  if (( has_dep == 1 )); then echo "DEP"; return; fi
  echo "AUTO-NONSUBSTANTIVE"
}

# plain counters (no associative arrays — portable to bash 3.2 / macOS)
c_auto=0 c_dep=0 c_cand=0 c_merge=0 c_empty=0
while IFS=$'\t' read -r sha subject; do
  parents="$(git rev-list --parents -n1 "$sha" | wc -w)"
  if (( parents > 2 )); then
    cls="MERGE"
  else
    files="$(git diff-tree --root --no-commit-id --name-only -r "$sha")"
    cls="$(printf '%s\n' "$files" | classify_footprint)"
  fi
  case "$cls" in
    AUTO-NONSUBSTANTIVE) c_auto=$((c_auto + 1)) ;;
    DEP)                 c_dep=$((c_dep + 1)) ;;
    CANDIDATE)           c_cand=$((c_cand + 1)) ;;
    MERGE)               c_merge=$((c_merge + 1)) ;;
    EMPTY)               c_empty=$((c_empty + 1)) ;;
  esac
  printf '%s\t%s\t%s\n' "$sha" "$cls" "$subject"
done < <(git log --reverse --format='%H%x09%s' "$range")

{
  echo "--- footprint pre-filter summary (agent still judges DEP / CANDIDATE) ---"
  printf '%-20s %s\n' AUTO-NONSUBSTANTIVE "$c_auto"
  printf '%-20s %s\n' DEP "$c_dep"
  printf '%-20s %s\n' CANDIDATE "$c_cand"
  printf '%-20s %s\n' MERGE "$c_merge"
  printf '%-20s %s\n' EMPTY "$c_empty"
} >&2
