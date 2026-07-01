#!/usr/bin/env python3
"""validate-tasks.py — deterministic structural linter for a tasks.md file.

Checks a written `<feature_dir>/tasks.md` against the contract in
`tasks/references/tasks-template.md`: location, metadata lines, the presence of
phase + dependency sections, well-formed and unique task ids, and that plan-step
references (`[Sn]`) exist so spec→plan→tasks traceability can close (proven
separately by trace-check.py).

Exit codes: 0 = pass, 1 = errors, 2 = bad usage.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _specdoc as doc  # noqa: E402

TASK_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*(T\d+)\b(.*)$")
CHECKBOX_RE = re.compile(r"^\s*-\s*\[[ xX]\]")


def main(argv):
    if len(argv) != 2:
        print("usage: validate-tasks.py <path-to-tasks.md>", file=sys.stderr)
        return 2
    path = argv[1]
    if not os.path.isfile(path):
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    body = doc.read(path)
    errors, warnings = [], []

    _check_location(path, warnings)
    _check_metadata(body, errors)
    _check_phases(body, errors)
    _check_tasks(body, errors, warnings)
    if "<!--" in body:
        warnings.append("template guidance comments (`<!-- ... -->`) remain — remove them")

    return _report(path, errors, warnings)


def _check_location(path, warnings):
    if os.path.basename(path) != "tasks.md":
        warnings.append(f"filename '{os.path.basename(path)}' is not 'tasks.md'")
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if not re.match(r"^\d{3,}-.+", parent):
        warnings.append(f"parent directory '{parent}' is not 'NNN-<slug>'")


def _check_metadata(body, errors):
    head = "\n".join(body.splitlines()[:10]).lower()
    for label in ("feature directory", "plan"):
        if f"**{label}**" not in head:
            errors.append(f"missing metadata line: **{label.title()}**")


def _check_phases(body, errors):
    h2 = [t.lower() for t, _ in doc.headings(body, 2)]
    if not any(t.startswith("phase") for t in h2):
        errors.append("no `## Phase ...` sections found")
    if not any("dependenc" in t for t in h2):
        errors.append("missing `## Dependencies & Execution Order` section")


def _check_tasks(body, errors, warnings):
    ids = []
    has_step_ref = False
    for n, line in enumerate(body.splitlines(), start=1):
        m = TASK_RE.match(line)
        if m:
            ids.append(m.group(1))
            if re.search(r"\[S\d+\]", line) or "[setup]" in line.lower():
                has_step_ref = has_step_ref or bool(re.search(r"\[S\d+\]", line))
        elif CHECKBOX_RE.match(line) and re.search(r"\bT\d", line) is None:
            # a checkbox that looks like a task but has no T-id
            if any(h.lower().startswith("phase") for h, ln in doc.headings(body, 2) if ln < n):
                warnings.append(f"line {n}: checkbox without a `T###` id — '{line.strip()[:60]}'")

    if not ids:
        errors.append("no `- [ ] T### ...` task lines found")
        return
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate task ids: {', '.join(dupes)}")
    if not has_step_ref:
        errors.append("no task carries a plan-step reference `[Sn]` — "
                      "spec→plan→tasks traceability cannot close")


def _report(path, errors, warnings):
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"\nFAIL: {path} — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: {path} conforms to the tasks template ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    rc = main(sys.argv)
    import _gate_telemetry  # noqa: E402

    _gate_telemetry.emit_gate(sys.argv[1] if len(sys.argv) > 1 else "", rc, "tasks")
    sys.exit(rc)
