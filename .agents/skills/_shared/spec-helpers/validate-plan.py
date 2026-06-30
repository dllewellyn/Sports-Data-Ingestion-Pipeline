#!/usr/bin/env python3
"""validate-plan.py — deterministic structural linter for a Plan file.

Checks a written `<feature_dir>/plan.md` against the contract in
`plan/references/plan-template.md`: location, metadata lines, section presence +
order, the **convention-audit hard gate** (no audit row may be marked a "gap"),
that every `### Step Sn` carries the seven mandated fields, and that the
Traceability section is filled.

The convention-gate check is the one `implementor` and `feature` rely on to refuse
an unready plan — here it is mechanical, not eyeballed.

Exit codes: 0 = pass, 1 = errors / not-ready, 2 = bad usage.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _specdoc as doc  # noqa: E402

STATUSES = {"draft", "in-review", "approved", "in-progress", "done"}

# Mandatory H2 sections, by keyword (lowercased), in required order.
SECTIONS = [
    "summary",
    "technical context",
    "constitution check",
    "project structure",
    "skills",
    "convention",
    "testable units",
    "guardrail",
    "implementation steps",
    "sequencing",
    "complexity tracking",
    "assumptions",
    "open questions",
    "traceability",
]
META_LINES = ["feature directory", "date", "spec", "status"]
STEP_FIELDS = [
    "goal",
    "spec trace",
    "red",
    "implementation",
    "green criterion",
    "guardrails to satisfy",
    "self-review checkpoint",
]


def main(argv):
    if len(argv) != 2:
        print("usage: validate-plan.py <path-to-plan.md>", file=sys.stderr)
        return 2
    path = argv[1]
    if not os.path.isfile(path):
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    body = doc.read(path)
    errors, warnings = [], []

    _check_location(path, warnings)
    _check_metadata(body, errors)
    _check_sections(body, errors)
    _check_convention_gate(body, errors)
    _check_steps(body, errors)
    _check_traceability(body, errors)
    if "<!--" in body:
        warnings.append("template guidance comments (`<!-- ... -->`) remain — remove them")

    return _report(path, errors, warnings)


def _check_location(path, warnings):
    base = os.path.basename(path)
    if base != "plan.md":
        warnings.append(f"filename '{base}' is not 'plan.md'")
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if not re.match(r"^\d{3,}-.+", parent):
        warnings.append(f"parent directory '{parent}' is not 'NNN-<slug>'")


def _check_metadata(body, errors):
    head = "\n".join(body.splitlines()[:12]).lower()
    for label in META_LINES:
        if f"**{label}**" not in head:
            errors.append(f"missing metadata line: **{label.title()}**")
    m = re.search(r"\*\*status\*\*\s*:?\s*([A-Za-z-]+)", body, re.IGNORECASE)
    if m and m.group(1).lower() not in STATUSES:
        errors.append(f"status '{m.group(1)}' not in {sorted(STATUSES)}")


def _h2(body):
    return [(t.lower(), ln) for t, ln in doc.headings(body, 2)]


def _check_sections(body, errors):
    found = [t for t, _ in _h2(body)]
    positions = []
    for keyword in SECTIONS:
        idx = next((i for i, t in enumerate(found) if keyword in t), None)
        if idx is None:
            errors.append(f"missing section: ## ... (expected to mention '{keyword}')")
        else:
            positions.append((keyword, idx))
    order = [i for _, i in positions]
    if order != sorted(order):
        errors.append(f"sections out of order: {[k for k, _ in positions]}")


def _section_region(body, keyword):
    """Body text from the H2 mentioning `keyword` up to the next H2."""
    h2 = _h2(body)
    start = next((ln for t, ln in h2 if keyword in t), None)
    if start is None:
        return None
    nexts = [ln for _, ln in h2 if ln > start]
    end = min(nexts) - 1 if nexts else len(body.splitlines())
    return "\n".join(body.splitlines()[start:end])


def _check_convention_gate(body, errors):
    """HARD GATE: no convention-audit row may still be marked a 'gap'."""
    region = _section_region(body, "convention")
    if region is None:
        return
    for tbl in doc.tables(region):
        for row in tbl["rows"]:
            cell = " ".join(row).lower()
            if re.search(r"\bgap\b", cell):
                errors.append(
                    "convention audit has an unresolved GAP row: "
                    f"{' | '.join(row)} — close it before implementation"
                )


def _check_steps(body, errors):
    region = _section_region(body, "implementation steps")
    if region is None:
        return
    lines = region.splitlines()
    step_starts = [
        (i, ln) for i, ln in enumerate(lines) if re.match(r"^###\s+Step\s+S\d+", ln, re.I)
    ]
    if not step_starts:
        errors.append("Implementation Steps has no `### Step Sn` blocks")
        return
    for idx, (start, header) in enumerate(step_starts):
        end = step_starts[idx + 1][0] if idx + 1 < len(step_starts) else len(lines)
        block = "\n".join(lines[start:end]).lower()
        sid = re.search(r"step\s+s\d+", header, re.I)
        sid = sid.group(0) if sid else header.strip()
        for field in STEP_FIELDS:
            if field not in block:
                errors.append(f"{sid}: missing field '**{field.title()}:**'")


def _check_traceability(body, errors):
    region = _section_region(body, "traceability")
    if region is None:
        return
    tbls = doc.tables(region)
    if not tbls or not tbls[0]["rows"]:
        errors.append("Traceability has no data rows (coverage not proven)")


def _report(path, errors, warnings):
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"\nFAIL: {path} — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: {path} conforms to the plan template ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    rc = main(sys.argv)
    import _gate_telemetry  # noqa: E402

    _gate_telemetry.emit_gate(sys.argv[1] if len(sys.argv) > 1 else "", rc, "plan")
    sys.exit(rc)
