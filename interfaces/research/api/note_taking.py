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

import asyncio
import contextlib
import os
import sys
import threading
from typing import Any

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.note_taker import (  # noqa: E402
    NOTE_TAKER_SYSTEM_PROMPT,
    DurableNoteTakerReplay,
    parse_notes_response,
)
from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.context_pack import LayerSource, assemble_context_pack  # noqa: E402
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, iter_physical_events, trajectory  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    NoteEmergedPayload,
)

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


def _resolve_threshold() -> int:
    """Honor ``ANTIEK_NOTE_TAKER_THRESHOLD`` env override."""
    raw = os.environ.get("ANTIEK_NOTE_TAKER_THRESHOLD")
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        value = int(raw)
        return max(1, value)
    except ValueError:
        return DEFAULT_THRESHOLD


def _default_replay_service(
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    threshold: int | None = None,
) -> DurableNoteTakerReplay:
    def durable_dispatch(
        request: dict[str, Any], *, idempotency_key: str
    ) -> Any:
        del idempotency_key
        return dispatch(
            request["prompt"],
            "note_taker",
            investigation_id=request["investigation_id"],
            parent_event_id=request["source_event_ids"][-1],
        )

    return DurableNoteTakerReplay(
        durable_dispatch,
        db_path=db_path or default_db_path(),
        events_dir=events_dir,
        threshold=threshold or _resolve_threshold(),
    )


def start_replay_recovery(
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    stop_event: threading.Event | None = None,
    poll_interval_s: float = 0.5,
) -> threading.Thread:
    """Continuously catch up every physical stream without blocking startup."""
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be positive")
    service = _default_replay_service(db_path=db_path, events_dir=events_dir)
    stop = stop_event or threading.Event()

    def recover() -> None:
        from substrate.graph.knowledge_event_projector import discover_investigations

        while not stop.is_set():
            if not os.path.exists(service.db_path):
                stop.wait(poll_interval_s)
                continue
            for investigation_id in discover_investigations(service.events_dir):
                if stop.is_set():
                    return
                try:
                    service.catch_up(investigation_id)
                except Exception as exc:
                    print(
                        "Note-taker replay recovery remains pending for "
                        f"{investigation_id}: {exc!r}",
                        file=sys.stderr,
                    )
            stop.wait(poll_interval_s)

    thread = threading.Thread(target=recover, name="note-taker-replay-recovery", daemon=True)
    thread.start()
    return thread


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
            lines.append(f'[{eid}] {at}: {claim_count} claims; "{rendered}"')
        elif at == ActionType.CLAIM_GROUNDING_CHECK_PASSED.value:
            claim = (payload.get("claim_text") or "")[:140]
            conf = payload.get("confidence", "?")
            region = payload.get("located_region_id") or "?"
            lines.append(f'[{eid}] {at}: ✓ "{claim}" → region={region} conf={conf}')
        elif at == ActionType.CLAIM_GROUNDING_CHECK_FAILED.value:
            claim = (payload.get("claim_text") or "")[:140]
            reason = payload.get("reason") or "?"
            lines.append(f'[{eid}] {at}: ⚠ "{claim}" → {reason}')
        elif at == ActionType.CLAIM_CHALLENGE_RAISED.value:
            claim = (payload.get("claim_text") or "")[:120]
            q = (payload.get("user_question") or "")[:80]
            lines.append(f'[{eid}] {at}: claim="{claim}" challenged="{q}"')
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
    db_path: str | None = None,
    events_dir: str | None = None,
    replay_service: DurableNoteTakerReplay | None = None,
):
    """Build the public async bridge over the durable replay service."""

    resolved_threshold = threshold if threshold is not None else _resolve_threshold()

    service = replay_service or _default_replay_service(
        db_path=db_path,
        events_dir=events_dir,
        threshold=resolved_threshold,
    )

    async def handle_subscribed_event(event: Event) -> None:
        # Skip note-taker's OWN emitted events to avoid feedback loops.
        # (Our note.emerged events aren't in SUBSCRIBED_ACTION_TYPES so
        # this is defense-in-depth; helps if someone later adds note
        # events to the subscription.)
        if event.role == "note_taker" or str(event.action_type) == ActionType.NOTE_EMERGED.value:
            return

        try:
            delivered = await asyncio.to_thread(service.catch_up, event.investigation_id)
        except Exception as exc:
            # Durable evidence records ambiguity; the event bus remains best-effort.
            print(
                "Note-taker live replay remains pending for "
                f"{event.investigation_id}: {exc!r}",
                file=sys.stderr,
            )
            return
        if not delivered:
            return
        delivered_ids = set(delivered)
        for row in iter_physical_events(event.investigation_id, events_dir=service.events_dir):
            if row.get("event_id") not in delivered_ids:
                continue
            with contextlib.suppress(Exception):
                await broadcaster.broadcast(Event.model_validate(row))

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
    history = [r for r in all_rows if r.get("action_type") in substantive_types]
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
        NOTE_TAKER_SYSTEM_PROMPT + "\n\n" + pack.text + "\n\n" + "Now produce the JSON object."
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
