"""Bridge DP preference observations → typed
``preference.observation.recorded`` events.

Per master-spec §16.2: each observation emits a typed event carrying
ONLY the noisy randomized output + ε accounting state. The truth
value is discarded inside ``PreferenceLearningStream.record`` before
this bridge is invoked — the contract is enforced at the source.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from substrate.schemas.events import (
    ActionType,
    Event,
    PreferenceObservationRecordedPayload,
)


def make_broadcasting_observation_hook(
    *,
    investigation_id: str,
    broadcast: Callable[[Event], None],
    param_version: str = "substrate-v0",
):
    """Build an ``on_observation`` hook for ``PreferenceLearningStream``
    that emits a typed event per accepted observation.

    ``broadcast`` is the sync-shaped event sink. Async broadcasters
    wrap this at the call site (the in-process ``EventBroadcaster``
    exposes both shapes).
    """

    def _hook(
        category: str,
        noisy_value: bool,
        per_obs_epsilon: float,
        cumulative_epsilon_spent: float,
        category_budget: float,
        user_id: str,
    ) -> None:
        payload = PreferenceObservationRecordedPayload(
            category=category,
            noisy_value=noisy_value,
            per_obs_epsilon=per_obs_epsilon,
            cumulative_epsilon_spent=cumulative_epsilon_spent,
            category_budget=category_budget,
            user_id=user_id,
        )
        evt = Event(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            investigation_id=investigation_id,
            action_type=ActionType.PREFERENCE_OBSERVATION_RECORDED,
            payload=payload,
            param_version=param_version,
            emitted_at=datetime.now(UTC),
        )
        broadcast(evt)

    return _hook
