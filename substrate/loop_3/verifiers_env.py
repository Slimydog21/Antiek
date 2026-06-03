"""Verifiers env scaffold (RLM-4 + master-spec §11.6 Prime Intellect).

Per `integration_prime_intellect.md` item B: verifiers env stub for
parameter_extractor. Substrate-only (training forbidden until
loop_3_unlock_criteria.md passes).

Maps Antiek trajectory events to verifiers env step shape per
tests/test_prime_intellect_compat.py."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerifierObservation:
    """What the agent sees at one step of an env episode."""

    observation: str
    info: dict


@dataclass(frozen=True)
class VerifierReward:
    """Scalar reward returned after the agent's action."""

    value: float
    info: dict = field(default_factory=dict)


@dataclass
class VerifierEnvScaffold:
    """A verifiers-shape env constructed from an Antiek trajectory.

    Per `rlm_integration_spec.md` RLM-4 + integration_prime_intellect.md
    item B: 'verifiers env stub for parameter_extractor. Substrate
    only, training forbidden until unlock.'

    The env replays a trajectory step-by-step; the agent's task is
    to produce the action that matches what the role actually did.
    Reward is rubric-graded once the unlock criteria pass; until
    then the env is observation-only."""

    trajectory_events: list[dict]
    current_step: int = 0

    def reset(self) -> VerifierObservation:
        self.current_step = 0
        return self._current_observation()

    def step(self, action: str) -> tuple[VerifierObservation, VerifierReward, bool]:
        """One env step. Returns (next_observation, reward, done).

        Pre-unlock: reward is always 0.0 with ``info.unlock_gated=True``
        — the env is observation-only per master-spec §14.2.
        Post-unlock: reward comes from the rubric verifier (see
        ``substrate/loop_3/rubric_verifier.py``).
        """
        # Capture ground truth from the trajectory BEFORE the index
        # advances so the rubric scorer compares apples-to-apples.
        ground_truth = ""
        if self.current_step < len(self.trajectory_events):
            current = self.trajectory_events[self.current_step]
            payload = current.get("payload", {}) or {}
            ground_truth = json.dumps(payload, sort_keys=True)

        try:
            from .rubric_verifier import score_against_ground_truth
            from .unlock_gate import Loop3UnlockRequired

            try:
                rubric = score_against_ground_truth(action, ground_truth)
                reward = VerifierReward(
                    value=rubric.reward,
                    info={
                        "unlock_gated": False,
                        "exact_match": rubric.exact_match,
                        "soft_overlap": rubric.soft_overlap,
                        "notes": rubric.notes,
                    },
                )
            except Loop3UnlockRequired:
                reward = VerifierReward(
                    value=0.0, info={"unlock_gated": True},
                )
        except Exception as exc:  # pragma: no cover — defensive
            reward = VerifierReward(
                value=0.0,
                info={"unlock_gated": True, "error": repr(exc)},
            )

        self.current_step += 1
        done = self.current_step >= len(self.trajectory_events)
        return (self._current_observation(), reward, done)

    def _current_observation(self) -> VerifierObservation:
        if self.current_step >= len(self.trajectory_events):
            return VerifierObservation(observation="<episode_done>", info={})
        ev = self.trajectory_events[self.current_step]
        payload = ev.get("payload", {}) or {}
        return VerifierObservation(
            observation=json.dumps(
                {k: v for k, v in payload.items() if k != "action_type"},
                sort_keys=True,
            ),
            info={
                "event_id": ev.get("event_id"),
                "action_type": ev.get("action_type"),
                "role": ev.get("role"),
                "step": self.current_step,
            },
        )


def build_env_from_trajectory(trajectory_events: list[dict]) -> VerifierEnvScaffold:
    """Build a verifiers env from an Antiek trajectory.

    Filters out non-substantive events (dispatch.call telemetry,
    health checks) so the env presents the agent with the actual
    role-driven decision points."""
    substantive = [
        e for e in trajectory_events
        if e.get("action_type") not in {
            "dispatch.call",
            "context_pack.assembled",
            "health.check",
        }
    ]
    return VerifierEnvScaffold(trajectory_events=substantive)
