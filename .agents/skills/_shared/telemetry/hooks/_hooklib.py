"""Shared helpers for the Claude Code telemetry hooks.

Hooks are the DETERMINISTIC half of feature-run tracing: the harness fires them on
every sub-agent spawn/stop regardless of what the model says, so they are the
trustworthy "this sub-agent actually ran" signal. They must be fast and totally
non-fatal — a telemetry problem must never block or fail a tool call, so every
entrypoint swallows errors and exits 0.

Correlation model (see emit.derive_span_id): each agent's span id is COMPUTED from
(trace_id, agent_id), so a child can point at its parent's span id without waiting
for the parent's span to be emitted (a parent sub-agent only stops AFTER its
children, so its span doesn't exist yet at child-stop time).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import emit  # noqa: E402

try:
    import fcntl  # POSIX; hooks run on the dev host (darwin/linux)

    _HAVE_FLOCK = True
except ImportError:  # pragma: no cover - Windows fallback
    _HAVE_FLOCK = False


def read_event():
    """Parse the hook JSON from stdin; {} on any problem."""
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}


def queue_path(run_id, filename):
    return os.path.join(emit._repo_root(), "temp", "telemetry", run_id, filename)


def _locked(fh, exclusive=True):
    if _HAVE_FLOCK:
        fcntl.flock(fh, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)


def append_jsonl(run_id, filename, obj):
    path = queue_path(run_id, filename)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            _locked(fh)
            fh.write(json.dumps(obj) + "\n")
    except OSError:
        pass


def write_agent(run_id, agent_id, obj):
    """Persist a per-agent record keyed by the child agent_id — set at SubagentStart
    (the first event carrying the child id) and read at SubagentStop. Keying by id
    (not FIFO) is what makes nesting correct: a child stops before its parent, so a
    stop-time FIFO pop would mispair, but an id lookup never does."""
    path = queue_path(run_id, os.path.join("agents", f"{agent_id}.json"))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            _locked(fh)
            json.dump(obj, fh)
    except OSError:
        pass


def read_agent(run_id, agent_id):
    path = queue_path(run_id, os.path.join("agents", f"{agent_id}.json"))
    try:
        with open(path, encoding="utf-8") as fh:
            _locked(fh, exclusive=False)
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def pop_oldest(run_id, filename):
    """Pop and return the oldest JSONL entry (FIFO), rewriting the remainder under a
    lock. Returns {} if empty/missing. FIFO is the best available pairing of a
    SubagentStop to the PreToolUse(Agent) that recorded its parent + start time."""
    path = queue_path(run_id, filename)
    try:
        with open(path, "r+", encoding="utf-8") as fh:
            _locked(fh)
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
            if not lines:
                return {}
            first, rest = lines[0], lines[1:]
            fh.seek(0)
            fh.truncate()
            if rest:
                fh.write("\n".join(rest) + "\n")
            try:
                return json.loads(first)
            except ValueError:
                return {}
    except OSError:
        return {}
