"""Minimal, zero-dependency parser for the spec/plan/tasks Markdown documents.

Shared by validate-spec.py, validate-plan.py, validate-tasks.py and trace-check.py
(the rule of three, comfortably). Pure stdlib so the helpers run under a bare
`python3` in any target repo without adding a dependency.

It parses two things the validators need:
  * the `##` section headings, in document order, via `headings()`.
  * GitHub-flavoured Markdown tables (header + data rows) via `tables()`.
"""

import re

_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def headings(body, level):
    """Ordered list of (title, lineno) for headings of exactly `level` hashes."""
    out = []
    for n, line in enumerate(body.splitlines(), start=1):
        m = _HEADING.match(line)
        if m and len(m.group("hashes")) == level:
            out.append((m.group("title").strip(), n))
    return out


def tables(body):
    """Extract Markdown tables. Returns list of dicts:
    {header: [cells], rows: [[cells], ...], start_line: int}.
    A table is a header row, a `---|---` separator row, then >=0 data rows."""
    lines = body.splitlines()
    result = []
    i = 0
    while i < len(lines) - 1:
        if _is_row(lines[i]) and _is_separator(lines[i + 1]):
            header = _cells(lines[i])
            rows = []
            j = i + 2
            while j < len(lines) and _is_row(lines[j]):
                rows.append(_cells(lines[j]))
                j += 1
            result.append({"header": header, "rows": rows, "start_line": i + 1})
            i = j
        else:
            i += 1
    return result


def _is_row(line):
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_separator(line):
    s = line.strip()
    if not _is_row(s):
        return False
    return all(set(c.strip()) <= set("-: ") and c.strip() for c in _cells(s))


def _cells(line):
    s = line.strip()
    return [c.strip() for c in s[1:-1].split("|")]
