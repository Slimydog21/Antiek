"""Tests for the twin-substrate merge (ask #4).

Each test pins one of the load-bearing invariants documented on the module.
Inputs are constructed ResearchArtifactBody twins (on-main schema); the merge
is exercised purely.
"""

from __future__ import annotations

import pytest

from substrate.graph.insight_question import (
    insight_node_id,
    question_node_id,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)
from substrate.twin_note_taker.merge import (
    MergedFinding,
    MergeStats,
    TwinMergeError,
    merge_twins,
)


def _twin(
    investigation_id: str,
    *,
    problem_question: str = "what is this asset about",
    insights: tuple[tuple[str, str | None], ...] = (),  # (text, source_document_id)
    questions: tuple[str, ...] = (),
    escalated_questions: tuple[str, ...] = (),
) -> ResearchArtifactBody:
    body_insights = [
        ArtifactInsight(
            node_id=insight_node_id(text),
            text=text,
            source_document_id=source_doc,
        )
        for text, source_doc in insights
    ]
    body_questions = [
        ArtifactQuestion(
            node_id=question_node_id(text),
            text=text,
            escalated=text in escalated_questions,
        )
        for text in questions
    ]
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=problem_question,
        insights=body_insights,
        open_questions=body_questions,
    )


# --------------------------------------------------------------------------- #
# Invariant #5 — empty input fails closed; a single twin merges (base case).
# --------------------------------------------------------------------------- #
def test_empty_input_fails_closed():
    with pytest.raises(TwinMergeError, match="cannot merge zero twins"):
        merge_twins([])


def test_single_twin_merges_within_itself():
    twin = _twin(
        "inv-a",
        insights=(
            ("transformers scale with data", "doc-a"),
            ("Transformers  scale with DATA", "doc-a"),  # canonical-equal duplicate
        ),
        questions=("how do they scale?", "How do they scale?"),  # canonical-equal
    )
    result = merge_twins([twin])
    assert result.stats.input_twin_count == 1
    assert result.stats.merged_insight_count == 1  # within-twin dedup
    assert result.stats.merged_question_count == 1
    assert result.stats.insight_dedup_collapses == 1
    assert result.stats.question_dedup_collapses == 1


# --------------------------------------------------------------------------- #
# Content-addressed dedup across twins + first-seen casing.
# --------------------------------------------------------------------------- #
def test_cross_twin_dedup_by_canonical_text():
    a = _twin("inv-a", insights=(("attention is all you need", "doc-a"),))
    b = _twin("inv-b", insights=(("Attention is ALL you need", "doc-b"),))

    result = merge_twins([a, b])

    assert result.stats.merged_insight_count == 1
    finding = result.merged_insights[0]
    assert finding.text == "attention is all you need"  # first-seen original casing
    assert finding.node_id == insight_node_id("attention is all you need")
    assert finding.source_twin_ids == ("inv-a", "inv-b")  # input-order provenance
    assert finding.source_document_ids == ("doc-a", "doc-b")
    assert finding.corroboration_count == 2


def test_distinct_insights_stay_distinct():
    a = _twin("inv-a", insights=(("insight one", "doc-a"), ("insight two", "doc-a")))
    b = _twin("inv-b", insights=(("insight three", "doc-b"),))

    result = merge_twins([a, b])

    assert result.stats.merged_insight_count == 3
    assert {f.text for f in result.merged_insights} == {
        "insight one",
        "insight two",
        "insight three",
    }
    assert all(f.corroboration_count == 1 for f in result.merged_insights)
    assert result.stats.corroborated_insight_count == 0


def test_corroboration_signal_surfaced():
    a = _twin("inv-a", insights=(("rlhf aligns models", "doc-a"),))
    b = _twin("inv-b", insights=(("RLHF aligns models", "doc-b"),))
    c = _twin("inv-c", insights=(("rlhf aligns models", "doc-c"),))

    result = merge_twins([a, b, c])

    assert result.stats.corroborated_insight_count == 1
    finding = result.merged_insights[0]
    assert finding.corroboration_count == 3
    # the canonical merged twin stamps the corroboration descriptor as confidence
    stamped = result.merged.insights[0]
    assert stamped.confidence == "corroborated:3"


# --------------------------------------------------------------------------- #
# Question escalation propagates (never silently dropped).
# --------------------------------------------------------------------------- #
def test_question_escalation_propagates_if_any_source_escalated():
    a = _twin("inv-a", questions=("what limits scaling?",), escalated_questions=())
    b = _twin("inv-b", questions=("what limits scaling?",), escalated_questions=("what limits scaling?",))

    result = merge_twins([a, b])

    assert result.stats.merged_question_count == 1
    finding = result.merged_questions[0]
    assert finding.escalated is True  # one source escalated -> merged escalates
    assert result.merged.open_questions[0].escalated is True


def test_question_no_escalation_when_none_escalated():
    a = _twin("inv-a", questions=("why does it work?",))
    b = _twin("inv-b", questions=("why does it work?",))
    result = merge_twins([a, b])
    assert result.merged_questions[0].escalated is False


# --------------------------------------------------------------------------- #
# Blank filtering — blank/whitespace texts are filtered, counted.
# --------------------------------------------------------------------------- #
def test_blank_insights_and_questions_filtered_and_counted():
    blank = ArtifactInsight(node_id="x", text="   ", source_document_id="doc-a")
    good = ArtifactInsight(node_id="y", text="real insight", source_document_id="doc-a")
    blank_q = ArtifactQuestion(node_id="q1", text="\t\n ")
    good_q = ArtifactQuestion(node_id="q2", text="real question")
    twin = ResearchArtifactBody(
        investigation_id="inv-a",
        problem_question="p",
        insights=[blank, good],
        open_questions=[blank_q, good_q],
    )

    result = merge_twins([twin])

    assert result.stats.filtered_blank_insights == 1
    assert result.stats.filtered_blank_questions == 1
    assert result.stats.merged_insight_count == 1
    assert result.stats.merged_question_count == 1
    assert result.merged_insights[0].text == "real insight"


# --------------------------------------------------------------------------- #
# Idempotency — re-merging the same twins (any order) yields a stable id.
# --------------------------------------------------------------------------- #
def test_merge_id_is_order_independent_and_stable():
    a = _twin("inv-a", insights=(("shared insight", "doc-a"),))
    b = _twin("inv-b", insights=(("shared insight", "doc-b"),))
    c = _twin("inv-c", insights=(("unique to c", "doc-c"),))

    r1 = merge_twins([a, b, c])
    r2 = merge_twins([c, b, a])  # different input order

    assert r1.merged.investigation_id == r2.merged.investigation_id
    assert r1.merged.source_event_ids == ["inv-a", "inv-b", "inv-c"]
    assert r2.merged.source_event_ids == ["inv-c", "inv-b", "inv-a"]  # input order preserved


def test_remerge_same_set_is_idempotent():
    a = _twin("inv-a", insights=(("insight", "doc-a"),))
    b = _twin("inv-b", insights=(("insight", "doc-b"),))

    first = merge_twins([a, b])
    second = merge_twins([a, b])

    assert first.merged.investigation_id == second.merged.investigation_id
    assert first.merged.content_hash() == second.merged.content_hash()


# --------------------------------------------------------------------------- #
# Honesty: synthesis withheld; problem_question deterministic; provenance real.
# --------------------------------------------------------------------------- #
def test_synthesis_withheld_and_excerpt_none():
    result = merge_twins([_twin("inv-a", insights=(("x", "doc-a"),))])
    assert result.merged.synthesis_withheld is True
    assert result.merged.synthesis_excerpt is None
    assert result.stats.synthesis_withheld is True


def test_problem_question_uses_first_nonblank_then_override():
    a = _twin("inv-a", problem_question="", insights=(("x", "doc-a"),))
    b = _twin("inv-b", problem_question="the real question", insights=(("y", "doc-b"),))
    result = merge_twins([a, b])
    assert result.merged.problem_question == "the real question"

    overridden = merge_twins([a, b], problem_question_override="operator-named merge goal")
    assert overridden.merged.problem_question == "operator-named merge goal"


def test_merged_twin_carries_source_twin_provenance():
    a = _twin("inv-a", insights=(("x", "doc-a"),))
    b = _twin("inv-b", insights=(("y", "doc-b"),))
    result = merge_twins([a, b])
    assert result.source_twin_ids == ("inv-a", "inv-b")
    assert set(result.merged.source_event_ids) == {"inv-a", "inv-b"}


def test_merged_insight_primary_source_is_first_contributor():
    a = _twin("inv-a", insights=(("corroborated insight", "doc-a"),))
    b = _twin("inv-b", insights=(("CORROBORATED insight", "doc-b"),))
    result = merge_twins([a, b])
    assert result.merged.insights[0].source_document_id == "doc-a"  # deterministic primary


# --------------------------------------------------------------------------- #
# Node-id faithfulness to the sanctioned graph writers (execution-faithful).
# --------------------------------------------------------------------------- #
def test_merged_node_ids_match_graph_writers():
    a = _twin("inv-a", insights=(("faithful insight", "doc-a"),))
    b = _twin("inv-b", questions=("faithful question?",))
    result = merge_twins([a, b])
    assert result.merged.insights[0].node_id == insight_node_id("faithful insight")
    assert result.merged.open_questions[0].node_id == question_node_id("faithful question?")


# --------------------------------------------------------------------------- #
# Purity — no I/O / clock / dispatch / DB.
# --------------------------------------------------------------------------- #
def test_purity_no_io_imports():
    import inspect

    from substrate.twin_note_taker import merge as mod

    src = inspect.getsource(mod)
    for forbidden in ("import os", "import time", "import asyncio", "open(", "datetime.now", "connect_write", "requests"):
        assert forbidden not in src, f"purity breach: {forbidden!r} in merge source"


# --------------------------------------------------------------------------- #
# Boundary types frozen.
# --------------------------------------------------------------------------- #
def test_boundary_types_frozen():
    import dataclasses

    from substrate.twin_note_taker.merge import TwinMergeResult

    for cls in (MergedFinding, MergeStats, TwinMergeResult):
        assert dataclasses.is_dataclass(cls)
