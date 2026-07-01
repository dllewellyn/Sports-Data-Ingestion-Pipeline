---
title: "Contract — enriched tool-input value capture (FR-009 / FR-010)"
---

# Contract — enriched tool-input value capture (FR-009 / FR-010)

The change to `subagent_stop.py` (`_transcript_records` / `_summarize_content`) and the records it
feeds. **Replaces** the keys-only summary for file-touching tools (Constitution I — no legacy
keys-only path retained for that set).

## Before (today, the gap)

```python
elif btype == "tool_use":
    keys = ",".join(sorted((block.get("input") or {}).keys()))
    parts.append(f"[tool_use {block.get('name','?')}] inputs: {keys}")
```
→ records that `Read` was called, never *what* was read. Worse, a single assistant message routinely
carries MULTIPLE `tool_use` blocks (parallel Reads/Edits), and `_summarize_content` packs the whole
message into ONE `(kind, text)` → one transcript `body`. A single per-record `tool_input_value` attr
could therefore only hold one of several values; the values would collide on one key.

## After (the contract) — one dedicated record per file-touching tool_use block

`_transcript_records` (delegating per-block work to `_summarize_content`) **yields one dedicated log
record per file-touching `tool_use` block**, instead of folding the tool input into the message's
body summary. For a `tool_use` block whose `name` is one of `Read`, `Edit`, `Write`, `Grep`, `Glob`:

| Tool | Captured input key | `tool_input_value` |
|------|--------------------|--------------------|
| `Read` / `Edit` / `Write` | `file_path` | the path string |
| `Grep` / `Glob` | `pattern` (and `path` if present, joined `"<pattern> @ <path>"`) | the pattern[+path] string |

The dedicated record's shape (carried via `emit.send_logs` as the existing transcript records are):

| Carrier | Field | Value |
|---------|-------|-------|
| per-record attr | `event_type` | `tool_read` (NEW value — distinct from `transcript`) |
| per-record attr | `tool_name` | `Read`/`Edit`/`Write`/`Grep`/`Glob` |
| per-record attr | `tool_input_value` | the captured path/pattern (bounded + redacted, see below) |
| per-record attr | `role` | the acting agent's role (already threaded into `_transcript_records`) — the attribution key (R5) |
| per-record attr | `agent_id` | already threaded into `_transcript_records` |
| per-record attr | `msg_index` | the transcript line index (carried from the existing transcript records) |
| per-record attr | `value_truncated` = `"true"` | **only when truncated** (Edge E5 — observable, not silent) |
| per-record attr | `value_len` = `str(orig_len)` | **only when truncated** — original length |
| per-record attr | `value_redacted` = `"true"` | **only when R10 secret-masking fired** — see Captured-value rules below (parity with `data-model.md`) |
| resource attr | `run_id` / `feature` / `service.name` | the existing index labels (set by `send_logs`) |
| body | `tool_read <tool_name> <tool_input_value>` | human-readable log line |

Captured-value rules:
- **Bounded** to `MAX_TOOL_INPUT_VALUE = 512` chars (R1). Over-bound ⇒ truncate to 512 + mark
  (`value_truncated="true"`, `value_len=<orig>`).
- **Secret-safe (FR-010, Security)** — applied BEFORE the bound. Capture-scope already limits the
  captured field to path/pattern keys only (never arbitrary tool input), so the only realistic leak
  vector is a `Grep`/`Glob` `pattern` that IS a secret being searched for. The redaction rule (R10):
  named credential prefixes (`sk-`/`ghp_`/`AKIA`/`xox*-`/JWT) mask regardless of any `/`, while the
  generic high-entropy catch-all fires ONLY on a whole-value-anchored, `/`-free ≥40-char base64-ish
  blob — so opaque/hashed PATH SEGMENTS (e.g. `dist/assets/index-<40hex>.js`) are never masked and a
  read path stays byte-identical to its `git_files` diff path. A masked value is replaced with its
  first 4 + `…` + last 4 chars and flagged `value_redacted="true"`. See R10 for the exact regex and the
  positive/negative tests.

### Removed (Constitution I — no legacy dual path)
The keys-only `[tool_use <name>] inputs: <keys>` branch is **removed for the file-touching tool set**.
Those blocks no longer contribute to the message body summary at all — their value rides on the
dedicated `tool_read` record. Non-file-touching `tool_use` blocks keep their existing keys-only body
summary unchanged.

## Secret redaction rule (R10 — FR-010 / Security)

```python
import re
# Named-prefix secret shapes — these mask REGARDLESS of any '/' in the value
# (a credential is a credential even if it appears inside a path-like string).
_SECRET_PREFIX_RE = re.compile(
    r"(?:sk-[A-Za-z0-9]{16,}"          # OpenAI-style
    r"|ghp_[A-Za-z0-9]{20,}"           # GitHub PAT
    r"|AKIA[0-9A-Z]{16}"               # AWS access key id
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"   # Slack token
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
```

The bound is applied to the (already-masked) value. Masking is deliberately conservative. The named
secret prefixes (`sk-`, `ghp_`, `AKIA`, `xox*-`, JWT) mask regardless of position — a credential is a
credential even if embedded in a path-shaped string. The **generic high-entropy branch is restricted**:
it fires ONLY on a value that (a) contains NO `/` path separator AND (b) is — whole-value-anchored — a
single unbroken ≥40-char base64-ish blob meeting the length floor. Because it is anchored to the entire
value, a path-bearing string such as `dist/assets/index-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.js`
(an opaque/hashed PATH SEGMENT) can never match — the `/` separators and the file extension break the
anchor — so the captured read path and the corresponding `git_files` diff path (which is never masked)
stay **byte-identical**, and the flagship read-vs-diff set comparison cannot spuriously desync. No real
`file_path` or `**/*.py`-style glob produces a match.

## Invariants the tests assert

1. A `Read` block with `input={"file_path": "src/foo.py"}` ⇒ a `tool_read` record whose
   `tool_input_value == "src/foo.py"`, `tool_name == "Read"`, attributable to the record's `role`.
   (US3 scenario 1, SC-003)
2. ONE assistant message carrying TWO `tool_use` blocks (`Read src/foo.py`, `Read src/bar.py`) ⇒ TWO
   `tool_read` records, one per block — they do NOT collide on one key. (Finding 1)
3. `Edit`/`Write` capture `file_path`; `Grep`/`Glob` capture `pattern`[+`path`]. (US3 scenario 3)
4. A value longer than 512 chars ⇒ `tool_input_value` truncated to 512, `value_truncated="true"`,
   `value_len` = original length. (Edge E5, US3 scenario 4)
5. **Secret positive:** `Grep` `pattern="sk-ABCD1234EFGH5678IJKL"` ⇒ `tool_input_value` masked to
   first/last 4 chars, `value_redacted="true"`. (FR-010, Security — R10)
6. **Secret negative:** NEITHER `Read` `file_path="src/services/auth_secret_loader.py"` (a path that
   merely contains the word "secret") NOR a ≥40-char opaque/hashed PATH SEGMENT such as
   `Read` `file_path="dist/assets/index-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.js"` is masked ⇒ in
   both cases `tool_input_value` is the full path VERBATIM, no `value_redacted`. The generic
   high-entropy branch is whole-value-anchored and `/`-free, so a long hashed segment embedded in a
   path never trips it — keeping the captured read path byte-identical to its `git_files` diff path.
   (FR-010 — no false positives on ordinary paths, including bundle/hash paths)
7. Capture never raises out of the hook (hook still swallows all, exits 0). (Hook safety convention)
8. No keys-only `inputs: …` body fragment is produced for the file-touching tool set. (Constitution I)
