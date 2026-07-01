#!/usr/bin/env python3
"""validate-spec.py — deterministic structural linter for a Specification file.

Checks a written `specs/NNN-<slug>/spec.md` against the contract in
`specification/references/specification-template.md`: the location and metadata
lines, the presence + naming of the mandatory sections, and that the load-bearing
content (prioritised user stories, BDD acceptance scenarios, functional
requirements, success criteria, open questions) is actually filled. This is the
"ruff for specs" check — it replaces eyeballing the template, NOT the authoring
judgement (good BDD, right altitude, real coverage) which stays with the
writer/reviewer.

Exit codes: 0 = pass (warnings allowed), 1 = errors found, 2 = bad usage.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _specdoc as doc  # noqa: E402

STATUSES = {"draft", "clarified", "planned", "implemented"}

# Mandatory H2 sections, identified by a keyword that must appear in the heading
# (lowercased). Order is enforced in the order listed here.
SECTIONS = [
    "user scenarios",
    "requirements",
    "success criteria",
    "constraints",
    "assumptions",
    "open questions",
]

# Metadata lines that must appear in the spec preamble.
META_LINES = [
    "feature directory",
    "created",
    "status",
    "input",
]

MAX_CLARIFICATIONS = 3


def main(argv):
    if len(argv) != 2:
        print("usage: validate-spec.py <path-to-spec.md>", file=sys.stderr)
        return 2
    path = argv[1]
    if not os.path.isfile(path):
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    body = doc.read(path)
    errors, warnings = [], []

    _check_location(path, errors, warnings)
    _check_metadata(body, errors, warnings)
    _check_sections(body, errors)
    _check_content(body, errors, warnings)
    if "<!--" in body:
        warnings.append("template guidance comments (`<!-- ... -->`) remain — remove them")

    return _report(path, "specification", errors, warnings)


def _check_location(path, errors, warnings):
    base = os.path.basename(path)
    if base != "spec.md":
        warnings.append(f"filename '{base}' is not 'spec.md'")
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if not re.match(r"^\d{3,}-.+", parent):
        warnings.append(f"parent directory '{parent}' is not 'NNN-<slug>'")


def _check_metadata(body, errors, warnings):
    head = "\n".join(body.splitlines()[:15]).lower()
    for label in META_LINES:
        if f"**{label}**" not in head:
            errors.append(f"missing metadata line: **{label.title()}**")
    m = re.search(r"\*\*status\*\*\s*:?\s*([A-Za-z-]+)", body, re.IGNORECASE)
    if m and m.group(1).lower() not in STATUSES:
        errors.append(f"status '{m.group(1)}' not in {sorted(STATUSES)}")


def _check_sections(body, errors):
    found = [t.lower() for t, _ in doc.headings(body, 2)]
    seen_positions = []
    for keyword in SECTIONS:
        idx = next((i for i, t in enumerate(found) if keyword in t), None)
        if idx is None:
            errors.append(f"missing section: ## ... (expected to mention '{keyword}')")
        else:
            seen_positions.append((keyword, idx))
    order = [i for _, i in seen_positions]
    if order != sorted(order):
        errors.append(f"sections out of order: {[k for k, _ in seen_positions]}")


def _check_content(body, errors, warnings):
    if not re.search(r"^###\s+User Story.*\(Priority:\s*P\d", body, re.MULTILINE):
        errors.append("no prioritised user story (`### User Story ... (Priority: P1)`) found")
    if not ("**Given**" in body and "**When**" in body and "**Then**" in body):
        errors.append("no BDD acceptance scenario (Given/When/Then) found")
    if not re.search(r"\bFR-\d", body):
        errors.append("no functional requirement (`FR-NNN`) found")
    if not re.search(r"\bSC-\d", body):
        errors.append("no success criterion (`SC-NNN`) found")

    n_clar = len(re.findall(r"\[NEEDS CLARIFICATION", body))
    if n_clar > MAX_CLARIFICATIONS:
        errors.append(f"{n_clar} [NEEDS CLARIFICATION] markers exceed the max of {MAX_CLARIFICATIONS}")
    elif n_clar > 0:
        warnings.append(f"{n_clar} [NEEDS CLARIFICATION] marker(s) remain — resolve before planning")

    _check_open_questions(body, errors)


def _check_open_questions(body, errors):
    h2 = doc.headings(body, 2)
    oq = next((ln for t, ln in h2 if "open questions" in t.lower()), None)
    if oq is None:
        return  # already reported missing
    lines = body.splitlines()
    # `oq` is the 1-based lineno of the heading, so lines[oq:] already starts on the
    # line *after* the heading. Gather up to the next H2.
    nexts = [ln for _, ln in h2 if ln > oq]
    end = min(nexts) - 1 if nexts else len(lines)
    section = "\n".join(lines[oq:end])
    content = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    if not content.strip():
        errors.append("§ Open Questions is empty — write 'None.' if there are none")


def _report(path, kind, errors, warnings):
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"\nFAIL: {path} — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: {path} conforms to the {kind} template ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    rc = main(sys.argv)
    import _gate_telemetry  # noqa: E402

    _gate_telemetry.emit_gate(sys.argv[1] if len(sys.argv) > 1 else "", rc, "specification")
    sys.exit(rc)
