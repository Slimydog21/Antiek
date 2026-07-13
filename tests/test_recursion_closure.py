"""Tests for the recursion-closure axis (did the chase resolve the question? ask #1).

Exercises: resolved/unresolved/orphaned/empty_child/unmeasurable/unreserved/
unescalated verdicts, closure ratio + rate, exclusion logic, custom threshold,
purity/immutability, validation. Fixtures use BARE NONSENSE TOKENS.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.recursion_closure import (
    QuestionClosure,
    RecursionClosureError,
    RecursionClosureReport,
    measure_recursion_closure,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _child(
    insights: list[str],
    *,
    investigation_id: str = "child-x",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the child question",
        insights=[
            ArtifactInsight(node_id=f"ci{k}", text=t) for k, t in enumerate(insights)
        ],
        open_questions=[],
    )


def _parent(
    questions: list[ArtifactQuestion],
    *,
    investigation_id: str = "parent-x",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the parent question",
        insights=[ArtifactInsight(node_id="pi0", text="parent insight")],
        open_questions=questions,
    )


def _q(
    text: str,
    *,
    escalated: bool = True,
    child_id: str | None = "child-1",
    node_id: str = "q0",
) -> ArtifactQuestion:
    return ArtifactQuestion(
        node_id=node_id, text=text, escalated=escalated,
        reserved_child_investigation_id=child_id,
    )


# --- core: resolved (child covers the question) --------------------------


def test_resolved() -> None:
    # question "alpha beta"; child insight "alpha beta gamma" covers both -> ratio 1.0
    parent = _parent([_q("alpha beta")])
    children = {"child-1": _child(["alpha beta gamma"])}
    report = measure_recursion_closure(parent, children)
    assert report.resolved_count == 1
    assert report.closure_rate == pytest.approx(1.0)
    assert report.question_closures[0].verdict == "resolved"
    assert report.question_closures[0].closure_ratio == pytest.approx(1.0)
    assert report.question_closures[0].reserved_child_id == "child-1"


def test_partial_coverage_resolved() -> None:
    # question "alpha beta gamma delta"; child covers alpha beta -> 2/4 = 0.5 >= 0.50
    parent = _parent([_q("alpha beta gamma delta")])
    children = {"child-1": _child(["alpha beta epsilon"])}
    report = measure_recursion_closure(parent, children)
    assert report.question_closures[0].verdict == "resolved"
    assert report.question_closures[0].closure_ratio == pytest.approx(0.5)
    assert set(report.question_closures[0].uncovered_terms) == {"gamma", "delta"}


# --- core: unresolved (child ran, doesn't cover) -------------------------


def test_unresolved() -> None:
    # question "alpha beta gamma"; child insight "delta epsilon zeta" -> 0/3 = 0.0
    parent = _parent([_q("alpha beta gamma")])
    children = {"child-1": _child(["delta epsilon zeta"])}
    report = measure_recursion_closure(parent, children)
    assert report.unresolved_count == 1
    assert report.closure_rate == pytest.approx(0.0)
    assert report.question_closures[0].verdict == "unresolved"


def test_just_below_threshold_unresolved() -> None:
    # 1 of 3 -> 0.33 < 0.50 -> unresolved
    parent = _parent([_q("alpha beta gamma")])
    children = {"child-1": _child(["alpha delta epsilon"])}
    report = measure_recursion_closure(parent, children)
    assert report.question_closures[0].verdict == "unresolved"


# --- core: orphaned (reservation made, child not in map) -----------------


def test_orphaned() -> None:
    parent = _parent([_q("alpha beta", child_id="ghost-child")])
    report = measure_recursion_closure(parent, {})
    assert report.orphaned_count == 1
    assert report.question_closures[0].verdict == "orphaned"
    assert report.closure_rate is None  # nothing ran


# --- core: empty_child (child ran, returned nothing) ---------------------


def test_empty_child() -> None:
    parent = _parent([_q("alpha beta")])
    children = {"child-1": _child([])}  # child with no insights
    report = measure_recursion_closure(parent, children)
    assert report.empty_child_count == 1
    assert report.question_closures[0].verdict == "empty_child"
    assert report.closure_rate == pytest.approx(0.0)  # ran, failed


# --- core: unmeasurable (child ran, question all-glue) --------------------


def test_unmeasurable_all_glue_question() -> None:
    parent = _parent([_q("the and is of")])  # all glue
    children = {"child-1": _child(["alpha beta"])}
    report = measure_recursion_closure(parent, children)
    assert report.unmeasurable_count == 1
    assert report.question_closures[0].verdict == "unmeasurable"
    # unmeasurable excluded from ran -> closure_rate None
    assert report.closure_rate is None


# --- exclusion: unescalated / unreserved ----------------------------------


def test_unescalated_excluded() -> None:
    parent = _parent([_q("alpha beta", escalated=False)])
    report = measure_recursion_closure(parent, {})
    assert report.unescalated_count == 1
    assert report.closure_rate is None


def test_unreserved_excluded() -> None:
    # escalated but no reserved_child_investigation_id (the #1941 leak)
    parent = _parent([_q("alpha beta", child_id=None)])
    report = measure_recursion_closure(parent, {})
    assert report.unreserved_count == 1
    assert report.closure_rate is None


# --- closure rate + verdict -----------------------------------------------


def test_closure_rate_mixed() -> None:
    parent = _parent([
        _q("alpha beta", node_id="q0"),       # resolved (child covers)
        _q("gamma delta", node_id="q1", child_id="child-2"),  # unresolved
    ])
    children = {
        "child-1": _child(["alpha beta"]),
        "child-2": _child(["epsilon zeta"]),
    }
    report = measure_recursion_closure(parent, children)
    assert report.resolved_count == 1
    assert report.unresolved_count == 1
    assert report.closure_rate == pytest.approx(0.5)


def test_rate_excludes_orphaned() -> None:
    # one resolved + one orphaned -> rate is 1.0 (orphaned excluded, it never ran)
    parent = _parent([
        _q("alpha beta", node_id="q0"),
        _q("gamma delta", node_id="q1", child_id="ghost"),
    ])
    children = {"child-1": _child(["alpha beta"])}
    report = measure_recursion_closure(parent, children)
    assert report.resolved_count == 1
    assert report.orphaned_count == 1
    assert report.closure_rate == pytest.approx(1.0)


def test_verdict_closed() -> None:
    parent = _parent([_q("alpha beta"), _q("gamma delta", child_id="c2")])
    children = {"child-1": _child(["alpha beta"]), "c2": _child(["gamma delta"])}
    report = measure_recursion_closure(parent, children)
    assert report.closure_rate == pytest.approx(1.0)
    assert report.verdict == "closed"


def test_verdict_open() -> None:
    parent = _parent([_q("alpha beta"), _q("gamma delta", child_id="c2")])
    children = {"child-1": _child(["zzz zzz"]), "c2": _child(["yyy yyy"])}
    report = measure_recursion_closure(parent, children)
    assert report.closure_rate == pytest.approx(0.0)
    assert report.verdict == "open"


def test_no_questions_unknown() -> None:
    report = measure_recursion_closure(_parent([]), {})
    assert report.closure_rate is None
    assert report.verdict == "unknown"


# --- multiple child insights union ---------------------------------------


def test_child_insights_union_for_coverage() -> None:
    # question "alpha beta gamma"; child insight1 covers alpha, insight2 covers beta
    # -> union covers 2/3 = 0.67 -> resolved
    parent = _parent([_q("alpha beta gamma")])
    children = {"child-1": _child(["alpha delta", "beta epsilon"])}
    report = measure_recursion_closure(parent, children)
    assert report.question_closures[0].closure_ratio == pytest.approx(2 / 3)
    assert report.question_closures[0].verdict == "resolved"


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    # ratio 0.5: resolved at 0.50, unresolved at 0.60
    parent = _parent([_q("alpha beta gamma delta")])
    children = {"child-1": _child(["alpha beta epsilon"])}
    assert measure_recursion_closure(parent, children).question_closures[0].verdict == "resolved"
    assert (
        measure_recursion_closure(parent, children, closure_threshold=0.60).question_closures[0].verdict
        == "unresolved"
    )


# --- ratio range ----------------------------------------------------------


def test_closure_ratio_in_unit_interval() -> None:
    parent = _parent([_q("alpha beta gamma")])
    for child_text in ["alpha", "alpha beta", "alpha beta gamma delta", "zzz"]:
        report = measure_recursion_closure(parent, {"child-1": _child([child_text])})
        if report.question_closures[0].closure_ratio is not None:
            assert 0.0 <= report.question_closures[0].closure_ratio <= 1.0


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    parent = _parent([_q("alpha beta")], investigation_id="parent-777")
    report = measure_recursion_closure(parent, {"child-1": _child(["alpha beta"])})
    assert report.artifact_id == "parent-777"


def test_authority_is_always_advisory() -> None:
    parent = _parent([_q("alpha beta")])
    assert measure_recursion_closure(parent, {"child-1": _child(["alpha beta"])}).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_recursion_closure(_parent([_q("alpha beta")]), {"child-1": _child(["alpha beta"])})
    assert isinstance(report, RecursionClosureReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.closure_rate = 0.0  # type: ignore[misc]


def test_question_closure_is_immutable() -> None:
    report = measure_recursion_closure(_parent([_q("alpha beta")]), {"child-1": _child(["alpha beta"])})
    c = report.question_closures[0]
    assert isinstance(c, QuestionClosure)
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.closure_ratio = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    parent = _parent([_q("alpha beta"), _q("gamma delta", child_id="c2")])
    children = {"child-1": _child(["alpha beta"]), "c2": _child(["gamma delta"])}
    assert measure_recursion_closure(parent, children) == measure_recursion_closure(parent, children)


def test_notes_describe_verdict() -> None:
    report = measure_recursion_closure(_parent([_q("alpha beta")]), {"child-1": _child(["alpha beta"])})
    joined = " | ".join(report.notes).lower()
    assert "closure" in joined or "resolv" in joined


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(RecursionClosureError, match="closure_threshold"):
        measure_recursion_closure(_parent([_q("alpha beta")]), {}, closure_threshold=bad)


# --- public api exports ---------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import recursion_closure as mod

    assert set(mod.__all__) == {
        "QuestionClosure",
        "RecursionClosureError",
        "RecursionClosureReport",
        "measure_recursion_closure",
    }
    assert issubclass(mod.RecursionClosureError, ValueError)
    assert dataclasses.is_dataclass(mod.QuestionClosure)
    assert dataclasses.is_dataclass(mod.RecursionClosureReport)
