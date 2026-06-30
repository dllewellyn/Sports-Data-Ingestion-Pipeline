#!/usr/bin/env python3
"""SubagentStop hook — close a sub-agent's span and ingest what it did.

This is where a sub-agent becomes visible in the trace:
  1. Emit the span (start time recovered from the matching PreToolUse spawn record;
     parent span id COMPUTED from the parent agent id) -> the node in the graph.
  2. Ingest the sub-agent's OWN transcript (its `transcript_path`) into Loki tagged
     run_id + agent_id -> the click-through: prompt, tool calls, reasoning. This is
     the deterministic source that makes "click a span, see what it did" work even
     if Claude Code's native OTEL log events don't carry an agent id (the spike's
     open question). Disable with FEATURE_TELEMETRY_INGEST_TRANSCRIPTS=0 if the
     spike shows native logs already discriminate by agent.
"""

import contextlib
import json
import os
import sys
import time

import _hooklib as h

MAX_MSGS = int(os.environ.get("FEATURE_TELEMETRY_MAX_MSGS", "1000"))
MAX_BODY = 6000


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
        kind, text = _summarize_content(msg.get("content", obj.get("content", "")))
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

    # Preferred path: the record SubagentStart keyed by this agent_id (correct under
    # nesting). Fallback: FIFO pop of the PreToolUse spawn records, if SubagentStart
    # never ran (degraded — only the timing/parent of nested siblings may be approximate).
    rec = h.read_agent(run_id, agent_id)
    if not rec:
        rec = h.pop_oldest(run_id, "pending-spawns.jsonl")
    start_ns = rec.get("start_ns") or end_ns
    parent_agent_id = rec.get("parent_agent_id") or "root"
    role = rec.get("role") or agent_type or "subagent"
    phase = rec.get("phase", "")

    span_id = h.emit.derive_span_id(trace_id, agent_id)
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
    # A hook must never block a tool call, so swallow everything.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
