"""Authoring-trajectory reconstruction (specs/write/ SPR-02 M2).

Reconstruct the authoring sequence — block-selection → draft → edits →
final — for one deliverable, from the immutable event log. Scoped per
deliverable, stitched across editing sessions (and across investigation
log files), with reverted edits excluded from the training signal.

The classification is intentionally a small, explicit table
(``_STEP_KIND``) so it is legible and extensible — SPR-06 will add a
draft-generation step kind when ``creative_writer`` is wired. Every step
carries its source ``event_id`` so reconstruction is deduplicated and
auditable.

Determinism: events arrive ordered by ``(emitted_at, event_id)`` from
``event_log.trajectory``; reconstruction preserves that order. The same
log always yields the same trajectory.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

try:
    from ..event_log import trajectory as _read_trajectory
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import trajectory as _read_trajectory  # type: ignore[no-redef]


# action_type → coarse authoring step kind. Block composition (SPR-01),
# edits (SPR-02), and operator prose-promotion are the authoring signals
# that carry a deliverable_id. SPR-06 adds 'draft' when generation lands.
_STEP_KIND: dict[str, str] = {
    "outline_block.placed": "block_selection",
    "outline_block.moved": "block_move",
    "outline_block.removed": "block_removal",
    "edit.captured": "edit",
    "claim.asserted_by_operator": "promote",
}


@dataclass(frozen=True)
class AuthoringStep:
    """One step in an authoring trajectory."""

    kind: str
    action_type: str
    event_id: str | None
    emitted_at: str | None
    payload: dict
    reverted: bool = False


@dataclass
class AuthoringTrajectory:
    """The reconstructed authoring sequence for one deliverable."""

    deliverable_id: str
    steps: list[AuthoringStep] = field(default_factory=list)

    @property
    def signal_steps(self) -> list[AuthoringStep]:
        """Steps usable as training signal — reverted edits removed (a
        revert is not an endorsement; rigor #3)."""
        return [s for s in self.steps if not s.reverted]

    @property
    def edit_steps(self) -> list[AuthoringStep]:
        return [s for s in self.steps if s.kind == "edit"]


def _payload_deliverable_id(payload: dict) -> str | None:
    return payload.get("deliverable_id") if isinstance(payload, dict) else None


def reconstruct_from_events(
    events: list[dict], deliverable_id: str,
) -> AuthoringTrajectory:
    """Reconstruct the trajectory for ``deliverable_id`` from a pre-read
    list of event dicts. Pure + deterministic; deduplicates by event_id.

    Events that don't belong to this deliverable, or that aren't authoring
    steps, are skipped. Reverted edits are kept in ``steps`` (the *chain*
    of edits is the signal) but flagged so ``signal_steps`` can drop them."""
    seen: set[str] = set()
    steps: list[AuthoringStep] = []
    for ev in events:
        action_type = ev.get("action_type", "")
        kind = _STEP_KIND.get(action_type)
        if kind is None:
            continue
        payload = ev.get("payload", {}) or {}
        if _payload_deliverable_id(payload) != deliverable_id:
            continue
        eid = ev.get("event_id")
        if eid is not None and eid in seen:
            continue  # dedupe — never double-count a step
        if eid is not None:
            seen.add(eid)
        steps.append(AuthoringStep(
            kind=kind,
            action_type=action_type,
            event_id=eid,
            emitted_at=ev.get("emitted_at"),
            payload=payload,
            reverted=bool(payload.get("reverted", False)),
        ))
    # Stable order across stitched sessions.
    steps.sort(key=lambda s: (s.emitted_at or "", s.event_id or ""))
    return AuthoringTrajectory(deliverable_id=deliverable_id, steps=steps)


def load_authoring_trajectory(
    deliverable_id: str,
    *,
    investigation_ids: list[str] | None = None,
    events_dir: str | None = None,
) -> AuthoringTrajectory:
    """Read the event log and reconstruct ``deliverable_id``'s trajectory.

    Authoring events default to ``investigation_id='__operator__'`` (the
    single-operator constant), so the common case reads one log file.
    Multi-session work that spanned other investigations passes their ids
    in ``investigation_ids`` — the events stitch by deliverable_id."""
    ids = investigation_ids or ["__operator__"]
    events: list[dict] = []
    for inv in ids:
        events.extend(_read_trajectory(inv, events_dir=events_dir))
    return reconstruct_from_events(events, deliverable_id)
