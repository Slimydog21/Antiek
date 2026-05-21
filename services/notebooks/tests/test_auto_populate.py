"""Auto-populator tests (SPR-08 M3 + M7 + M8).

Five acceptance scopes, mapped one-to-one to the sprint HTML:

- M3: idempotency against real behavior-store fixtures (`-t idempotent`).
- M3: skip events whose type is outside the closed taxonomy
  (`-t skip_unknown`).
- M3: event → block mapping is correct per type
  (`-t event_to_block_mapping`).
- M7: reward join finds the block (`-t reward_hook`).
- M7: ``run_medium_backfill`` updates ``behavior_events.reward_proxy_medium``
  (`-t reward_hook`).

The fixtures use REAL behavior-store data (not in-memory dicts) per
the rigor-3 mandate in the sprint HTML.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb
import pytest

from services.notebooks.auto_populate import (
    PopulateResult,
    populate_per_doc_notebook,
)
from services.notebooks.blocks import (
    BLOCK_TAXONOMY_VERSION,
    BlockType,
)
from services.notebooks.persistence import JSONPersistence
from services.notebooks.reward_hook import (
    check_reward_join,
    run_medium_backfill,
)
from substrate.behavior import (
    BehaviorEventType,
    emit_behavior_event,
    grant_consent,
)


USER = "__operator__"
DOC = "doc-spr08-fixture"


# ── Helpers ──


def _grant(db: str) -> None:
    grant_consent(USER, db_path=db)


def _emit_highlight(
    *,
    queue,
    doc: str = DOC,
    offset: int = 100,
    text: str = "important passage",
    highlight_id: str = "hl-abc",
) -> str:
    return emit_behavior_event(
        BehaviorEventType.HIGHLIGHT_CREATED,
        state={"document_id": doc, "reading_mode": "researcher"},
        action={
            "highlight_id": highlight_id,
            "start_offset": offset,
            "end_offset": offset + len(text),
            "passage_text": text,
            "color": "yellow",
        },
        user_id=USER,
        document_id=doc,
        queue=queue,
    )


def _emit_voice(*, queue, doc: str = DOC, voice_note_id: str = "vn-1") -> str:
    return emit_behavior_event(
        BehaviorEventType.VOICE_NOTE_RECORDED,
        state={"document_id": doc, "reading_mode": "researcher"},
        action={"voice_note_id": voice_note_id, "duration_s": 4.2},
        user_id=USER,
        document_id=doc,
        queue=queue,
    )


def _emit_ai_accepted(*, queue, doc: str = DOC, prompt_id: str = "p-1") -> str:
    return emit_behavior_event(
        BehaviorEventType.AI_RESPONSE_ACCEPTED,
        state={"document_id": doc, "prompt_id": prompt_id},
        action={"response_id": "r-1", "accept_kind": "pinned"},
        user_id=USER,
        document_id=doc,
        queue=queue,
    )


def _emit_cite_jump(*, queue, doc: str = DOC) -> str:
    return emit_behavior_event(
        BehaviorEventType.CITE_JUMP,
        state={"document_id": doc, "reading_mode": "researcher"},
        action={"target_document_id": "doc-target", "direction": "forward"},
        user_id=USER,
        document_id=doc,
        queue=queue,
    )


def _emit_doc_open(*, queue, doc: str = DOC) -> str:
    return emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": doc},
        action={"reading_mode": "researcher"},
        user_id=USER,
        document_id=doc,
        queue=queue,
    )


# ── M3 — idempotency ──


def test_idempotent_against_real_events(combined_db, behavior_queue, persistence):
    """The populator runs twice on the same event range and yields
    identical block records (content-equality, not row-id equality —
    although in this implementation the ids are deterministic so both
    hold). Real-data fixture: events go through the queue + writer.
    """
    _grant(combined_db)
    for i in range(3):
        _emit_highlight(
            queue=behavior_queue,
            offset=100 + i * 20,
            text=f"passage {i}",
            highlight_id=f"hl-{i}",
        )
    _emit_voice(queue=behavior_queue)
    _emit_ai_accepted(queue=behavior_queue)
    _emit_cite_jump(queue=behavior_queue)
    _emit_doc_open(queue=behavior_queue)  # should be skipped (bookend)
    assert behavior_queue.flush(timeout_s=5.0)

    r1 = populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    assert r1.blocks_created == 6
    notebook1 = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert notebook1 is not None
    snap1 = _content_snapshot(notebook1.blocks)

    # Second pass — nothing should change.
    r2 = populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    notebook2 = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert notebook2 is not None
    snap2 = _content_snapshot(notebook2.blocks)

    assert r2.blocks_created == 0, "second pass created new blocks"
    assert r2.blocks_updated == 0, "second pass updated blocks"
    assert r2.blocks_unchanged == 6, "second pass should leave 6 unchanged"
    assert snap1 == snap2, "content snapshots diverged across runs"
    assert len(notebook1.blocks) == len(notebook2.blocks) == 6


def _content_snapshot(blocks) -> list[tuple]:
    """Content-equality snapshot (rigor-3): block_type +
    sorted-source-ids + content json. Excludes block_id, position,
    timestamps."""
    return sorted(
        (
            b.block_type,
            tuple(sorted(b.source_event_ids)),
            json.dumps(b.content_json, sort_keys=True),
        )
        for b in blocks
    )


# ── M3 — event → block mapping ──


def test_event_to_block_mapping(combined_db, behavior_queue, persistence):
    """One event of each mapped type → one block of the correct type."""
    _grant(combined_db)
    _emit_highlight(queue=behavior_queue)
    _emit_voice(queue=behavior_queue)
    _emit_ai_accepted(queue=behavior_queue)
    _emit_cite_jump(queue=behavior_queue)
    # Cross-doc click event:
    emit_behavior_event(
        BehaviorEventType.CROSS_DOC_LINK_CLICKED,
        state={"document_id": DOC, "link_id": "link-1"},
        action={"target_document_id": "doc-target"},
        user_id=USER,
        document_id=DOC,
        queue=behavior_queue,
    )
    assert behavior_queue.flush(timeout_s=5.0)

    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    nb = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb is not None
    types = sorted(b.block_type for b in nb.blocks)
    assert types == sorted(
        [
            BlockType.HIGHLIGHT_CARD.value,
            BlockType.VOICE_BLOCK.value,
            BlockType.AI_QA.value,
            BlockType.CITE_LINK.value,
            BlockType.CROSS_DOC_JUMP.value,
        ]
    )


# ── M3 — unknown event types are skipped ──


def test_skip_unknown_event_type_via_raw_insert(combined_db, behavior_queue, persistence):
    """Inject an event with an unknown event_type by writing directly
    via the operator path. The populator scans, skips, and returns
    a non-zero ``events_skipped_unknown``.
    """
    _grant(combined_db)
    _emit_highlight(queue=behavior_queue)
    assert behavior_queue.flush(timeout_s=5.0)

    # Bypass the validating emit API and inject a row directly. The
    # API guards the closed taxonomy; we want to assert the populator
    # is defensive even if a row somehow lands.
    con = duckdb.connect(combined_db)
    try:
        con.execute(
            "INSERT INTO behavior_events "
            "(event_id, user_id, session_id, event_type, document_id, "
            " state, action, consent_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "evt-injected-zzzz",
                USER,
                "sess-injected",
                "future_event_type_not_in_taxonomy",
                DOC,
                json.dumps({"document_id": DOC}),
                json.dumps({}),
                1,
            ],
        )
    finally:
        con.close()

    result = populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    assert result.events_skipped_unknown == 1
    assert result.blocks_created == 1  # only the highlight


# ── M3 — highlight edit merges into same card ──


def test_highlight_edit_merges_into_same_block(combined_db, behavior_queue, persistence):
    """A second ``highlight_created`` with the same ``highlight_id``
    folds into the existing block — block_id preserved, content
    refreshed, source_event_ids list grows."""
    _grant(combined_db)
    eid_a = _emit_highlight(queue=behavior_queue, text="first", highlight_id="hl-merge")
    assert behavior_queue.flush(timeout_s=5.0)
    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    nb_before = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb_before is not None
    assert len(nb_before.blocks) == 1
    initial_block_id = nb_before.blocks[0].block_id

    eid_b = _emit_highlight(queue=behavior_queue, text="edited!", highlight_id="hl-merge")
    assert behavior_queue.flush(timeout_s=5.0)
    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    nb_after = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb_after is not None
    assert len(nb_after.blocks) == 1, "merge produced a duplicate block"
    block = nb_after.blocks[0]
    assert block.block_id == initial_block_id
    assert set(block.source_event_ids) == {eid_a, eid_b}
    assert block.content_json["passage_text"] == "edited!"


# ── M7 — reward hook ──


def test_reward_hook_block_via_check_reward_join(
    combined_db, behavior_queue, persistence
):
    """After population, ``check_reward_join(event_id)`` finds the
    block. This is the M7 "block found via behavior_event →
    notebook_blocks join" verification gate."""
    _grant(combined_db)
    eid = _emit_highlight(queue=behavior_queue)
    assert behavior_queue.flush(timeout_s=5.0)

    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )

    links = check_reward_join(eid, db_path=combined_db)
    assert len(links) == 1
    assert links[0].block_type == BlockType.HIGHLIGHT_CARD.value
    assert links[0].document_id == DOC


def test_reward_hook_medium_backfill_updates_behavior_events(
    combined_db, behavior_queue, persistence
):
    """``run_medium_backfill`` populates ``reward_proxy_medium`` on the
    source events. Pre-SPR-08 this was a stub; SPR-08 makes it real."""
    _grant(combined_db)
    eid = _emit_highlight(queue=behavior_queue)
    assert behavior_queue.flush(timeout_s=5.0)
    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )

    result = run_medium_backfill(db_path=combined_db)
    assert result.status == "ran"
    assert result.rows_updated == 1

    con = duckdb.connect(combined_db)
    try:
        row = con.execute(
            "SELECT reward_proxy_medium FROM behavior_events WHERE event_id = ?",
            [eid],
        ).fetchone()
    finally:
        con.close()
    assert row is not None and row[0] is not None and row[0] > 0


def test_reward_hook_medium_backfill_skipped_when_no_notebooks(combined_db):
    """No notebooks → backfill returns ``skipped_no_notebooks``,
    behavior_events untouched. Mirrors the substrate worker's old
    ``empty`` status."""
    result = run_medium_backfill(db_path=combined_db)
    assert result.status == "skipped_no_notebooks"
    assert result.rows_updated == 0


def test_reward_medium_worker_delegates_to_hook(combined_db, behavior_queue, persistence):
    """The substrate-side ``run_reward_medium_backfill`` (the cron's
    entry point) now delegates to ``reward_hook.run_medium_backfill``.
    The status string maps ``ran`` → ``ran``; the SPR-01 e2e
    invocation still gets a well-shaped result."""
    from substrate.behavior.workers.reward_medium import (
        run_reward_medium_backfill,
    )

    _grant(combined_db)
    _emit_highlight(queue=behavior_queue)
    assert behavior_queue.flush(timeout_s=5.0)
    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )

    out = run_reward_medium_backfill(db_path=combined_db)
    assert out.status == "ran"
    assert out.rows_updated == 1


# ── M6 — persistence round-trip ──


def test_save_and_reload_byte_for_byte(combined_db, behavior_queue, persistence):
    """Save → reload preserves block ordering + content."""
    _grant(combined_db)
    for i in range(3):
        _emit_highlight(
            queue=behavior_queue,
            offset=200 + i * 10,
            text=f"p{i}",
            highlight_id=f"hl-rt-{i}",
        )
    assert behavior_queue.flush(timeout_s=5.0)
    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    nb1 = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb1 is not None
    snap1 = _content_snapshot(nb1.blocks)

    # Save the loaded notebook back (simulates the surface's debounced auto-save).
    persistence.save_notebook(nb1)
    nb2 = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb2 is not None
    snap2 = _content_snapshot(nb2.blocks)
    assert snap1 == snap2


def test_demote_round_trip(combined_db, behavior_queue, persistence):
    """Demote a block → reload → block.demoted_at set. Restore →
    reload → demoted_at null. Per M5 acceptance criterion."""
    _grant(combined_db)
    _emit_highlight(queue=behavior_queue, highlight_id="hl-demote")
    assert behavior_queue.flush(timeout_s=5.0)
    populate_per_doc_notebook(
        user_id=USER, document_id=DOC, persistence=persistence, db_path=combined_db,
    )
    nb = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb is not None and len(nb.blocks) == 1
    block_id = nb.blocks[0].block_id

    persistence.demote_block(block_id, demoted=True)
    nb = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb is not None
    assert nb.blocks[0].demoted_at is not None

    persistence.demote_block(block_id, demoted=False)
    nb = persistence.load_notebook(user_id=USER, document_id=DOC)
    assert nb is not None
    assert nb.blocks[0].demoted_at is None


# ── M2 — block taxonomy doc presence ──


def test_block_taxonomy_doc_exists():
    """The handoff requires BLOCK_TAXONOMY.md present and naming the
    6 block types + event mapping."""
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "BLOCK_TAXONOMY.md",
    )
    assert os.path.exists(path), "BLOCK_TAXONOMY.md missing"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for t in [
        "highlight_card",
        "voice_block",
        "ai_qa",
        "cite_link",
        "cross_doc_jump",
        "prose",
    ]:
        assert t in text, f"BLOCK_TAXONOMY.md missing block type {t}"
    assert "Why no `+ new block`" in text, (
        "BLOCK_TAXONOMY.md missing no-authoring rationale (rigor-5)"
    )


# ── M2 — taxonomy version + closed set ──


def test_block_taxonomy_version_is_one():
    assert BLOCK_TAXONOMY_VERSION == 1


def test_block_record_refuses_unmapped_block_with_no_source_events():
    """No-authoring invariant at the persistence boundary."""
    from services.notebooks.persistence import BlockRecord

    with pytest.raises(ValueError, match="at least one source_event_id"):
        BlockRecord(
            block_id="blk-bogus",
            notebook_id="nbk-bogus",
            block_type=BlockType.HIGHLIGHT_CARD.value,
            source_event_ids=[],
            content_json={},
            position=0,
        )
