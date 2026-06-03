"""Trajectory harvest CLI scaffold (RLM-5, master-spec §14.2 RLM track).

Per `rlm_integration_spec.md` RLM-5: 'trajectory harvest CLI for
`prime-rl`'. Harvests Antiek trajectories into the prime-rl input
format. Loop-3-gated; runs only after unlock."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .unlock_gate import check_unlocked


@dataclass(frozen=True)
class HarvestedTrajectory:
    """One trajectory in prime-rl format: a list of (observation,
    action, reward) triples + metadata."""

    investigation_id: str
    triples: list[dict]
    metadata: dict = field(default_factory=dict)


def harvest_trajectory_for_prime_rl(
    *,
    trajectory_events: list[dict],
    investigation_id: str,
    role_filter: str | None = None,
) -> HarvestedTrajectory:
    """Convert Antiek trajectory events into prime-rl format.

    Each (observation, action, reward) triple is one role-driven
    decision. role_filter scopes to a single role
    (e.g. 'parameter_extractor') so a harvest targets one specific
    eval/training set."""
    check_unlocked()

    triples: list[dict] = []
    for i, ev in enumerate(trajectory_events):
        action_type = ev.get("action_type", "")
        role = ev.get("role")
        if role_filter and role != role_filter:
            continue
        if not (action_type.endswith(".delivered") or action_type.endswith(".completed")):
            continue
        payload = ev.get("payload", {}) or {}
        # The "observation" is the prior event's context; "action" is
        # the role's output. For a scaffold, we use the payload as the
        # action shape and reserve "observation" for the prior event's
        # payload.
        prev_payload = (trajectory_events[i - 1].get("payload", {}) or {}) if i > 0 else {}
        triples.append({
            "observation": json.dumps(prev_payload, sort_keys=True),
            "action": json.dumps(payload, sort_keys=True),
            "reward": None,  # computed by rubric verifier (post-unlock)
            "info": {
                "event_id": ev.get("event_id"),
                "action_type": action_type,
                "role": role,
                "step": i,
            },
        })

    return HarvestedTrajectory(
        investigation_id=investigation_id,
        triples=triples,
        metadata={
            "role_filter": role_filter,
            "source_event_count": len(trajectory_events),
            "harvested_triple_count": len(triples),
        },
    )
