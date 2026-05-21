"""Rubric verifier for the post-unlock Verifiers env (RLM-4 + §11.6).

Per master-spec §14.2: 'until the unlock criteria pass, the env is
observation-only.' Once unlocked, the env needs a scalar reward
function. This module ships the minimum useful scorer:

  - Exact-action match: did the agent's serialized action exactly
    equal the role's actual action in the trajectory?
  - Soft-keys overlap: when exact match fails, score by the fraction
    of top-level keys + values that match.

The scorer is intentionally simple — a Sprint-30 scaffold. Real
production gradient flow will eventually use a learned reward model
(per docs/loop_3_unlock_criteria.md item 3 'validated_reward'), but
that lands AFTER the unlock criteria pass.

The verifier always runs through ``check_unlocked()`` so it CAN'T
fire pre-unlock — failing the env-gate raises
``Loop3UnlockRequired`` per master-spec §14.2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .unlock_gate import check_unlocked


@dataclass(frozen=True)
class RubricScore:
    """One rubric verdict on a single (agent_action, ground_truth) pair."""

    exact_match: bool
    soft_overlap: float  # [0, 1]
    reward: float  # [0, 1]; combined score
    notes: str


def score_against_ground_truth(
    agent_action: str,
    ground_truth_action: str,
) -> RubricScore:
    """Compute a rubric score for one step.

    Args:
      agent_action: serialized JSON the agent emitted (the env passes
        this in via ``step()``).
      ground_truth_action: serialized JSON the role actually emitted
        in the source trajectory (held in the env's trajectory_events).

    Returns:
      A ``RubricScore``. The reward is 1.0 on exact match, otherwise
      the soft-overlap fraction.

    Raises:
      Loop3UnlockRequired: if ANTIEK_LOOP3_UNLOCKED=1 isn't set. The
        gate is the same one the harvest CLI runs through — the
        substrate refuses to compute reward signals pre-unlock.
    """
    check_unlocked()

    if agent_action == ground_truth_action:
        return RubricScore(
            exact_match=True,
            soft_overlap=1.0,
            reward=1.0,
            notes="exact serialized-action match",
        )

    # Soft-overlap: parse both as JSON dicts; score = fraction of
    # ground-truth keys whose value matches the agent's.
    try:
        agent_dict = json.loads(agent_action)
        truth_dict = json.loads(ground_truth_action)
    except (json.JSONDecodeError, TypeError):
        return RubricScore(
            exact_match=False,
            soft_overlap=0.0,
            reward=0.0,
            notes="malformed JSON; no overlap to compute",
        )

    if not isinstance(truth_dict, dict) or not isinstance(agent_dict, dict):
        return RubricScore(
            exact_match=False,
            soft_overlap=0.0,
            reward=0.0,
            notes="non-dict shapes; can't compute key-level overlap",
        )

    if not truth_dict:
        # Empty ground truth — an exact-empty agent dict gets full
        # credit, otherwise zero.
        if not agent_dict:
            return RubricScore(
                exact_match=True, soft_overlap=1.0, reward=1.0,
                notes="both empty dicts",
            )
        return RubricScore(
            exact_match=False, soft_overlap=0.0, reward=0.0,
            notes="ground truth empty; agent emitted extra keys",
        )

    matches = sum(
        1 for k, v in truth_dict.items()
        if k in agent_dict and agent_dict[k] == v
    )
    overlap = matches / len(truth_dict)
    return RubricScore(
        exact_match=False,
        soft_overlap=overlap,
        reward=overlap,
        notes=f"soft-overlap match: {matches}/{len(truth_dict)} truth keys",
    )


__all__ = [
    "RubricScore",
    "score_against_ground_truth",
]
