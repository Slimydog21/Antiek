"""Investigation-scoped kwargs for ``dispatch()`` (latency + brain).

Call sites pass ``**dispatch_routing_kwargs(investigation_id)`` so engaged
research uses GLM/TileRT by default and premium brain opts into Opus/pro.
"""

from __future__ import annotations

from typing import Any, Literal

from .brain_choice import read_deliverable_speed_preference, resolve_brain_choice
from .engagement_mode import LatencyMode, resolve_latency_mode

PresenceHint = Literal["engaged", "background"]


def dispatch_routing_kwargs(
    investigation_id: str,
    *,
    presence: PresenceHint | None = "engaged",
    latency_mode: LatencyMode | None = None,
    brain: str | None = None,
    deliverable_speed_preference: bool = False,
) -> dict[str, Any]:
    """Build optional ``dispatch()`` routing keyword arguments."""
    if latency_mode is None:
        if presence == "engaged":
            latency_mode = "interactive"
        elif presence == "background":
            latency_mode = "autonomous"
        else:
            latency_mode = resolve_latency_mode(None, policy=None)

    resolved_brain = resolve_brain_choice(brain, investigation_id=investigation_id)
    speed_pref = deliverable_speed_preference or read_deliverable_speed_preference(
        investigation_id,
    )
    return {
        "latency_mode": latency_mode,
        "brain": resolved_brain,
        "deliverable_speed_preference": speed_pref,
    }