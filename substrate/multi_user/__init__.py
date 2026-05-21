"""Multi-user substrate (master-spec §13.2 — personal-graph-as-memory).

Sprint 22+ ship. Per master-spec §13.4: multi-user is gated on six
months of operator-graph compounding demonstration. This module
ships the substrate primitives so when that gate opens the architecture
is already designed in (per §13.10: 'cheap to do now, expensive to
do later').

Three graphs, one architecture:
1. Personal graph (per-user) — the user's memory; contains both
   private-facing and public-facing partitions inside.
2. Collective graph (one global aggregation) — built from every
   user's public-facing portions plus pre-onboarded IP holder content.
3. Shared substrate (one global, platform-owned) — skill versions,
   source-tier rules, rubric registry, attribution algorithm versions.

Cross-graph writes flow through the shared substrate via the writer
queue, never directly. Discovered rules propagate; underlying private
content does not (§13.3 de-identification claim).
"""

from .auth import (
    AuthError,
    AuthProvider,
    MockAuthProvider,
    UserClaims,
    decode_token,
)
from .graph_router import (
    GraphRouter,
    PersonalGraphHandle,
    SharedSubstrateHandle,
    resolve_personal_graph,
    resolve_shared_substrate,
)
from .partition import (
    PartitionAssignment,
    PartitionInvariantViolation,
    PartitionKind,
    assign_to_partition,
    move_to_partition,
    validate_partition,
)
from .skill_accumulator import (
    MAX_CUMULATIVE_EPSILON,
    MIN_USERS_FOR_HIGH_CONFIDENCE,
    MIN_USERS_FOR_PROMOTION,
    ContributedDigest,
    PromotionDecision,
    SkillAccumulatorError,
    SkillRuleAccumulator,
)
from .skill_propagation import (
    SkillRuleDigest,
    extract_discovered_rule,
    propagate_to_shared_substrate,
)
from .skill_writer import (
    WriteOutcome,
    drain_promotable_to_substrate,
)

__all__ = [
    "AuthError",
    "AuthProvider",
    "ContributedDigest",
    "GraphRouter",
    "MAX_CUMULATIVE_EPSILON",
    "MIN_USERS_FOR_HIGH_CONFIDENCE",
    "MIN_USERS_FOR_PROMOTION",
    "MockAuthProvider",
    "PartitionAssignment",
    "PartitionInvariantViolation",
    "PartitionKind",
    "PersonalGraphHandle",
    "PromotionDecision",
    "SharedSubstrateHandle",
    "SkillAccumulatorError",
    "SkillRuleAccumulator",
    "SkillRuleDigest",
    "UserClaims",
    "WriteOutcome",
    "assign_to_partition",
    "decode_token",
    "drain_promotable_to_substrate",
    "extract_discovered_rule",
    "move_to_partition",
    "propagate_to_shared_substrate",
    "resolve_personal_graph",
    "resolve_shared_substrate",
    "validate_partition",
]
