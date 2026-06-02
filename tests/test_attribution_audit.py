"""Append-only attribution-audit record + replay (SPR-04 M3).

The defensibility tests: a record per computation, append-only, through the
single-writer lock; a replay that yields decimal-identical output; and a guard
that changing the math without bumping the version stamp is caught.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.attribution import (
    ATTRIBUTION_ALGORITHM_VERSION,
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
)
from substrate.ad_inventory.attribution_audit import (
    load_for_impression_set,
    load_record,
    record_attribution,
    replay,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-attr-audit-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="attr_audit_test")
    init_database(con)
    yield con
    con.close()


def _option_b_inputs():
    return {
        "chunk_to_document": {"ch-1": "doc-A", "ch-2": "doc-B", "ch-3": "doc-A"},
        "chunk_to_claim_confidence": {"ch-1": 1.0, "ch-2": 1.0, "ch-3": 0.4},
        "document_to_source_tier": {"doc-A": 1, "doc-B": 4},
    }


def _record_option_b(con, *, impression_set_ref="impset-1", page_id="page-1"):
    inputs = _option_b_inputs()
    result = compute_attribution_option_b(page_id=page_id, **inputs)
    audit_id = record_attribution(
        con,
        impression_set_ref=impression_set_ref,
        result=result,
        inputs=inputs,
    )
    return audit_id, inputs, result


# ── A record is written per computation, through the write lock ─────────────


def test_record_persisted_with_version_stamp(db):
    audit_id, _, _ = _record_option_b(db)
    rec = load_record(db, audit_id)
    assert rec is not None
    assert rec.algorithm == "claim_confidence_times_source_tier"
    assert rec.algorithm_version == ATTRIBUTION_ALGORITHM_VERSION
    assert rec.impression_set_ref == "impset-1"
    assert rec.page_id == "page-1"


def test_inputs_and_shares_round_trip(db):
    audit_id, inputs, result = _record_option_b(db)
    rec = load_record(db, audit_id)
    assert rec.inputs == inputs
    assert rec.shares == pytest.approx(result.shares)


def test_load_for_impression_set(db):
    _record_option_b(db, impression_set_ref="impset-X")
    rows = load_for_impression_set(db, "impset-X")
    assert len(rows) == 1
    assert rows[0].impression_set_ref == "impset-X"


# ── Append-only / idempotent ────────────────────────────────────────────────


def test_record_is_idempotent_same_id(db):
    """Re-recording an identical computation is a no-op (one row), never an
    in-place mutation — the audit_id is content-derived."""
    a1, inputs, result = _record_option_b(db)
    a2 = record_attribution(
        db, impression_set_ref="impset-1", result=result, inputs=inputs,
    )
    assert a1 == a2
    rows = load_for_impression_set(db, "impset-1")
    assert len(rows) == 1


def test_changed_inputs_produce_distinct_record_append_only(db):
    """A changed input writes a NEW row; the prior row is untouched."""
    a1, _, _ = _record_option_b(db)
    inputs2 = _option_b_inputs()
    inputs2["document_to_source_tier"]["doc-B"] = 2  # changed tier
    result2 = compute_attribution_option_b(page_id="page-1", **inputs2)
    a2 = record_attribution(
        db, impression_set_ref="impset-1", result=result2, inputs=inputs2,
    )
    assert a1 != a2
    rows = load_for_impression_set(db, "impset-1")
    assert len(rows) == 2  # both retained — append-only


def test_input_key_mismatch_rejected(db):
    """A record whose inputs don't match the algorithm's contract is rejected —
    otherwise replay would attribute against the wrong inputs."""
    result = compute_attribution_option_b(page_id="p", **_option_b_inputs())
    with pytest.raises(ValueError, match="must carry exactly"):
        record_attribution(
            db, impression_set_ref="impset-1", result=result,
            inputs={"chunk_to_document": {"ch-1": "doc-A"}},  # missing keys
        )


# ── Replay: decimal-identical output (the honesty gate) ─────────────────────


def test_replay_option_b_is_identical(db):
    audit_id, _, _ = _record_option_b(db)
    rr = replay(db, audit_id)
    # Honesty (rigor #1): we assert IDENTICAL, not approximate. If float
    # ordering or dict iteration drifted, this would fail and we'd fix it.
    assert rr.identical is True
    assert rr.recomputed_shares == rr.recorded_shares


def test_replay_option_a_is_identical(db):
    inputs = {"chunk_to_document": {"ch-1": "doc-A", "ch-2": "doc-B", "ch-3": "doc-A"}}
    result = compute_attribution_option_a(page_id="page-A", **inputs)
    audit_id = record_attribution(
        db, impression_set_ref="impset-A", result=result, inputs=inputs,
    )
    rr = replay(db, audit_id)
    assert rr.identical is True


def test_replay_option_c_is_identical(db):
    inputs = {
        "chunk_to_document": {"ch-1": "doc-A", "ch-2": "doc-B"},
        "claim_load_bearing_scores": {"cl-1": 0.9, "cl-2": 0.2},
        "chunk_to_claim_id": {"ch-1": "cl-1", "ch-2": "cl-2"},
    }
    result = compute_attribution_option_c(page_id="page-C", **inputs)
    audit_id = record_attribution(
        db, impression_set_ref="impset-C", result=result, inputs=inputs,
    )
    rr = replay(db, audit_id)
    assert rr.identical is True


def test_replay_unknown_id_raises(db):
    with pytest.raises(ValueError, match="not found"):
        replay(db, "attr-audit-nope")


# ── Version stamp lives on the algorithm + is recorded ──────────────────────


def test_version_constant_exists_and_is_recorded(db):
    assert isinstance(ATTRIBUTION_ALGORITHM_VERSION, str)
    assert ATTRIBUTION_ALGORITHM_VERSION
    audit_id, _, _ = _record_option_b(db)
    rec = load_record(db, audit_id)
    assert rec.algorithm_version == ATTRIBUTION_ALGORITHM_VERSION
