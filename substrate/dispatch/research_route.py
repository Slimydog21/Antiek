"""Server-owned research route choices for the cold-question composer.

The browser receives opaque choice IDs and safe display metadata.  Concrete
provider/model values never cross the launch request boundary: launch resolves
the choice again against the closed Cycle 590 tier map.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .research_tier import RESEARCH_TIERS, ResearchTier, resolve_research_tier

RESEARCH_ROUTE_POLICY_VERSION = "research-route.v1"


class ResearchRouteError(ValueError):
    """A client route proof cannot be resolved under the current policy."""


@dataclass(frozen=True)
class ResearchRouteChoice:
    choice_id: str
    tier: ResearchTier
    configuration_fingerprint: str
    display_name: str
    model_policy_label: str
    rationale: str


def prompt_fingerprint(question: str) -> str:
    """Bind a preview to the exact trimmed question without echoing it."""
    return _digest({"question": question.strip()})


def route_choices() -> tuple[ResearchRouteChoice, ...]:
    choices: list[ResearchRouteChoice] = []
    for tier in RESEARCH_TIERS:
        target = resolve_research_tier(tier)
        configuration_fingerprint = _digest(
            {
                "policy": RESEARCH_ROUTE_POLICY_VERSION,
                "tier": tier,
                "provider": target.provider,
                "model": target.model,
                # Bind behavior, not presentation copy. Editing the rationale
                # must not churn otherwise identical route receipts.
                "purpose": "exploratory" if tier == "fast" else "reasoning-heavy",
                "thinking_policy": (
                    "disabled" if tier == "fast" else "enabled"
                ),
            }
        )
        choice_id = "rr_" + _digest(
            {
                "policy": RESEARCH_ROUTE_POLICY_VERSION,
                "tier": tier,
                "configuration": configuration_fingerprint,
            }
        )[:24]
        choices.append(
            ResearchRouteChoice(
                choice_id=choice_id,
                tier=tier,
                configuration_fingerprint=configuration_fingerprint,
                display_name="Fast lens" if tier == "fast" else "Deep lens",
                model_policy_label=(
                    "GLM-5.2 · thinking off"
                    if tier == "fast"
                    else "GLM-5.2 · thinking on"
                ),
                rationale=target.why,
            )
        )
    return tuple(choices)


def resolve_route_choice(
    *,
    choice_id: str,
    question: str,
    supplied_prompt_fingerprint: str,
    policy_version: str,
    configuration_fingerprint: str,
) -> ResearchRouteChoice:
    """Re-resolve a browser proof and reject stale or unknown IDs.

    The proof is deliberately not a one-time capability. Reusing it for the
    same question is safe because launch re-resolves current policy,
    configuration, and readiness before emitting an event.
    """
    if policy_version != RESEARCH_ROUTE_POLICY_VERSION:
        raise ResearchRouteError("research route policy is stale")
    if supplied_prompt_fingerprint != prompt_fingerprint(question):
        raise ResearchRouteError("research route preview does not match this question")
    choice = next((row for row in route_choices() if row.choice_id == choice_id), None)
    if choice is None:
        raise ResearchRouteError("research route choice is unknown or stale")
    if choice.configuration_fingerprint != configuration_fingerprint:
        raise ResearchRouteError("research route configuration is stale")
    return choice


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "RESEARCH_ROUTE_POLICY_VERSION",
    "ResearchRouteChoice",
    "ResearchRouteError",
    "prompt_fingerprint",
    "resolve_route_choice",
    "route_choices",
]
