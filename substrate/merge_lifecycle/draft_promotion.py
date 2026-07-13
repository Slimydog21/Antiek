"""Draft-before-merge promotion state machine (ask #3d).

The operator's vision (ask #3d): *"...create a draft version with the combined
document before fully merging."* #1837 produces the non-destructive draft
(``EnrichedAssetDraft`` with ``merge_executed=False``, ``draft=True`` always) —
the pure combined-document producer. What #1837 defers — by design — is the
**lifecycle authority**: who may promote a draft to a live merge, when, and
irreversibly. THIS module is that lifecycle state machine.

**The load-bearing invariant: promotion is ONE-WAY and IRREVERSIBLE.** A draft is
reversible (discard it; the parent is untouched). A *promoted* merge is committed
— the parent asset now carries the findings. There is no "un-promote": once the
operator commits, the merge is permanent. This asymmetry is the whole point of
"create a draft BEFORE fully merging" — the draft is the safe rehearsal; the
promotion is the irrevocable commit. Blurring them would destroy the safety the
operator asked for.

**Pure — no I/O, no clock, no dispatch.** A pure state machine over the actions
handed to it. ``DraftLifecycle`` is an immutable value; every transition returns a
NEW lifecycle (never mutates). The caller persists the lifecycle between actions;
this module only computes the next state. The clock is the caller's: promotion
arrives with ``promoted_at`` already resolved.

**States:**

    draft ──mark_for_review──▶ under_review
      │                           │
      ├──promote─────────────────▶ promoted   (TERMINAL — irreversible)
      │ (requires consent +        │
      │  hash match)               ├──promote──▶ promoted (TERMINAL)
      │                            │
      ├──discard──────────────────▶ discarded  (TERMINAL for this version)
      │                            ├──discard──▶ discarded
      │
      └──supersede (by newer draft)─▶ superseded

**Honesty rules (load-bearing):**

  * **Promotion requires explicit operator consent.** ``OperatorConsent`` names
    the operator + a fresh approval; no consent → rejected (never auto-promote).
  * **Promotion pins the exact draft reviewed.** ``DraftRef.content_hash`` must
    match at promote-time — the operator promotes the draft they SAW, not a
    mutated version. A hash mismatch → rejected (the draft changed under review).
  * **Only draft/under_review can be promoted or discarded.** A promoted/
    discarded/superseded lifecycle is terminal — re-acting on it raises (the
    caller must start a fresh draft, not revive a dead one).
  * **Every transition is append-only.** ``history`` records each action with its
    actor + reason; the log is never rewritten. The operator can always audit
    *why* a draft was promoted or discarded.
  * **Supersede records the successor.** A superseded draft names the newer
    ``draft_id`` that replaced it — no orphan drafts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal


class DraftPromotionError(ValueError):
    """A lifecycle action violates a state invariant."""


def _redact_token(token: str) -> str:
    """Hash a consent token for the audit log — proves identity, never leaks the raw secret.

    The append-only history is permanent; storing a raw approval token there would
    make a credential impossible to redact. The hash lets the audit trail prove
    WHICH token authorized a promotion (identity) without persisting the secret.
    This is an unsalted identity hash (proves which-token over the operator token
    space), NOT a password hash — do not 'strengthen' it with a salt; that would
    change the identity-matching contract.
    """
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


DraftState = Literal["draft", "under_review", "promoted", "discarded", "superseded"]


@dataclass(frozen=True)
class DraftRef:
    """A reference to a reviewable draft. Pinned by content_hash at promote-time.

    ``content_hash`` is the exact bytes the operator reviewed. The authority
    layer builds this from #1837's ``EnrichedAssetDraft`` (or any draft
    producer); this module is decoupled from that producer's concrete type.
    """

    draft_id: str
    parent_asset_id: str
    content_hash: str
    draft_version: int = 1


@dataclass(frozen=True)
class OperatorConsent:
    """Explicit operator approval to promote. The lifecycle never invents this."""

    operator_id: str
    consent_token: str
    promoted_at: str  # caller-resolved ISO timestamp; pure module owns no clock


@dataclass(frozen=True)
class LifecycleEvent:
    """One append-only entry in the draft's history log."""

    action: str  # "created" | "marked_for_review" | "promoted" | "discarded" | "superseded"
    actor: str
    at: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class DraftLifecycle:
    """The immutable lifecycle of one draft. Transitions return a new instance."""

    draft: DraftRef
    state: DraftState = "draft"
    history: tuple[LifecycleEvent, ...] = ()
    promoted_by: OperatorConsent | None = None
    superseded_by: str | None = None  # the successor draft_id

    @property
    def is_terminal(self) -> bool:
        return self.state in ("promoted", "discarded", "superseded")

    @property
    def is_promoted(self) -> bool:
        return self.state == "promoted"


def create_lifecycle(draft: DraftRef, *, actor: str, at: str) -> DraftLifecycle:
    """Begin a draft's lifecycle. The draft starts in ``draft`` state."""
    if not draft.draft_id.strip() or not draft.parent_asset_id.strip():
        raise DraftPromotionError("draft_id and parent_asset_id must be non-empty")
    if not draft.content_hash.strip():
        raise DraftPromotionError("content_hash must be non-empty (pins the reviewed draft)")
    if not actor.strip():
        raise DraftPromotionError("actor must be non-empty")
    return DraftLifecycle(
        draft=draft,
        state="draft",
        history=(LifecycleEvent("created", actor, at, "draft lifecycle begun"),),
    )


def mark_for_review(lc: DraftLifecycle, *, actor: str, at: str, reason: str = "") -> DraftLifecycle:
    """Move a draft to ``under_review``. Only a ``draft`` may be marked."""
    if lc.state != "draft":
        raise DraftPromotionError(
            f"cannot mark_for_review a draft in state {lc.state!r}; "
            "only a 'draft' can enter review"
        )
    return DraftLifecycle(
        draft=lc.draft,
        state="under_review",
        history=lc.history + (LifecycleEvent("marked_for_review", actor, at, reason),),
        promoted_by=lc.promoted_by,
        superseded_by=lc.superseded_by,
    )


def promote(
    lc: DraftLifecycle,
    *,
    consent: OperatorConsent,
    content_hash: str,
    at: str,
    reason: str = "",
) -> DraftLifecycle:
    """Promote a draft to a live, IRREVERSIBLE merge. Terminal.

    Requires: the lifecycle is in ``draft`` or ``under_review``; explicit operator
    consent; and ``content_hash`` matches the draft pinned at creation. A mismatch
    means the draft changed under review → rejected (the operator did not approve
    this exact content).
    """
    if lc.is_terminal:
        raise DraftPromotionError(
            f"cannot promote a draft in terminal state {lc.state!r}; "
            "start a fresh draft to merge again"
        )
    if not consent.operator_id.strip() or not consent.consent_token.strip():
        raise DraftPromotionError("promotion requires explicit operator consent (id + token)")
    if content_hash != lc.draft.content_hash:
        raise DraftPromotionError(
            "content_hash mismatch: the draft changed since creation; the operator "
            "did not approve this exact content — re-review the new draft"
        )
    return DraftLifecycle(
        draft=lc.draft,
        state="promoted",
        history=lc.history
        + (LifecycleEvent("promoted", consent.operator_id, at, reason, f"token_hash={_redact_token(consent.consent_token)}"),),
        # promoted_by is part of the persisted lifecycle value, so it carries the
        # same redacted token as history — the raw credential is never retained on
        # any surface a caller might serialize, back up, or dump.
        promoted_by=OperatorConsent(
            operator_id=consent.operator_id,
            consent_token=_redact_token(consent.consent_token),
            promoted_at=consent.promoted_at,
        ),
        superseded_by=lc.superseded_by,
    )


def discard(lc: DraftLifecycle, *, actor: str, at: str, reason: str = "") -> DraftLifecycle:
    """Discard a draft. Terminal for this version (parent untouched).

    Only a ``draft`` or ``under_review`` may be discarded. A promoted/superseded
    draft cannot be discarded (it already reached a different terminal state).
    """
    if lc.is_terminal:
        raise DraftPromotionError(
            f"cannot discard a draft in terminal state {lc.state!r}"
        )
    return DraftLifecycle(
        draft=lc.draft,
        state="discarded",
        history=lc.history + (LifecycleEvent("discarded", actor, at, reason),),
        promoted_by=lc.promoted_by,
        superseded_by=lc.superseded_by,
    )


def supersede(
    lc: DraftLifecycle,
    *,
    successor_draft_id: str,
    actor: str,
    at: str,
    reason: str = "",
) -> DraftLifecycle:
    """Mark this draft superseded by a newer draft. Terminal.

    Only a ``draft`` or ``under_review`` may be superseded (a promoted/discarded
    draft already reached its own terminal outcome). The successor draft_id is
    recorded so no draft is orphaned.
    """
    if lc.is_terminal:
        raise DraftPromotionError(
            f"cannot supersede a draft in terminal state {lc.state!r}"
        )
    if not successor_draft_id.strip():
        raise DraftPromotionError("successor_draft_id must be non-empty (no orphans)")
    return DraftLifecycle(
        draft=lc.draft,
        state="superseded",
        history=lc.history + (LifecycleEvent("superseded", actor, at, reason, f"by={successor_draft_id}"),),
        promoted_by=lc.promoted_by,
        superseded_by=successor_draft_id,
    )


__all__ = [
    "DraftPromotionError",
    "DraftState",
    "DraftRef",
    "OperatorConsent",
    "LifecycleEvent",
    "DraftLifecycle",
    "create_lifecycle",
    "mark_for_review",
    "promote",
    "discard",
    "supersede",
]
