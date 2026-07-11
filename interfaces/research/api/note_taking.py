"""Backend note-taker bridge (Sprint 4 day 1-2).

Subscribes to the wrestling-loop events the user actually interacts
with (``distillation.delivered``, ``claim.grounding_check_passed``,
``claim.grounding_check_failed``) and runs a periodic synthesis pass:

- Per-investigation event counter. Every ``ANTIEK_NOTE_TAKER_THRESHOLD``
  events (default 5), the next subscribed event triggers a synthesis.
- Reads the recent wrestling slice from the trajectory store.
- Builds a 4-layer context pack and dispatches the ``note_taker``
  role (flash tier per ``substrate.constants.DEFAULT_ROLE_TIER``).
- Parses 0-N ``ExtractedNote`` from the response (the role prompt
  caps it at 5; empty arrays are valid output).
- For each note: emits ``NoteEmergedPayload`` and broadcasts so the
  reading UI sees notes accumulate live.

Failure-mode discipline (mirrors wrestling + grounding):

- Malformed JSON → 0 notes emitted (silent skip; next tick tries again).
- Provider unavailable → 0 notes (no fallback event because there's
  no UX requirement to show "synthesis attempted but failed" — the
  next tick succeeds when the provider returns).
- Same event won't trigger two syntheses (counter resets to 0 on
  threshold-crossing fire).

Defers ``note.compressed_doc_written`` materialization to a later
turn — Sprint 4 day 1-2 ships per-note emergence; the per-document
reminder file lands when the per-doc note count crosses a higher
threshold and the operator wants the artifact.
"""

from __future__ import annotations

import os
import sys

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.note_taker import (  # noqa: E402
    NOTE_TAKER_SYSTEM_PROMPT,
    parse_notes_response,
)
from roles.note_taker.parser import ExtractedNote  # noqa: E402
from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.context_pack import LayerSource, assemble_context_pack  # noqa: E402
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    NoteEmergedPayload,
)
from substrate.twin_notes.store import TwinDocument, TwinNotesStore  # noqa: E402

from .broadcast import EventBroadcaster  # noqa: E402

# Action types the note-taker subscribes to. Tightened to the events
# that ACTUALLY reflect substantive wrestling movement — distillations
# returned, grounding verdicts arrived. Region selections and chat
# requests are too noisy to count toward synthesis cadence.
SUBSCRIBED_ACTION_TYPES: tuple[str, ...] = (
    ActionType.DISTILLATION_DELIVERED.value,
    ActionType.CLAIM_GROUNDING_CHECK_PASSED.value,
    ActionType.CLAIM_GROUNDING_CHECK_FAILED.value,
)

# Default synthesis cadence. The role prompt is tuned for short
# windows (last ~30 events of wrestling history); cadence < 3 would
# trigger before there's anything emergent; cadence > 10 lets the
# operator wrestle for a while without seeing notes accumulate.
DEFAULT_THRESHOLD = 5

# How much wrestling history the synthesis call sees. Reasonable
# trade-off between recall (more context = better notes) and cost
# (more context = more tokens billed at the flash tier).
SYNTHESIS_HISTORY_WINDOW = 30

# Twin-document bridge (recursive note-taker substrate, PR #785).
# Default ON so emerged notes land in the twin store; set
# ANTIEK_TWIN_NOTES_FROM_NOTE_TAKER=0 to disable without code change.
_TWIN_ENV = "ANTIEK_TWIN_NOTES_FROM_NOTE_TAKER"


def _twin_bridge_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = os.environ.get(_TWIN_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def record_emerged_notes_as_twin(
    notes: list[ExtractedNote],
    *,
    parent_asset_id: str,
    store: TwinNotesStore | None = None,
    enabled: bool | None = None,
    source_label: str = "note_taker",
) -> TwinDocument | None:
    """Write emerged notes into the twin-document substrate.

    Heuristic: note text ending with ``?`` is a question; otherwise an
    insight. Empty note lists or disabled bridge return ``None`` without
    touching the store. Never raises into the note-taker hot path —
    callers that need failures should use ``TwinNotesStore`` directly.
    """
    if not _twin_bridge_enabled(enabled):
        return None
    if not notes:
        return None
    parent = (parent_asset_id or "").strip()
    if not parent:
        return None
    insights: list[str] = []
    questions: list[str] = []
    for n in notes:
        text = (n.text or "").strip()
        if not text:
            continue
        if text.endswith("?"):
            questions.append(text)
        else:
            insights.append(text)
    if not insights and not questions:
        return None
    try:
        twin_store = store if store is not None else TwinNotesStore()
        return twin_store.record(
            parent,
            insights=insights,
            questions=questions,
            source_label=source_label,
        )
    except Exception:  # noqa: BLE001 — note-taker must not fail closed on twin I/O
        return None


def _resolve_threshold() -> int:
    """Honor ``ANTIEK_NOTE_TAKER_THRESHOLD`` env override."""
    raw = os.environ.get("ANTIEK_NOTE_TAKER_THRESHOLD")
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        v = int(raw)
        return max(1, v)
    except ValueError:
        return DEFAULT_THRESHOLD


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_recent_events_for_prompt(rows: list[dict]) -> str:
    """Compact one-line-per-event rendering of the recent wrestling
    history. The role prompt needs each event identifiable by its
    event_id (for attribution) and its type (for context). Full
    payloads are too long; we truncate to the discriminating fields."""
    if not rows:
        return "(no recent wrestling history)"
    lines: list[str] = []
    for r in rows:
        eid = r.get("event_id", "?")
        at = r.get("action_type", "?")
        payload = r.get("payload") or {}
        if at == ActionType.DISTILLATION_DELIVERED.value:
            claim_count = len(payload.get("claims") or [])
            rendered = (payload.get("rendered_text") or "")[:160]
            lines.append(
                f"[{eid}] {at}: {claim_count} claims; \"{rendered}\""
            )
        elif at == ActionType.CLAIM_GROUNDING_CHECK_PASSED.value:
            claim = (payload.get("claim_text") or "")[:140]
            conf = payload.get("confidence", "?")
            region = payload.get("located_region_id") or "?"
            lines.append(
                f"[{eid}] {at}: ✓ \"{claim}\" → region={region} conf={conf}"
            )
        elif at == ActionType.CLAIM_GROUNDING_CHECK_FAILED.value:
            claim = (payload.get("claim_text") or "")[:140]
            reason = payload.get("reason") or "?"
            lines.append(
                f"[{eid}] {at}: ⚠ \"{claim}\" → {reason}"
            )
        elif at == ActionType.CLAIM_CHALLENGE_RAISED.value:
            claim = (payload.get("claim_text") or "")[:120]
            q = (payload.get("user_question") or "")[:80]
            lines.append(
                f"[{eid}] {at}: claim=\"{claim}\" challenged=\"{q}\""
            )
        else:
            lines.append(f"[{eid}] {at}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_note_taker_handler(
    broadcaster: EventBroadcaster,
    *,
    threshold: int | None = None,
):
    """Build the async handler closed over a broadcaster. Maintains a
    per-investigation event counter and triggers a synthesis pass
    every ``threshold`` qualifying events. Same handler is registered
    against all three SUBSCRIBED_ACTION_TYPES."""

    resolved_threshold = threshold if threshold is not None else _resolve_threshold()
    counters: dict[str, int] = {}

    async def handle_subscribed_event(event: Event) -> None:
        counter_key = event.investigation_id
        # Skip note-taker's OWN emitted events to avoid feedback loops.
        # (Our note.emerged events aren't in SUBSCRIBED_ACTION_TYPES so
        # this is defense-in-depth; helps if someone later adds note
        # events to the subscription.)
        if (
            event.role == "note_taker"
            or str(event.action_type) == ActionType.NOTE_EMERGED.value
        ):
            return

        counters[counter_key] = counters.get(counter_key, 0) + 1
        if counters[counter_key] < resolved_threshold:
            return

        # Threshold crossed — reset and run synthesis.
        counters[counter_key] = 0
        await _run_note_synthesis(event, broadcaster=broadcaster)

    return handle_subscribed_event


async def _run_note_synthesis(
    triggering_event: Event,
    *,
    broadcaster: EventBroadcaster,
) -> None:
    """One synthesis pass — read recent history, dispatch role,
    emit notes."""

    # 1. Pull recent wrestling history. Walking the whole trajectory
    # is O(events) — fine for hundreds-of-events sessions. We then
    # filter to substantive event types so the role sees signal, not
    # noise from dispatch.call / context_pack.assembled / etc.
    substantive_types = SUBSCRIBED_ACTION_TYPES + (
        ActionType.DISTILLATION_REQUESTED.value,
        ActionType.CLAIM_CHALLENGE_RAISED.value,
    )
    all_rows = trajectory(triggering_event.investigation_id)
    history = [
        r for r in all_rows if r.get("action_type") in substantive_types
    ]
    if not history:
        return
    recent = history[-SYNTHESIS_HISTORY_WINDOW:]
    canonical_event_ids = tuple(
        str(r.get("event_id")).strip()
        for r in recent
        if isinstance(r.get("event_id"), str) and str(r.get("event_id")).strip()
    )
    rendered_history = _format_recent_events_for_prompt(recent)

    # 2. Build context pack. The session layer carries the recent
    # wrestling slice; the role tail (added below) is the synthesis
    # instruction.
    pack = assemble_context_pack(
        role="note_taker",
        investigation_id=triggering_event.investigation_id,
        layers=[
            LayerSource(
                kind="param_version_stamp",
                source="antiek",
                content=f"ANTIEK_PARAM_VERSION={ANTIEK_PARAM_VERSION}",
            ),
            LayerSource(
                kind="phase_metadata",
                source="loop2.note_taking",
                content=(
                    f"loop=wrestling.note_taking investigation="
                    f"{triggering_event.investigation_id} "
                    f"document={triggering_event.document_id or '<none>'} "
                    f"history_events={len(recent)}"
                ),
            ),
            LayerSource(
                kind="session",
                source="recent_wrestling_history",
                content=rendered_history,
            ),
        ],
        parent_event_id=triggering_event.event_id,
    )

    full_prompt = (
        NOTE_TAKER_SYSTEM_PROMPT + "\n\n"
        + pack.text + "\n\n"
        + "Now produce the JSON object."
    )

    # 3. Dispatch the note_taker role. Failure → no notes this round;
    # the next tick retries naturally.
    try:
        result = dispatch(
            full_prompt,
            "note_taker",
            investigation_id=triggering_event.investigation_id,
            context_pack_event_id=pack.event_id,
            parent_event_id=triggering_event.event_id,
        )
        response_text = result.text
        policy_id = f"{result.provider}/{result.model}"
    except (ProviderError, KeyError):
        return

    # 4. Parse + emit + broadcast.
    notes = parse_notes_response(
        response_text,
        canonical_event_ids=canonical_event_ids,
    )
    for note in notes:
        emitted_id = emit_typed(
            triggering_event.investigation_id,
            NoteEmergedPayload(
                note_id=note.note_id,
                note_text=note.text,
                source_event_ids=list(note.source_event_ids),
                # Sprint 5 day 1-2: confidence now persists from the
                # parser into the typed event so the NotesFeed UI can
                # render the badge.
                confidence=note.confidence,  # type: ignore[arg-type]
                node_id=None,  # graph promotion comes when Sprint 6 wires it
            ),
            parent_event_id=triggering_event.event_id,
            role="note_taker",
            document_id=triggering_event.document_id,
            policy_id=policy_id,
        )
        if emitted_id is None:
            continue
        # Find the just-written row to broadcast its typed form.
        for row in reversed(trajectory(triggering_event.investigation_id)):
            if row.get("event_id") == emitted_id:
                try:
                    note_event = Event.model_validate(row)
                    await broadcaster.broadcast(note_event)
                except Exception:  # pragma: no cover — broadcast is best-effort
                    pass
                break

    # Recursive note-taker: also land insights/questions on the twin
    # document for this investigation (or document when present).
    parent_asset = (
        str(triggering_event.document_id).strip()
        if triggering_event.document_id
        else str(triggering_event.investigation_id).strip()
    )
    record_emerged_notes_as_twin(notes, parent_asset_id=parent_asset)


def register_handlers(
    broadcaster: EventBroadcaster,
    *,
    threshold: int | None = None,
) -> None:
    """Wire the note-taker into the broadcaster. Same handler instance
    is registered for all three subscribed action types so a single
    per-investigation counter sees every qualifying event in order."""
    handler = make_note_taker_handler(broadcaster, threshold=threshold)
    for at in SUBSCRIBED_ACTION_TYPES:
        broadcaster.register_handler(at, handler)
