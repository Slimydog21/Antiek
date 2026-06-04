"""ACV SPR-06 — the reuse-CONSUMING browse loop (M1 + M2 unit gates).

These tests run against the CONSUMING loop, NOT the demo loop (which stays the
deterministic loop for the rest of unit CI). They prove:

  * M1 — cost drops MONOTONICALLY as pack coverage rises (0% / 50% / 100%), and
    a step is skipped ONLY when a pack entry genuinely covers ITS sub-question
    (the no-false-skip guard: an off-topic / low-similarity / look-alike unit
    must NOT cause a skip).
  * M2 — the consuming loop emits a real ``dispatch.call`` per UNCOVERED step, so
    the measurement sees a genuinely-lower cost for a more-covered run.

The failure modes rigor #3 enumerates each have a test: empty pack → full work;
100%-coverage pack → ~zero work; a pack entry that LOOKS like a match but is for a
different sub-question → must NOT skip; a warm run reusing its OWN deposits is
measured on THIS investigation's cost (the events_dir isolates it).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass

from compounding.benchmark.measure import measure_investigation
from runtime.research_runner.browse_loop import (
    COVERAGE_SIMILARITY_FLOOR,
    coverage_summary,
    decide_coverage,
    make_reuse_consuming_loop,
    plan_sub_questions,
)
from runtime.research_runner.host_local import HostLocalRunner
from runtime.research_runner.protocol import BudgetCap, ResearchPlan

# ---------------------------------------------------------------------------
# A lightweight pack-unit double (the loop reads only .text / .similarity /
# .unit_id / .source_investigation_id — the RetrievedUnit surface).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeUnit:
    text: str
    similarity: float
    unit_id: str = "u"
    source_investigation_id: str = "prior-1"


# A 4-salient-term root question with steps=4 so each planned sub-question keys
# on a single distinct term → clean, controllable partial coverage.
_ROOT = "alpha beta gamma delta epsilon zeta"


def _unit_covering(terms: list[str], *, uid: str, sim: float = 0.9) -> FakeUnit:
    """A pack unit whose text contains the given salient terms (so it covers the
    sub-questions keyed on those terms) at a real retrieval similarity."""
    return FakeUnit(text=" ".join(terms) + " padding context", similarity=sim, unit_id=uid)


def _measure_cost(root: str, pack, *, steps: int) -> float:
    """Run the consuming loop with ``pack`` and return the measured
    ``token_cost_usd`` (Σ dispatch.call cost over UNCOVERED steps)."""
    tmp = tempfile.mkdtemp(prefix="consuming-")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    iid = f"consuming-{id(pack)}-{steps}"

    async def _run() -> None:
        loop_fn = make_reuse_consuming_loop(steps=steps, events_dir=events_dir)
        runner = HostLocalRunner(loop_fn=loop_fn, events_dir=events_dir, seal_on_complete=False)
        plan = ResearchPlan(
            investigation_id=iid, sub_question=root, budget=BudgetCap(cost_usd=10.0, max_steps=50)
        )
        # Pre-seat the pack on the state BEFORE start schedules the loop: we
        # register the state, set reuse_pack, then start. HostLocalRunner.start
        # creates _ResearchState fresh, so we instead monkey-set via a subclass
        # hook — simplest: set the pack through the documented threading path by
        # calling start (which builds the state + task) and relying on _run
        # reading st.reuse_pack at ctx-creation time. To avoid the race, we set
        # reuse_pack on the state object the instant start returns the handle,
        # which is BEFORE the scheduled task's first await (the event loop has not
        # yielded to it yet within this coroutine).
        # Set the pack on the state the instant start() returns the handle —
        # BEFORE this coroutine awaits, so the scheduled _run task (which has not
        # been given a turn yet) reads it at ctx creation. This is the same
        # threading path the runner uses for a real reuse substrate
        # (st.reuse_pack → ctx.pack), without needing a live substrate (M1 tests
        # the loop CONSUMING the pack, not SPR-02's wire that assembles it).
        handle = await runner.start(iid, plan)
        runner._states[iid].reuse_pack = list(pack) if pack is not None else None
        async for ev in runner.stream(handle):
            if ev.kind == "done":
                break
        await runner.join()

    asyncio.run(_run())
    return measure_investigation(iid, events_dir=events_dir).token_cost_usd


# ── M1 coverage monotonicity (the headline gate) ──────────────────────────────


def test_consuming_loop_coverage_monotonic_cost():
    """M1: token cost drops MONOTONICALLY across 0% / 50% / 100% pack coverage.
    (Named so `pytest -k 'consuming_loop and coverage'` selects it.)"""
    steps = 4
    planned = plan_sub_questions(_ROOT, steps=steps)
    # 0% — empty pack.
    cost_0 = _measure_cost(_ROOT, [], steps=steps)
    # 50% — units covering exactly half the planned sub-questions' terms.
    half_terms = [t for sq in planned[: steps // 2] for t in sq.coverage_key]
    cost_50 = _measure_cost(_ROOT, [_unit_covering(half_terms, uid="u-half")], steps=steps)
    # 100% — a rich unit covering every planned sub-question's terms.
    all_terms = [t for sq in planned for t in sq.coverage_key]
    cost_100 = _measure_cost(_ROOT, [_unit_covering(all_terms, uid="u-all")], steps=steps)

    assert cost_0 > cost_50 > cost_100, f"cost must drop monotonically: {cost_0} {cost_50} {cost_100}"
    assert cost_0 > 0.0, "an empty pack must do full (non-zero) work"
    assert cost_100 == 0.0, "a fully-covered pack must do ~zero work"


def test_consuming_loop_coverage_counts_monotonic():
    """The coverage decision itself rises monotonically (a pure-function check
    that does not spin a runner)."""
    steps = 4
    planned = plan_sub_questions(_ROOT, steps=steps)
    c0, _ = coverage_summary(decide_coverage(planned, []))
    half_terms = [t for sq in planned[: steps // 2] for t in sq.coverage_key]
    c50, _ = coverage_summary(decide_coverage(planned, [_unit_covering(half_terms, uid="h")]))
    all_terms = [t for sq in planned for t in sq.coverage_key]
    c100, _ = coverage_summary(decide_coverage(planned, [_unit_covering(all_terms, uid="a")]))
    assert c0 < c50 < c100 == steps


# ── M1 no-false-skip guard (rigor #3 failure modes) ───────────────────────────


def test_empty_pack_does_full_work():
    cost = _measure_cost(_ROOT, [], steps=3)
    assert cost > 0.0


def test_off_topic_unit_does_not_skip():
    """A high-similarity but OFF-TOPIC unit (no shared salient tokens) must NOT
    cover any step — the irrelevant-arm control depends on this."""
    off = FakeUnit(text="tardigrade anhydrobiosis trehalose desiccation survival", similarity=0.95)
    cost_off = _measure_cost(_ROOT, [off], steps=4)
    cost_empty = _measure_cost(_ROOT, [], steps=4)
    assert cost_off == cost_empty, "an off-topic unit must do the SAME (full) work as an empty pack"


def test_low_similarity_lookalike_does_not_skip():
    """A unit whose TEXT matches a sub-question's terms but whose recorded
    retrieval similarity is BELOW the floor (a hash collision, not a real hit)
    must NOT skip — the dual floor's similarity half."""
    planned = plan_sub_questions(_ROOT, steps=4)
    all_terms = [t for sq in planned for t in sq.coverage_key]
    lookalike = _unit_covering(all_terms, uid="collision", sim=COVERAGE_SIMILARITY_FLOOR - 0.05)
    cost = _measure_cost(_ROOT, [lookalike], steps=4)
    cost_empty = _measure_cost(_ROOT, [], steps=4)
    assert cost == cost_empty, "a below-similarity-floor look-alike must NOT cause a skip"


def test_unit_for_different_subquestion_does_not_cross_skip():
    """A unit that covers sub-question 0's terms must skip ONLY sub-question 0,
    not the others (each skip is keyed to its OWN sub-question)."""
    planned = plan_sub_questions(_ROOT, steps=4)
    sq0_terms = list(planned[0].coverage_key)
    decisions = decide_coverage(planned, [_unit_covering(sq0_terms, uid="u0")])
    covered_ids = {d.sq_id for d in decisions if d.covered}
    assert covered_ids == {"sq-0"}, f"only sq-0 should be covered, got {covered_ids}"


def test_skip_records_covering_unit_provenance():
    """The skip is AUDITABLE: the covering unit's id + source are recorded on the
    coverage decision (so a reader can reconstruct WHY cost dropped)."""
    planned = plan_sub_questions(_ROOT, steps=4)
    all_terms = [t for sq in planned for t in sq.coverage_key]
    unit = _unit_covering(all_terms, uid="u-prov")
    unit = FakeUnit(text=unit.text, similarity=unit.similarity, unit_id="u-prov", source_investigation_id="prior-XYZ")
    decisions = decide_coverage(planned, [unit])
    covered = [d for d in decisions if d.covered]
    assert covered, "expected coverage"
    for d in covered:
        assert d.unit_id == "u-prov"
        assert d.source_investigation_id == "prior-XYZ"
        assert d.unit_similarity >= COVERAGE_SIMILARITY_FLOOR


# ── M2 the measurement sees the saving (real dispatch.call) ────────────────────


def test_more_coverage_is_strictly_cheaper_measured():
    """M2 at the unit level: a more-covered run measures a strictly LOWER
    token_cost_usd than a less-covered run (the saving is real, via dispatch.call,
    not a clamp)."""
    steps = 4
    planned = plan_sub_questions(_ROOT, steps=steps)
    one_term = list(planned[0].coverage_key)
    all_terms = [t for sq in planned for t in sq.coverage_key]
    cost_low = _measure_cost(_ROOT, [_unit_covering(one_term, uid="low")], steps=steps)
    cost_high = _measure_cost(_ROOT, [_unit_covering(all_terms, uid="high")], steps=steps)
    assert cost_high < cost_low, f"more coverage must be cheaper: high={cost_high} low={cost_low}"


def test_skip_emits_no_dispatch_call():
    """A fully-covered run emits ZERO dispatch.call events (the absence IS the
    saving) → measured cost is exactly 0."""
    planned = plan_sub_questions(_ROOT, steps=3)
    all_terms = [t for sq in planned for t in sq.coverage_key]
    cost = _measure_cost(_ROOT, [_unit_covering(all_terms, uid="full")], steps=3)
    assert cost == 0.0
