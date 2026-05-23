"""Trust Center publication payload assembly.

The `/trust-center` endpoint calls `build_publication()` and returns
its dict to the React frontend. Pure-functional over (registry,
loop_3_status, override_substrate_controls); easy to test without
the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from substrate.dp_shuffler.epsilon_registry import EpsilonRegistry

from .default_registry import DEFAULT_DELETION_SLA_DAYS, default_registry


_DEFAULT_SUBSTRATE_CONTROLS: tuple[str, ...] = (
    "encryption at rest (per-graph keys via KMS)",
    "access logging (append-only)",
    "change management (CI gates on schema)",
    "vulnerability scanning (Dependabot/Snyk)",
    "backup testing (quarterly restore drill)",
    "retrieval-time policy_tag gating (§9.0)",
)


_DEFAULT_COMPLIANCE_FRAMEWORKS: tuple[str, ...] = (
    "GDPR Article 13/14 transparency",
    "CCPA notice + opt-out",
    "engineering-grade differential privacy (ε ≤ 10 hard cap)",
    "SOC 2 Type II — deferred (not required for consumer Phase 1)",
)


@dataclass(frozen=True)
class TrustCenterPayload:
    """The serialised Trust Center surface — what /trust-center returns."""

    differential_privacy_epsilon_budgets: dict[str, float]
    deletion_sla_days: int
    substrate_controls: tuple[str, ...]
    compliance_frameworks: tuple[str, ...]
    loop_3_unlock_status: dict[str, bool]

    def as_dict(self) -> dict:
        return {
            "differential_privacy_epsilon_budgets": dict(
                self.differential_privacy_epsilon_budgets,
            ),
            "deletion_sla_days": self.deletion_sla_days,
            "substrate_controls": list(self.substrate_controls),
            "compliance_frameworks": list(self.compliance_frameworks),
            "loop_3_unlock_status": dict(self.loop_3_unlock_status),
        }


def build_publication(
    *,
    registry: Optional[EpsilonRegistry] = None,
    loop_3_unlock_status: Optional[dict[str, bool]] = None,
    substrate_controls: Optional[tuple[str, ...]] = None,
    compliance_frameworks: Optional[tuple[str, ...]] = None,
    deletion_sla_days: int = DEFAULT_DELETION_SLA_DAYS,
) -> TrustCenterPayload:
    """Assemble the publication payload.

    The registry argument allows tests + admin tools to publish
    against an isolated registry without touching the singleton.
    Loop-3 status flows in from the caller (the API endpoint reads
    it from the persistent checklist store)."""
    reg = registry if registry is not None else default_registry()
    surfaces = {
        s.surface_name: s.epsilon_per_day
        for s in reg.list_surfaces()
    }
    return TrustCenterPayload(
        differential_privacy_epsilon_budgets=surfaces,
        deletion_sla_days=deletion_sla_days,
        substrate_controls=substrate_controls or _DEFAULT_SUBSTRATE_CONTROLS,
        compliance_frameworks=compliance_frameworks or _DEFAULT_COMPLIANCE_FRAMEWORKS,
        loop_3_unlock_status=dict(loop_3_unlock_status or {
            "trajectory_volume": False,
            "sft_readiness": False,
            "validated_reward": False,
            "open_weight_justification": False,
            "eval_headroom": False,
        }),
    )


def list_surface_descriptions(
    *,
    registry: Optional[EpsilonRegistry] = None,
) -> list[dict]:
    """Enumerate registered surfaces in description form for the
    PrivacyDashboard — caller may include per-category descriptions
    that the dashboard renders alongside each ε budget."""
    reg = registry if registry is not None else default_registry()
    return [
        {
            "surface_name": s.surface_name,
            "epsilon_per_day": s.epsilon_per_day,
            "sensitivity": s.sensitivity,
            "description": s.description,
            "opt_in_required": s.opt_in_required,
        }
        for s in reg.list_surfaces()
    ]
