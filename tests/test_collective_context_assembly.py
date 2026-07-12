"""Tests for substrate/collective/context_assembly.py — prompt-N-as-one (ask #3f)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from substrate.collective.context_assembly import (
    CollectiveContext,
    CollectiveContextError,
    DedupedFinding,
    assemble_collective_context,
)


@dataclass
class FakeInsight:
    node_id: str
    text: str


@dataclass
class FakeQuestion:
    node_id: str
    text: str


@dataclass
class FakeBody:
    investigation_id: str
    problem_question: str
    insights: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)
    synthesis_excerpt: str | None = None
    synthesis_withheld: bool = False


def _inst(iid, pq, insights=(), questions=(), synth=None, withheld=False):
    return FakeBody(iid, pq, list(insights), list(questions), synth, withheld)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_empty_instances_rejected():
    with pytest.raises(CollectiveContextError):
        assemble_collective_context([])


def test_instance_without_id_rejected():
    bad = FakeBody(investigation_id="  ", problem_question="q")
    with pytest.raises(CollectiveContextError):
        assemble_collective_context([bad])


# ---------------------------------------------------------------------------
# every selected instance appears (no silent drop)
# ---------------------------------------------------------------------------


def test_empty_insight_instance_still_appears():
    ctx = assemble_collective_context(
        [
            _inst("i1", "what is X", insights=[FakeInsight("n1", "X is great")]),
            _inst("i2", "what is Y"),  # zero insights
        ]
    )
    ids = {c.investigation_id for c in ctx.instances}
    assert ids == {"i1", "i2"}
    assert ctx.instance_count == 2


def test_problem_question_carried_through():
    ctx = assemble_collective_context([_inst("i1", "why transformers?")])
    assert ctx.instances[0].problem_question == "why transformers?"


# ---------------------------------------------------------------------------
# dedup by content-addressed node_id
# ---------------------------------------------------------------------------


def test_same_insight_deduped_with_both_sources():
    shared = FakeInsight("node-abc", "attention scales")
    ctx = assemble_collective_context(
        [
            _inst("i1", "q1", insights=[shared]),
            _inst("i2", "q2", insights=[shared]),
        ]
    )
    assert len(ctx.deduped_insights) == 1
    d = ctx.deduped_insights[0]
    assert d.node_id == "node-abc"
    assert set(d.source_investigation_ids) == {"i1", "i2"}


def test_distinct_insights_not_deduped():
    ctx = assemble_collective_context(
        [
            _inst("i1", "q1", insights=[FakeInsight("a", "alpha")]),
            _inst("i2", "q2", insights=[FakeInsight("b", "beta")]),
        ]
    )
    assert len(ctx.deduped_insights) == 2


def test_open_questions_deduped():
    shared_q = FakeQuestion("qnode", "what next?")
    ctx = assemble_collective_context(
        [
            _inst("i1", "q1", questions=[shared_q]),
            _inst("i2", "q2", questions=[shared_q]),
        ]
    )
    assert len(ctx.deduped_open_questions) == 1
    assert set(ctx.deduped_open_questions[0].source_investigation_ids) == {"i1", "i2"}


# ---------------------------------------------------------------------------
# synthesis_withheld flagged, never faked
# ---------------------------------------------------------------------------


def test_synthesis_withheld_flagged():
    ctx = assemble_collective_context(
        [_inst("i1", "q1", withheld=True, insights=[FakeInsight("n", "x")])]
    )
    assert ctx.instances[0].synthesis_withheld is True
    rendered = ctx.render()
    assert "synthesis withheld" in rendered


def test_synthesis_excerpt_carried():
    ctx = assemble_collective_context(
        [_inst("i1", "q1", synth="transformers win")]
    )
    assert ctx.instances[0].synthesis_excerpt == "transformers win"
    assert "transformers win" in ctx.render()


# ---------------------------------------------------------------------------
# token budget — fair, even truncation, honest flagging
# ---------------------------------------------------------------------------


def test_no_budget_no_truncation():
    ctx = assemble_collective_context(
        [_inst("i1", "q", insights=[FakeInsight(f"n{i}", f"insight {i}") for i in range(10)])]
    )
    assert ctx.truncated is False
    assert ctx.insights_held_back_total == 0


def test_budget_truncates_evenly_and_flags():
    big = [_inst(f"i{n}", f"problem {n}", insights=[FakeInsight(f"n{n}k", f"insight {n}-{k} " * 20) for k in range(5)]) for n in range(3)]
    ctx = assemble_collective_context(big, token_budget=200)
    assert ctx.truncated is True
    assert ctx.insights_held_back_total > 0
    assert any("truncated" in note for note in ctx.notes)
    # every instance lost the same count (fair)
    counts = [c.insights_held_back for c in ctx.instances]
    assert len(set(counts)) == 1


def test_truncation_fits_budget_or_exhausts():
    # force an extreme budget so all insights get dropped
    ctx = assemble_collective_context(
        [_inst("i1", "a" * 1000, insights=[FakeInsight("n", "b" * 1000)])],
        token_budget=10,
    )
    assert ctx.truncated is True
    assert ctx.instances[0].insights_included == 0
    # problem_question + open_questions remain (instance not dropped)
    assert ctx.instance_count == 1
    assert any("could not fit" in n for n in ctx.notes)


def test_budget_none_means_no_limit():
    ctx = assemble_collective_context(
        [_inst("i1", "q", insights=[FakeInsight(f"n{i}", "x" * 1000) for i in range(50)])],
        token_budget=None,
    )
    assert ctx.truncated is False
    assert ctx.instances[0].insights_included == 50


# ---------------------------------------------------------------------------
# render is labeled + source-attributed
# ---------------------------------------------------------------------------


def test_render_labels_findings_with_source():
    ctx = assemble_collective_context(
        [_inst("i1", "q1", insights=[FakeInsight("n1", "alpha finding")])]
    )
    rendered = ctx.render()
    assert "[i1]" in rendered
    assert "alpha finding" in rendered
    assert "COLLECTIVE CONTEXT" in rendered


def test_render_empty_context_is_empty_string():
    # build a CollectiveContext directly to test the empty case
    ctx = CollectiveContext(
        instances=(), deduped_insights=(), deduped_open_questions=(),
        token_count=0, truncated=False, insights_held_back_total=0,
    )
    assert ctx.render() == ""


def test_render_lists_cross_instance_insights():
    ctx = assemble_collective_context(
        [
            _inst("i1", "q1", insights=[FakeInsight("shared", "common insight")]),
            _inst("i2", "q2", insights=[FakeInsight("shared", "common insight")]),
        ]
    )
    rendered = ctx.render()
    assert "Cross-instance insights" in rendered
    assert "i1, i2" in rendered


# ---------------------------------------------------------------------------
# purity + determinism
# ---------------------------------------------------------------------------


def test_assembly_is_pure_idempotent():
    insts = [
        _inst("i1", "q1", insights=[FakeInsight("n1", "a")]),
        _inst("i2", "q2", insights=[FakeInsight("n2", "b")]),
    ]
    assert assemble_collective_context(insts) == assemble_collective_context(insts)


def test_deduped_finding_is_frozen():
    ctx = assemble_collective_context(
        [_inst("i1", "q1", insights=[FakeInsight("n1", "a")])]
    )
    assert isinstance(ctx.deduped_insights[0], DedupedFinding)
    assert isinstance(ctx.deduped_insights[0].source_investigation_ids, tuple)


def test_blank_text_insights_ignored():
    ctx = assemble_collective_context(
        [_inst("i1", "q1", insights=[FakeInsight("n1", "   "), FakeInsight("n2", "real")])]
    )
    assert ctx.instances[0].insights_included == 1
    assert ctx.deduped_insights[0].text == "real"
