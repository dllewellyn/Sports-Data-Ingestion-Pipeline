#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent|Task) — records a sub-agent spawn.

Fires in the PARENT agent's turn just before a sub-agent starts, so its `agent_id`
is the parent (absent for the top-level orchestrator). We can't see the child's id
yet, so we stash what we know — parent id, start time, and the role the orchestrator
queued via `emit.py label-next` — for the matching PostToolUse (preferred) or
SubagentStop (fallback) to consume.

Pairing key: the `tool_use_id` is shared with the PostToolUse for the SAME tool call,
so we persist the spawn record KEYED by it (spawns/<tool_use_id>.json) for
deterministic pairing. If no tool_use_id is present we fall back to the FIFO
pending-spawns.jsonl so nothing regresses.
"""

import contextlib
import sys
import time

import _hooklib as h


def main():
    event = h.read_event()
    ctx = h.emit.current_context()
    run_id, trace_id = ctx.get("run_id"), ctx.get("trace_id")
    if not run_id or not trace_id:
        return  # no active feature run -> nothing to trace

    parent_agent_id = event.get("agent_id") or "root"
    tool_input = event.get("tool_input") or {}
    subagent_type = tool_input.get("subagent_type") or event.get("agent_type") or ""
    description = tool_input.get("description") or ""
    tool_use_id = h.extract_tool_use_id(event)

    # The orchestrator labels the NEXT spawn it makes; pair FIFO.
    role_entry = h.pop_oldest(run_id, "pending-roles.jsonl")
    role = role_entry.get("role", "")
    phase = role_entry.get("phase", "")

    record = {
        "parent_agent_id": parent_agent_id,
        "start_ns": time.time_ns(),
        "role": role,
        "phase": phase,
        "subagent_type": subagent_type,
        "description": description,
        "tool_use_id": tool_use_id,
    }
    if tool_use_id:
        # Deterministic pairing: PostToolUse for this tool call reads spawns/<id>.json.
        h.write_keyed(run_id, "spawns", tool_use_id, record)
    else:
        # No id available -> degrade to FIFO so nothing regresses.
        h.append_jsonl(run_id, "pending-spawns.jsonl", record)

    h.emit.send_logs(
        trace_id=trace_id,
        run_id=run_id,
        records=[
            {
                "body": f"spawn {role or subagent_type or 'subagent'}: {description}"[:300],
                "severity": "INFO",
                "attrs": [
                    ("event_type", "spawn"),
                    ("phase", phase),
                    ("role", role),
                    ("agent_type", subagent_type),
                    ("parent_agent_id", parent_agent_id),
                ],
            }
        ],
    )


if __name__ == "__main__":
    # A hook must never block a tool call: swallow everything and always exit 0.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
