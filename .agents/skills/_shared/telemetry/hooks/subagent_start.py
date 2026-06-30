#!/usr/bin/env python3
"""SubagentStart hook — bind a spawn (parent + role + start time) to the child id.

This is the FIRST event that carries the new sub-agent's `agent_id`, but it does
NOT carry the parent. The parent (and the orchestrator's role label) were recorded
by the matching PreToolUse(Agent) a moment earlier; we pop that FIFO — valid here
because PreToolUse→SubagentStart pairs fire in spawn order — and persist the joined
record keyed by the child `agent_id`, where SubagentStop can find it by id (no
fragile stop-time ordering).
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
        return

    agent_id = event.get("agent_id") or ""
    agent_type = event.get("agent_type") or ""
    if not agent_id:
        return

    spawn = h.pop_oldest(run_id, "pending-spawns.jsonl")
    parent_agent_id = spawn.get("parent_agent_id") or "root"
    role = spawn.get("role") or agent_type or "subagent"
    phase = spawn.get("phase", "")

    h.write_agent(
        run_id,
        agent_id,
        {
            "start_ns": time.time_ns(),
            "parent_agent_id": parent_agent_id,
            "role": role,
            "phase": phase,
            "agent_type": agent_type,
            "session_id": event.get("session_id", ""),
        },
    )

    h.emit.send_logs(
        trace_id=trace_id,
        run_id=run_id,
        records=[
            {
                "body": f"subagent started: {role} ({agent_type})",
                "severity": "INFO",
                "attrs": [
                    ("event_type", "subagent_start"),
                    ("phase", phase),
                    ("role", role),
                    ("agent_id", agent_id),
                    ("agent_type", agent_type),
                    ("parent_agent_id", parent_agent_id),
                ],
            }
        ],
    )


if __name__ == "__main__":
    # A hook must never block a tool call, so swallow everything.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
