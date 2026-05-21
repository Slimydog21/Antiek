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
    FederatedOutboundCitation,
    FederationConfig,
    FederationGateError,
    OutboundEmittedHook,
    federate_outbound_citation,
    federate_search,
    record_cross_graph_citation,
)
from .inbound import (
    DEFAULT_NONCE_RETENTION_SECONDS,
    InboundCitationOutcome,
    InboundOutcomeHook,
    InboundRejection,
    NonceLedger,
    accept_inbound_citation,
    ensure_nonce_table,
    load_active_nonces,
    prune_expired_nonces,
    remember_nonce_persistent,
)
from .partner_identity import (
    DEFAULT_CLOCK_SKEW_SECONDS,
    DEFAULT_TOKEN_TTL_SECONDS,
    PartnerIdentityError,
    PartnerRegistry,
    PartnerSubstrate,
    PartnerTrustState,
    ensure_table,
    generate_partner_token,
    generate_shared_secret,
    is_partner_trusted,
    load_registry,
    register_partner,
    revoke_partner,
    save_record,
    trust_partner,
    verify_partner_token,
)

__all__ = [
    "AskExpertRequest",
    "AskExpertResponse",
    "CrossGraphReference",
    "DEFAULT_CLOCK_SKEW_SECONDS",
    "DEFAULT_NONCE_RETENTION_SECONDS",
    "DEFAULT_TOKEN_TTL_SECONDS",
    "ExpertCandidate",
    "FederatedOutboundCitation",
    "FederationConfig",
    "FederationGateError",
    "InboundCitationOutcome",
    "InboundOutcomeHook",
    "InboundRejection",
    "NonceLedger",
    "OptInRequired",
    "OutboundEmittedHook",
    "PartnerIdentityError",
    "PartnerRegistry",
    "PartnerSubstrate",
    "PartnerTrustState",
    "accept_inbound_citation",
    "ensure_nonce_table",
    "ensure_table",
    "federate_outbound_citation",
    "federate_search",
    "find_user_experts",
    "generate_partner_token",
    "generate_shared_secret",
    "is_partner_trusted",
    "load_active_nonces",
    "load_registry",
    "prune_expired_nonces",
    "record_cross_graph_citation",
    "register_partner",
    "remember_nonce_persistent",
    "request_user_interview",
    "revoke_partner",
    "save_record",
    "trust_partner",
    "verify_partner_token",
]
