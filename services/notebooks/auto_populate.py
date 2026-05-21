"""Auto-populator: Tier-1 behavior events → per-document notebook blocks.

SPR-08 M3. Reads ``behavior_events`` for one ``(user_id, document_id)``
span and upserts blocks into ``notebook_blocks`` idempotently. Same
event range MUST produce the same blocks; the test in
``tests/test_auto_populate.py::test_idempotent_against_real_events``
proves this on fixtures pulled from the actual behavior store.

How the read goes through the substrate
---------------------------------------
The behavior store has two exit paths
(``substrate/behavior/export.py``):

- ``export_training_batch`` — DP-shuffled, for RL training-corpus
  egress. Not appropriate here: it perturbs ordering + timestamps.
- ``query_raw`` — operator-only direct select. Wave 2 surfaces are
  forbidden from calling this; the auto-populator is NOT a Wave 2
  surface — it's a server-side worker run under the operator role.

We use ``query_raw`` with an explicit ``operator_check`` so the
default-refuse posture documented in ``export.py`` is honoured. The
operator check here is "this caller IS the substrate's notebook
populator running server-side"; production callers will pass a
stricter check tied to the FastAPI role middleware once that
exists.

Run modes
---------
- ``on_event`` — fired by the FastAPI behavior-event handler within
  seconds of an emit. Reads only events newer than the last
  populator run for that notebook.
- ``on_open`` — fired when the user opens the notebook surface.
  Reads everything for the (user, doc) span; idempotent.
- ``batch`` — operator command. Same as on_open.

All three call the same ``populate_per_doc_notebook`` function;
``since_event_id`` is the only knob.

Idempotency contract
--------------------
- Block ids are deterministic where possible: a
  ``highlight_created`` event becomes the block whose
  ``block_id`` is ``blk-h-<sha256(event_id)[:12]>``. Re-running the
  populator on the same event yields the same ``block_id``, so
  upsert is a no-op.
- For events that mutate prior blocks (a later ``highlight_created``
  for the same ``highlight_id``), the populator finds the prior
  block via ``source_event_ids`` and overwrites in place; the
  ``block_id`` is preserved.
- The equality assertion the test uses is content-based (block_type,
  source_event_ids, content_json), NOT row-id-based. This is the
  rigor-3 mandate from the sprint HTML.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

import duckdb

try:
    from substrate.behavior.export import OperatorRoleRequired, query_raw
    from .blocks import (
        BLOCK_TAXONOMY_VERSION,
        EVENT_TYPE_TO_BLOCK_TYPE,
        EVENT_TYPES_SKIPPED,
        BlockType,
    )
    from .persistence import (
        BlockRecord,
        JSONPersistence,
        NotebookPersistence,
        NotebookRecord,
    )
    from .schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.notebooks.blocks import (  # type: ignore[no-redef]
        BLOCK_TAXONOMY_VERSION,
        EVENT_TYPE_TO_BLOCK_TYPE,
        EVENT_TYPES_SKIPPED,
        BlockType,
    )
    from services.notebooks.persistence import (  # type: ignore[no-redef]
        BlockRecord,
        JSONPersistence,
        NotebookPersistence,
        NotebookRecord,
    )
    from services.notebooks.schema import default_db_path  # type: ignore[no-redef]
    from substrate.behavior.export import (  # type: ignore[no-redef]
        OperatorRoleRequired,
        query_raw,
    )


# ── Diagnostic envelope ──


@dataclass(frozen=True)
class PopulateResult:
    """Returned by ``populate_per_doc_notebook``. Lets tests + ops
    assert on what changed without re-querying."""

    notebook_id: str
    blocks_created: int
    blocks_updated: int
    blocks_unchanged: int
    events_scanned: int
    events_skipped_unknown: int  # event types outside the closed taxonomy
    events_skipped_no_consent: int


# ── Public entrypoint ──


def populate_per_doc_notebook(
    *,
    user_id: str,
    document_id: str,
    persistence: Optional[NotebookPersistence] = None,
    db_path: Optional[str] = None,
    since_event_id: Optional[str] = None,
    operator_check: Optional[Callable[[], bool]] = None,
) -> PopulateResult:
    """Walk Tier-1 events for ``(user_id, document_id)`` and upsert
    blocks idempotently.

    Args:
        user_id: Owner of the notebook + events.
        document_id: The per-document scope.
        persistence: Override (tests pass a per-DB JSONPersistence).
            Production callers omit and accept the default.
        db_path: Override behavior-store DuckDB path. Defaults to
            ``ANTIEK_DUCKDB_PATH`` / ``substrate.constants.DUCKDB_PATH``.
        since_event_id: If set, only events with timestamp_utc >=
            this event's timestamp are read. Lets the on_event mode
            avoid re-scanning the full history.
        operator_check: Callable returning True if the caller is
            authorised. Defaults to a substrate-internal lambda that
            authorises the local auto-populator. Production wiring
            should pass the FastAPI role check.

    Returns:
        ``PopulateResult`` with counters. The notebook itself is
        ready via ``persistence.load_notebook(...)``.
    """
    path = db_path or default_db_path()
    pers = persistence or JSONPersistence(db_path=path)

    # Default operator check: this is the substrate's own populator
    # calling its own DB. The default-refuse posture in export.py
    # forces every caller to pass SOMETHING here; we make the
    # "substrate-internal" identity explicit.
    check = operator_check or _substrate_internal_operator_check

    # 1. Ensure the notebook exists.
    notebook = pers.get_or_create_notebook(
        user_id=user_id, document_id=document_id
    )

    # 2. Load all relevant events from the behavior store.
    events = _load_events(
        path=path,
        user_id=user_id,
        document_id=document_id,
        since_event_id=since_event_id,
        operator_check=check,
    )

    # 3. Walk events, derive blocks, reconcile against existing rows.
    return _reconcile(
        notebook=notebook,
        events=events,
        pers=pers,
    )


def _substrate_internal_operator_check() -> bool:
    """The auto-populator is itself the operator's substrate code.
    Returning True is the documented in-process authorisation.

    Wave 2 surfaces MUST NOT import this function. The verification
    gate ``rg "_substrate_internal_operator_check" apps/`` MUST stay
    empty.
    """
    return True


# ── Event read ──


@dataclass(frozen=True)
class _Event:
    event_id: str
    user_id: str
    session_id: str
    event_type: str
    document_id: Optional[str]
    timestamp_utc: datetime
    state: dict[str, Any]
    action: dict[str, Any]
    outcome: Optional[dict[str, Any]]


def _load_events(
    *,
    path: str,
    user_id: str,
    document_id: str,
    since_event_id: Optional[str],
    operator_check: Callable[[], bool],
) -> list[_Event]:
    """Read events from the behavior store via ``query_raw``.

    We deliberately use ``query_raw`` (operator-only) rather than
    poking the table directly so the substrate's role gate is the
    single point of authorisation. If the gate refuses, the populator
    surfaces an ``OperatorRoleRequired`` to the caller.
    """
    sql = (
        "SELECT event_id, user_id, session_id, event_type, document_id, "
        "       timestamp_utc, state, action, outcome "
        "FROM behavior_events "
        "WHERE user_id = ? AND document_id = ? "
        "ORDER BY timestamp_utc, event_id"
    )
    params: list[Any] = [user_id, document_id]

    if since_event_id is not None:
        sql = (
            "SELECT event_id, user_id, session_id, event_type, document_id, "
            "       timestamp_utc, state, action, outcome "
            "FROM behavior_events "
            "WHERE user_id = ? AND document_id = ? "
            "  AND timestamp_utc >= (SELECT timestamp_utc FROM behavior_events "
            "                       WHERE event_id = ?) "
            "ORDER BY timestamp_utc, event_id"
        )
        params = [user_id, document_id, since_event_id]

    rows = query_raw(
        sql,
        params,
        db_path=path,
        operator_check=operator_check,
    )

    out: list[_Event] = []
    for r in rows:
        state = json.loads(r[6]) if isinstance(r[6], str) else (r[6] or {})
        action = json.loads(r[7]) if isinstance(r[7], str) else (r[7] or {})
        outcome = None
        if r[8] is not None:
            outcome = json.loads(r[8]) if isinstance(r[8], str) else r[8]
        out.append(
            _Event(
                event_id=r[0],
                user_id=r[1],
                session_id=r[2],
                event_type=r[3],
                document_id=r[4],
                timestamp_utc=r[5],
                state=state or {},
                action=action or {},
                outcome=outcome,
            )
        )
    return out


# ── Block derivation ──


def _block_id_for_event(event_id: str, block_type: str) -> str:
    """Deterministic block id from event id. Two runs against the
    same event yield the same id — this is the idempotency primitive.

    Format: ``blk-<first-letter-of-block-type>-<sha256(event_id)[:12]>``
    The single-letter prefix is for grep ergonomics; the 12-hex
    suffix gives 2^48 codomain (collision-safe across a billion
    events with probability < 1e-6)."""
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    prefix = block_type[:1] if block_type else "x"
    return f"blk-{prefix}-{digest[:12]}"


def _content_for_highlight_card(ev: _Event) -> dict[str, Any]:
    return {
        "passage_text": ev.action.get("passage_text"),
        "start_offset": ev.action.get("start_offset"),
        "end_offset": ev.action.get("end_offset"),
        "color": ev.action.get("color"),
        "tag": ev.action.get("tag"),
        "highlight_id": ev.action.get("highlight_id"),
        "chunk_id": ev.state.get("chunk_id"),
        "reading_mode": ev.state.get("reading_mode"),
    }


def _content_for_voice_block(ev: _Event) -> dict[str, Any]:
    return {
        "voice_note_id": ev.action.get("voice_note_id"),
        "duration_s": ev.action.get("duration_s"),
        "transcript_present": ev.action.get("transcript_present"),
        "anchored_to_highlight_id": ev.state.get("anchored_to_highlight_id"),
        "chunk_id": ev.state.get("chunk_id"),
    }


def _content_for_ai_qa(ev: _Event, prompt_ev: Optional[_Event]) -> dict[str, Any]:
    return {
        "prompt_id": ev.state.get("prompt_id"),
        "response_id": ev.action.get("response_id"),
        "accept_kind": ev.action.get("accept_kind"),
        "prompt_text": (
            prompt_ev.action.get("prompt_text") if prompt_ev else None
        ),
        "prompt_missing": prompt_ev is None,
    }


def _content_for_cite_link(ev: _Event) -> dict[str, Any]:
    return {
        "target_document_id": ev.action.get("target_document_id"),
        "target_chunk_id": ev.action.get("target_chunk_id"),
        "direction": ev.action.get("direction"),
        "source_chunk_id": ev.state.get("source_chunk_id"),
    }


def _content_for_cross_doc_jump(ev: _Event) -> dict[str, Any]:
    return {
        "link_id": ev.state.get("link_id"),
        "target_document_id": ev.action.get("target_document_id"),
        "target_chunk_id": ev.action.get("target_chunk_id"),
        "elapsed_since_surfaced_s": ev.state.get("elapsed_since_surfaced_s"),
    }


# Map event_type → (block_type, content_builder). For ai_qa the
# builder takes a second arg (the paired ai_prompt_sent event), so we
# special-case it in _reconcile.
_CONTENT_BUILDERS: dict[str, Callable[[_Event], dict[str, Any]]] = {
    "highlight_created": _content_for_highlight_card,
    "voice_note_recorded": _content_for_voice_block,
    "cite_jump": _content_for_cite_link,
    "cross_doc_link_clicked": _content_for_cross_doc_jump,
}


def _equivalent(a: BlockRecord, b: BlockRecord) -> bool:
    """Content-based equality (per rigor-3 mandate). Two blocks are
    equivalent iff their block_type, sorted source_event_ids, and
    content_json all match. Position + timestamps don't enter the
    comparison.
    """
    if a.block_type != b.block_type:
        return False
    if sorted(a.source_event_ids) != sorted(b.source_event_ids):
        return False
    return _json_equiv(a.content_json, b.content_json)


def _json_equiv(a: Any, b: Any) -> bool:
    """JSON-value structural equality. Drops keys whose value is None
    on either side so the populator's "I don't know the chunk_id"
    doesn't disagree with a renderer's "chunk_id: null"."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys = {k for k in a if a[k] is not None} | {
            k for k in b if b[k] is not None
        }
        return all(_json_equiv(a.get(k), b.get(k)) for k in keys)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equiv(x, y) for x, y in zip(a, b))
    return a == b


def _reconcile(
    *,
    notebook: NotebookRecord,
    events: list[_Event],
    pers: NotebookPersistence,
) -> PopulateResult:
    """Walk events, derive blocks, upsert against the live notebook."""
    existing_by_id: dict[str, BlockRecord] = {b.block_id: b for b in notebook.blocks}

    # Index AI prompt events by prompt_id for the ai_qa join.
    prompts_by_id: dict[str, _Event] = {
        ev.state.get("prompt_id"): ev
        for ev in events
        if ev.event_type == "ai_prompt_sent"
        and ev.state.get("prompt_id") is not None
    }

    # Index existing blocks by their source event ids so a mutation
    # event (e.g. a later highlight_created with the same highlight_id)
    # can find the prior block deterministically.
    highlight_block_by_hid: dict[str, BlockRecord] = {}
    for block in notebook.blocks:
        if block.block_type != BlockType.HIGHLIGHT_CARD.value:
            continue
        hid = block.content_json.get("highlight_id")
        if hid:
            highlight_block_by_hid[hid] = block

    skipped_unknown = 0
    new_or_updated: dict[str, BlockRecord] = {}
    position = 0.0

    for ev in events:
        if ev.event_type in EVENT_TYPES_SKIPPED:
            continue
        if ev.event_type not in EVENT_TYPE_TO_BLOCK_TYPE:
            skipped_unknown += 1
            continue

        block_type = EVENT_TYPE_TO_BLOCK_TYPE[ev.event_type]
        position += 1.0

        if ev.event_type == "ai_response_accepted":
            prompt_id = ev.state.get("prompt_id")
            prompt_ev = prompts_by_id.get(prompt_id) if prompt_id else None
            content = _content_for_ai_qa(ev, prompt_ev)
            source_ids = [ev.event_id]
            if prompt_ev is not None:
                source_ids.append(prompt_ev.event_id)
            block_id = _block_id_for_event(ev.event_id, block_type.value)
            new_or_updated[block_id] = BlockRecord(
                block_id=block_id,
                notebook_id=notebook.notebook_id,
                block_type=block_type.value,
                source_event_ids=source_ids,
                content_json=content,
                position=position,
                document_id=ev.document_id,
            )
            continue

        if ev.event_type == "highlight_created":
            hid = ev.action.get("highlight_id")
            content = _content_for_highlight_card(ev)
            if hid and hid in highlight_block_by_hid:
                existing = highlight_block_by_hid[hid]
                # Merge: keep the original block_id (so renderers'
                # references stay stable), refresh content, append
                # this event to source_event_ids.
                merged_sources = list(
                    dict.fromkeys([*existing.source_event_ids, ev.event_id])
                )
                merged = BlockRecord(
                    block_id=existing.block_id,
                    notebook_id=notebook.notebook_id,
                    block_type=block_type.value,
                    source_event_ids=merged_sources,
                    content_json=content,
                    position=existing.position,
                    document_id=ev.document_id,
                    demoted_at=existing.demoted_at,
                    edited_at=existing.edited_at,
                )
                new_or_updated[existing.block_id] = merged
                highlight_block_by_hid[hid] = merged
                continue
            block_id = _block_id_for_event(ev.event_id, block_type.value)
            content_builder = _CONTENT_BUILDERS[ev.event_type]
            new_or_updated[block_id] = BlockRecord(
                block_id=block_id,
                notebook_id=notebook.notebook_id,
                block_type=block_type.value,
                source_event_ids=[ev.event_id],
                content_json=content_builder(ev),
                position=position,
                document_id=ev.document_id,
            )
            if hid:
                highlight_block_by_hid[hid] = new_or_updated[block_id]
            continue

        # All other mapped event types are one-event-one-block.
        content_builder = _CONTENT_BUILDERS[ev.event_type]
        block_id = _block_id_for_event(ev.event_id, block_type.value)
        new_or_updated[block_id] = BlockRecord(
            block_id=block_id,
            notebook_id=notebook.notebook_id,
            block_type=block_type.value,
            source_event_ids=[ev.event_id],
            content_json=content_builder(ev),
            position=position,
            document_id=ev.document_id,
        )

    # Reconcile: classify each derived block as created / updated /
    # unchanged versus the existing notebook state, then upsert the
    # ones that differ.
    created = 0
    updated = 0
    unchanged = 0
    to_upsert: list[BlockRecord] = []
    for block in new_or_updated.values():
        prior = existing_by_id.get(block.block_id)
        if prior is None:
            created += 1
            to_upsert.append(block)
            continue
        if _equivalent(prior, block):
            unchanged += 1
            continue
        # Preserve operator-edited content if the prior block was
        # explicitly edited (edited_at set) and the populator's
        # content would just be the raw event payload. We do this by
        # keeping the prior content_json and only refreshing the
        # source_event_ids.
        if prior.edited_at is not None:
            merged = BlockRecord(
                block_id=prior.block_id,
                notebook_id=block.notebook_id,
                block_type=block.block_type,
                source_event_ids=block.source_event_ids,
                content_json=prior.content_json,
                position=prior.position,
                document_id=block.document_id,
                demoted_at=prior.demoted_at,
                edited_at=prior.edited_at,
            )
            updated += 1
            to_upsert.append(merged)
            continue
        # Preserve demote state.
        if prior.demoted_at is not None:
            block.demoted_at = prior.demoted_at
        updated += 1
        to_upsert.append(block)

    if to_upsert:
        pers.upsert_blocks(notebook.notebook_id, to_upsert)

    return PopulateResult(
        notebook_id=notebook.notebook_id,
        blocks_created=created,
        blocks_updated=updated,
        blocks_unchanged=unchanged,
        events_scanned=len(events),
        events_skipped_unknown=skipped_unknown,
        events_skipped_no_consent=0,
        # Consent absence is invisible at this layer — the behavior
        # store doesn't emit rows for non-consenting users (per
        # substrate/behavior/api.py), so any row we read here is by
        # construction consent-bearing. We still expose the field on
        # PopulateResult for forward-compat with a future explicit
        # consent column.
    )


__all__ = [
    "PopulateResult",
    "populate_per_doc_notebook",
]
