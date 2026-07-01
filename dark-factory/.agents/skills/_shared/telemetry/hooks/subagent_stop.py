#!/usr/bin/env python3
"""SubagentStop hook — ingest a sub-agent's transcript and emit its span as a FALLBACK.

The span is normally emitted by PostToolUse (which provably fires for the Agent tool).
This hook's primary job is transcript ingestion; it emits the span itself ONLY when no
PostToolUse dedup marker exists for the paired tool_use_id, so the span is never
double-counted but is still produced if PostToolUse somehow didn't fire.

  1. Ingest the sub-agent's OWN transcript (its `transcript_path`) into Loki tagged
     run_id + agent_id -> the click-through: prompt, tool calls, reasoning. This is
     the deterministic source that makes "click a span, see what it did" work even
     if Claude Code's native OTEL log events don't carry an agent id (the spike's
     open question). Disable with FEATURE_TELEMETRY_INGEST_TRANSCRIPTS=0 if the
     spike shows native logs already discriminate by agent.
  2. Fallback span (start time recovered from the matching spawn record; parent span
     id COMPUTED from the parent agent id) -> the node in the graph, only when
     PostToolUse left no marker.

Pairing: prefer the agent record PostToolUse wrote keyed by this agent_id; else the
spawn record keyed by tool_use_id; else FIFO pop (degraded).
"""

import contextlib
import json
import os
import re
import sys
import time

import _hooklib as h

MAX_MSGS = int(os.environ.get("FEATURE_TELEMETRY_MAX_MSGS", "1000"))
MAX_BODY = 6000
MAX_TOOL_INPUT_VALUE = 512

# File-touching tools whose input value gets a dedicated tool_read record.
_FILE_TOUCHING_TOOLS = ("Read", "Edit", "Write", "Grep", "Glob")

# --- Secret redaction rule (R10 — FR-010 / Security) ---
# Named-prefix secret shapes — these mask REGARDLESS of any '/' in the value
# (a credential is a credential even if it appears inside a path-like string).
_SECRET_PREFIX_RE = re.compile(
    r"(?:sk-[A-Za-z0-9]{16,}"  # OpenAI-style
    r"|ghp_[A-Za-z0-9]{20,}"  # GitHub PAT
    r"|AKIA[0-9A-Z]{16}"  # AWS access key id
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"  # Slack token
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"  # JWT
)
# Generic high-entropy catch-all — ONLY fires on a WHOLE value that is a single
# unbroken >=40-char base64-ish blob (anchored, no '/' path separator). Anchoring
# to the whole value means a path-bearing string such as
# `dist/assets/index-<40hex>.js` can NEVER match: the '/' (and the '.js' tail)
# break the anchor, so opaque/hashed PATH SEGMENTS are left verbatim. Without the
# anchor a long hashed segment inside a path would be masked, desyncing a captured
# read path from the byte-identical `git_files` diff path (which is never masked).
_SECRET_GENERIC_RE = re.compile(r"\A[A-Za-z0-9+/]{40,}\Z")


def _mask(value: str) -> tuple[str, bool]:
    is_secret = bool(_SECRET_PREFIX_RE.search(value)) or (
        "/" not in value and _SECRET_GENERIC_RE.fullmatch(value) is not None
    )
    if is_secret:
        masked = value[:4] + "…" + value[-4:] if len(value) > 8 else "…"
        return masked, True
    return value, False


def _tool_read_record(block, idx, agent_id, role):
    """Build a dedicated tool_read record for a file-touching tool_use block, else None."""
    name = block.get("name", "")
    if name not in _FILE_TOUCHING_TOOLS:
        return None
    tool_input = block.get("input") or {}
    if name in ("Read", "Edit", "Write"):
        raw = tool_input.get("file_path")
    else:  # Grep / Glob
        pattern = tool_input.get("pattern")
        if pattern is None:
            raw = None
        else:
            path = tool_input.get("path")
            raw = f"{pattern} @ {path}" if path else pattern
    if not isinstance(raw, str):
        return None

    masked_value, redacted = _mask(raw)
    value = masked_value
    truncated = len(masked_value) > MAX_TOOL_INPUT_VALUE
    if truncated:
        value = masked_value[:MAX_TOOL_INPUT_VALUE]

    attrs = [
        ("event_type", "tool_read"),
        ("tool_name", name),
        ("tool_input_value", value),
        ("role", role),
        ("agent_id", agent_id),
        ("msg_index", idx),
    ]
    if truncated:
        attrs.append(("value_truncated", "true"))
        attrs.append(("value_len", str(len(masked_value))))
    if redacted:
        attrs.append(("value_redacted", "true"))
    return {
        "body": f"tool_read {name} {value}",
        "severity": "INFO",
        "attrs": attrs,
    }


def _summarize_content(content):
    """Flatten an Anthropic-style content list (or string) into (kind, text)."""
    if isinstance(content, str):
        return "text", content
    if not isinstance(content, list):
        return "other", json.dumps(content)[:MAX_BODY]
    kinds, parts = [], []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue
        btype = block.get("type", "")
        if btype == "text":
            kinds.append("text")
            parts.append(block.get("text", ""))
        elif btype == "thinking":
            kinds.append("thinking")
            parts.append("[thinking] " + str(block.get("thinking", ""))[:MAX_BODY])
        elif btype == "tool_use":
            # File-touching tools get a dedicated tool_read record (built in
            # _transcript_records); they no longer contribute a keys-only body
            # fragment (Constitution I — no legacy dual path).
            if block.get("name") in _FILE_TOUCHING_TOOLS:
                continue
            kinds.append("tool_use")
            keys = ",".join(sorted((block.get("input") or {}).keys()))
            parts.append(f"[tool_use {block.get('name', '?')}] inputs: {keys}")
        elif btype == "tool_result":
            kinds.append("tool_result")
            parts.append("[tool_result] " + json.dumps(block.get("content", ""))[:MAX_BODY])
        else:
            kinds.append(btype or "other")
            parts.append(json.dumps(block)[:500])
    return ("+".join(dict.fromkeys(kinds)) or "other", "\n".join(p for p in parts if p))


def _transcript_records(transcript_path, run_id, agent_id, role):
    records = []
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return records
    for idx, line in enumerate(lines[:MAX_MSGS]):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
        entry_type = obj.get("type") or msg.get("role") or "entry"
        content = msg.get("content", obj.get("content", ""))
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_read = _tool_read_record(block, idx, agent_id, role)
                    if tool_read is not None:
                        records.append(tool_read)
        kind, text = _summarize_content(content)
        body = (text or json.dumps(obj))[:MAX_BODY]
        records.append(
            {
                "body": body,
                "severity": "INFO",
                "attrs": [
                    ("event_type", "transcript"),
                    ("agent_id", agent_id),
                    ("role", role),
                    ("msg_index", idx),
                    ("entry_type", entry_type),
                    ("content_kind", kind),
                ],
            }
        )
    if len(lines) > MAX_MSGS:
        records.append(
            {
                "body": f"[truncated: {len(lines) - MAX_MSGS} more transcript lines]",
                "severity": "WARN",
                "attrs": [("event_type", "transcript"), ("agent_id", agent_id), ("role", role)],
            }
        )
    return records


def main():
    event = h.read_event()
    ctx = h.emit.current_context()
    run_id, trace_id = ctx.get("run_id"), ctx.get("trace_id")
    root_span_id = ctx.get("root_span_id", "")
    if not run_id or not trace_id:
        return

    end_ns = time.time_ns()
    agent_id = event.get("agent_id") or f"anon-{end_ns}"
    agent_type = event.get("agent_type") or ""
    transcript_path = event.get("transcript_path") or ""
    session_id = event.get("session_id") or ""
    tool_use_id = h.extract_tool_use_id(event)

    # Pairing, preferred -> degraded:
    #   1. agent record PostToolUse wrote keyed by this agent_id (carries span_id/role).
    #   2. spawn record keyed by tool_use_id.
    #   3. FIFO pop of the PreToolUse spawn records.
    rec = h.read_agent(run_id, agent_id)
    if not rec and tool_use_id:
        rec = h.read_keyed(run_id, "spawns", tool_use_id)
    if not rec:
        rec = h.pop_oldest(run_id, "pending-spawns.jsonl")
    start_ns = rec.get("start_ns") or end_ns
    parent_agent_id = rec.get("parent_agent_id") or "root"
    role = rec.get("role") or agent_type or "subagent"
    phase = rec.get("phase", "")

    # Emit the span ONLY if PostToolUse didn't already (no dedup marker). Reuse the
    # span_id PostToolUse computed if we have it, else compute from this agent_id.
    if not h.marker_exists(run_id, "spawns", tool_use_id):
        span_id = rec.get("span_id") or h.emit.derive_span_id(trace_id, agent_id)
        parent_span_id = (
            root_span_id
            if parent_agent_id in ("", "root", None)
            else h.emit.derive_span_id(trace_id, parent_agent_id)
        )
        h.emit.send_span(
            trace_id=trace_id,
            run_id=run_id,
            name=role,
            span_id=span_id,
            parent_span_id=parent_span_id,
            start_ns=start_ns,
            end_ns=end_ns,
            attrs=[
                ("role", role),
                ("phase", phase),
                ("agent_id", agent_id),
                ("agent_type", agent_type),
                ("session.id", session_id),
                ("tool_use_id", tool_use_id),
            ],
        )

    records = [
        {
            "body": f"subagent stopped: {role} ({agent_type})",
            "severity": "INFO",
            "attrs": [
                ("event_type", "subagent_stop"),
                ("phase", phase),
                ("role", role),
                ("agent_id", agent_id),
                ("agent_type", agent_type),
            ],
        }
    ]
    if transcript_path and os.environ.get("FEATURE_TELEMETRY_INGEST_TRANSCRIPTS", "1") != "0":
        records.extend(_transcript_records(transcript_path, run_id, agent_id, role))
    h.emit.send_logs(trace_id=trace_id, run_id=run_id, records=records)


if __name__ == "__main__":
    # A hook must never block a tool call: swallow everything and always exit 0.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
