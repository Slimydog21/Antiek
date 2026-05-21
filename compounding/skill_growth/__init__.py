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
    PatchDecision,
    PatchOutcome,
    SkillPatchGate,
    apply_patch_with_gate,
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

__all__ = [
    "AppliedPromptRecord",
    "BridgeOutcome",
    "CompositeKeyFn",
    "GepaToPhase8Bridge",
    "PatchDecision",
    "PatchOutcome",
    "PromptApplyError",
    "SkillPatchGate",
    "apply_patch_with_gate",
    "apply_prompt_variant",
    "bridge_gepa_result_to_phase8",
    "load_active_variant",
    "propose_skill_patch",
]
