"""Tests for the MO run-findings promotion substrate (ask #13 loop-closer).

Each load-bearing invariant in the module docstring is a named test. Run with:

    .venv/bin/python -m pytest tests/test_midnight_oil_promote_findings -q \
        --noconftest --override-ini="addopts=" -p no:cacheprovider
"""

from __future__ import annotations

import copy

import pytest

from substrate.midnight_oil.promote_findings import (
    CompletedRun,
    PhaseOutcome,
    PromoteFindingsError,
    ResolvedFinding,
    promote_run_findings,
)
from substrate.research_artifact.schema import ResearchArtifactBody

# --------------------------------------------------------------------------- #
# Fake resolver
# --------------------------------------------------------------------------- #


class _FakeResolver:
    """Deterministic resolver: a fixed map ref -> ResolvedFinding, else None."""

    def __init__(self, mapping: dict[str, ResolvedFinding]) -> None:
        self._mapping = mapping
        self.calls: list[str] = []

    def resolve(self, finding_ref: str) -> ResolvedFinding | None:
        self.calls.append(finding_ref)
        return self._mapping.get(finding_ref)


def _phase(ordinal: int, *, ran: bool, refs: tuple[str, ...], goal_index: int = 0,
           gate_authorized: bool = True) -> PhaseOutcome:
    return PhaseOutcome(
        ordinal=ordinal,
        goal_index=goal_index,
        ran=ran,
        gate_authorized=gate_authorized,
        finding_refs=refs,
    )


def _run(phases, completion="completed", **kw) -> CompletedRun:
    base = dict(
        run_id="mo-2026-w29-1",
        run_label="Midnight Oil 2026-W29 #1",
        goals=("summarize arxiv diffusion models 2024",),
        phase_outcomes=tuple(phases),
        completion=completion,
    )
    base.update(kw)
    return CompletedRun(**base)


# --------------------------------------------------------------------------- #
# Invariant 1: findings only from phases that actually ran
# --------------------------------------------------------------------------- #


def test_denied_phase_contributes_no_findings():
    resolver = _FakeResolver({"f1": ResolvedFinding("insight one")})
    run = _run([
        _phase(0, ran=True, refs=("f1",)),
        _phase(1, ran=False, refs=("f1",), gate_authorized=False),  # denied
    ])
    art = promote_run_findings(run, resolver)
    # f1 resolved once (from phase 0); phase 1 denied → no second resolution
    # (refs still collected for source_event_ids, but only phase 0 resolves)
    assert len(art.insights) == 1
    assert resolver.calls.count("f1") == 1


def test_skipped_phase_no_findings_but_refs_preserved():
    resolver = _FakeResolver({"f2": ResolvedFinding("insight two")})
    run = _run([_phase(0, ran=False, refs=("f2",))])
    art = promote_run_findings(run, resolver)
    assert art.insights == []
    assert resolver.calls == []  # never even asked
    assert "f2" in art.source_event_ids  # ref still preserved


# --------------------------------------------------------------------------- #
# Invariant 2: incomplete run withholds synthesis
# --------------------------------------------------------------------------- #


def test_stopped_early_withholds_synthesis():
    run = _run([_phase(0, ran=True, refs=())], completion="stopped_early")
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.synthesis_withheld is True
    assert any("synthesis_withheld=True" in n for n in art.agent_notes)


def test_completed_does_not_withhold():
    run = _run([_phase(0, ran=True, refs=())], completion="completed")
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.synthesis_withheld is False


def test_unknown_completion_withholds_synthesis():
    run = _run([_phase(0, ran=True, refs=())], completion="unknown")
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.synthesis_withheld is True


# --------------------------------------------------------------------------- #
# Invariant 3: node_id content-addressed + dedup
# --------------------------------------------------------------------------- #


def test_same_finding_content_dedups_to_one_insight():
    finding = ResolvedFinding("identical claim", source_ids=("s1",))
    resolver = _FakeResolver({"a": finding, "b": finding})
    run = _run([_phase(0, ran=True, refs=("a", "b"))])
    art = promote_run_findings(run, resolver)
    assert len(art.insights) == 1
    assert art.insights[0].node_id.startswith("mo:")


def test_different_content_different_node_ids():
    resolver = _FakeResolver({
        "a": ResolvedFinding("claim one"),
        "b": ResolvedFinding("claim two"),
    })
    run = _run([_phase(0, ran=True, refs=("a", "b"))])
    art = promote_run_findings(run, resolver)
    assert len(art.insights) == 2
    ids = {i.node_id for i in art.insights}
    assert len(ids) == 2


# --------------------------------------------------------------------------- #
# Invariant 4: provenance carried verbatim
# --------------------------------------------------------------------------- #


def test_all_refs_survive_in_source_event_ids():
    resolver = _FakeResolver({"resolvable": ResolvedFinding("x")})
    run = _run([_phase(0, ran=True, refs=("resolvable", "ghost", "also-ghost"))])
    art = promote_run_findings(run, resolver)
    assert set(art.source_event_ids) == {"resolvable", "ghost", "also-ghost"}


def test_source_ids_deduped_preserving_order():
    resolver = _FakeResolver({})
    run = _run([_phase(0, ran=True, refs=("r1", "r2", "r1", "r3"))])
    art = promote_run_findings(run, resolver)
    assert art.source_event_ids == ["r1", "r2", "r3"]


# --------------------------------------------------------------------------- #
# Invariant 5: unresolvable ref noted, not fabricated
# --------------------------------------------------------------------------- #


def test_unresolvable_ref_noted_not_fabricated():
    resolver = _FakeResolver({"good": ResolvedFinding("real insight")})
    run = _run([_phase(0, ran=True, refs=("good", "missing"))])
    art = promote_run_findings(run, resolver)
    assert len(art.insights) == 1
    assert art.insights[0].text == "real insight"
    assert any("1 finding_ref/s unresolvable" in n for n in art.agent_notes)
    assert "missing" in art.source_event_ids  # preserved


def test_empty_resolved_text_treated_as_unresolved():
    resolver = _FakeResolver({"blank": ResolvedFinding("   ")})
    run = _run([_phase(0, ran=True, refs=("blank",))])
    art = promote_run_findings(run, resolver)
    assert art.insights == []
    assert any("unresolvable" in n for n in art.agent_notes)


# --------------------------------------------------------------------------- #
# Invariant 6: cost/budget surfaced verbatim, never fabricated
# --------------------------------------------------------------------------- #


def test_unknown_budget_surfaced_as_unknown():
    run = _run([_phase(0, ran=True, refs=())], within_budget=None, actual_total_usd=None, overage_usd=None)
    art = promote_run_findings(run, _FakeResolver({}))
    budget_note = next(n for n in art.agent_notes if "budget" in n or "spend" in n)
    assert "unknown" in budget_note


def test_over_budget_surfaced_with_overage():
    run = _run([_phase(0, ran=True, refs=())], within_budget=False, actual_total_usd=5.0, overage_usd=1.5)
    art = promote_run_findings(run, _FakeResolver({}))
    budget_note = next(n for n in art.agent_notes if "OVER" in n or "overage" in n)
    assert "OVER budget" in budget_note
    assert "overage $1.5" in budget_note


def test_within_budget_no_overage():
    run = _run([_phase(0, ran=True, refs=())], within_budget=True, actual_total_usd=2.0, overage_usd=0.0)
    art = promote_run_findings(run, _FakeResolver({}))
    budget_note = next(n for n in art.agent_notes if "within budget" in n)
    assert "within budget" in budget_note and "no overage" in budget_note


# --------------------------------------------------------------------------- #
# Invariant 7: goals compose problem_question
# --------------------------------------------------------------------------- #


def test_single_goal_becomes_problem_question():
    run = _run([_phase(0, ran=True, refs=())], goals=("what is RLHF?",))
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.problem_question == "what is RLHF?"


def test_multiple_goals_joined_deterministically():
    run = _run([_phase(0, ran=True, refs=())], goals=("goal one", "goal two"))
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.problem_question == "goal one ; goal two"


def test_empty_goals_flagged_not_empty_string():
    run = _run([_phase(0, ran=True, refs=())], goals=())
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.problem_question != ""
    assert "no goals recorded" in art.problem_question
    assert any("goals were empty" in n for n in art.agent_notes)


# --------------------------------------------------------------------------- #
# Invariant 8: deterministic + pure
# --------------------------------------------------------------------------- #


def test_identical_inputs_produce_identical_artifact_hash():
    resolver_map = {"f1": ResolvedFinding("claim", source_ids=("s",))}
    run = _run([_phase(0, ran=True, refs=("f1",))])
    a1 = promote_run_findings(run, _FakeResolver(resolver_map))
    a2 = promote_run_findings(copy.deepcopy(run), _FakeResolver(dict(resolver_map)))
    assert a1.content_hash() == a2.content_hash()


# --------------------------------------------------------------------------- #
# Invariant 9: authority is operator-side (produces, never mutates)
# --------------------------------------------------------------------------- #


def test_output_is_research_artifact_body_not_a_merge():
    run = _run([_phase(0, ran=True, refs=())])
    art = promote_run_findings(run, _FakeResolver({}))
    assert isinstance(art, ResearchArtifactBody)
    # No merge/promotion happened — this is just an artifact value.
    assert art.investigation_id == "mo-2026-w29-1"


# --------------------------------------------------------------------------- #
# Invariant 10: real ResearchArtifactBody (content_hash works, consumable)
# --------------------------------------------------------------------------- #


def test_content_hash_works_on_output():
    resolver = _FakeResolver({"f1": ResolvedFinding("insight", source_ids=("s1",), confidence="high")})
    run = _run([_phase(0, ran=True, refs=("f1",))])
    art = promote_run_findings(run, resolver)
    h = art.content_hash()
    assert isinstance(h, str) and len(h) > 0


def test_insight_carries_source_and_confidence():
    resolver = _FakeResolver({"f1": ResolvedFinding("claim", source_ids=("doc-7",), confidence="high")})
    run = _run([_phase(0, ran=True, refs=("f1",))])
    art = promote_run_findings(run, resolver)
    ins = art.insights[0]
    assert ins.source_document_id == "doc-7"
    assert ins.confidence == "high"


def test_open_question_promoted_when_resolved():
    resolver = _FakeResolver({
        "f1": ResolvedFinding("claim", open_question="why does X happen?"),
    })
    run = _run([_phase(0, ran=True, refs=("f1",))])
    art = promote_run_findings(run, resolver)
    assert len(art.open_questions) == 1
    assert art.open_questions[0].text == "why does X happen?"


# --------------------------------------------------------------------------- #
# Validation + edge cases
# --------------------------------------------------------------------------- #


def test_empty_run_id_rejected():
    run = CompletedRun(
        run_id="  ", run_label="x", goals=("g",), phase_outcomes=(),
        completion="completed",
    )
    with pytest.raises(PromoteFindingsError):
        promote_run_findings(run, _FakeResolver({}))


def test_invalid_completion_rejected():
    run = _run([_phase(0, ran=True, refs=())], completion="halfway")
    with pytest.raises(PromoteFindingsError):
        promote_run_findings(run, _FakeResolver({}))


def test_no_phases_no_findings_clean_artifact():
    run = _run([], completion="completed")
    art = promote_run_findings(run, _FakeResolver({}))
    assert art.insights == []
    assert art.source_event_ids == []
    assert art.synthesis_withheld is False


def test_run_label_and_id_in_provenance_note():
    run = _run([_phase(0, ran=True, refs=())])
    art = promote_run_findings(run, _FakeResolver({}))
    prov = next(n for n in art.agent_notes if "produced_by" in n)
    assert "mo-2026-w29-1" in prov and "Midnight Oil 2026-W29 #1" in prov


def test_end_to_end_realistic_run():
    resolver = _FakeResolver({
        "ref-1": ResolvedFinding("Diffusion models learn score gradients.", source_ids=("arxiv-2401",), confidence="high"),
        "ref-2": ResolvedFinding("Classifier-free guidance improves sample quality.", source_ids=("arxiv-2204",)),
        "ref-3": ResolvedFinding("Diffusion models learn score gradients.", source_ids=("arxiv-2401",)),  # dup of ref-1
        # ref-4 unresolvable
    })
    run = _run([
        _phase(0, ran=True, refs=("ref-1", "ref-2"), goal_index=0),
        _phase(1, ran=True, refs=("ref-3", "ref-4"), goal_index=0),
        _phase(2, ran=False, refs=("ref-5",), gate_authorized=False),  # denied
    ], completion="completed", within_budget=True, actual_total_usd=1.2, overage_usd=None)
    art = promote_run_findings(run, resolver)
    # ref-1 and ref-3 dedup (same content); ref-2 distinct; ref-4 unresolved; ref-5 denied
    assert len(art.insights) == 2
    assert set(art.source_event_ids) == {"ref-1", "ref-2", "ref-3", "ref-4", "ref-5"}
    assert art.synthesis_withheld is False
    assert any("1 finding_ref/s unresolvable" in n for n in art.agent_notes)
    assert art.content_hash()  # consumable by merge/promote/twin
