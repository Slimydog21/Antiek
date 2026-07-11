"""Finalize gate for provisional draft-merge → parent mutation authorization.

Operator vision: after reviewing a provisional draft (parent HTML + twins),
an explicit acceptance is required before any parent-mutating merge path may
run. This module is pure authorization only — it never writes the parent
store, never calls network, and never performs the merge itself.

Rules:
* ``provisional`` must be True (non-provisional drafts are not finalize-gated
  drafts — reject as not a draft-merge artifact).
* ``operator_accepted`` must be True (explicit human/agent accept flag).
* ``draft_id`` and ``parent_asset_id`` must be non-empty.
* Cross-parent twin lists are rejected when provided and mixed.

Callers that mutate parent content must call ``authorize_finalize`` first and
only proceed when ``authorized`` is True.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


class FinalizeGateError(ValueError):
    """Invalid finalize request (malformed, not provisional, or not accepted)."""


@dataclass(frozen=True)
class FinalizeAuthorization:
    authorized: bool
    draft_id: str
    parent_asset_id: str
    reason: str
    notes: list[str] = field(default_factory=list)


def authorize_finalize(
    *,
    draft_id: str,
    parent_asset_id: str,
    provisional: bool,
    operator_accepted: bool,
    twin_ids: Sequence[str] | None = None,
    twin_parent_ids: Sequence[str] | None = None,
) -> FinalizeAuthorization:
    """Return whether a provisional draft may proceed to parent mutation.

    Raises :class:`FinalizeGateError` for malformed inputs (empty ids).
    Returns ``authorized=False`` with an honest reason when policy denies.
    """
    did = (draft_id or "").strip()
    parent = (parent_asset_id or "").strip()
    if not did:
        raise FinalizeGateError("draft_id must be non-empty")
    if not parent:
        raise FinalizeGateError("parent_asset_id must be non-empty")

    notes: list[str] = []

    if provisional is not True:
        return FinalizeAuthorization(
            authorized=False,
            draft_id=did,
            parent_asset_id=parent,
            reason="not_provisional_draft",
            notes=[
                "finalize gate only applies to provisional draft-merge artifacts",
                "non-provisional payloads must not be treated as draft-merge finalization",
            ],
        )

    if operator_accepted is not True:
        return FinalizeAuthorization(
            authorized=False,
            draft_id=did,
            parent_asset_id=parent,
            reason="operator_accept_required",
            notes=["explicit operator_accepted=True required before parent mutation"],
        )

    if twin_parent_ids is not None:
        parents = {str(p).strip() for p in twin_parent_ids if str(p).strip()}
        if parents and parents != {parent}:
            return FinalizeAuthorization(
                authorized=False,
                draft_id=did,
                parent_asset_id=parent,
                reason="cross_parent_twins",
                notes=[
                    "finalize requires all twins to share parent_asset_id=" + repr(parent),
                    "got parents=" + ", ".join(sorted(parents)),
                ],
            )

    if twin_ids is not None and len(list(twin_ids)) == 0:
        return FinalizeAuthorization(
            authorized=False,
            draft_id=did,
            parent_asset_id=parent,
            reason="no_twins",
            notes=["finalize requires at least one twin when twin_ids is provided"],
        )

    notes.append("authorized: provisional draft accepted by operator")
    notes.append("caller may proceed to parent-mutating merge (not performed here)")
    return FinalizeAuthorization(
        authorized=True,
        draft_id=did,
        parent_asset_id=parent,
        reason="ok",
        notes=notes,
    )


__all__ = [
    "FinalizeAuthorization",
    "FinalizeGateError",
    "authorize_finalize",
]
