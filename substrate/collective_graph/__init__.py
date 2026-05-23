"""Collective-graph eligibility flags (Sprint 22 Phase 3).

Per master-spec §13.2 + §13.9 + Sprint 22 §2 Phase 3: a
collective-graph document carries two boolean flags derived from
the §13.9 quality gate's outcome:

- `attribution_eligible` — true if the document came through the
  PASS_PUBLIC verdict; eligible to earn 70% creator rev-share when
  cited
- `ad_eligible` — true if the document's owning page passes the
  §5.5 voice-discipline test at render time

Both flags are derivable, not load-bearing storage. This module
computes them deterministically from the document's quality-gate
trail; the API layer just reads.
"""

from .eligibility import (
    CollectiveGraphDocument,
    EligibilityFlags,
    compute_eligibility,
    is_ad_eligible,
    is_attribution_eligible,
)

__all__ = [
    "CollectiveGraphDocument",
    "EligibilityFlags",
    "compute_eligibility",
    "is_ad_eligible",
    "is_attribution_eligible",
]
