"""query.py — read-only Loki client an audit body uses to interrogate a feature run.

An audit check receives a :class:`FeatureRunQuery` handle scoped to the run under
audit. It reads that run's recorded telemetry over the Loki HTTP query API
(``GET /loki/api/v1/query_range``) using stdlib ``urllib`` only — never POSTs,
never mutates. Env-configurable endpoint, short timeout, no third-party deps
(mirrors ``emit.py``; no pydantic/pydantic-settings — research R4).

Query surface (contracts/audit-api.md §"Run query surface", data-model.md §3):
  * ``reads_by_role(role)`` — the set of ``tool_input_value`` attrs off the run's
    ``event_type="tool_read"`` records for that ``role``. Read cleanly off the
    structured-metadata attr, never grepped from the free-text body.
  * ``get_all_reads_from_code_review_agent()`` — ``reads_by_role(CODE_REVIEW_ROLE)``.
  * ``all_diffs_for_feature()`` — the union of comma-split ``git_files`` across the
    run's ``event_type="commit"`` records.

Known vs unknown run — the E2/E3 discriminator (contracts §, data-model §3):
  A run is *known* iff at least one record of ANY event_type exists for its
  ``run_id`` (a one-shot ``{run_id="…"}`` probe, ``limit=1``, cached on the
  instance). An *unknown* run (zero records) makes the query methods raise
  :class:`UnknownRunError` — the runner turns that into the distinct ``error``
  verdict, never a silent ``pass``. A *known* run with zero commit records
  legitimately returns the empty set with no raise.
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ENDPOINT = "http://localhost:3100"
TIMEOUT_S = 2.0

# The code-review role string (research R5) — the attribution key on tool_read
# records emitted by the code-review sub-agent.
CODE_REVIEW_ROLE = "code-review"


def _escape_logql(value):
    """Escape a value for safe interpolation inside a LogQL ``"…"`` string literal.

    ``run_id``/``feature`` reach this client from the runner's ``--run-id``/``--feature``
    CLI args — externally-supplied values that land in a LogQL stream selector / label
    filter. Escape backslash then double-quote so a value containing ``"`` or ``\\``
    cannot break out of the quoted literal or alter the query (carry-forward hardening).
    ``role`` is escaped on the same path.
    """
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


class UnknownRunError(Exception):
    """Raised when the queried run has no recorded telemetry (Edge E2).

    Distinguishes an *unknown* run (probe finds zero records) from a *known* run
    with an empty result (Edge E3), so the runner never coerces the former into a
    silent pass.
    """


def _repo_root():
    """Repo root by walking up for ``.specify``/``.git`` (mirrors emit.py)."""
    cur = Path(os.environ.get("FEATURE_REPO_ROOT", os.getcwd())).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".specify").is_dir() or (candidate / ".git").is_dir():
            return candidate
    return cur


def _current_context():
    """Active-run pointer written by run-context.sh; {} if no run is active.

    Same source of truth as ``run-context.sh current`` (mirrors emit.py's
    ``current_context`` — read the file directly rather than shelling out).
    """
    path = _repo_root() / "temp" / "telemetry" / "current.json"
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _feature_from_dir(feature_dir):
    """Feature slug = basename of the bound feature dir (mirrors emit.py)."""
    fd = (feature_dir or "").rstrip("/")
    return os.path.basename(fd) if fd else ""


class FeatureRunQuery:
    """Read-only query handle over one feature run's Loki telemetry."""

    def __init__(self, run_id=None, feature=None, endpoint=None):
        ctx = None
        if run_id is None or feature is None:
            ctx = _current_context()
        self.run_id = run_id if run_id is not None else (ctx.get("run_id") or "")
        if feature is not None:
            self.feature = feature
        else:
            self.feature = _feature_from_dir(ctx.get("feature_dir"))
        self._endpoint = (
            endpoint or os.environ.get("FEATURE_LOKI_HTTP_ENDPOINT") or DEFAULT_ENDPOINT
        ).rstrip("/")
        self._known_cache = None

    # ----------------------------------------------------------------- #
    # Loki HTTP (read-only GET /loki/api/v1/query_range)
    # ----------------------------------------------------------------- #
    def _query_range(self, logql, limit=None):
        params = {"query": logql}
        if limit is not None:
            params["limit"] = str(limit)
        url = f"{self._endpoint}/loki/api/v1/query_range?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            payload = json.load(resp)
        return payload.get("data", {}).get("result", [])

    def _streams(self, logql, limit=None):
        """Return the per-record structured-metadata attr dicts for a query."""
        return [entry.get("stream", {}) for entry in self._query_range(logql, limit)]

    # ----------------------------------------------------------------- #
    # Known/unknown discriminator (E2/E3) — probe once, cached
    # ----------------------------------------------------------------- #
    def _known(self):
        if self._known_cache is None:
            run = _escape_logql(self.run_id)
            records = self._query_range(f'{{run_id="{run}"}}', limit=1)
            self._known_cache = len(records) > 0
        return self._known_cache

    def _require_known(self):
        if not self._known():
            raise UnknownRunError(self.run_id)

    # ----------------------------------------------------------------- #
    # Query surface
    # ----------------------------------------------------------------- #
    def get_all_reads_from_code_review_agent(self):
        return self.reads_by_role(CODE_REVIEW_ROLE)

    def reads_by_role(self, role):
        self._require_known()
        run = _escape_logql(self.run_id)
        logql = f'{{run_id="{run}"}} | event_type="tool_read" | role="{_escape_logql(role)}"'
        return {
            value for stream in self._streams(logql) if (value := stream.get("tool_input_value"))
        }

    def all_diffs_for_feature(self):
        self._require_known()
        run = _escape_logql(self.run_id)
        logql = f'{{run_id="{run}"}} | event_type="commit"'
        diffs = set()
        for stream in self._streams(logql):
            for part in (stream.get("git_files") or "").split(","):
                part = part.strip()
                if part:
                    diffs.add(part)
        return diffs
