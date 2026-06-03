"""Interviewer / consent / economics contracts (Speak).

Three Speak-owned shapes the flywheel's speak→write and speak→read seams
carry:

* **InterviewerResultContract** (Speak interviewer) — the output of one
  compounding interview: the claims it produced and its corroboration status.
  Corroboration is **never "proven"**: a claim is at most *multiply attested*
  (corroboration ≠ truth — an honesty call from the Speak spec).
* **ConsentContract** (Speak SPR-01) — the scoped consent + rights gate that
  ``speak_derived`` content must clear before Read serves it (the other half
  of seam #4; see ``servable.py``). Scoped consent ∈ {record, attribute,
  publish}, verification-before-publish, defamation / right-of-publicity, and
  takedown.
* **EconomicsCellContract** (Speak SPR-07) — one cell of the Speak economics
  matrix: per visibility, the contributor split and the platform margin.
  ``public`` ⇒ algorithmic 70% contributor split + 10% margin; private-
  published ⇒ 50% margin (the master-spec economics matrix; the 70% split is
  always algorithmic for public content, even private invites — the operator's
  own self-correction).

These are PROVISIONAL where Speak has not pinned the field shape (the
interviewer result), COMMITTED where the constant exists (the 70% split is
``CREATOR_REV_SHARE``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

CorroborationStatus = Literal["uncorroborated", "multiply_attested"]
# Scoped consent verbs — consent is per-scope, not all-or-nothing.
ConsentScope = Literal["record", "attribute", "publish"]
Visibility = Literal["public", "private_published"]


class InterviewerResultContract(BaseModel):
    """The output of one interview turn in the compounding interviewer.
    ``corroboration`` tops out at ``multiply_attested`` — the contract has no
    'proven' value, by design."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    interview_id: str
    project_id: str
    contributor_ip_holder_id: str | None = None
    extracted_claim_ids: tuple[str, ...] = ()
    corroboration: CorroborationStatus = "uncorroborated"


class ConsentContract(BaseModel):
    """The consent + rights state a speak-derived document carries. Read's
    servability check (seam #4) serves full text only when ``publish`` is in
    ``scopes``, ``verified_before_publish`` is True, and ``taken_down`` is
    False."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    interview_id: str
    ip_holder_id: str | None = None
    scopes: tuple[ConsentScope, ...] = ()
    verified_before_publish: bool = False
    right_of_publicity_cleared: bool = False
    taken_down: bool = False

    @property
    def publishable(self) -> bool:
        """Deny-by-default: publishable only with explicit publish consent,
        verification, rights clearance, and no takedown."""
        return (
            "publish" in self.scopes
            and self.verified_before_publish
            and self.right_of_publicity_cleared
            and not self.taken_down
        )


class EconomicsCellContract(BaseModel):
    """One cell of the Speak economics matrix. ``contributor_split`` is the
    fraction routed to contributors (0.70 for public); ``platform_margin`` is
    the platform's take (0.10 public, 0.50 private-published)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    visibility: Visibility
    contributor_split: float
    platform_margin: float
