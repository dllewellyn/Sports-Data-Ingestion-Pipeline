#!/usr/bin/env python3
"""arch-lint.py — deterministic conformance checks for the ARCHITECTURE.md contract.

Encodes the mechanically-checkable rules of `code-architecture-review` (ARCHITECTURE.md
§3-§4) as an AST/import scan, so the review starts from a precise violation list
instead of ad-hoc greps the agent eyeballs. Zero third-party deps (stdlib `ast`),
so it runs under a bare `python3` in the target repo and can drop straight into its
pre-commit.

Covers the rules that are decidable from imports + call sites:
  Rule 1  Single network edge      — network libs imported outside the bronze edge file
  Rule 3  dbt owns the warehouse   — duckdb.connect()/warehouse path opened from Python
  Rule 4  Composition root only    — asset module imports another asset module
  Rule 5  Dependency direction     — a leaf (config/models) imports assets/definitions
  Rule 7  Config discipline        — os.getenv/os.environ outside config.py

Rules 2 (validate-in-order), 6 (transformation belongs in dbt) and 8 (contract
staleness) need reading/judgement and remain the agent's job — this tool does not
fake them.

Grep matches are signals, not verdicts: confirm each hit in context before
reporting. Exit codes: 0 = clean, 1 = findings, 2 = bad usage / no source root.
"""

import argparse
import ast
import os
import sys

NETWORK_MODULES = {"requests", "httpx", "urllib", "urllib3", "socket", "aiohttp", "http"}


def main(argv):
    ap = argparse.ArgumentParser(description="ARCHITECTURE.md conformance linter")
    ap.add_argument("--src", default="src/data_platform",
                    help="package root to scan (default: src/data_platform)")
    ap.add_argument("--edge", default="assets/bronze.py",
                    help="the one file allowed outbound network calls "
                         "(path relative to --src)")
    ap.add_argument("--config", default="config.py",
                    help="the settings module that may read env (relative to --src)")
    args = ap.parse_args(argv[1:])

    if not os.path.isdir(args.src):
        print(f"error: source root not found: {args.src}", file=sys.stderr)
        return 2

    edge = os.path.normpath(os.path.join(args.src, args.edge))
    config = os.path.normpath(os.path.join(args.src, args.config))
    findings = []

    for path in _py_files(args.src):
        rel = os.path.relpath(path, args.src)
        try:
            tree = ast.parse(_read(path), filename=path)
        except SyntaxError as exc:
            findings.append((path, exc.lineno or 0, "parse", f"could not parse: {exc.msg}"))
            continue
        in_assets = rel.split(os.sep)[0] == "assets"
        is_leaf = rel == "config.py" or rel.split(os.sep)[0] == "models"
        mod_name = _module_name(rel)

        for node in ast.walk(tree):
            _check_imports(node, path, rel, edge, in_assets, is_leaf, mod_name, findings)
            _check_calls(node, path, config, findings)

    return _report(args.src, findings)


def _check_imports(node, path, rel, edge, in_assets, is_leaf, mod_name, findings):
    for name, level, lineno in _imported_modules(node):
        top = name.split(".")[0] if name else ""
        # Rule 1 — network libraries only in the bronze edge file
        if top in NETWORK_MODULES and os.path.normpath(path) != edge:
            findings.append((path, lineno, "Rule 1",
                             f"network module '{name}' imported outside the edge "
                             f"({os.path.relpath(edge)})"))
        # Rule 4 — asset module importing a *sibling* asset module
        if in_assets and _references_assets(name, level, mod_name):
            findings.append((path, lineno, "Rule 4",
                             f"asset module imports another asset ('{name or '.'}') "
                             "— wire cross-asset deps via definitions.py / AssetKey"))
        # Rule 5 — a leaf (config/models) importing assets or definitions
        if is_leaf and _references_up(name):
            findings.append((path, lineno, "Rule 5",
                             f"leaf module imports '{name}' — config/models must not "
                             "depend on assets/definitions (dependency direction)"))


def _check_calls(node, path, config, findings):
    if not isinstance(node, ast.Attribute):
        return
    base = node.value
    # Rule 7 — os.getenv / os.environ outside config.py
    if (isinstance(base, ast.Name) and base.id == "os"
            and node.attr in {"getenv", "environ", "putenv"}
            and os.path.normpath(path) != config):
        findings.append((path, node.lineno, "Rule 7",
                         f"os.{node.attr} outside config — settings belong in "
                         "config.py (pydantic-settings), not ad-hoc env reads"))
    # Rule 3 — duckdb.connect(<a real db path>) from Python
    if (isinstance(base, ast.Name) and base.id == "duckdb" and node.attr == "connect"):
        findings.append((path, node.lineno, "Rule 3",
                         "duckdb.connect() in Python — dbt owns warehouse writes; "
                         "Python consumers read the Parquet artifacts (confirm it is "
                         "not an in-memory read)"))


def _imported_modules(node):
    """Yield (module_name, relative_level, lineno) for import nodes."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name, 0, node.lineno
    elif isinstance(node, ast.ImportFrom):
        yield (node.module or ""), node.level, node.lineno


def _references_assets(name, level, mod_name):
    if level > 0:  # relative import within the assets package, e.g. `from .silver import x`
        return True
    return ".assets." in f".{name}." or name.startswith("assets.") or ".assets" in f".{name}"


def _references_up(name):
    return any(seg in (name or "").split(".") for seg in ("assets", "definitions"))


def _module_name(rel):
    return rel[:-3].replace(os.sep, ".")


def _py_files(root):
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _report(src, findings):
    if not findings:
        print(f"OK: no mechanical ARCHITECTURE.md violations under {src} "
              "(rules 2/6/8 still need agent review)")
        return 0
    for path, lineno, rule, msg in sorted(findings):
        print(f"{path}:{lineno}: [{rule}] {msg}")
    print(f"\n{len(findings)} finding(s) — confirm each in context; "
          "rules 2/6/8 are not checked here")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
