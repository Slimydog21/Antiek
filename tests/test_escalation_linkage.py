"""Tests for the escalation-linkage (recursive-chase accountability) axis.

Exercises the load-bearing invariants: linkage coverage over escalated questions,
the no-escalated-questions honesty rule (None never fabricated), the orphaned-
escalation leak surface, the unescalated-reservation oddity, the partition, and
purity/immutability/determinism.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.escalation_linkage import (
    EscalationLinkageReport,
    measure_escalation_linkage,
)
from substrate.research_artifact.schema import (
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    questions: list[tuple[str, bool, str | None]],
    *,
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    """Build an artifact from (node_id, escalated, reserved_child_id) tuples."""
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        open_questions=[
            ArtifactQuestion(
                node_id=nid,
                text=f"question {nid}",
                escalated=esc,
                reserved_child_investigation_id=res,
            )
            for nid, esc, res in questions
        ],
    )


# --- core linkage ---------------------------------------------------------


def test_all_linked_yields_full_linkage() -> None:
    art = _artifact(
        [
            ("q1", True, "child-inv-1"),
            ("q2", True, "child-inv-2"),
        ]
    )
    report = measure_escalation_linkage(art)
    assert report.escalated_count == 2
    assert report.linked_count == 2
    assert report.orphaned_count == 0
    assert report.escalation_linkage == pytest.approx(1.0)
    assert report.linked_escalation_ids == ("q1", "q2")
    assert report.orphaned_escalation_ids == ()


def test_all_orphaned_yields_zero_linkage() -> None:
    art = _artifact([("q1", True, None), ("q2", True, None)])
    report = measure_escalation_linkage(art)
    assert report.escalated_count == 2
    assert report.linked_count == 0
    assert report.orphaned_count == 2
    assert report.escalation_linkage == pytest.approx(0.0)
    assert report.orphaned_escalation_ids == ("q1", "q2")
    assert any("LEAK" in n for n in report.notes)


def test_mixed_linkage() -> None:
    art = _artifact(
        [
            ("q1", True, "child-inv-1"),   # linked
            ("q2", True, None),            # orphaned (leak)
            ("q3", True, "child-inv-3"),   # linked
        ]
    )
    report = measure_escalation_linkage(art)
    assert report.escalation_linkage == pytest.approx(2 / 3)
    assert report.linked_escalation_ids == ("q1", "q3")
    assert report.orphaned_escalation_ids == ("q2",)


def test_linkage_in_unit_interval() -> None:
    for art in [
        _artifact([("q1", True, "c1")]),
        _artifact([("q1", True, None)]),
        _artifact([("q1", True, "c1"), ("q2", True, None)]),
    ]:
        link = measure_escalation_linkage(art).escalation_linkage
        assert link is not None and 0.0 <= link <= 1.0


# --- honesty rules: no escalated questions --------------------------------


def test_no_escalated_questions_yields_none_linkage() -> None:
    art = _artifact(
        [
            ("q1", False, None),
            ("q2", False, None),
        ]
    )
    report = measure_escalation_linkage(art)
    assert report.escalated_count == 0
    assert report.linked_count == 0
    assert report.orphaned_count == 0
    assert report.escalation_linkage is None
    assert report.orphaned_escalation_ids == ()
    assert any("not measurable" in n for n in report.notes)


def test_empty_artifact_yields_none_linkage() -> None:
    report = measure_escalation_linkage(_artifact([]))
    assert report.question_count == 0
    assert report.escalated_count == 0
    assert report.escalation_linkage is None
    assert report.orphaned_escalation_ids == ()


# --- whitespace reservation treated as absent -----------------------------


def test_whitespace_only_reservation_treated_as_orphaned() -> None:
    art = _artifact([("q1", True, "   "), ("q2", True, "child-inv-2")])
    report = measure_escalation_linkage(art)
    assert report.orphaned_escalation_ids == ("q1",)
    assert report.linked_escalation_ids == ("q2",)
    assert report.escalation_linkage == pytest.approx(0.5)


def test_empty_string_reservation_treated_as_orphaned() -> None:
    art = _artifact([("q1", True, "")])
    report = measure_escalation_linkage(art)
    assert report.orphaned_count == 1
    assert report.linked_count == 0
    assert report.escalation_linkage == pytest.approx(0.0)


# --- unescalated-reservation oddity ---------------------------------------


def test_unescalated_reservation_is_an_oddity_not_a_leak() -> None:
    art = _artifact(
        [
            ("q1", True, "child-inv-1"),     # linked (normal)
            ("q2", False, "child-inv-2"),    # reservation but NOT escalated (oddity)
        ]
    )
    report = measure_escalation_linkage(art)
    assert report.escalated_count == 1
    assert report.linked_count == 1
    assert report.orphaned_count == 0
    assert report.escalation_linkage == pytest.approx(1.0)
    assert report.unescalated_reservation_ids == ("q2",)
    assert any("INTEGRITY ODDITY" in n for n in report.notes)
    # the oddity does NOT pollute the leak surface
    assert "q2" not in report.orphaned_escalation_ids


def test_no_oddity_note_when_clean() -> None:
    art = _artifact([("q1", True, "c1"), ("q2", False, None)])
    report = measure_escalation_linkage(art)
    assert report.unescalated_reservation_ids == ()
    assert not any("INTEGRITY ODDITY" in n for n in report.notes)


# --- partition & subset ---------------------------------------------------


def test_escalation_partition_complete_and_disjoint() -> None:
    art = _artifact(
        [
            ("q1", True, "c1"),
            ("q2", True, None),
            ("q3", True, "c3"),
            ("q4", False, None),
        ]
    )
    report = measure_escalation_linkage(art)
    union = set(report.linked_escalation_ids) | set(report.orphaned_escalation_ids)
    assert union == {"q1", "q2", "q3"}
    assert not (set(report.linked_escalation_ids) & set(report.orphaned_escalation_ids))
    assert report.linked_count + report.orphaned_count == report.escalated_count


def test_orphaned_subset_of_escalated() -> None:
    art = _artifact([("q1", True, None), ("q2", False, None)])
    report = measure_escalation_linkage(art)
    # orphaned ids are by construction escalated; verify the invariant holds.
    assert set(report.orphaned_escalation_ids).issubset(
        {q.node_id for q in art.open_questions if q.escalated}
    )


def test_unescalated_reservation_disjoint_from_escalation_surfaces() -> None:
    art = _artifact(
        [
            ("q1", True, "c1"),
            ("q2", False, "c2"),
        ]
    )
    report = measure_escalation_linkage(art)
    esc = set(report.linked_escalation_ids) | set(report.orphaned_escalation_ids)
    assert not (esc & set(report.unescalated_reservation_ids))


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    art = _artifact([("q1", True, "c1")], investigation_id="inv-777")
    assert measure_escalation_linkage(art).artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    assert measure_escalation_linkage(_artifact([("q1", True, "c1")])).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_escalation_linkage(_artifact([("q1", True, "c1")]))
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.escalation_linkage = 0.0  # type: ignore[misc]


def test_determinism_same_artifact_same_report() -> None:
    art = _artifact([("q1", True, "c1"), ("q2", True, None)])
    assert measure_escalation_linkage(art) == measure_escalation_linkage(art)


def test_isinstance_report_type() -> None:
    art = _artifact([("q1", True, "c1")])
    assert isinstance(measure_escalation_linkage(art), EscalationLinkageReport)


def test_notes_describe_findings() -> None:
    art = _artifact([("q1", True, None), ("q2", False, "c2")])
    joined = " | ".join(measure_escalation_linkage(art).notes)
    assert "structural" in joined.lower()
    assert "leak" in joined.lower()
    assert "integrity oddity" in joined.lower()


def test_non_escalated_without_reservation_is_baseline_not_leak() -> None:
    # A normal open question (not escalated, no reservation) must never appear
    # in any surface and must not affect the linkage ratio.
    art = _artifact(
        [
            ("q1", True, "c1"),
            ("q2", False, None),
            ("q3", False, None),
        ]
    )
    report = measure_escalation_linkage(art)
    assert report.escalation_linkage == pytest.approx(1.0)
    assert "q2" not in report.orphaned_escalation_ids
    assert "q3" not in report.orphaned_escalation_ids
    assert "q2" not in report.unescalated_reservation_ids


# --- public API -----------------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import escalation_linkage as mod

    assert set(mod.__all__) == {
        "EscalationLinkageReport",
        "measure_escalation_linkage",
    }
    assert dataclasses.is_dataclass(mod.EscalationLinkageReport)
