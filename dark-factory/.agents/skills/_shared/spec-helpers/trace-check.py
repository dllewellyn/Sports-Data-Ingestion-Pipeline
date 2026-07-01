#!/usr/bin/env python3
"""trace-check.py — deterministic traceability-closure check across the feature artifacts.

Does the set arithmetic that `implementor` and `feature` otherwise do by eye:
every spec coverage item (functional requirement `FR-NNN` / success criterion
`SC-NNN`) must be implemented by at least one plan step, and every plan step must
trace back in the plan's Traceability section. With a third argument it also checks
that every plan step is covered by at least one task in `tasks.md`.

It is a MECHANICAL aid — it matches ids as text; whether a given mapping is
*meaningful* is still the reviewer's judgement.

Usage:
  trace-check.py <spec.md> <plan.md>            # spec → plan closure
  trace-check.py <spec.md> <plan.md> <tasks.md> # spec → plan → tasks closure
Exit codes: 0 = closed, 1 = gaps found, 2 = bad usage.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _specdoc as doc  # noqa: E402


def main(argv):
    if len(argv) not in (3, 4):
        print("usage: trace-check.py <spec.md> <plan.md> [tasks.md]", file=sys.stderr)
        return 2
    paths = argv[1:]
    for p in paths:
        if not os.path.isfile(p):
            print(f"error: no such file: {p}", file=sys.stderr)
            return 2

    spec_body = doc.read(paths[0])
    plan_body = doc.read(paths[1])
    tasks_body = doc.read(paths[2]) if len(paths) == 3 else None

    spec_items = _spec_items(spec_body)        # FR-/SC- ids
    plan_steps = _step_ids(plan_body)          # Sn ids
    plan_trace = _h2_section(plan_body, "traceability")

    errors = []

    if not spec_items:
        print("warning: no `FR-NNN`/`SC-NNN` ids found in the spec — nothing to trace")
    uncovered = [i for i in spec_items if not re.search(rf"\b{re.escape(i)}\b", plan_trace)]
    if uncovered:
        errors.append("spec FR/SC absent from the plan's Traceability: "
                      + ", ".join(sorted(uncovered, key=_idsort)))

    if not plan_steps:
        print("warning: no `### Step Sn` blocks found in the plan")
    setup_steps = _setup_steps(plan_body)  # setup/enabler steps need not trace to a spec item
    orphans = [s for s in plan_steps
               if s not in setup_steps and not re.search(rf"\b{s}\b", plan_trace)]
    if orphans:
        errors.append("non-setup plan steps absent from the plan's Traceability: "
                      + ", ".join(sorted(orphans, key=_idsort)))

    if tasks_body is not None:
        uncovered_steps = [s for s in plan_steps
                           if not re.search(rf"\b{s}\b", tasks_body)]
        if uncovered_steps:
            errors.append("plan steps with no task in tasks.md: "
                          + ", ".join(sorted(uncovered_steps, key=_idsort)))

    return _report(paths, spec_items, plan_steps, tasks_body, errors)


def _spec_items(body):
    return sorted(set(re.findall(r"\b(?:FR|SC)-\d+\b", body)), key=_idsort)


def _step_ids(body):
    return sorted(set(re.findall(r"\bS\d+\b", body)), key=_idsort)


def _setup_steps(body):
    """Step ids whose block declares them setup/enabler (spec-trace mentions 'setup')."""
    region = _h2_section(body, "implementation steps")
    lines = region.splitlines()
    starts = [(i, re.search(r"\bS\d+\b", ln).group(0))
              for i, ln in enumerate(lines)
              if re.match(r"^###\s+Step\s+S\d+", ln, re.I)]
    setup = set()
    for idx, (start, sid) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        if "setup" in "\n".join(lines[start:end]).lower():
            setup.add(sid)
    return setup


def _h2_section(body, keyword):
    """Text of the H2 section whose title mentions `keyword`, to the next H2."""
    h2 = [(t.lower(), ln) for t, ln in doc.headings(body, 2)]
    start = next((ln for t, ln in h2 if keyword in t), None)
    if start is None:
        return ""
    nexts = [ln for _, ln in h2 if ln > start]
    end = min(nexts) - 1 if nexts else len(body.splitlines())
    return "\n".join(body.splitlines()[start:end])


def _idsort(s):
    return (re.sub(r"[-\d].*", "", s), int(re.sub(r"\D", "", s) or 0))


def _report(paths, spec_items, plan_steps, tasks_body, errors):
    print(f"spec:  {os.path.basename(paths[0])} — {len(spec_items)} FR/SC items")
    print(f"plan:  {os.path.basename(paths[1])} — {len(plan_steps)} steps")
    if tasks_body is not None:
        ntasks = len(re.findall(r"^\s*-\s*\[[ xX]\]\s*T\d", tasks_body, re.M))
        print(f"tasks: {os.path.basename(paths[2])} — {ntasks} tasks")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"\nFAIL: traceability not closed — {len(errors)} gap(s)")
        return 1
    print("OK: traceability closed (every FR/SC reaches a step; every step traces back"
          + ("; every step has a task)" if tasks_body is not None else ")"))
    return 0


if __name__ == "__main__":
    rc = main(sys.argv)
    import _gate_telemetry  # noqa: E402

    _gate_telemetry.emit_gate(sys.argv[-1] if len(sys.argv) > 1 else "", rc, "trace")
    sys.exit(rc)
