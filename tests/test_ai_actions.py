"""AI sidecar undoable actions (PostHog Wedge 4, master-spec §5.5)."""

from __future__ import annotations

import json

import pytest

from substrate.ai_actions import (
    AIActionError,
    apply_ai_action,
    undo_ai_action,
)
from substrate.ai_actions.actions import _hash_prev
from substrate.schemas.events import (
    AIActionAppliedPayload,
    AIActionUndonePayload,
    ActionType,
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
)


# ── Schema-level sanity ──────────────────────────────────────────────


def test_action_types_registered_in_enum():
    assert ActionType.AI_ACTION_APPLIED.value == "ai.action.applied"
    assert ActionType.AI_ACTION_UNDONE.value == "ai.action.undone"


def test_action_types_in_typed_union():
    assert "ai.action.applied" in TYPED_PAYLOAD_ACTION_TYPES
    assert "ai.action.undone" in TYPED_PAYLOAD_ACTION_TYPES


def test_schema_version_bumped():
    assert EVENT_SCHEMA_VERSION >= 11


def test_applied_payload_validates():
    p = AIActionAppliedPayload(
        target_kind="notebook_block",
        target_id="nbb-1",
        operator_prompt="add a claim card for X",
        prev_state={"block_id": "nbb-1", "block_type": "prose"},
        next_state={"block_id": "nbb-1", "block_type": "claim_card", "ref_id": "c-1"},
        prev_state_hash="deadbeef" * 8,
    )
    assert p.action_type == ActionType.AI_ACTION_APPLIED


def test_applied_payload_rejects_unknown_kind():
    with pytest.raises(Exception):
        AIActionAppliedPayload(
            target_kind="garbage",  # type: ignore[arg-type]
            target_id="x",
            operator_prompt="x",
            prev_state={},
            next_state={},
            prev_state_hash="x",
        )


def test_undone_payload_validates():
    p = AIActionUndonePayload(
        inverted_event_id="evt-abc",
        target_kind="notebook_block",
        target_id="nbb-1",
    )
    assert p.reason == "operator_undo"


# ── Apply / undo flow ────────────────────────────────────────────────


def _capture_emitter():
    """Returns (emit_fn, captured_list)."""
    captured: list = []

    def emit(event) -> None:
        captured.append(event)

    return emit, captured


def test_apply_emits_event_with_prev_state_hash():
    emit, captured = _capture_emitter()
    result = apply_ai_action(
        con=None,  # handlers don't run on apply
        investigation_id="inv-1",
        target_kind="notebook_block",
        target_id="nbb-1",
        operator_prompt="convert block to claim card",
        prev_state={"block_id": "nbb-1", "block_type": "prose"},
        next_state={"block_id": "nbb-1", "block_type": "claim_card", "ref_id": "c-1"},
        emit_event_fn=emit,
    )
    assert len(captured) == 1
    assert result.event_id.startswith("evt-")
    assert len(result.prev_state_hash) == 64  # sha256 hex
    event = captured[0]
    assert event.action_type == ActionType.AI_ACTION_APPLIED
    assert event.payload.target_kind == "notebook_block"


def test_apply_rejects_unknown_kind():
    emit, _ = _capture_emitter()
    with pytest.raises(AIActionError, match="no inverse handler"):
        apply_ai_action(
            con=None,
            investigation_id="inv-1",
            target_kind="unknown_kind",
            target_id="x",
            operator_prompt="x",
            prev_state={},
            next_state={},
            emit_event_fn=emit,
        )


def test_hash_is_deterministic():
    h1 = _hash_prev("notebook_block", "nbb-1", {"a": 1, "b": 2})
    h2 = _hash_prev("notebook_block", "nbb-1", {"b": 2, "a": 1})  # diff order
    assert h1 == h2  # canonical sort flattens key order


def test_hash_changes_on_state_diff():
    h1 = _hash_prev("notebook_block", "nbb-1", {"a": 1})
    h2 = _hash_prev("notebook_block", "nbb-1", {"a": 2})
    assert h1 != h2


# ── Undo flow against a real DuckDB ──────────────────────────────────


def _fresh_db(tmp_path):
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database

    path = tmp_path / "test.duckdb"
    # init_database requires a LockedConnection per the single-writer
    # invariant. Subsequent test operations use the same lock.
    with connect_write(str(path), purpose="test_ai_actions:init") as con:
        init_database(con)
    return connect_write(str(path), purpose="test_ai_actions:run")


def test_undo_restores_notebook_block(tmp_path):
    """End-to-end: AI changes a block from prose → claim_card; undo
    sets it back to prose."""
    cm = _fresh_db(tmp_path)
    con = cm.__enter__()
    from substrate.notebooks import create_notebook, append_block, get_notebook

    nb_id = create_notebook(con, title="T")
    block_id = append_block(
        con,
        notebook_id=nb_id,
        block_type="prose",
        content={"type": "paragraph", "content": [{"type": "text", "text": "old"}]},
    )

    # Capture the prev state
    prev_state = {
        "block_id": block_id,
        "notebook_id": nb_id,
        "block_type": "prose",
        "ref_id": None,
        "content_json": {"type": "paragraph", "content": [{"type": "text", "text": "old"}]},
    }

    # AI applies: flip to claim_card via direct SQL (handler-less path)
    con.execute(
        "UPDATE notebook_blocks SET block_type = ?, ref_id = ? WHERE block_id = ?",
        ["claim_card", "c-1", block_id],
    )

    emit, captured = _capture_emitter()
    applied = apply_ai_action(
        con=con,
        investigation_id="inv-1",
        target_kind="notebook_block",
        target_id=block_id,
        operator_prompt="convert this paragraph to a claim card",
        prev_state=prev_state,
        next_state={
            "block_id": block_id,
            "block_type": "claim_card",
            "ref_id": "c-1",
        },
        emit_event_fn=emit,
    )
    assert len(captured) == 1

    # Undo
    applied_event = {
        "event_id": applied.event_id,
        "investigation_id": "inv-1",
        "payload": {
            "action_type": "ai.action.applied",
            "target_kind": "notebook_block",
            "target_id": block_id,
            "prev_state": prev_state,
            "next_state": {
                "block_id": block_id,
                "block_type": "claim_card",
                "ref_id": "c-1",
            },
        },
    }
    undone_id = undo_ai_action(con, applied_event=applied_event, emit_event_fn=emit)
    assert undone_id.startswith("evt-")
    assert len(captured) == 2

    # Block should be back to prose with no ref_id
    nb = get_notebook(con, nb_id)
    assert nb is not None
    restored = nb.blocks[0]
    assert restored.block_type == "prose"
    assert restored.ref_id is None


def test_undo_rejects_unknown_action_type():
    """Undo refuses if the event isn't ai.action.applied."""
    with pytest.raises(AIActionError, match="not an ai.action.applied"):
        undo_ai_action(
            con=None,
            applied_event={
                "event_id": "evt-x",
                "investigation_id": "inv-1",
                "payload": {"action_type": "dispatch.call"},
            },
            emit_event_fn=lambda e: None,
        )


def test_undo_emits_linking_event(tmp_path):
    """The ai.action.undone event references the applied event by id."""
    cm = _fresh_db(tmp_path)
    con = cm.__enter__()
    from substrate.notebooks import create_notebook, append_block

    nb_id = create_notebook(con, title="T")
    block_id = append_block(con, notebook_id=nb_id, block_type="prose", content={})

    applied_event = {
        "event_id": "evt-applied-123",
        "investigation_id": "inv-1",
        "payload": {
            "action_type": "ai.action.applied",
            "target_kind": "notebook_block",
            "target_id": block_id,
            "prev_state": {"block_id": block_id, "notebook_id": nb_id, "block_type": "prose", "content_json": {}},
            "next_state": {"block_id": block_id, "block_type": "claim_card"},
        },
    }
    emit, captured = _capture_emitter()
    undo_ai_action(con, applied_event=applied_event, emit_event_fn=emit)
    assert len(captured) == 1
    undone = captured[0]
    assert undone.payload.inverted_event_id == "evt-applied-123"
    assert undone.payload.target_id == block_id
