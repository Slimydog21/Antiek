"""Cross-graph network effects (Sprint 25+, master-spec §13.9 + §11.6).

Federation scaffold + 'ask an expert' flow connecting users across
graphs. Per master-spec §13.9 cross-user network effects:

- User A interviews their colleague C; the transcript becomes a
  public document in A's graph.
- User B is researching the same topic; B's investigations can
  cite C's transcript via cross-graph search.
- The substrate's 'ask an expert' flow surfaces user A as a
  potential interview subject for B (with A's opt-in).

Sprint 25+ vision. Depends on:
- Multi-user accounts shipped (Sprint 22+, substrate/multi_user/)
- Two-graph architecture proven (master-spec §13.2)
- Creator population active and earning meaningful rev-share
- DeepBlu interview surface mature enough for cross-user interview
  requests (master-spec §11)
"""

from .ask_expert import (
    AskExpertRequest,
    AskExpertResponse,
    ExpertCandidate,
    OptInRequired,
    find_user_experts,
    request_user_interview,
)
from .federation import (
    CrossGraphReference,
    FederationConfig,
    federate_search,
    record_cross_graph_citation,
)

__all__ = [
    "AskExpertRequest",
    "AskExpertResponse",
    "CrossGraphReference",
    "ExpertCandidate",
    "FederationConfig",
    "OptInRequired",
    "federate_search",
    "find_user_experts",
    "record_cross_graph_citation",
    "request_user_interview",
]
