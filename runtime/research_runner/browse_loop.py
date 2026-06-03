"""ACV SPR-06 — the reuse-CONSUMING browse loop (compounding made measurable).

The keystone of this sprint. ``make_demo_loop`` (``host_local.py``) is
reuse-BLIND: it charges a fixed ``cost_per_step`` for a fixed number of steps
regardless of the reuse pack, so a warm run does exactly as much work as a cold
run and the compounding benchmark's cost delta on it is an HONEST NULL (≈0 by
construction — see the "KEYSTONE CAVEAT" at
``compounding/benchmark/harness.py:36-45`` and the fixed-cost
``ctx.step(..., cost_usd=cost_per_step, ...)`` at ``host_local.py:471``).

This loop replaces that null with a REAL measurement. It:

  1. plans ``n`` sub-questions for the investigation (stable planner ids
     ``sq-0 … sq-(n-1)`` derived deterministically from the root question), then
  2. reads ``ctx.pack`` (the units ``HostLocalRunner.start`` injected — already
     §9.0-servable + trust-gated + relevance-floored + budget-fit), and
  3. for each planned sub-question, SHORT-CIRCUITS the browse/extract work iff a
     pack entry GENUINELY covers it — emitting a ``dispatch.call`` cost event
     ONLY for the UNCOVERED sub-questions.

The measurement (``compounding/benchmark/measure.py``) sums ``dispatch.call``
``cost_usd``. So cost is a function of UNCOVERED work:

    empty pack          → n dispatch.call events → full cost
    pack covers k of n  → (n − k) dispatch.call events → (n−k)/n of full cost
    pack covers all n   → 0 dispatch.call events → ~0 cost

Cost therefore drops MONOTONICALLY as coverage rises, so a warm run primed by
prior knowledge is strictly cheaper than a cold one — a genuinely-negative
warm−cold delta, NOT a clamp.

────────────────────────────────────────────────────────────────────────────
The keying decision (rigor #1 — never fabricate a saving)
────────────────────────────────────────────────────────────────────────────
A step is skipped ONLY when a pack entry genuinely covers ITS sub-question. The
keying strategy is **planner-sub-question coverage-key match + a relevance
floor**, NOT raw text similarity to the whole question:

  * Each planned sub-question gets a deterministic ``coverage_key`` — a sorted
    token signature over its salient (>3-char, de-stopworded) terms.
  * Each pack unit gets the SAME signature over its own text.
  * A sub-question is covered iff some pack unit's key SHARES enough salient
    tokens with the sub-question's key (Jaccard ≥ ``COVERAGE_JACCARD_FLOOR``)
    AND that unit's recorded similarity to the root question is ≥
    ``COVERAGE_SIMILARITY_FLOOR`` (the unit was a real retrieval hit, not noise).

Why this and not "skip any step a high-similarity unit exists for": a single
on-topic unit must not silently mark EVERY planned sub-question covered — that
would fabricate savings the graph did not earn. Keying each skip to a SPECIFIC
sub-question's tokens means an irrelevant-arm pack (off-topic units) shares no
salient tokens → covers nothing → the irrelevant arm stays FLAT (the §2 validity
control), exactly as a warm-vs-irrelevant control demands. The dual floor
(token-overlap AND retrieval-similarity) is the no-false-skip guard rigor #3
enumerates: a pack entry that merely LOOKS like a match (shares a stopword, or is
a low-similarity collision) does NOT skip.

The skip is AUDITABLE: each skipped sub-question emits a ``step`` note naming the
covering unit's ``unit_id`` + ``source_investigation_id`` + the matched key, so a
reader can reconstruct WHY cost dropped, not merely THAT it dropped.

§16: this loop NEVER opens a graph write connection. It reads ``ctx.pack``
(an in-memory list handed to it) and appends ``dispatch.call`` / ``step`` events
to its own per-investigation JSONL — the same single-writer-safe surface the
demo loop uses. No second graph writer.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

try:
    from ..event_log import emit_typed
    from ..schemas.events import DispatchCallPayload
    from .host_local import LoopContext
    from .protocol import StepEvent
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.research_runner.host_local import LoopContext  # type: ignore[no-redef]
    from runtime.research_runner.protocol import StepEvent  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas.events import DispatchCallPayload  # type: ignore[no-redef]


# --- defensible numbers (rigor #5: every constant cites its source) ---------

# How many sub-questions a single investigation plans. SOURCE: matches the demo
# loop's default ``steps=3`` (``host_local.py:452``) so the consuming loop's
# UNCOVERED-arm cost is directly comparable to the demo loop's fixed cost and the
# benchmark's existing per-arm shape is unchanged. A reviewer can raise it; cost
# scales linearly with it and the monotonicity proof is independent of the value.
DEFAULT_PLANNED_STEPS = 3

# Per-sub-question browse/extract cost when the work is NOT covered by reuse.
# SOURCE: mirrors the demo loop's ``cost_per_step=0.01`` (``host_local.py:452``)
# so the cold (fully-uncovered) arm of the consuming loop charges the same total
# the reuse-blind demo loop would — the ONLY difference this loop introduces is
# that COVERED steps are skipped. Expressed as a real provider ``dispatch.call``
# cost so ``measure.py`` (which sums ``dispatch.call.cost_usd``) sees it.
DEFAULT_COST_PER_STEP_USD = 0.01

# Tokens charged per uncovered browse step (provenance on the dispatch.call).
# SOURCE: mirrors the demo loop's ``tokens=10`` (``host_local.py:471``). Split
# 60/40 input/output is arbitrary-but-fixed; only the SUM is load-bearing for the
# token corroborating metric, and it is held constant across arms.
DEFAULT_INPUT_TOKENS = 6
DEFAULT_OUTPUT_TOKENS = 4

# Coverage floors (the no-false-skip guard). A planned sub-question is covered
# ONLY if BOTH hold for some pack unit:
#   * CONTAINMENT(sub_question_key, unit_key) >= COVERAGE_CONTAINMENT_FLOOR,
#     where containment = |sq_key ∩ unit_key| / |sq_key| — the fraction of the
#     SUB-QUESTION's distinguishing terms the unit's text contains. Containment
#     (NOT symmetric Jaccard) is the correct measure here because a real reused
#     unit is a rich multi-sentence text: a unit that fully covers a 3-term
#     sub-question shares all 3 of its terms but has many MORE of its own, so a
#     symmetric Jaccard would be small and wrongly mark the step UNCOVERED. We
#     ask "does the unit contain THIS sub-question's terms?", not "are the two
#     texts the same size?".
#   * the unit's recorded similarity to the root question >= COVERAGE_SIMILARITY_FLOOR.
# SOURCE for the similarity floor: ``RELEVANCE_FLOOR = 0.25`` in
# ``substrate/context_pack/knowledge_reuse.py:173`` — the same floor the reuse
# assembler already applied to ADMIT a unit. Re-asserting it here means a unit
# the assembler injected at exactly the floor cannot then fail this guard; we do
# NOT invent a second, looser bar. SOURCE for the containment floor: a planned
# sub-question keys on ~1-3 salient terms; 0.5 requires at least HALF of them to
# appear in the unit's text. A single shared STOPWORD never reaches the key
# (stopwords are removed), and an off-topic unit (irrelevant arm) contains NONE
# of the sub-question's distinguishing terms and scores 0 — so the irrelevant
# arm covers nothing and stays FLAT (the §2 validity control). Set at 0.5 (not
# 1.0) so a partially-stated unit still counts, but high enough that a lone
# coincidental term in a many-term sub-question does not.
COVERAGE_CONTAINMENT_FLOOR = 0.5
COVERAGE_SIMILARITY_FLOOR = 0.25

# Salient-token extraction: drop tokens <= this length + an explicit stopword set
# so a coverage key is the QUESTION's distinguishing terms, not its scaffolding.
_MIN_TOKEN_LEN = 3
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "what", "how", "why", "does", "did", "are",
        "was", "were", "from", "into", "that", "this", "which", "given", "near",
        "single", "scale", "between", "within", "current", "than",
    }
)


# ---------------------------------------------------------------------------
# Planned sub-question + coverage decision (auditable, deterministic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedSubQuestion:
    """One planned unit of browse work. ``sq_id`` is the stable planner id the
    coverage decision keys on; ``coverage_key`` is its salient-token signature."""

    sq_id: str
    text: str
    coverage_key: frozenset[str]


@dataclass(frozen=True)
class CoverageDecision:
    """Whether a planned sub-question is covered by reuse, and by WHICH unit.
    Recorded so the skip is auditable (rigor #1: name the covering unit, never
    just "cost dropped")."""

    sq_id: str
    covered: bool
    unit_id: str | None = None
    source_investigation_id: str | None = None
    matched_containment: float = 0.0
    unit_similarity: float = 0.0


def _salient_tokens(text: str) -> frozenset[str]:
    """The distinguishing terms of a text: lowercased, punctuation-split, with
    short tokens + stopwords removed. Deterministic and content-addressed (a set,
    order-independent) so identical text always yields the identical key."""
    out: set[str] = set()
    token = []
    for ch in text.lower():
        if ch.isalnum():
            token.append(ch)
        else:
            if token:
                w = "".join(token)
                if len(w) > _MIN_TOKEN_LEN and w not in _STOPWORDS:
                    out.add(w)
                token = []
    if token:
        w = "".join(token)
        if len(w) > _MIN_TOKEN_LEN and w not in _STOPWORDS:
            out.add(w)
    return frozenset(out)


def _containment(sub_key: frozenset[str], unit_key: frozenset[str]) -> float:
    """Containment of ``sub_key`` in ``unit_key``: the fraction of the
    SUB-QUESTION's distinguishing terms present in the unit's text.

    ``|sub_key ∩ unit_key| / |sub_key|`` (0 when ``sub_key`` is empty). Asymmetric
    on purpose — a rich reused unit can fully cover a small sub-question (see the
    COVERAGE_CONTAINMENT_FLOOR justification)."""
    if not sub_key or not unit_key:
        return 0.0
    inter = len(sub_key & unit_key)
    if inter == 0:
        return 0.0
    return inter / len(sub_key)


def plan_sub_questions(
    root_question: str, *, steps: int = DEFAULT_PLANNED_STEPS
) -> list[PlannedSubQuestion]:
    """Deterministically plan ``steps`` sub-questions for ``root_question``.

    DETERMINISTIC + content-addressed: the SAME root question always yields the
    SAME planned sub-questions (so cold and warm arms of the SAME question plan
    the SAME work, and the only thing that differs between arms is what the pack
    covers). Each sub-question's salient-token key is a ROTATION of the root
    question's salient tokens, so a sub-question keys on a real subset of the
    question's distinguishing terms — coverable iff a pack unit shares those
    terms. A question with too few salient terms falls back to the whole-question
    key for every sub-question (still deterministic; coverage then keys on the
    whole-question overlap)."""
    salient = sorted(_salient_tokens(root_question))
    planned: list[PlannedSubQuestion] = []
    for i in range(max(1, steps)):
        if len(salient) >= steps and steps > 0:
            # Assign a distinct, deterministic slice of the salient terms to each
            # sub-question (round-robin) so different sub-questions key on
            # different terms — a partial-overlap pack covers SOME but not all.
            key_terms = frozenset(salient[i::steps]) or frozenset(salient)
        else:
            key_terms = frozenset(salient)
        planned.append(
            PlannedSubQuestion(
                sq_id=f"sq-{i}",
                text=f"sub-question {i} of: {root_question}",
                coverage_key=key_terms,
            )
        )
    return planned


def _unit_key_and_sim(unit: Any) -> tuple[frozenset[str], float]:
    """Extract a pack unit's coverage key + its recorded similarity.

    Accepts either a ``RetrievedUnit`` (the real pack shape — ``.text`` +
    ``.similarity``) or a lightweight test double exposing the same two
    attributes. Read-only; never re-scores."""
    text = getattr(unit, "text", "") or ""
    sim = float(getattr(unit, "similarity", 0.0) or 0.0)
    return _salient_tokens(str(text)), sim


def decide_coverage(
    planned: Sequence[PlannedSubQuestion],
    pack: Sequence[Any] | None,
    *,
    containment_floor: float = COVERAGE_CONTAINMENT_FLOOR,
    similarity_floor: float = COVERAGE_SIMILARITY_FLOOR,
) -> list[CoverageDecision]:
    """Decide, for each planned sub-question, whether a pack unit GENUINELY
    covers it (and which one).

    A sub-question is covered iff some pack unit has BOTH (a) containment of the
    sub-question's key in the unit's key >= ``containment_floor`` AND (b) recorded
    similarity to the root question >= ``similarity_floor``. The dual floor is
    the no-false-skip guard (rigor #3): a unit that merely shares a stopword
    (removed from keys) or is a low-similarity collision does NOT cover.

    An EMPTY/None pack covers nothing (every sub-question UNCOVERED → full work).
    Deterministic: the best (highest-containment, tie-broken by unit_id) covering
    unit is chosen, so the recorded provenance is stable."""
    units = list(pack or ())
    unit_keys = [(_unit_key_and_sim(u), u) for u in units]
    decisions: list[CoverageDecision] = []
    for sq in planned:
        best: tuple[float, float, str, Any] | None = None  # (containment, sim, uid, unit)
        for (ukey, usim), unit in unit_keys:
            if usim < similarity_floor:
                continue
            c = _containment(sq.coverage_key, ukey)
            if c < containment_floor:
                continue
            uid = str(getattr(unit, "unit_id", "") or "")
            cand = (c, usim, uid, unit)
            # Highest containment wins; ties broken by unit_id ASC for determinism.
            if best is None or (c, usim) > (best[0], best[1]) or (
                (c, usim) == (best[0], best[1]) and uid < best[2]
            ):
                best = cand
        if best is None:
            decisions.append(CoverageDecision(sq_id=sq.sq_id, covered=False))
        else:
            c, usim, uid, unit = best
            decisions.append(
                CoverageDecision(
                    sq_id=sq.sq_id,
                    covered=True,
                    unit_id=uid or None,
                    source_investigation_id=str(
                        getattr(unit, "source_investigation_id", "") or ""
                    )
                    or None,
                    matched_containment=round(c, 6),
                    unit_similarity=round(usim, 6),
                )
            )
    return decisions


def coverage_summary(decisions: Sequence[CoverageDecision]) -> tuple[int, int]:
    """``(covered, total)`` over the decisions — the headline coverage ratio."""
    total = len(decisions)
    covered = sum(1 for d in decisions if d.covered)
    return covered, total


# ---------------------------------------------------------------------------
# The reuse-consuming loop
# ---------------------------------------------------------------------------


def _emit_uncovered_dispatch(
    ctx: LoopContext,
    sq: PlannedSubQuestion,
    *,
    cost_per_step: float,
    input_tokens: int,
    output_tokens: int,
    events_dir: str | None,
) -> None:
    """Emit ONE ``dispatch.call`` event for an UNCOVERED sub-question — the real
    browse/extract spend the measurement sums. Skipped sub-questions emit NO
    dispatch.call (that absence IS the saving). Read-only re: the graph."""
    payload = DispatchCallPayload(
        provider="browse_loop",
        model="reuse_consuming_demo",
        tier="flash",
        target_role="user_agent",
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cost_usd=float(cost_per_step),
        latency_ms=1,
        prompt_hash=f"sq:{ctx.investigation_id}:{sq.sq_id}",
        finish_reason="stop",
    )
    emit_typed(
        ctx.investigation_id,
        payload,
        role="user_agent",
        events_dir=events_dir,
    )


def make_reuse_consuming_loop(
    *,
    steps: int = DEFAULT_PLANNED_STEPS,
    cost_per_step: float = DEFAULT_COST_PER_STEP_USD,
    input_tokens: int = DEFAULT_INPUT_TOKENS,
    output_tokens: int = DEFAULT_OUTPUT_TOKENS,
    events_dir: str | None = None,
    emit_note: bool = True,
):
    """Build a reuse-CONSUMING browse loop.

    For each planned sub-question:
      * if a pack entry GENUINELY covers it → SHORT-CIRCUIT (emit an auditable
        skip ``step`` naming the covering unit; emit NO ``dispatch.call``), else
      * do the work → emit one ``dispatch.call`` (the real cost the measurement
        sums) + a ``step``.

    Empty pack → every sub-question uncovered → full cost (≡ the demo loop's
    fixed total). A pack covering k of n → (n−k) dispatch.calls → cost drops
    monotonically as coverage rises. The loop reads ``ctx.pack`` (threaded by
    ``HostLocalRunner.start``); it never writes the graph (§16).

    ``events_dir`` MUST match the runner's events dir so the dispatch.call lands
    on the same per-investigation JSONL the measurement reads. When None, the
    loop falls back to the process default events dir (the runner passes its own;
    a direct test passes the tmp dir)."""

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        root_q = ctx.sub_question
        planned = plan_sub_questions(root_q, steps=steps)
        pack = getattr(ctx, "pack", None)
        decisions = decide_coverage(planned, pack)
        decision_by_id = {d.sq_id: d for d in decisions}
        covered, total = coverage_summary(decisions)

        yield ctx.plan_event(
            f"plan for: {root_q} ({total} sub-questions; "
            f"reuse covers {covered}/{total})",
            planned_steps=total,
            covered_steps=covered,
        )

        for sq in planned:
            # Re-read the (possibly redirected) sub-question at the steering
            # checkpoint — preserves the demo loop's pause/stop/redirect contract.
            await ctx.checkpoint()
            d = decision_by_id[sq.sq_id]
            if d.covered:
                # SHORT-CIRCUIT: the pack already covers this sub-question. Emit
                # an auditable skip naming the covering unit — NO dispatch.call,
                # so the measurement sees zero cost for this step (the saving).
                yield ctx.step(
                    f"reuse-skip {sq.sq_id}: covered by prior unit "
                    f"{d.unit_id} (from {d.source_investigation_id})",
                    cost_usd=0.0,
                    tokens=0,
                    reuse_skipped=True,
                    sq_id=sq.sq_id,
                    covering_unit_id=d.unit_id,
                    covering_source_investigation_id=d.source_investigation_id,
                    matched_containment=d.matched_containment,
                    unit_similarity=d.unit_similarity,
                )
                continue
            # UNCOVERED: do the browse/extract work — one real dispatch.call.
            _emit_uncovered_dispatch(
                ctx,
                sq,
                cost_per_step=cost_per_step,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                events_dir=events_dir,
            )
            yield ctx.step(
                f"browse {sq.sq_id}: '{sq.text}'",
                cost_usd=cost_per_step,
                tokens=input_tokens + output_tokens,
                reuse_skipped=False,
                sq_id=sq.sq_id,
            )

        if emit_note:
            yield ctx.note(
                f"insight from {ctx.investigation_id}: {root_q} "
                f"(reuse covered {covered}/{total} sub-questions)"
            )
            yield ctx.question(f"open question from {ctx.investigation_id}?")

    return _loop
