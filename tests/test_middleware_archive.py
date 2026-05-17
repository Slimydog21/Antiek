"""Tests for middleware/archive/.

What this file proves:

1. ``new_synthesis_id`` returns a stable UUID-shaped id.
2. ``serialize_json_field`` round-trips None, strings (validated), and
   arbitrary objects via ``json.dumps``.
3. ``compute_manifest_counts`` returns the expected per-kind counts in
   the canonical ``{document, chunk, node, edge}`` order.
4. ``emit_synthesis_archived`` produces a typed event with envelope
   synthesis_id set and payload fields matching the ArchiveInputs.
5. ``emit_substrate_manifest_written`` produces a typed event with the
   counts breakdown.
6. ``archive_synthesis_via_db`` raises NotImplementedError until init_db
   migrates — failing loudly is the right move.
7. Payload-level validators (status / recommendation Literals) reject
   unknown values.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import pytest
from pydantic import ValidationError

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.archive import (  # noqa: E402
    MANIFEST_ENTITY_KINDS,
    ArchiveInputs,
    archive_synthesis_via_db,
    compute_manifest_counts,
    emit_substrate_manifest_written,
    emit_synthesis_archived,
    new_synthesis_id,
    serialize_json_field,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    SubstrateManifestWrittenPayload,
    SynthesisArchivedPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# 1. new_synthesis_id
# ---------------------------------------------------------------------------


def test_new_synthesis_id_is_uuid_shaped_and_unique():
    ids = {new_synthesis_id() for _ in range(50)}
    assert len(ids) == 50
    for sid in ids:
        # UUID4 string form: 36 chars including 4 hyphens.
        assert len(sid) == 36 and sid.count("-") == 4


# ---------------------------------------------------------------------------
# 2. serialize_json_field
# ---------------------------------------------------------------------------


def test_serialize_json_field_none_returns_none():
    assert serialize_json_field(None) is None


def test_serialize_json_field_object_json_dumps():
    s = serialize_json_field({"a": 1, "b": [2, 3]})
    assert json.loads(s) == {"a": 1, "b": [2, 3]}


def test_serialize_json_field_validates_pre_serialized_strings():
    # Valid pre-serialized JSON passes through.
    assert serialize_json_field('{"a":1}') == '{"a":1}'
    # Invalid pre-serialized strings fail loudly — better than silently
    # writing garbage into the DB column.
    with pytest.raises(json.JSONDecodeError):
        serialize_json_field("not valid json {{")


def test_serialize_json_field_handles_datetime_via_default():
    s = serialize_json_field({"ts": datetime(2026, 5, 16, 12, 0, 0)})
    parsed = json.loads(s)
    assert "2026" in parsed["ts"]


# ---------------------------------------------------------------------------
# 3. compute_manifest_counts
# ---------------------------------------------------------------------------


def test_compute_manifest_counts_all_kinds():
    counts = compute_manifest_counts(
        document_ids=["d1", "d2"],
        chunk_ids=["c1", "c2", "c3"],
        node_ids=["n1"],
        edge_ids=["e1", "e2"],
    )
    assert counts == {"document": 2, "chunk": 3, "node": 1, "edge": 2}


def test_compute_manifest_counts_handles_empty():
    counts = compute_manifest_counts()
    assert counts == {"document": 0, "chunk": 0, "node": 0, "edge": 0}


def test_manifest_entity_kinds_in_canonical_order():
    """The order is part of the contract — analytics consumers diff
    counts position-by-position when comparing manifests."""
    assert MANIFEST_ENTITY_KINDS == ("document", "chunk", "node", "edge")


# ---------------------------------------------------------------------------
# 4. emit_synthesis_archived
# ---------------------------------------------------------------------------


def _inputs(**overrides) -> ArchiveInputs:
    defaults = {
        "target_question": "Is X causally related to Y?",
        "synthesis_timestamp": datetime(2026, 5, 16, 12, 30, 0),
        "status": "passed",
        "implicit_recommendation": "conditional",
        "thesis_text": "X correlates with Y but causation has not been shown.",
        "model_versions": {"decomposer": "claude-opus-4-7/v1", "synthesizer": "claude-opus-4-7/v1"},
        "constraint_check_result": {"checks": {"hard": "passed"}},
    }
    defaults.update(overrides)
    return ArchiveInputs(**defaults)


def test_emit_synthesis_archived_round_trips_typed():
    sid = new_synthesis_id()
    eid = emit_synthesis_archived(
        investigation_id="inv-archive-1",
        synthesis_id=sid,
        inputs=_inputs(),
    )
    rows = trajectory("inv-archive-1")
    assert len(rows) == 1
    event = Event.model_validate(rows[0])
    assert event.event_id == eid
    assert event.action_type == ActionType.SYNTHESIS_ARCHIVED.value
    assert event.synthesis_id == sid
    assert event.role == "synthesizer"
    assert isinstance(event.payload, SynthesisArchivedPayload)
    p = event.payload
    assert p.target_question.startswith("Is X")
    assert p.status == "passed"
    assert p.implicit_recommendation == "conditional"
    assert p.model_versions["synthesizer"].startswith("claude-")
    assert p.thesis_token_count > 0  # heuristic produced something
    assert p.has_constraint_check_result is True


def test_emit_synthesis_archived_zero_token_count_for_empty_thesis():
    sid = new_synthesis_id()
    emit_synthesis_archived(
        investigation_id="inv-archive-empty",
        synthesis_id=sid,
        inputs=_inputs(thesis_text=None),
    )
    event = Event.model_validate(trajectory("inv-archive-empty")[0])
    assert event.payload.thesis_token_count == 0
    assert event.payload.has_constraint_check_result is True


def test_emit_synthesis_archived_no_constraint_check_result_flag():
    sid = new_synthesis_id()
    emit_synthesis_archived(
        investigation_id="inv-archive-noc",
        synthesis_id=sid,
        inputs=_inputs(constraint_check_result=None),
    )
    event = Event.model_validate(trajectory("inv-archive-noc")[0])
    assert event.payload.has_constraint_check_result is False


# ---------------------------------------------------------------------------
# 5. emit_substrate_manifest_written
# ---------------------------------------------------------------------------


def test_emit_substrate_manifest_written_round_trips_typed():
    sid = new_synthesis_id()
    counts = compute_manifest_counts(
        document_ids=["d1"], chunk_ids=["c1", "c2"],
        node_ids=["n1", "n2", "n3"], edge_ids=["e1"],
    )
    eid = emit_substrate_manifest_written(
        investigation_id="inv-manifest-1",
        synthesis_id=sid,
        synthesis_timestamp=datetime(2026, 5, 16, 12, 30, 0),
        counts_by_kind=counts,
    )
    event = Event.model_validate(trajectory("inv-manifest-1")[0])
    assert event.event_id == eid
    assert event.synthesis_id == sid
    assert isinstance(event.payload, SubstrateManifestWrittenPayload)
    p = event.payload
    assert p.manifest_rows_written == sum(counts.values())
    assert p.counts_by_kind == counts


# ---------------------------------------------------------------------------
# 6. DB writer requires a LockedConnection (Sprint 10 day 4-5 — wired)
# ---------------------------------------------------------------------------


def test_archive_synthesis_via_db_requires_locked_connection():
    """The DB writer is the SOLE writer to the syntheses table per
    architecture_notes §4. Calling it without a LockedConnection
    must fail loudly so the only-writer invariant can't be bypassed
    accidentally."""
    with pytest.raises(TypeError, match="LockedConnection"):
        archive_synthesis_via_db(
            None, _inputs(), investigation_id="inv-test",
        )


# ---------------------------------------------------------------------------
# 7. Payload validators reject unknown enum values
# ---------------------------------------------------------------------------


def test_synthesis_archived_payload_rejects_unknown_status():
    with pytest.raises(ValidationError):
        SynthesisArchivedPayload(
            target_question="?",
            synthesis_timestamp=datetime(2026, 5, 16),
            status="archived",  # not in SynthesisStatus
            implicit_recommendation="proceed",
            thesis_token_count=10,
        )


def test_synthesis_archived_payload_rejects_unknown_recommendation():
    with pytest.raises(ValidationError):
        SynthesisArchivedPayload(
            target_question="?",
            synthesis_timestamp=datetime(2026, 5, 16),
            status="passed",
            implicit_recommendation="strong_buy",  # not in SynthesisRecommendation
            thesis_token_count=10,
        )


def test_substrate_manifest_written_rejects_negative_rows():
    with pytest.raises(ValidationError):
        SubstrateManifestWrittenPayload(
            synthesis_timestamp=datetime(2026, 5, 16),
            manifest_rows_written=-1,
            counts_by_kind={"document": 0, "chunk": 0, "node": 0, "edge": 0},
        )
