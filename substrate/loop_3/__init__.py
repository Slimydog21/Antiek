"""Loop 3 — RL training substrate scaffolds (master-spec §14.2 parallel track).

ALL work in this module is **strictly gated** by the 5 criteria in
`docs/loop_3_unlock_criteria.md`:
1. Trajectory volume
2. SFT readiness
3. Validated reward
4. Open-weight justification
5. Eval headroom

Sessions refuse to run without operator-set ANTIEK_LOOP3_UNLOCKED=1
in env — explicit affirmative ratification per the same discipline as
RLM-1 (master-spec §15.7).

When unlocked, `integration_prime_intellect.md` governs whether to use
`prime rl run` (DEFERRED until unlock) or the local SFT loop pattern
from `integration_autoresearch.md` Wedge 4. The two are compared at
unlock time, not before.
"""

from .unlock_gate import (
    Loop3UnlockCriterion,
    Loop3UnlockRequired,
    UnlockChecklist,
    check_unlocked,
)
from .sft_runner import (
    SFTConfig,
    SFTIteration,
    SFTRunner,
    run_sft_iteration,
)
from .verifiers_env import (
    VerifierEnvScaffold,
    VerifierObservation,
    VerifierReward,
    build_env_from_trajectory,
)
from .trajectory_harvest import (
    HarvestedTrajectory,
    harvest_trajectory_for_prime_rl,
)

__all__ = [
    "HarvestedTrajectory",
    "Loop3UnlockCriterion",
    "Loop3UnlockRequired",
    "SFTConfig",
    "SFTIteration",
    "SFTRunner",
    "UnlockChecklist",
    "VerifierEnvScaffold",
    "VerifierObservation",
    "VerifierReward",
    "build_env_from_trajectory",
    "check_unlocked",
    "harvest_trajectory_for_prime_rl",
    "run_sft_iteration",
]
