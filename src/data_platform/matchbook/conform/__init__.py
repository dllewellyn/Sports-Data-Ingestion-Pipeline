"""Matchbook conform package — public surface."""

from .engine import ConformReport, compute_canonical_match_id, run_conform
from .overrides import load_overrides
from .reversal import parse_event_name
from .scoring import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE

__all__ = [
    "run_conform",
    "ConformReport",
    "compute_canonical_match_id",
    "load_overrides",
    "parse_event_name",
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
]
