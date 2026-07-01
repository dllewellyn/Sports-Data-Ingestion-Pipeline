"""Provider-agnostic conform layer.

Home of the single identity authority (`resolve.py`) that every soccer provider's
conform and the ESPN dbt path share, so identical inputs compute identical ids.
The Matchbook conform engine now lives here too (`matchbook.py` + `matchbook_*`
helpers), rewired onto the shared resolver.
"""

from .matchbook import ConformReport, compute_canonical_match_id, run_conform
from .matchbook_event_name import parse_event_name
from .matchbook_overrides import load_overrides
from .matchbook_scoring import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE

__all__ = [
    "run_conform",
    "ConformReport",
    "compute_canonical_match_id",
    "load_overrides",
    "parse_event_name",
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
]
