"""Challenger role types — Challenge dataclass + composer.

A ``Challenge`` is the typed input the bridge needs to build a
``ClaimChallengeRaisedPayload``. The composer ``compose_challenge``
fills in optional fields with sensible defaults so the UI button and
the future autonomous challenger handler use the same shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .prompt import DEFAULT_CHALLENGE_PROMPT


@dataclass(frozen=True)
class Challenge:
    """Typed input for raising a challenge against a claim.

    Maps 1:1 onto ``ClaimChallengeRaisedPayload``:

    - ``challenged_claim_id``: claim_id from a prior
      DistillationDelivered. None means the user is challenging a
      claim that isn't in the system yet (verbatim claim_text only).
    - ``claim_text``: verbatim claim being challenged.
    - ``anchor_region_id``: optional region the claim was sourced
      from (one of the claim's attribution_region_ids if any).
    - ``user_question``: the prompt the grounder sees. Default is
      DEFAULT_CHALLENGE_PROMPT.
    """

    claim_text: str
    challenged_claim_id: Optional[str] = None
    anchor_region_id: Optional[str] = None
    user_question: str = DEFAULT_CHALLENGE_PROMPT


def compose_challenge(
    *,
    claim_text: str,
    claim_id: Optional[str] = None,
    anchor_region_id: Optional[str] = None,
    user_question: Optional[str] = None,
) -> Challenge:
    """Build a ``Challenge`` with the default user_question when none
    is provided. Used by the UI button (user clicks → bridge posts)
    and by the future autonomous challenger handler (LLM picks targets
    → bridge posts). Centralizes the default so both paths agree."""
    if not claim_text or not claim_text.strip():
        raise ValueError("claim_text is required")
    return Challenge(
        claim_text=claim_text.strip(),
        challenged_claim_id=claim_id,
        anchor_region_id=anchor_region_id,
        user_question=(user_question or DEFAULT_CHALLENGE_PROMPT).strip(),
    )
