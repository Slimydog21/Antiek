"""SPR-02 measurement log — writer validation, reader compat, reconstruction.

What this file proves (one test per claim, adversarially):

1. WRITER-REJECTS (rubber-stamp lens): the writer rejects each invalid
   case — (a) out-of-range confidence, (b) missing required field,
   (c) negative cost, (d) unknown task_class — and EACH reject is
   proven to RAISE and WRITE NOTHING (the file is absent or unchanged).
   A writer that only accepts good records proves nothing; these
   negative tests are mandatory.

2. READER-COMPAT (schema-leak/compat lens): a MIXED-version fixture
   (v27 old-style records with fewer fields + v28 new measurement
   records with the full field set + a forward-future record with an
   EXTRA unknown field) round-trips through the reader without
   crashing. The reader tolerates older versions AND unknown fields.

3. RECONSTRUCTION-COMPLETENESS (INV-2): given a fixture with MULTIPLE
   investigations, ``reconstruct_trajectory`` returns ONLY the requested
   investigation's records (no bleed) in EMISSION ORDER. The provider
   trajectory is fully rebuildable from the log.

4. DETERMINISM/ATOMICITY: ``from_research_result`` deterministically
   maps a SPR-01 ``ResearchResult`` to a record carrying ONLY normalized
   fields (INV-4 — no raw payload shape leaks). Observed cost/latency are
   distinct from estimates (the record carries the result's observed
   values, not the CostModel estimates). Append is atomic per line (a
   reject writes nothing — proven by the negative tests checking the
   file is untouched).

No network. No live provider calls. The stub provider is not even used
— the tests construct ``ResearchResult`` fixtures directly because the
measurement layer measures the RESULT, not the provider.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from research.measurement import (
    MEASUREMENT_RECORD_SCHEMA_VERSION,
    MeasurementLogError,
    MeasurementRecord,
    Outcome,
    TaskClass,
    append_measurement,
    classify,
    from_research_result,
    read_measurements,
    reconstruct_trajectory,
)
from research.measurement.log import _measurements_path
from research.providers.types import RawRef, ResearchResult, Source
from substrate.schemas.events import ActionType, EVENT_SCHEMA_VERSION


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _make_result(
    *,
    provider: str = "exa",
    tier: str = "deep",
    cost: float = 0.0023,
    latency: int = 1450,
    confidence: float = 0.9,
    handle: str = "exa:raw:abc123",
) -> ResearchResult:
    """Build a SPR-01 ResearchResult fixture with normalized fields."""
    return ResearchResult(
        fields={"answer": "42"},
        field_citations={"answer": [Source(url="https://example.com", title="Ex")]},
        confidence=confidence,
        cost=cost,
        latency=latency,
        provider=provider,
        tier=tier,
        raw_ref=RawRef(handle=handle, provider=provider),
    )


def _make_record(
    *,
    investigation_id: str = "inv-001",
    sub_question_id: str = "sq-1",
    task_class: str = TaskClass.STRUCTURED_EXTRACT.value,
    provider: str = "exa",
    tier: str = "deep",
    cost_usd: float = 0.0023,
    latency_ms: int = 1450,
    confidence: float = 0.9,
    outcome: str = Outcome.SUCCESS.value,
    correlation_id: str = "exa:raw:abc123",
    emitted_at: str = "2026-06-26T12:00:00Z",
    schema_version: int = MEASUREMENT_RECORD_SCHEMA_VERSION,
) -> MeasurementRecord:
    """Build a valid MeasurementRecord fixture with sane defaults."""
    return MeasurementRecord(
        schema_version=schema_version,
        investigation_id=investigation_id,
        sub_question_id=sub_question_id,
        task_class=task_class,
        provider=provider,
        tier=tier,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        confidence=confidence,
        outcome=outcome,
        correlation_id=correlation_id,
        emitted_at=emitted_at,
    )


@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    """Isolated events dir per test — no bleed into ~/.antiek."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(d))
    return str(d)


# --------------------------------------------------------------------------
# Schema + ActionType surface (M2)
# --------------------------------------------------------------------------


def test_event_schema_version_bumped_to_28():
    """The v28 bump is the additive ActionType addition. Monotonic floor."""
    assert EVENT_SCHEMA_VERSION == 28


def test_research_provider_measured_action_type_exists():
    """The new ActionType member follows the existing naming convention
    (dotted, lowercase, verb-ish)."""
    assert ActionType.RESEARCH_PROVIDER_MEASURED.value == "research.provider.measured"
    # It's a real enum member, not a stray string.
    assert ActionType.RESEARCH_PROVIDER_MEASURED in ActionType


def test_v28_bump_is_additive_no_existing_member_removed():
    """A representative sample of pre-v28 members still exist (the bump
    added a member; it did not remove or retype any)."""
    for member in (
        ActionType.DISPATCH_CALL,
        ActionType.DOCUMENT_LOADED,
        ActionType.GRAPH_NODE_INSERTED,
        ActionType.SYNTHESIS_ARCHIVED,
        ActionType.DOCUMENT_CONTENT_CLASS_DEFAULTED,  # the v27 member
    ):
        assert member in ActionType


def test_outcome_enum_has_five_distinct_members():
    vals = {o.value for o in Outcome}
    assert vals == {"success", "partial", "failed", "timeout", "budget_exceeded"}


def test_measurement_record_is_frozen():
    """Frozen dataclass — a caller cannot mutate after the writer
    serializes (a mutated record would diverge from the log)."""
    rec = _make_record()
    with pytest.raises(Exception):  # FrozenInstanceError
        rec.cost_usd = 999.0  # type: ignore[misc]


def test_measurement_record_has_no_raw_payload_fields():
    """INV-4: the record carries only normalized fields. It must NOT have
    a `fields`, `field_citations`, or any provider-specific-shape field.
    The raw payload is behind the correlation_id handle, not on the record."""
    rec = _make_record()
    field_names = {f for f in dir(rec) if not f.startswith("_") and not callable(getattr(rec, f))}
    # The normalized field set — no answer payload, no citations, no raw dict.
    assert "fields" not in field_names
    assert "field_citations" not in field_names
    assert "raw_ref" not in field_names
    # correlation_id IS present (the opaque handle — a string, not a dict).
    assert "correlation_id" in field_names
    assert isinstance(rec.correlation_id, str)


# --------------------------------------------------------------------------
# from_research_result — INV-4 normalized mapping (determinism lens)
# --------------------------------------------------------------------------


def test_from_research_result_carries_only_normalized_fields():
    """The helper reads exclusively from the normalized ResearchResult.
    The resulting record has provider/tier/cost/latency/confidence from
    the result and correlation_id == raw_ref.handle — and NOT the
    result's fields/field_citations (the answer payload stays off the
    measurement record)."""
    result = _make_result(
        provider="parallel", tier="ultra8x", cost=0.05, latency=3200,
        confidence=0.75, handle="parallel:raw:xyz789",
    )
    rec = from_research_result(
        result,
        investigation_id="inv-002",
        sub_question_id="sq-9",
        task_class=TaskClass.MULTI_HOP.value,
        outcome=Outcome.PARTIAL,
    )
    assert rec.provider == "parallel"
    assert rec.tier == "ultra8x"
    assert rec.cost_usd == 0.05
    assert rec.latency_ms == 3200
    assert rec.confidence == 0.75
    assert rec.outcome == "partial"
    assert rec.task_class == "multi_hop"
    assert rec.investigation_id == "inv-002"
    assert rec.sub_question_id == "sq-9"
    assert rec.correlation_id == "parallel:raw:xyz789"
    assert rec.schema_version == MEASUREMENT_RECORD_SCHEMA_VERSION
    # emitted_at is a real ISO 8601 UTC string with Z suffix.
    assert rec.emitted_at.endswith("Z")
    assert "T" in rec.emitted_at


def test_from_research_result_observed_not_estimated():
    """The record carries the ResearchResult's OBSERVED cost/latency
    (post-call), NOT the CostModel estimates. This proves the
    observed-vs-estimate distinction: the result's cost is what was
    actually spent; the CostModel's cost_usd_estimate is a different
    field on a different object and never enters this record."""
    from research.providers.types import CostModel

    result = _make_result(cost=0.0123, latency=987)
    # A CostModel with DIFFERENT estimates — the record must carry the
    # result's observed values, not these estimates.
    _estimate = CostModel(tier="deep", cost_usd_estimate=99.99, latency_ms_estimate=99999)

    rec = from_research_result(
        result,
        investigation_id="inv-est",
        sub_question_id="sq-est",
        task_class=TaskClass.STRUCTURED_EXTRACT.value,
        outcome=Outcome.SUCCESS,
    )
    assert rec.cost_usd == 0.0123  # observed, NOT 99.99
    assert rec.latency_ms == 987   # observed, NOT 99999


def test_from_research_result_rejects_non_research_result():
    """A non-normalized input (a raw dict) is rejected at the source —
    silently accepting it would let a raw payload shape leak into the
    record (INV-4 breach)."""
    with pytest.raises(TypeError, match="ResearchResult"):
        from_research_result(
            {"provider": "exa", "cost": 0.01},  # type: ignore[arg-type]
            investigation_id="inv",
            sub_question_id="sq",
            task_class=TaskClass.STRUCTURED_EXTRACT.value,
            outcome=Outcome.SUCCESS,
        )


def test_from_research_result_deterministic_with_explicit_timestamp():
    """Given the same inputs + explicit emitted_at, the helper produces
    byte-identical records (determinism)."""
    from datetime import datetime, UTC

    result = _make_result()
    ts = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    r1 = from_research_result(
        result, investigation_id="inv", sub_question_id="sq",
        task_class=TaskClass.STRUCTURED_EXTRACT.value, outcome=Outcome.SUCCESS,
        emitted_at=ts,
    )
    r2 = from_research_result(
        result, investigation_id="inv", sub_question_id="sq",
        task_class=TaskClass.STRUCTURED_EXTRACT.value, outcome=Outcome.SUCCESS,
        emitted_at=ts,
    )
    assert r1 == r2


# --------------------------------------------------------------------------
# Writer — happy path + atomicity (writes one line per record)
# --------------------------------------------------------------------------


def test_append_measurement_writes_one_jsonl_line(events_dir):
    rec = _make_record()
    cid = append_measurement(rec)
    assert cid == rec.correlation_id
    path = _measurements_path(rec.investigation_id, events_dir=events_dir)
    assert os.path.exists(path)
    lines = open(path).read().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["correlation_id"] == rec.correlation_id
    assert row["provider"] == "exa"
    assert row["schema_version"] == MEASUREMENT_RECORD_SCHEMA_VERSION


def test_append_multiple_records_preserves_order(events_dir):
    """Append order == emission order. Three records appended in sequence
    are read back in the same sequence (INV-2 reconstruction relies on this)."""
    base = "2026-06-26T12:00:0"
    recs = [
        _make_record(correlation_id="c1", emitted_at=f"{base}1Z"),
        _make_record(correlation_id="c2", emitted_at=f"{base}2Z"),
        _make_record(correlation_id="c3", emitted_at=f"{base}3Z"),
    ]
    for r in recs:
        append_measurement(r)
    rows = read_measurements("inv-001")
    assert [r["correlation_id"] for r in rows] == ["c1", "c2", "c3"]


def test_append_accepts_dict_record(events_dir):
    """Dict acceptance for adapters that build rows incrementally —
    validated identically to a dataclass."""
    data = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-dict",
        "sub_question_id": "sq-d",
        "task_class": TaskClass.BROAD_GATHER.value,
        "provider": "stub",
        "tier": "basic",
        "cost_usd": 0.0,
        "latency_ms": 5,
        "confidence": 0.5,
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "stub:raw:1",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    append_measurement(data)
    rows = read_measurements("inv-dict")
    assert len(rows) == 1
    assert rows[0]["correlation_id"] == "stub:raw:1"


# --------------------------------------------------------------------------
# WRITER-REJECTS (mandatory negative tests — rubber-stamp lens)
#
# Each invalid case is PROVEN to (1) raise MeasurementLogError naming the
# field and (2) write NOTHING (file absent or line count unchanged).
# --------------------------------------------------------------------------


def _assert_wrote_nothing(events_dir, investigation_id: str):
    """Assert no file exists OR the file has zero measurement lines for
    this investigation. A reject must never leave a malformed line."""
    path = _measurements_path(investigation_id, events_dir=events_dir)
    if os.path.exists(path):
        lines = [l for l in open(path).read().splitlines() if l.strip()]
        assert lines == [], (
            f"writer wrote a line despite reject — file {path} has "
            f"{len(lines)} line(s): {lines!r}"
        )


def test_writer_rejects_out_of_range_confidence_high(events_dir):
    """(a) confidence > 1.0 — rejected, nothing written."""
    rec = _make_record(confidence=1.5)
    with pytest.raises(MeasurementLogError, match="confidence"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_out_of_range_confidence_low(events_dir):
    """(a) confidence < 0.0 — rejected, nothing written."""
    rec = _make_record(confidence=-0.1)
    with pytest.raises(MeasurementLogError, match="confidence"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_nan_confidence(events_dir):
    """NaN confidence is not a valid probability — rejected."""
    rec = _make_record(confidence=float("nan"))
    with pytest.raises(MeasurementLogError, match="confidence"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_missing_required_field(events_dir):
    """(b) missing required field — rejected, nothing written. Build via
    dict so we can omit a field (the dataclass forbids it at construction,
    which is itself a guard, but the writer must also reject a dict that
    omits it)."""
    data = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-miss",
        "sub_question_id": "sq-1",
        "task_class": TaskClass.STRUCTURED_EXTRACT.value,
        "provider": "exa",
        "tier": "deep",
        # cost_usd OMITTED
        "latency_ms": 100,
        "confidence": 0.9,
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "exa:raw:x",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    with pytest.raises(MeasurementLogError, match="cost_usd"):
        append_measurement(data)
    _assert_wrote_nothing(events_dir, "inv-miss")


def test_writer_rejects_none_required_field(events_dir):
    """(b-variant) a None on a required field is also a missing value."""
    data = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-none",
        "sub_question_id": "sq-1",
        "task_class": TaskClass.STRUCTURED_EXTRACT.value,
        "provider": "exa",
        "tier": "deep",
        "cost_usd": None,  # None on a required field
        "latency_ms": 100,
        "confidence": 0.9,
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "exa:raw:x",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    with pytest.raises(MeasurementLogError, match="cost_usd"):
        append_measurement(data)
    _assert_wrote_nothing(events_dir, "inv-none")


def test_writer_rejects_negative_cost(events_dir):
    """(c) negative cost — a call cannot earn money — rejected, nothing written."""
    rec = _make_record(cost_usd=-0.01)
    with pytest.raises(MeasurementLogError, match="cost_usd"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_negative_latency(events_dir):
    """Negative latency — a call cannot finish before it starts."""
    rec = _make_record(latency_ms=-1)
    with pytest.raises(MeasurementLogError, match="latency_ms"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_unknown_task_class(events_dir):
    """(d) unknown task_class — rejected, nothing written. A typo must
    not land on disk and poison the trajectory."""
    rec = _make_record(task_class="vibes_based_retrieval")
    with pytest.raises(MeasurementLogError, match="task_class"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_unknown_outcome(events_dir):
    """Unknown outcome — same discipline as task_class."""
    rec = _make_record(outcome="maybe")
    with pytest.raises(MeasurementLogError, match="outcome"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "inv-001")


def test_writer_rejects_empty_investigation_id(events_dir):
    """Empty investigation_id would partition to '.measurements.jsonl' —
    a silent bug. Rejected."""
    rec = _make_record(investigation_id="")
    with pytest.raises(MeasurementLogError, match="investigation_id"):
        append_measurement(rec)
    _assert_wrote_nothing(events_dir, "")


def test_writer_rejects_bool_latency(events_dir):
    """bool is a subtype of int in Python — True would silently
    serialize as 1. The writer rejects it explicitly."""
    data = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-bool",
        "sub_question_id": "sq-1",
        "task_class": TaskClass.STRUCTURED_EXTRACT.value,
        "provider": "exa",
        "tier": "deep",
        "cost_usd": 0.01,
        "latency_ms": True,  # bool, not int
        "confidence": 0.9,
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "exa:raw:x",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    with pytest.raises(MeasurementLogError, match="latency_ms"):
        append_measurement(data)
    _assert_wrote_nothing(events_dir, "inv-bool")


def test_writer_reject_does_not_corrupt_prior_good_records(events_dir):
    """Atomicity: a reject after good records does NOT touch the good
    records already on disk. The file's good lines are intact, and no
    malformed line is appended."""
    good = _make_record(correlation_id="good-1")
    append_measurement(good)
    path = _measurements_path("inv-001", events_dir=events_dir)
    good_lines_before = open(path).read().splitlines()
    # Now attempt a bad append — must raise and leave the file untouched.
    bad = _make_record(confidence=2.0, correlation_id="bad-1")
    with pytest.raises(MeasurementLogError):
        append_measurement(bad)
    good_lines_after = open(path).read().splitlines()
    assert good_lines_after == good_lines_before
    assert len(good_lines_after) == 1
    assert json.loads(good_lines_after[0])["correlation_id"] == "good-1"


# --------------------------------------------------------------------------
# READER-COMPAT — mixed versions + unknown fields (schema-leak/compat lens)
# --------------------------------------------------------------------------


def _write_raw_lines(events_dir, investigation_id, lines):
    """Write raw JSONL lines directly, bypassing the writer — for fixtures
    that simulate older/future schema versions the writer would reject."""
    path = _measurements_path(investigation_id, events_dir=events_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")


def test_reader_tolerates_mixed_versions_roundtrip(events_dir):
    """A MIXED-version fixture: an old-style v27 record (fewer fields),
    a current v28 measurement record (full field set), and a future
    record with an EXTRA unknown field. All parse without crashing."""
    # Old-style record: schema_version lower, MISSING task_class +
    # correlation_id (fields added after v27 in this fixture's fiction).
    # The reader must not crash on the missing fields.
    old_record = {
        "schema_version": 0,  # pre-measurement-schema
        "investigation_id": "inv-mix",
        "sub_question_id": "sq-old",
        "provider": "exa",
        "tier": "deep",
        "cost_usd": 0.001,
        "latency_ms": 800,
        "confidence": 0.6,
        "outcome": "success",
        "emitted_at": "2026-06-26T11:00:00Z",
        # task_class + correlation_id absent (older shape)
    }
    # Current record: full field set.
    current_record = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-mix",
        "sub_question_id": "sq-cur",
        "task_class": TaskClass.MULTI_HOP.value,
        "provider": "parallel",
        "tier": "ultra8x",
        "cost_usd": 0.05,
        "latency_ms": 3200,
        "confidence": 0.8,
        "outcome": Outcome.PARTIAL.value,
        "correlation_id": "parallel:raw:cur",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    # Future record: current fields + an EXTRA unknown field
    # (``retrieval_depth`` — a field a future version might add). The
    # reader must tolerate it (forward-compat) and preserve it.
    future_record = {
        "schema_version": 2,  # future bump
        "investigation_id": "inv-mix",
        "sub_question_id": "sq-fut",
        "task_class": TaskClass.NEEDLE_IN_HAYSTACK.value,
        "provider": "exa",
        "tier": "deep-reasoning",
        "cost_usd": 0.02,
        "latency_ms": 2100,
        "confidence": 0.95,
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "exa:raw:fut",
        "emitted_at": "2026-06-26T13:00:00Z",
        "retrieval_depth": 7,  # unknown future field
    }
    _write_raw_lines(
        events_dir, "inv-mix",
        [json.dumps(old_record), json.dumps(current_record), json.dumps(future_record)],
    )

    rows = read_measurements("inv-mix")
    assert len(rows) == 3
    # Old record: missing fields are absent (backward-compat — reader
    # does not invent defaults).
    assert rows[0]["sub_question_id"] == "sq-old"
    assert "task_class" not in rows[0]
    assert "correlation_id" not in rows[0]
    # Current record: full field set round-trips.
    assert rows[1]["correlation_id"] == "parallel:raw:cur"
    assert rows[1]["task_class"] == "multi_hop"
    # Future record: unknown field preserved (forward-compat).
    assert rows[2]["correlation_id"] == "exa:raw:fut"
    assert rows[2]["retrieval_depth"] == 7


def test_reader_tolerates_unknown_outcome_and_task_class(events_dir):
    """A record from a future version with an outcome/task_class value
    the current enums don't know. The reader parses it as the raw string
    — it does NOT crash (forward-compat for additive enum evolution)."""
    future_record = {
        "schema_version": 2,
        "investigation_id": "inv-unk",
        "sub_question_id": "sq-1",
        "task_class": "semantic_synthesis",  # future class
        "provider": "exa",
        "tier": "deep",
        "cost_usd": 0.01,
        "latency_ms": 100,
        "confidence": 0.7,
        "outcome": "rate_limited",  # future outcome
        "correlation_id": "exa:raw:1",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    _write_raw_lines(events_dir, "inv-unk", [json.dumps(future_record)])
    rows = read_measurements("inv-unk")
    assert len(rows) == 1
    assert rows[0]["outcome"] == "rate_limited"
    assert rows[0]["task_class"] == "semantic_synthesis"


def test_reader_skips_malformed_line_without_crashing(events_dir):
    """A single corrupt JSON line does not poison the read — it's
    skipped (with a warning) and the good lines on either side parse."""
    good1 = json.dumps(_make_record(correlation_id="g1").__dict__)
    bad = "{not valid json"
    good2 = json.dumps(_make_record(correlation_id="g2").__dict__)
    _write_raw_lines(events_dir, "inv-mal", [good1, bad, good2])
    rows = read_measurements("inv-mal")
    assert len(rows) == 2
    assert [r["correlation_id"] for r in rows] == ["g1", "g2"]


def test_reader_returns_empty_for_missing_file(events_dir):
    """No file yet — fresh investigation — empty list, no crash."""
    assert read_measurements("never-existed") == []


def test_reader_normalizes_int_cost_to_float(events_dir):
    """A whole-number cost on the wire (JSON int) normalizes to float so
    downstream consumers expecting a float aren't surprised."""
    data = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-int",
        "sub_question_id": "sq-1",
        "task_class": TaskClass.STRUCTURED_EXTRACT.value,
        "provider": "exa",
        "tier": "deep",
        "cost_usd": 2,  # int on the wire
        "latency_ms": 100,
        "confidence": 0,  # int on the wire
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "exa:raw:1",
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    _write_raw_lines(events_dir, "inv-int", [json.dumps(data)])
    rows = read_measurements("inv-int")
    assert isinstance(rows[0]["cost_usd"], float)
    assert rows[0]["cost_usd"] == 2.0
    assert isinstance(rows[0]["confidence"], float)
    assert rows[0]["confidence"] == 0.0


# --------------------------------------------------------------------------
# RECONSTRUCTION — INV-2 trajectory purity (completeness lens)
# --------------------------------------------------------------------------


def test_reconstruct_returns_ordered_records_for_one_investigation(events_dir):
    """Given a fixture log, reconstruct_trajectory returns the records in
    emission order. Proves the trajectory is rebuildable from the log."""
    recs = [
        _make_record(investigation_id="inv-recon", correlation_id="c3",
                     emitted_at="2026-06-26T12:00:03Z"),
        _make_record(investigation_id="inv-recon", correlation_id="c1",
                     emitted_at="2026-06-26T12:00:01Z"),
        _make_record(investigation_id="inv-recon", correlation_id="c2",
                     emitted_at="2026-06-26T12:00:02Z"),
    ]
    # Append OUT of emission order to prove reconstruct sorts.
    for r in recs:
        append_measurement(r)
    traj = reconstruct_trajectory("inv-recon")
    assert [r.correlation_id for r in traj] == ["c1", "c2", "c3"]
    # Returns typed MeasurementRecord instances, not raw dicts.
    assert all(isinstance(r, MeasurementRecord) for r in traj)


def test_reconstruct_does_not_bleed_across_investigations(events_dir):
    """A fixture with MULTIPLE investigations: reconstruct returns ONLY
    the requested investigation's records — no bleed. This is the
    scoping guarantee (INV-2: the trajectory is per-investigation)."""
    inv_a_recs = [
        _make_record(investigation_id="inv-A", correlation_id="a1",
                     emitted_at="2026-06-26T12:00:01Z"),
        _make_record(investigation_id="inv-A", correlation_id="a2",
                     emitted_at="2026-06-26T12:00:02Z"),
    ]
    inv_b_recs = [
        _make_record(investigation_id="inv-B", correlation_id="b1",
                     emitted_at="2026-06-26T12:00:03Z"),
        _make_record(investigation_id="inv-B", correlation_id="b2",
                     emitted_at="2026-06-26T12:00:04Z"),
        _make_record(investigation_id="inv-B", correlation_id="b3",
                     emitted_at="2026-06-26T12:00:05Z"),
    ]
    for r in inv_a_recs + inv_b_recs:
        append_measurement(r)

    traj_a = reconstruct_trajectory("inv-A")
    traj_b = reconstruct_trajectory("inv-B")

    assert [r.correlation_id for r in traj_a] == ["a1", "a2"]
    assert [r.correlation_id for r in traj_b] == ["b1", "b2", "b3"]
    # No cross-contamination.
    assert all(r.investigation_id == "inv-A" for r in traj_a)
    assert all(r.investigation_id == "inv-B" for r in traj_b)


def test_reconstruct_empty_for_investigation_with_no_records(events_dir):
    assert reconstruct_trajectory("no-records") == []


def test_reconstruct_filters_to_measurement_file_only(events_dir):
    """The measurement file is distinct from the typed-Event trajectory
    ({investigation_id}.jsonl). A typed event in the events dir must NOT
    appear in the measurement reconstruction (they're different record
    kinds in different files)."""
    # Write a typed-Event-style JSONL (the event_log shape) for the same
    # investigation — it must not bleed into measurement reconstruction.
    event_path = os.path.join(events_dir, "inv-both.jsonl")
    with open(event_path, "w") as f:
        f.write(json.dumps({
            "event_id": "evt-1", "investigation_id": "inv-both",
            "action_type": "phase.enter", "payload": {},
        }) + "\n")
    # And a real measurement record.
    append_measurement(_make_record(investigation_id="inv-both", correlation_id="m1"))
    traj = reconstruct_trajectory("inv-both")
    assert [r.correlation_id for r in traj] == ["m1"]
    # The typed event did not leak in.
    assert all(hasattr(r, "cost_usd") for r in traj)


def test_reconstruct_roundtrip_with_from_research_result(events_dir):
    """End-to-end: a ResearchResult -> from_research_result -> append ->
    reconstruct returns a record whose normalized fields match the
    original result. Proves the measurement pipeline preserves the
    normalized shape through write + read."""
    result = _make_result(
        provider="parallel", tier="deep-reasoning", cost=0.075,
        latency=4100, confidence=0.82, handle="parallel:raw:e2e",
    )
    rec = from_research_result(
        result, investigation_id="inv-e2e", sub_question_id="sq-e2e",
        task_class=TaskClass.MULTI_HOP.value, outcome=Outcome.SUCCESS,
    )
    append_measurement(rec)
    traj = reconstruct_trajectory("inv-e2e")
    assert len(traj) == 1
    got = traj[0]
    assert got.provider == "parallel"
    assert got.tier == "deep-reasoning"
    assert got.cost_usd == 0.075
    assert got.latency_ms == 4100
    assert got.confidence == 0.82
    assert got.correlation_id == "parallel:raw:e2e"
    assert got.outcome == "success"
    assert got.task_class == "multi_hop"


# --------------------------------------------------------------------------
# Task-class taxonomy (M3) — deterministic classify rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question, expected", [
    # multi_hop: chaining signals
    ("Who is the current CEO of the company that acquired the startup?",
     TaskClass.MULTI_HOP),
    # needle_in_haystack: locator signals
    ("Which SEC filing first disclosed the Series E round?",
     TaskClass.NEEDLE_IN_HAYSTACK),
    # structured_extract: value-extract signals
    ("What was Anthropic's ARR as of 2024-12-31?",
     TaskClass.STRUCTURED_EXTRACT),
    # broad_gather: survey signals
    ("What are the main open-source vector databases and their features?",
     TaskClass.BROAD_GATHER),
    # unclassified: no signal
    ("Discuss the implications.", TaskClass.UNCLASSIFIED),
    # multi_hop wins over structured_extract (chaining is dominant)
    ("What was the revenue of the company that acquired X?", TaskClass.MULTI_HOP),
    # empty -> unclassified (honest escape)
    ("", TaskClass.UNCLASSIFIED),
    ("   ", TaskClass.UNCLASSIFIED),
])
def test_classify_is_deterministic(question, expected):
    """The classify rule is deterministic: the same question always maps
    to the same class. A reviewer handed these examples would agree."""
    assert classify(question) == expected


def test_classify_priority_multi_hop_beats_structured():
    """The priority order resolves overlaps: a question hitting both
    multi_hop and structured_extract signals classifies as multi_hop
    (the chaining is the structurally dominant feature)."""
    q = "What was the revenue of the company that acquired the startup?"
    assert classify(q) == TaskClass.MULTI_HOP


def test_task_class_has_unclassified_escape_hatch():
    """unclassified exists so nothing is silently force-fit. A question
    the heuristic can't place returns UNCLASSIFIED, not a guess."""
    assert classify("contemplate the aesthetic") == TaskClass.UNCLASSIFIED


def test_task_class_all_values_serializable_as_strings():
    """Every TaskClass value is a plain string (for JSON serialization +
    forward-compat: an unknown class parses as a string)."""
    for tc in TaskClass:
        assert isinstance(tc.value, str)
        assert tc.value  # non-empty


# --------------------------------------------------------------------------
# Atomic-append idiom matches event_log (determinism/atomicity lens)
# --------------------------------------------------------------------------


def test_append_creates_parent_dir_if_missing(events_dir):
    """The writer makedirs the parent (matches event_log _append_jsonl)
    so a fresh events dir works without pre-creation."""
    nested = os.path.join(events_dir, "nested", "deep")
    os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = nested
    try:
        rec = _make_record(investigation_id="inv-nest")
        append_measurement(rec)
        path = _measurements_path("inv-nest", events_dir=nested)
        assert os.path.exists(path)
    finally:
        os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] = events_dir


def test_appended_record_has_no_embedded_newline(events_dir):
    """A record's serialized form is a single line (no embedded newline
    that would split it across two log lines and corrupt the log). The
    writer replaces embedded newlines (defense in depth)."""
    # A correlation_id with a literal newline (shouldn't happen, but if
    # it did, the writer must not let it split the line). Build via dict.
    data = {
        "schema_version": MEASUREMENT_RECORD_SCHEMA_VERSION,
        "investigation_id": "inv-nl",
        "sub_question_id": "sq-1",
        "task_class": TaskClass.STRUCTURED_EXTRACT.value,
        "provider": "exa",
        "tier": "deep",
        "cost_usd": 0.01,
        "latency_ms": 100,
        "confidence": 0.9,
        "outcome": Outcome.SUCCESS.value,
        "correlation_id": "exa:raw:a\nb",  # embedded newline
        "emitted_at": "2026-06-26T12:00:00Z",
    }
    append_measurement(data)
    path = _measurements_path("inv-nl", events_dir=events_dir)
    content = open(path).read()
    # Exactly one record line (one trailing newline) — the embedded
    # newline in the value was escaped during serialization so it did
    # NOT split the record across two log lines.
    assert content.count("\n") == 1
    rows = read_measurements("inv-nl")
    assert len(rows) == 1
    # json.loads round-trips the escaped newline back to a real newline
    # char in the parsed value — that's correct (the value is preserved);
    # what matters is the on-disk line count stayed at 1.
    assert "\n" in rows[0]["correlation_id"]
