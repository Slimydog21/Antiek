"""Per-surface ε budget registry. Operator inspects via the Trust
Center (Sprint 22+, master-spec §13.7) and the substrate refuses to
register a surface with ε > MAX_EPSILON.

Per master-spec §16.2 REJECT canon: 'No epsilon > 10 on any DP claim.'
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


MAX_EPSILON: float = 10.0  # §16.2 hard cap; 'pointless in terms of privacy' above this
SENSITIVITY_BUDGETS = {
    "low": 4.0,      # e.g., skill-invocation frequency (Apple emoji parallel)
    "medium": 2.0,   # e.g., source-tier preference signals (Apple HealthKit parallel)
    "high": 1.0,     # any signal whose leakage would identify the user
    "forbidden": 0.0,  # query-content telemetry — DP cannot save this
}


class EpsilonRegistryError(Exception):
    """Raised on attempts to register a surface with invalid ε."""


@dataclass(frozen=True)
class SurfaceConfig:
    """Configuration for one telemetry surface."""

    surface_name: str
    epsilon_per_day: float
    sensitivity: str  # "low" | "medium" | "high" | "forbidden"
    description: str
    opt_in_required: bool


@dataclass
class EpsilonRegistry:
    """The substrate's registry of telemetry surfaces and their
    ε budgets. Operator-visible via the Trust Center; programmatic
    access via `list_surfaces()`."""

    surfaces: dict[str, SurfaceConfig] = field(default_factory=dict)

    def register(self, config: SurfaceConfig) -> None:
        if config.sensitivity == "forbidden":
            if config.epsilon_per_day != 0.0:
                raise EpsilonRegistryError(
                    f"surface {config.surface_name!r} marked 'forbidden' "
                    f"must have epsilon=0 (no collection)"
                )
        else:
            cap = SENSITIVITY_BUDGETS.get(config.sensitivity)
            if cap is None:
                raise EpsilonRegistryError(
                    f"unknown sensitivity {config.sensitivity!r}; "
                    f"valid: {list(SENSITIVITY_BUDGETS)}"
                )
            if config.epsilon_per_day > cap:
                raise EpsilonRegistryError(
                    f"surface {config.surface_name!r} epsilon "
                    f"{config.epsilon_per_day} exceeds the {config.sensitivity} "
                    f"cap of {cap} per master-spec §13.3"
                )
        if config.epsilon_per_day > MAX_EPSILON:
            raise EpsilonRegistryError(
                f"surface {config.surface_name!r} epsilon "
                f"{config.epsilon_per_day} exceeds MAX_EPSILON={MAX_EPSILON} "
                f"per §16.2 REJECT canon"
            )
        self.surfaces[config.surface_name] = config

    def list_surfaces(self) -> list[SurfaceConfig]:
        return list(self.surfaces.values())

    def total_daily_epsilon(self) -> float:
        """Sum of per-surface daily ε. The substrate-wide budget
        the operator publishes via the Trust Center."""
        return sum(s.epsilon_per_day for s in self.surfaces.values())


def register_surface(
    registry: EpsilonRegistry,
    *,
    surface_name: str,
    epsilon_per_day: float,
    sensitivity: str,
    description: str,
    opt_in_required: bool = False,
) -> None:
    """Convenience: register a surface into a registry. Raises
    EpsilonRegistryError on policy violation."""
    registry.register(SurfaceConfig(
        surface_name=surface_name,
        epsilon_per_day=epsilon_per_day,
        sensitivity=sensitivity,
        description=description,
        opt_in_required=opt_in_required,
    ))
