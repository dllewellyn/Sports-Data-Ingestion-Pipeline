#!/usr/bin/env python3
"""PostToolUse hook (matcher: Agent|Task) — the RELIABLE span emitter.

PostToolUse provably fires for the Agent tool (a global PreToolUse/PostToolUse
matcher runs here), whereas SubagentStop's firing for background Agent-tool spawns is
unconfirmed. So this is where a sub-agent's span is normally emitted.

It fires in the PARENT's turn when the spawned sub-agent has FINISHED, and the tool
result carries the CHILD agent's id. We:
  1. Pair to the PreToolUse spawn record DETERMINISTICALLY by tool_use_id (FIFO
     fallback only if the id is absent).
  2. Pull the child agent id out of the tool result (dict agentId/agent_id/id, or a
     bare string).
  3. Emit the span — span id COMPUTED from (trace_id, child_agent_id) so a grandchild
     spawned BY this child resolves the same parent span id by computation alone.
  4. Drop a dedup marker keyed by tool_use_id so a later SubagentStop won't re-emit,
     and write an agent record keyed by the child agent_id so SubagentStop can attach
     the transcript to the right span and nested grandchildren find this parent.
"""

import contextlib
import sys
import time

import _hooklib as h


def main():
    event = h.read_event()
    ctx = h.emit.current_context()
    run_id, trace_id = ctx.get("run_id"), ctx.get("trace_id")
    root_span_id = ctx.get("root_span_id", "")
    if not run_id or not trace_id:
        return  # no active feature run -> nothing to trace

    now = time.time_ns()
    tool_use_id = h.extract_tool_use_id(event)

    # Load the spawn record: preferred by tool_use_id, else FIFO pop.
    rec = h.read_keyed(run_id, "spawns", tool_use_id) if tool_use_id else {}
    if not rec:
        rec = h.pop_oldest(run_id, "pending-spawns.jsonl")

    child_agent_id = h.extract_child_agent_id(event)
    parent_agent_id = rec.get("parent_agent_id") or "root"
    role = rec.get("role") or rec.get("subagent_type") or "subagent"
    phase = rec.get("phase", "")
    subagent_type = rec.get("subagent_type", "")
    start_ns = rec.get("start_ns") or now

    # Span id from the child agent id when known (so grandchildren match), else from
    # the tool_use_id as a stable fallback.
    span_key = child_agent_id or tool_use_id or f"anon-{now}"
    span_id = h.emit.derive_span_id(trace_id, span_key)
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
        end_ns=now,
        attrs=[
            ("role", role),
            ("phase", phase),
            ("agent_id", child_agent_id),
            ("agent_type", subagent_type),
            ("tool_use_id", tool_use_id),
        ],
    )

    # Dedup marker keyed by tool_use_id so SubagentStop knows the span is already out.
    if tool_use_id:
        h.write_marker(run_id, "spawns", tool_use_id)
    # Agent record keyed by child agent_id: lets SubagentStop attach the transcript to
    # this span, and lets a grandchild (parent_agent_id == child_agent_id) compute the
    # matching parent span id.
    if child_agent_id:
        h.write_agent(
            run_id,
            child_agent_id,
            {"span_id": span_id, "role": role, "phase": phase},
        )

    h.emit.send_logs(
        trace_id=trace_id,
        run_id=run_id,
        records=[
            {
                "body": f"subagent complete: {role} ({subagent_type})"[:300],
                "severity": "INFO",
                "attrs": [
                    ("event_type", "subagent_complete"),
                    ("phase", phase),
                    ("role", role),
                    ("agent_id", child_agent_id),
                    ("agent_type", subagent_type),
                    ("parent_agent_id", parent_agent_id),
                    ("tool_use_id", tool_use_id),
                ],
            }
        ],
    )


if __name__ == "__main__":
    # A hook must never block a tool call: swallow everything and always exit 0.
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
