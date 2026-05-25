"""Speak SPR-07 — the economics matrix + publishing modes.

A policy layer that resolves a project's MODE (two dimensions) to the
inference margin, the revenue-split rule, and the gating. It is policy
over existing plumbing (SPR-06 split, SPR-01 gate, dispatch billing) —
NOT new payment infrastructure.

Two dimensions:
    invitation  ∈ {private, public}        (public is gated on G7)
    publishing  ∈ {never_published, public}

The four cells:
    private-invite / never-published  → 50% margin · no split · creator carries cost
    private-invite / public           → 10% margin · ALGORITHMIC 70% SPLIT (binding) · publish consent
    public-invite  / public           → 10% margin · algorithmic split · publish consent
    public-invite  / never-published  → 50% margin · no split · creator carries cost

The binding rule, and it OVERRIDES creator preference (rigor #1): if a
project will be PUBLIC, the algorithmic 70% contributor split governs —
even for private invitations. A creator does not control contributor
economics on a public, ad-monetised work. There is deliberately NO
creator-override knob; ``resolve_policy`` cannot be told "public but no
split". The margin numbers are POLICY (the matrix), documented here,
not derived.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from .consent import ConsentScope, has_consent
from .project import interview_ids, set_publish_intent

# Margin policy — POLICY numbers from the economics matrix (master-spec
# §13.5 / the Speak spec), not derived. A public work pays a thin 10%
# inference margin because ad revenue offsets it; a non-public work pays
# the standard 50% margin the creator carries.
MARGIN_PUBLIC = Decimal("0.10")
MARGIN_PRIVATE_PUBLISHED = Decimal("0.50")


class InvitationMode(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class PublishingMode(str, enum.Enum):
    NEVER_PUBLISHED = "never_published"
    PUBLIC = "public"


@dataclass(frozen=True)
class EconomicsPolicy:
    invitation: str
    publishing: str
    inference_margin: Decimal
    split_applies: bool          # the algorithmic 70% contributor split
    creator_carries_cost: bool   # creator pays inference (+ physical + prompt)
    requires_publish_consent: bool

    @property
    def cell(self) -> str:
        return f"{self.invitation}-invite / {self.publishing}"


def resolve_policy(invitation: str, publishing: str) -> EconomicsPolicy:
    """Resolve the (invitation × publishing) mode to its economics. The
    binding rule lives here and ONLY here: ``split_applies`` is exactly
    ``publishing == public`` — there is no override parameter."""
    invitation = InvitationMode(invitation).value
    publishing = PublishingMode(publishing).value
    if publishing == PublishingMode.PUBLIC.value:
        # Public ⇒ algorithmic split ALWAYS (even private invitations).
        return EconomicsPolicy(
            invitation=invitation, publishing=publishing,
            inference_margin=MARGIN_PUBLIC,
            split_applies=True,            # binding — not configurable
            creator_carries_cost=False,    # ad revenue offsets inference
            requires_publish_consent=True,
        )
    # Never-published ⇒ no ad revenue ⇒ creator carries cost, no split.
    return EconomicsPolicy(
        invitation=invitation, publishing=publishing,
        inference_margin=MARGIN_PRIVATE_PUBLISHED,
        split_applies=False,
        creator_carries_cost=True,
        requires_publish_consent=False,
    )


def _publishing_from_intent(publish_intent: str) -> str:
    return (PublishingMode.PUBLIC.value
            if publish_intent == "will_be_public"
            else PublishingMode.NEVER_PUBLISHED.value)


def policy_for_project(con: Any, project_id: str) -> EconomicsPolicy:
    """Resolve a project's economics from its ``speak_projects`` row."""
    row = con.execute(
        "SELECT invitation_mode, publish_intent FROM speak_projects WHERE project_id = ?",
        [project_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"speak project {project_id!r} not found")
    invitation_mode, publish_intent = row[0], row[1]
    return resolve_policy(invitation_mode, _publishing_from_intent(publish_intent))


# ---------------------------------------------------------------------------
# M2 — margin billing (selection only; dispatch does the billing)
# ---------------------------------------------------------------------------


def billed_inference_cost(base_cost_usd: Decimal, policy: EconomicsPolicy) -> Decimal:
    """Apply the mode's inference margin to a base dispatch cost. The
    actual billing happens in ``substrate/dispatch/router.py``; this
    selects the margin per the matrix so the dispatch path can bill it."""
    return (Decimal(base_cost_usd) * (Decimal("1") + policy.inference_margin)).quantize(
        Decimal("0.000001")
    )


# ---------------------------------------------------------------------------
# M4 — cost-carry for private-never-published
# ---------------------------------------------------------------------------


def creator_cost(
    policy: EconomicsPolicy,
    *,
    base_inference_cost_usd: Decimal,
    prompt_inference_cost_usd: Decimal = Decimal("0"),
    physical_cost_usd: Decimal = Decimal("0"),
) -> Decimal:
    """What the CREATOR carries. For a private-never-published project
    that's the margined inference + the inference cost of prompting the
    book + (later) the physical-book cost. For a public project the ad
    revenue offsets inference, so the creator carries nothing here."""
    if not policy.creator_carries_cost:
        return Decimal("0")
    inference = billed_inference_cost(base_inference_cost_usd, policy)
    return (inference + Decimal(prompt_inference_cost_usd) + Decimal(physical_cost_usd)).quantize(
        Decimal("0.000001")
    )


# ---------------------------------------------------------------------------
# M5 — mode transitions (flip + consent re-check)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlipResult:
    policy: EconomicsPolicy
    # Contributors lacking publish-scope consent — their content must be
    # EXCLUDED from the public work, not silently kept. Publishing stays
    # blocked (SPR-01 publish gate) until this is empty or they're excluded.
    contributors_without_publish_consent: tuple[str, ...]


def flip_to_public(con: Any, *, project_id: str) -> FlipResult:
    """Flip a project private-never-published → public: switch economics
    to the 10%-margin + algorithmic-split policy and RE-CHECK consent.

    The split applies FORWARD from the flip (a never-published project
    has no prior ad revenue, so there's nothing retroactive to re-split;
    this forward-only policy is documented + tested). Returns the
    contributors who have NOT granted publish-scope consent — their
    content is excluded from the public work; publishing stays blocked
    by the SPR-01 gate until consent is present or they're excluded."""
    set_publish_intent(con, project_id=project_id, publish_intent="will_be_public")
    missing: list[str] = []
    for iv in interview_ids(con, project_id):
        if not has_consent(con, iv, ConsentScope.PUBLISH):
            missing.append(iv)
    return FlipResult(
        policy=policy_for_project(con, project_id),
        contributors_without_publish_consent=tuple(missing),
    )


def publish_consent_complete(con: Any, project_id: str) -> bool:
    """Whether every interviewee in the project has granted publish-scope
    consent — the condition the public-publish gate needs satisfied (or
    the non-consenting interviewees explicitly excluded)."""
    return all(
        has_consent(con, iv, ConsentScope.PUBLISH)
        for iv in interview_ids(con, project_id)
    )
