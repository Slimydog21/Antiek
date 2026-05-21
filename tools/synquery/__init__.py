"""Synquery expert-network API client (Sprint 21, master-spec §11.6).

GLG-style AI-native expert network. Per master-spec §14.1 Sprint 21
slot: 'Synquery API client (deferred from Sprint 18); only after
creation surface PMF signal that warrants paying for expert calls.'

Per master-spec §11.6 integration shape:
- Operator's substrate identifies 'you need to interview someone with
  expertise in X' via the open-question chase
- Operator clicks 'find an expert' → Synquery API call
- Synquery returns matching experts + booking flow
- Interview happens through Synquery's platform
- Transcript returned to Antiek as a new ingested source

Sprint 21 ships the API client + adapter behind a feature flag
(ANTIEK_SYNQUERY_ENABLED) so the surface is wired without burning
the operator's Synquery credits during dev iteration.
"""

from .adapter import SynqueryAdapter, SynqueryRequest, SynqueryResponse
from .client import (
    MockSynqueryClient,
    SynqueryAPIError,
    SynqueryClient,
    SynqueryExpert,
    SynqueryInterview,
)

__all__ = [
    "MockSynqueryClient",
    "SynqueryAdapter",
    "SynqueryAPIError",
    "SynqueryClient",
    "SynqueryExpert",
    "SynqueryInterview",
    "SynqueryRequest",
    "SynqueryResponse",
]
