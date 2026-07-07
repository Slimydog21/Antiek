"""Phase 8 accept/reject gate for skill auto-patching (autoresearch Wedge 2).

Sprint 20-21 ship. Per integration_autoresearch.md Wedge 2:
currently Phase 8 (compounding) auto-patches `<domain>/SKILL.md`
unconditionally. A bad investigation can poison the skill; the next
investigation that loads the skill inherits the poison.

This module wraps the patch in a propose → backtest → keep-or-reject
loop. Shadow mode runs the gate but applies the patch anyway (data
collection); enforcing mode applies only on accept.

Per master-spec §14.1 Sprint 20+ shadow-mode → Sprint 21+ enforcing,
**gated on autoresearch Wedge 1 ratifying** (§15.6 Lutke gap).
"""

from .gate import (
    DEFAULT_PHASE8_EPSILON,
    DEFAULT_PHASE8_MINIMUM_COHORT_SIZE,
    PHASE8_EPSILON_ENV,
    PHASE8_MINIMUM_COHORT_SIZE_ENV,
    PHASE8_MODE_ENFORCING,
    PHASE8_MODE_ENV,
    PHASE8_MODE_SHADOW,
    PatchDecision,
    PatchOutcome,
    SkillPatchGate,
    apply_patch_with_gate,
    phase8_gate_from_env,
    propose_skill_patch,
)
from .gepa_bridge import (
    BridgeOutcome,
    CompositeKeyFn,
    GepaToPhase8Bridge,
    bridge_gepa_result_to_phase8,
)
from .prompt_applier import (
    AppliedPromptRecord,
    PromptApplyError,
    apply_prompt_variant,
    load_active_variant,
)
from .replay import (
    CandidateBacktestReplay,
    CandidateBacktestRunner,
    CandidateReplayError,
    CandidateReplayEvaluation,
    CandidateSkillOverlay,
    evaluate_candidate_replay_for_gate,
    materialize_candidate_skill_overlay,
    replay_candidate_backtest_cohort,
)

__all__ = [
    "AppliedPromptRecord",
    "BridgeOutcome",
    "CompositeKeyFn",
    "DEFAULT_PHASE8_EPSILON",
    "DEFAULT_PHASE8_MINIMUM_COHORT_SIZE",
    "GepaToPhase8Bridge",
    "CandidateSkillOverlay",
    "CandidateBacktestReplay",
    "CandidateBacktestRunner",
    "CandidateReplayEvaluation",
    "CandidateReplayError",
    "PHASE8_EPSILON_ENV",
    "PHASE8_MINIMUM_COHORT_SIZE_ENV",
    "PHASE8_MODE_ENFORCING",
    "PHASE8_MODE_ENV",
    "PHASE8_MODE_SHADOW",
    "PatchDecision",
    "PatchOutcome",
    "PromptApplyError",
    "SkillPatchGate",
    "apply_patch_with_gate",
    "apply_prompt_variant",
    "bridge_gepa_result_to_phase8",
    "load_active_variant",
    "evaluate_candidate_replay_for_gate",
    "materialize_candidate_skill_overlay",
    "phase8_gate_from_env",
    "propose_skill_patch",
    "replay_candidate_backtest_cohort",
]
