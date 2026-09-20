"""Midnight Oil pure substrates (ask #13 — unattended autonomous research).

Import-free pure-Python substrates for the unattended execution mode of the
research loop: estimate → approve → plan → launch brief → swarm → receipt →
promote findings into the knowledge substrate. Each module is independently
bar-clean off frozen main; the route layer composes them.
"""

from .contracts import (
    MidnightOilArtifactContract,
    MidnightOilPreflight,
    MidnightOilRequest,
    MidnightOilRolePlan,
    preflight_midnight_oil,
)

__all__ = [
    "MidnightOilArtifactContract",
    "MidnightOilPreflight",
    "MidnightOilRequest",
    "MidnightOilRolePlan",
    "preflight_midnight_oil",
]
