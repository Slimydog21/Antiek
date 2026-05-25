"""Wire authoring trajectories into the Loop-3 harvest (specs/write/ SPR-02 M3+M4).

Two functions, one bright line between them:

- ``harvest_authoring_trajectory`` — the UNGATED storage-harvest. Converts
  an ``AuthoringTrajectory`` into the existing
  ``loop_3.HarvestedTrajectory`` prime-rl shape (reuse, not a parallel
  format) with ``reward = None``. Capture + storage-harvest are always
  available — they do not train.

- ``harvest_authoring_for_training`` — the GATED training-harvest. Calls
  ``unlock_gate.check_unlocked()`` FIRST and refuses (raising
  ``Loop3UnlockRequired`` / ``AuthoringHarvestGated``) unless the operator
  has ratified G8. Even after the gate opens, the reward is still ``None``
  here — it is computed downstream by ``rubric_verifier`` (also gated).
  This function exists so the *training-bound* path is the one that hits
  the gate; storage is never blocked.

Why two functions instead of one gated harvest: the existing
``harvest_trajectory_for_prime_rl`` calls ``check_unlocked()`` at entry,
which is correct for the research-pipeline harvest but would block the
Write workflow from staging its data for the gated downstream. SPR-02's
contract is "capture and harvest-for-storage are unaffected by the gate;
only training is blocked" — hence the split.

A maintainer can confirm there is no pre-gate training path:
``harvest_authoring_trajectory`` imports nothing from ``sft_runner`` /
``rubric_verifier`` and never computes a reward; the only gated entry is
``harvest_authoring_for_training``, which calls ``check_unlocked()`` on
its first line.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

try:
    from ..loop_3.trajectory_harvest import HarvestedTrajectory
    from ..loop_3.unlock_gate import Loop3UnlockRequired, check_unlocked
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.loop_3.trajectory_harvest import HarvestedTrajectory  # type: ignore[no-redef]
    from substrate.loop_3.unlock_gate import (  # type: ignore[no-redef]
        Loop3UnlockRequired,
        check_unlocked,
    )

from .authoring_trajectory import AuthoringTrajectory

# Write-friendly alias for the gate exception — same type, clearer name at
# the Write call sites. A training attempt pre-gate raises this.
AuthoringHarvestGated = Loop3UnlockRequired


def _triples_from_trajectory(traj: AuthoringTrajectory) -> list[dict]:
    """Build prime-rl (observation, action, reward, info) triples from the
    trajectory's SIGNAL steps (reverted edits excluded). reward is always
    ``None`` here — it is the rubric_verifier's job, post-unlock."""
    signal = traj.signal_steps
    triples: list[dict] = []
    for i, step in enumerate(signal):
        prev_payload = signal[i - 1].payload if i > 0 else {}
        info = {
            "event_id": step.event_id,
            "action_type": step.action_type,
            "kind": step.kind,
            "step": i,
        }
        # For edits, surface the before/after directly in info so a
        # downstream reward model can score the edit without re-parsing.
        if step.kind == "edit":
            info["edit_kind"] = step.payload.get("edit_kind")
            info["granularity"] = step.payload.get("granularity")
            info["before_text"] = step.payload.get("before_text")
            info["after_text"] = step.payload.get("after_text")
        triples.append({
            "observation": json.dumps(prev_payload, sort_keys=True),
            "action": json.dumps(step.payload, sort_keys=True),
            "reward": None,  # computed by rubric_verifier (post-unlock)
            "info": info,
        })
    return triples


def harvest_authoring_trajectory(
    traj: AuthoringTrajectory,
) -> HarvestedTrajectory:
    """UNGATED storage-harvest. Stage an authoring trajectory in the
    existing prime-rl shape (reward ``None``). Does NOT train, does NOT
    call the gate — safe to run any time, including pre-unlock."""
    triples = _triples_from_trajectory(traj)
    return HarvestedTrajectory(
        # The HarvestedTrajectory key is named investigation_id; authoring
        # is deliverable-scoped, so the deliverable_id is the trajectory
        # key and the kind is recorded in metadata.
        investigation_id=traj.deliverable_id,
        triples=triples,
        metadata={
            "kind": "authoring",
            "deliverable_id": traj.deliverable_id,
            "source_step_count": len(traj.steps),
            "signal_step_count": len(traj.signal_steps),
            "reverted_excluded": len(traj.steps) - len(traj.signal_steps),
            "reward_status": "none_pre_unlock",
        },
    )


def harvest_authoring_for_training(
    traj: AuthoringTrajectory,
) -> HarvestedTrajectory:
    """GATED training-harvest. Refuses unless ``check_unlocked()`` passes
    (G8). This is the ONLY training-bound entry point; storage-harvest is
    always available via ``harvest_authoring_trajectory``.

    Raises ``AuthoringHarvestGated`` (== ``Loop3UnlockRequired``) with the
    gate reason when the operator has not ratified the unlock. Even when
    unlocked, the reward is still ``None`` — reward computation is the
    rubric_verifier's job, downstream of this call."""
    check_unlocked()  # refuses pre-unlock with the gate reason
    return harvest_authoring_trajectory(traj)
