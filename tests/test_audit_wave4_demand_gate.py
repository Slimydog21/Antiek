"""Audit wave 4 — demand gate (C16, C17).

C16: the verdict was satisfiable by the operator. Third-party / agent events
counted with no actor or evidence check, the round-trip operator exclusion was
an exact-string denylist ('', 'OPERATOR', ' operator' all got past), and
neither the pre-registered window nor "exported by a non-operator" was checked.

C17: nothing in production emits demand-gate events, so the verdict ran on an
empty list and returned RETIRE ("no admissible signal observed") — missing
instrumentation reported as a finding about demand. The detector's own event
was also thrown away by ``ingest_antiek``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import services.demand_gate.analysis as analysis
from services.demand_gate.analysis import (
    AGENT_UNPROMPTED,
    RETIRE,
    ROUNDTRIP,
    SUSTAIN,
    THIRD_PARTY_READER,
    compute_verdict,
)
from services.demand_gate.events import (
    EXPORT_OFFERED,
    assert_no_content,
    build_export_offered,
    build_re_import_detected,
)
from services.demand_gate.roundtrip_detector import ExportRegistry, classify_roundtrip

OP = "operator"
TESTERS = frozenset({"tester-1", "tester-2", "tester-3", "tester-4", "tester-5"})
START = datetime(2026, 10, 1, tzinfo=UTC)
END = START + timedelta(days=14)
IN = (START + timedelta(days=3)).isoformat()
BEFORE = (START - timedelta(days=1)).isoformat()
AFTER = (END + timedelta(hours=1)).isoformat()

# The neutral dual offer reached a pinned tester inside the window, so the
# window was actually instrumented and a verdict is computable.
OFFERED = {
    "action_type": EXPORT_OFFERED,
    "user_id": "tester-1",
    "surface": "synthesis_share",
    "formats": ["html", "antiek"],
    "emitted_at": IN,
}


def _verdict(events, **overrides):
    kwargs = {
        "operator_user_id": OP,
        "tester_ids": TESTERS,
        "window_start": START,
        "window_end": END,
    }
    kwargs.update(overrides)
    return compute_verdict([OFFERED, *events], **kwargs)


def _rt(user_id, *, exported_by=("tester-2",), emitted_at=IN):
    return {
        "action_type": ROUNDTRIP,
        "document_id": "d",
        "classification": "traveled_and_changed",
        "user_id": user_id,
        "exported_by": list(exported_by),
        "emitted_at": emitted_at,
    }


# ── C16: the operator cannot satisfy the gate ──


def test_positive_control_pinned_tester_roundtrip_sustains():
    v = _verdict([_rt("tester-3")])
    assert v.verdict == SUSTAIN and v.counts["organic_roundtrip"] == 1


@pytest.mark.parametrize("actor", [OP, "", " operator", "OPERATOR", "anonymous", None])
def test_roundtrip_actor_must_be_a_pinned_tester(actor):
    # Allowlist, not denylist: case/padding variants of the operator, an empty
    # actor, and an unknown actor are all not "a pinned non-operator tester".
    v = _verdict([_rt(actor)])
    assert v.verdict == RETIRE and v.counts["organic_roundtrip"] == 0


@pytest.mark.parametrize("exported_by", [(), (OP,), ("OPERATOR",), ("stranger",)])
def test_roundtrip_must_have_been_exported_by_a_pinned_tester(exported_by):
    # "exported by a non-operator" (pre-registered criterion 1): the operator
    # exporting and a tester merely re-importing is not organic demand.
    v = _verdict([_rt("tester-3", exported_by=exported_by)])
    assert v.verdict == RETIRE


@pytest.mark.parametrize("emitted_at", [BEFORE, AFTER, None, "not-a-date", "2026-10-04T00:00:00"])
def test_signal_outside_the_window_or_undated_does_not_count(emitted_at):
    # "observed in the window": out-of-window, undated, unparseable, and
    # timezone-naive stamps are all inadmissible (fail closed).
    v = _verdict([_rt("tester-3", emitted_at=emitted_at)])
    assert v.verdict == RETIRE


@pytest.mark.parametrize("action_type,who_key", [(THIRD_PARTY_READER, "tool"), (AGENT_UNPROMPTED, "agent")])
def test_operator_emitted_third_party_and_agent_events_do_not_sustain(action_type, who_key):
    for actor in (OP, "OPERATOR", " operator ", "", None):
        ev = {"action_type": action_type, who_key: "x", "evidence_ref": "https://e/1",
              "user_id": actor, "emitted_at": IN}
        assert _verdict([ev]).verdict == RETIRE, actor


@pytest.mark.parametrize("action_type,who_key", [(THIRD_PARTY_READER, "tool"), (AGENT_UNPROMPTED, "agent")])
def test_third_party_and_agent_events_need_evidence_and_the_window(action_type, who_key):
    good = {"action_type": action_type, who_key: "someones-parser",
            "evidence_ref": "https://github.com/someone/parser/commit/abc",
            "user_id": "someone-else", "emitted_at": IN}
    assert _verdict([good]).verdict == SUSTAIN  # positive control
    for drop in (who_key, "evidence_ref", "emitted_at"):
        ev = {k: v for k, v in good.items() if k != drop}
        assert _verdict([ev]).verdict == RETIRE, drop
    assert _verdict([{**good, "evidence_ref": "  "}]).verdict == RETIRE
    assert _verdict([{**good, "emitted_at": AFTER}]).verdict == RETIRE


def test_tester_set_cannot_smuggle_in_the_operator():
    with pytest.raises(analysis.GateNotRunnable):
        _verdict([], tester_ids=TESTERS | {" Operator"})


@pytest.mark.parametrize("n", [0, 4, 16])
def test_n_testers_is_the_preregistered_5_to_15(n):
    testers = frozenset(f"t-{i}" for i in range(n))
    with pytest.raises(analysis.GateNotRunnable):
        _verdict([], tester_ids=testers)


def test_window_is_the_fixed_two_weeks():
    with pytest.raises(analysis.GateNotRunnable):  # an extension is a finding, not a parameter
        _verdict([], window_end=END + timedelta(days=1))
    with pytest.raises(analysis.GateNotRunnable):  # naive datetimes cannot be compared honestly
        _verdict([], window_start=START.replace(tzinfo=None),
                 window_end=END.replace(tzinfo=None))


def test_registry_records_the_exporter_and_the_event_carries_it():
    reg = ExportRegistry()
    doc = {"type": "doc", "content": [{"type": "paragraph"}]}
    reg.record_export("doc-1", doc, exporter_id="tester-2")
    rt = classify_roundtrip("doc-1", doc, reg, user_id="tester-3")
    assert rt.event is not None
    assert rt.event["exported_by"] == ["tester-2"]
    assert rt.event["emitted_at"]  # stamped, so the window filter can apply
    assert_no_content(rt.event)
    with pytest.raises(ValueError):
        reg.record_export("doc-1", doc, exporter_id="  ")


# Exporter attribution is per exported CONTENT, not per document: a tester
# re-importing the operator's exact bytes is the operator's export coming back,
# not "exported by a non-operator" (REWORK: the registry keyed exporters by
# document_id only, so t1 having exported some other version laundered it).
_VERSION_A = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "A"}]}]}
_VERSION_B = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "B"}]}]}
_VERSION_C = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "C"}]}]}


def _two_version_registry():
    reg = ExportRegistry()
    reg.record_export("d", _VERSION_A, exporter_id="tester-1")
    reg.record_export("d", _VERSION_B, exporter_id=OP)
    return reg


def test_unmodified_reimport_of_the_operators_export_does_not_sustain():
    rt = classify_roundtrip("d", _VERSION_B, _two_version_registry(), user_id="tester-2")
    assert rt.classification == "returned_unmodified"
    assert rt.event is not None and rt.event["exported_by"] == [OP]
    assert _verdict([{**rt.event, "emitted_at": IN}]).verdict == RETIRE


def test_unmodified_reimport_of_a_testers_export_is_attributed_to_that_tester():
    # Positive control on the same registry: the tester's own bytes coming back
    # are attributed to that tester alone and still sustain.
    rt = classify_roundtrip("d", _VERSION_A, _two_version_registry(), user_id="tester-2")
    assert rt.classification == "returned_unmodified"
    assert rt.event is not None and rt.event["exported_by"] == ["tester-1"]
    assert _verdict([{**rt.event, "emitted_at": IN}]).verdict == SUSTAIN


def test_changed_reimport_with_an_operator_among_the_exporters_does_not_sustain():
    # Edited bytes match no export, so the source is ambiguous: every exporter of
    # the document rides along, and an operator among them refuses the signal.
    rt = classify_roundtrip("d", _VERSION_C, _two_version_registry(), user_id="tester-2")
    assert rt.classification == "traveled_and_changed"
    assert rt.event is not None and rt.event["exported_by"] == [OP, "tester-1"]
    assert _verdict([{**rt.event, "emitted_at": IN}]).verdict == RETIRE


@pytest.mark.parametrize("operator_variant", [OP, "OPERATOR", " operator "])
def test_roundtrip_exported_by_a_tester_and_the_operator_does_not_count(operator_variant):
    v = _verdict([_rt("tester-3", exported_by=("tester-2", operator_variant))])
    assert v.verdict == RETIRE and v.counts["organic_roundtrip"] == 0


def test_tester_set_cannot_pad_n_with_spellings_of_one_id():
    variants = frozenset({"alice", "Alice", "ALICE", " alice", "alice "})
    assert len(variants) == 5  # meets N >= 5 on raw strings
    # One real person, fully instrumented, "round-tripping" to herself: without
    # the collision check this is a SUSTAIN from a panel of one.
    events = [{**OFFERED, "user_id": "alice"}, _rt("Alice", exported_by=("alice",))]
    with pytest.raises(analysis.GateNotRunnable, match="variants"):
        _verdict(events, tester_ids=variants)


def test_builder_rejects_a_blank_actor():
    with pytest.raises(ValueError):
        build_re_import_detected("d", "returned_unmodified", "h", user_id="")
    with pytest.raises(ValueError):
        build_re_import_detected("d", "returned_unmodified", "h", user_id="   ")


# ── C17: an uninstrumented window is refused, not RETIREd ──


def test_zero_events_is_refused_not_retired():
    with pytest.raises(analysis.GateNotRunnable, match="export_offered"):
        compute_verdict([], operator_user_id=OP, tester_ids=TESTERS,
                        window_start=START, window_end=END)


def test_offers_only_to_the_operator_or_outside_the_window_are_refused():
    for offered in ({**OFFERED, "user_id": OP}, {**OFFERED, "emitted_at": BEFORE}):
        with pytest.raises(analysis.GateNotRunnable):
            compute_verdict([offered], operator_user_id=OP, tester_ids=TESTERS,
                            window_start=START, window_end=END)


def test_instrumented_window_with_no_signal_is_a_real_retire():
    v = _verdict([])
    assert v.verdict == RETIRE
    assert "1 export offer" in v.rationale


def test_builder_made_offer_is_countable():
    # The builders stamp emitted_at, so an offer built through the privacy gate
    # is admissible coverage without hand-editing.
    offered = build_export_offered("tester-1", "notebook_share", ("html", "antiek"),
                                   emitted_at=START + timedelta(days=1))
    assert_no_content(offered)
    v = compute_verdict([offered], operator_user_id=OP, tester_ids=TESTERS,
                        window_start=START, window_end=END)
    assert v.verdict == RETIRE


def test_ingest_keeps_the_detection_event(tmp_path):
    from services.antiek_format import read_antiek
    from services.antiek_format.native_writer import WriterInput, write_antiek
    from services.antiek_format.signature import ensure_keypair
    from services.ingestion.ingest_antiek import ingest_antiek

    keypair = ensure_keypair("tester-2", db_path=str(tmp_path / "k.duckdb"))

    def container(text):
        return write_antiek(
            WriterInput(
                notebook_id="nb", user_id="tester-2", document_id="doc-1",
                parent_document_id=None, content_class="notebook", title="t",
                content_tiptap={"type": "doc", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": text}]}]},
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            keypair=keypair,
        )

    reg = ExportRegistry()
    first = read_antiek(container("original"))
    reg.record_export(first.document_id, first.content_tiptap, exporter_id="tester-2")
    result = ingest_antiek(container("EDITED"), export_registry=reg, user_id="tester-3")
    assert result.roundtrip == "traveled_and_changed"
    ev = result.roundtrip_event
    assert ev is not None and ev["user_id"] == "tester-3" and ev["exported_by"] == ["tester-2"]
    # ...and the kept event is exactly what the verdict consumes.
    ev = {**ev, "emitted_at": IN}
    assert _verdict([ev]).verdict == SUSTAIN
