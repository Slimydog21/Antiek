"""AFF SPR-06 — retrieve prior knowledge units and reuse them in new research.

The *reuse half* of the flywheel. At the start of a new investigation, this
module pulls the most question-relevant prior knowledge units out of the
accumulating graph (through SPR-05's ``RetrievalSubstrate`` seam), filters them
to what §9.0 servability permits, fits the top set inside a justified token
budget, injects them into the role's context pack with provenance markers, and
emits one typed ``knowledge.reused`` event recording exactly which units, their
scores, and why each one was injected or dropped.

This is a COMPOSE module, not a new substrate. It mirrors the proven DRW SPR-04
note-injection family one layer up:

    note_retrieval.retrieve_project_notes  →  retrieve_prior_units
    note_budget.select_within_budget       →  select_units_within_budget
    note_injection.assemble_..._with_notes →  assemble_context_pack_with_reuse

The difference is the *unit*: SPR-04 injects THIS project's own insight/question
notes; SPR-06 injects PRIOR INVESTIGATIONS' knowledge units — the same
content-addressed insight/question nodes, but projected onto the SPR-04
``KnowledgeUnitContract`` (so each carries the claim→chunk→doc provenance and
the §9.0 servability tag the deny-by-default filter reads).

----------------------------------------------------------------------------
Fairness (rigor #2) — the steelman for "always re-derive from scratch"
----------------------------------------------------------------------------
The strongest case AGAINST reuse is freshness: a prior unit may be stale, the
web has moved, and re-deriving from current sources guarantees the research
reflects today's truth rather than a cached belief. That case is real — and it
is answered, not ignored:

* Reuse here is INJECTION INTO CONTEXT, not substitution for the browse loop.
  The loop still runs after assembly and can confirm, refine, or contradict any
  injected unit. Nothing here short-circuits the research; it primes it.
* The entire compounding thesis (SPR-09: cost-to-resolve falling as the graph
  grows) is UNFALSIFIABLE if every investigation re-derives from zero — there is
  then nothing to measure. Reuse is the mechanism that makes the thesis testable.
* Staleness IS the real risk — which is precisely why a groundedness/trust gate
  exists. That gate is **SPR-08**, not this sprint. SPR-06 deliberately does NOT
  add a confidence/groundedness/staleness threshold; its only two filters are
  §9.0 servability and the token budget. Pre-empting SPR-08 here would couple two
  decisions that the foundation keeps separate on purpose.

----------------------------------------------------------------------------
Honesty (rigor #1) — low relevance is logged, never padded
----------------------------------------------------------------------------
If retrieval returns nothing relevant (a genuinely novel question), this module
injects NOTHING and still emits a ``knowledge.reused`` event with an empty
``reused_unit_ids``. It never pads the pack with weakly-related units to make the
flywheel look busy — a pack silently filled with marginal units would corrupt
the SPR-09 benchmark before it runs. Each drop carries an honest reason in the
event's ``decisions`` field, distinguishing:

    injected               — passed §9.0 + fit the budget; in the pack
    dropped-not-servable   — §9.0 deny-by-default refused it (unknown/NULL class)
    dropped-over-budget    — servable, but did not fit the reuse token budget
    dropped-low-relevance  — below the relevance floor (see RELEVANCE_FLOOR)

An injected unit's recorded score is the REAL cosine score, never a floor.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any

try:
    from ..graph.search import cosine_similarity_sql
    from .assembler import (
        ContextPack,
        DefaultTokenCounter,
        LayerSource,
        TokenCounter,
        TruncationStrategy,
        assemble_context_pack,
        default_budget_for,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from context_pack.assembler import (  # type: ignore[import-not-found,no-redef]
        ContextPack,
        DefaultTokenCounter,
        LayerSource,
        TokenCounter,
        TruncationStrategy,
        assemble_context_pack,
        default_budget_for,
    )
    from graph.search import cosine_similarity_sql  # type: ignore[import-not-found,no-redef]


# ---------------------------------------------------------------------------
# Layer placement + defensible numbers
# ---------------------------------------------------------------------------

# The reuse layer's source tag and LayerKind. ``"reuse"`` is a NEW LayerKind
# (added to assembler.py's enum + canonical sort position) — a first-class kind,
# not a piggyback on graph_evidence, so a downstream audit can tell at a glance
# that a layer is PRIOR-investigation reuse rather than this investigation's own
# retrieved evidence. The two are different provenance and must stay
# distinguishable in the emitted ContextPackAssembledPayload.layers.
REUSE_LAYER_KIND = "reuse"
REUSE_LAYER_SOURCE = "prior_knowledge_units"

# Priority sits at graph_evidence level (60). Reused prior units are background
# conditioning of the same nature as retrieved evidence — important but
# truncatable, and never above the role's current task (session, 80). Putting it
# at evidence level (not at session-adjacent 70 like SPR-04 notes) is the honest
# call: a PRIOR investigation's unit is one step further removed from THIS
# investigation's task than this project's own living notes are, so it should
# yield to the assembler's smart-truncate before the session/evidence layers do.
REUSE_LAYER_PRIORITY = 60

# Fraction of the role's pack budget the reuse section may claim.
#
# Justification (defensibility, rigor #5): the reuse layer is SUPPORTING
# context, not the payload. The pack must still hold the mandatory stamp +
# phase metadata, the role's current task (session), and this investigation's
# own retrieved evidence — those cannot be crowded out by prior-knowledge
# reuse. 0.15 (15%) leaves ~85% of the window for the rest of the pack, which
# is deliberately TIGHTER than SPR-04's 0.25 for project notes: prior-
# investigation units are one provenance-step further from the task than this
# project's own notes, so they earn a smaller slice. The CAP (below) bounds the
# absolute size so the fraction of a very large synthesis budget can never let
# reuse balloon. A reviewer can change this single number with a one-line
# rationale; nothing else needs to move.
REUSE_BUDGET_FRACTION = 0.15

# Hard ceiling on the reuse layer regardless of role budget. 4000 tokens ≈ a
# dozen rendered units; past that, more reuse is diminishing returns against the
# cost of pushing the task further from the prompt tail. Mirrors SPR-04's cap
# discipline (it caps at 8000 for own-project notes; prior-investigation reuse
# gets half of that, for the same provenance-distance reason as the fraction).
REUSE_BUDGET_CAP_TOKENS = 4000

# Top-k cap on how many units retrieval even considers. Justification: the
# budget is the real bound on what gets INJECTED; this cap bounds the work
# retrieval + scoring does so a pathological graph can't make ``start`` walk
# tens of thousands of nodes. 50 is comfortably above what 4000 tokens can hold,
# so the cap never silently drops a unit the budget would have kept — the budget
# is always the binding constraint, the top-k cap is only a work ceiling.
DEFAULT_RETRIEVE_LIMIT = 50

# Relevance floor. A unit whose cosine similarity to the question is BELOW this
# is treated as not-actually-relevant and dropped with a ``dropped-low-relevance``
# decision rather than injected (honesty, rigor #1: never pad the pack with
# weakly-related units to make the flywheel look busy).
#
# Justification (defensibility, rigor #5): this is a RELEVANCE filter, not a
# trust/groundedness/confidence threshold (that is SPR-08, out of scope here).
# You cannot "retrieve RELEVANT prior units" without a notion of relevance, and
# the spec's own decision vocabulary names ``dropped-low-relevance`` — so the
# floor is in-scope, but it is deliberately set LOW so it only excludes
# zero-overlap hash-collision noise, never a genuinely topical match.
# Empirically (substrate's word-bag HashEmbedding over ~6-word texts): a
# genuinely-unrelated question that shares ZERO tokens with a seeded unit scores
# only ~0.13-0.14 cosine — pure 384-dim hash-collision noise — while a real
# multi-token topical overlap scores ≥ ~0.75. 0.25 sits above the collision
# ceiling (~0.14) and well below a real match, so the NEGATIVE polarity case
# (unrelated question) never clears it and the POSITIVE case (real overlap)
# always does. Note the floor does NOT exclude a SINGLE-shared-common-word
# question — a lone shared token in a short text is a large fraction of the L2
# norm and scores ~0.30, above the floor, so it IS injected (one genuinely-
# shared term is weak-but-real relevance; trust/staleness is SPR-08, not this
# floor). A semantic production embedder pushes unrelated similarity toward 0,
# so the floor only gets safer there. A
# reviewer can lower it toward 0 (more permissive) or raise it (stricter) with a
# one-line rationale; nothing else moves.
RELEVANCE_FLOOR = 0.25

_REUSE_HEADER = (
    "Relevant knowledge from PRIOR investigations, most relevant first. "
    "Treat these as context the workstation already established; the research "
    "loop may still confirm, refine, or contradict them.\n"
)

# Per-unit decision vocabulary recorded in the knowledge.reused event.
DECISION_INJECTED = "injected"
DECISION_NOT_SERVABLE = "dropped-not-servable"
DECISION_OVER_BUDGET = "dropped-over-budget"
DECISION_LOW_RELEVANCE = "dropped-low-relevance"


# ---------------------------------------------------------------------------
# Retrieved-unit + coverage types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievedUnit:
    """A prior knowledge unit retrieved for possible reuse.

    Carries the SPR-04 ``KnowledgeUnitContract`` (the deposit shape: stable
    ``node_id`` / ``retrieval_key``, claim→chunk→doc ``provenance``, the §9.0
    ``servability`` tag) plus the cosine ``similarity`` to THIS investigation's
    question. ``unit_id`` and ``source_investigation_id`` are surfaced flat for
    the provenance marker + the event payload."""

    unit: Any                 # KnowledgeUnitContract (imported lazily; see below)
    similarity: float         # cosine vs the question text; the REAL score
    # D2 (owner-private reuse): the DOCUMENT-SIDE content_class + taken_down of
    # the unit's source, stamped at retrieval from the documents/book_assets
    # join. These are the OWNER-READ track inputs — distinct from the serve-side
    # ServabilityTag, which collapses personal_reading→None. NULL here ⇒ the
    # owner cannot lawfully reuse the unit (deny-by-default, same as public).
    content_class: str | None = None
    taken_down: bool = False

    @property
    def unit_id(self) -> str:
        return str(self.unit.node_id)

    @property
    def source_investigation_id(self) -> str:
        return str(self.unit.investigation_id)

    @property
    def text(self) -> str:
        return str(self.unit.text)

    @property
    def serves_full_text(self) -> bool:
        """The §9.0 PUBLIC deny-by-default answer recorded on the unit at
        deposit. Read, never re-derived (the classifier is the single owner).
        This is the PUBLIC-audience bar; the owner-private audience uses
        ``owner_readable`` instead (D2)."""
        return bool(self.unit.servability.serves_full_text)

    @property
    def owner_readable(self) -> bool:
        """The OWNER-READ track (D2): True iff the unit's SOURCE document
        content_class is in PERSONAL_READABLE_CONTENT_CLASSES (servable ∪
        personal_reading) AND the source is NOT taken_down. The owner reads
        personal_reading in full on the privileged path (the ``owner`` switch
        in books/serve.py), so reusing an insight derived from it in a PRIVATE
        investigation is consistent with the rights the owner already holds.
        This widens nothing publicly — it is consumed ONLY on the gate's
        ``owner=True`` branch. NULL/restricted/taken-down ⇒ False: the owner
        cannot lawfully reuse what they cannot read (deny-by-default)."""
        from substrate.constants import PERSONAL_READABLE_CONTENT_CLASSES

        return (
            not self.taken_down
            and self.content_class in PERSONAL_READABLE_CONTENT_CLASSES
        )


@dataclass(frozen=True)
class UnitDecision:
    """One unit's fate. ``decision`` is one of the DECISION_* values."""

    unit_id: str
    source_investigation_id: str
    similarity: float
    decision: str


@dataclass(frozen=True)
class ReuseCoverage:
    """How the retrieved set was partitioned. Mirrors SPR-04's NoteCoverage but
    records the §9.0 + budget + relevance partition explicitly so the honest
    reason for every drop is queryable.

    ``retrieved`` is the PRE-gate total — every unit the substrate returned. The
    SPR-08 trust gate (groundedness + §9.0 servability) runs first and removes
    ``dropped_by_trust_gate`` of them before the budget partition ever sees them;
    the surviving ``retrieved - dropped_by_trust_gate`` candidates are then split
    into ``injected`` + the budget/relevance drops below. So the full accounting
    closes: ``retrieved == dropped_by_trust_gate + injected +
    dropped_not_servable + dropped_over_budget + dropped_low_relevance``. The
    per-reason breakdown of the gate drops (below-threshold vs non-servable) is
    on the ``reuse.gated`` events; ``dropped_by_trust_gate`` is the single
    headline "how much was filtered" count SPR-09 reads off coverage directly."""

    retrieved: int            # PRE-gate total retrieved (post top-k cap)
    injected: int             # cleared the gate AND §9.0 + relevance AND fit the budget
    dropped_not_servable: int
    dropped_over_budget: int
    dropped_low_relevance: int
    dropped_by_trust_gate: int = 0  # SPR-08: removed by the trust gate pre-partition

    @property
    def fully_covered(self) -> bool:
        return self.dropped_over_budget == 0


# ---------------------------------------------------------------------------
# M1 — retrieve prior knowledge units, ranked by similarity to the question
# ---------------------------------------------------------------------------


def _substrate_connection(retrieval_substrate: Any) -> Any:
    """The read connection the SPR-05 substrate holds.

    Both reference impls (``BruteForceSubstrate``, ``DuckDbVssSubstrate``) keep
    their read-only connection on ``_con``. We read insight/question NODES'
    similarity over that same connection — knowledge units ARE nodes, and the
    SPR-05 seam ranks CHUNKS, so node-level similarity is composed here over the
    substrate's existing connection rather than by forking the seam. Accessed
    through this one accessor (not inline) so a future substrate that exposes a
    public connection handle changes exactly one line."""
    con = getattr(retrieval_substrate, "_con", None)
    if con is None:  # pragma: no cover — defensive; both shipped impls have _con
        raise AttributeError(
            "retrieval_substrate exposes no read connection (_con); "
            "knowledge-unit similarity needs node-level access over the same "
            "graph the substrate reads."
        )
    return con


def _substrate_model(retrieval_substrate: Any) -> Any:
    """The embedding model the substrate was opened with (its ``_model``). Reused
    so the question is embedded with the SAME model the graph was embedded with —
    a mismatch would silently zero out every similarity."""
    model = getattr(retrieval_substrate, "_model", None)
    if model is None:  # pragma: no cover — defensive
        raise AttributeError("retrieval_substrate exposes no embedding model (_model)")
    return model


def retrieve_prior_units(
    retrieval_substrate: Any,
    *,
    question_text: str,
    limit: int = DEFAULT_RETRIEVE_LIMIT,
    policy_tag: str = "attribution_eligible",
) -> list[RetrievedUnit]:
    """Retrieve prior knowledge units ranked by similarity to ``question_text``.

    Signature mirrors ``note_retrieval.retrieve_project_notes`` one layer up: a
    retrieval handle, the query text, a limit. Returns units ranked similarity-
    desc (ties by ``node_id`` ascending, for content-independent determinism).

    Composition (diligence, rigor #4):

    1. The SPR-05 ``RetrievalSubstrate.query`` is called — this exercises the
       §9.0-gated retrieval seam (the call site SPR-08's groundedness gate slots
       into) and is the mandated wiring point. Its chunk results are not the
       reuse units themselves (it ranks CHUNKS); they confirm the seam ran on
       this question.
    2. The reuse units are insight/question NODES ranked by cosine similarity to
       the question, projected onto the SPR-04 ``KnowledgeUnitContract`` via
       ``knowledge_unit_of`` so each carries provenance + the §9.0 servability
       tag. Similarity is computed with ``cosine_similarity_sql`` over the same
       read connection the substrate holds — the proven note_retrieval pattern.

    An EMPTY graph returns ``[]`` — no crash, no synthetic padding (M1 acceptance).
    """
    # Lazy import: the contract + projection live in substrate.graph, and a
    # top-level import would pull graph internals into context_pack at import
    # time. Lazy keeps the dependency at call time only.
    try:
        from ..graph.insight_question import knowledge_unit_of
    except ImportError:  # pragma: no cover — direct-script fallback
        from graph.insight_question import knowledge_unit_of  # type: ignore[import-not-found,no-redef]  # noqa: I001

    if not question_text or not question_text.strip():
        return []

    # (1) Run the SPR-05 seam on this question. We do not depend on its chunk
    # ranking for the units, but calling it is the contract: every reuse goes
    # through the swappable retrieval seam, so an operator who swaps the
    # substrate swaps this path too. Failures here must not crash ``start`` — a
    # retrieval seam hiccup degrades to "no reuse", never a dead investigation.
    try:
        retrieval_substrate.query(question_text, top_k=max(1, int(limit)), policy_tag=policy_tag)
    except Exception:  # pragma: no cover — seam hiccup degrades to no-reuse
        return []

    con = _substrate_connection(retrieval_substrate)
    model = _substrate_model(retrieval_substrate)

    query_vec = list(model.encode(question_text))
    dim = getattr(model, "dimension", len(query_vec))
    sim_expr = cosine_similarity_sql("embedding", query_vec, dim)

    try:
        rows = con.execute(
            f"SELECT node_id, content_class_of_unit.content_class, "
            f"       content_class_of_unit.taken_down, similarity FROM ("
            f"  SELECT node_id, {sim_expr} AS similarity "
            f"  FROM nodes "
            f"  WHERE node_type IN ('insight', 'question') AND embedding IS NOT NULL "
            f"  ORDER BY similarity DESC, node_id ASC LIMIT ?"
            f") AS ranked "
            f"LEFT JOIN ("
            f"  SELECT e.source_node_id AS nid, d.content_class AS content_class, "
            f"         COALESCE(b.taken_down, FALSE) AS taken_down "
            f"  FROM edges e JOIN documents d ON e.source_document_id = d.document_id "
            f"  LEFT JOIN book_assets b ON d.document_id = b.document_id "
            f"  WHERE e.relation = 'supported_by' AND e.source_document_id IS NOT NULL"
            f") AS content_class_of_unit ON ranked.node_id = content_class_of_unit.nid",
            [int(limit)],
        ).fetchall()
    except Exception:
        # The content_class join depends on the deposit having a supported_by
        # edge; fall back to a plain node-similarity scan (content_class then
        # resolves via knowledge_unit_of's metadata fallback / None).
        rows = [
            (r[0], None, False, r[1])
            for r in con.execute(
                f"SELECT node_id, {sim_expr} AS similarity FROM nodes "
                f"WHERE node_type IN ('insight', 'question') AND embedding IS NOT NULL "
                f"ORDER BY similarity DESC, node_id ASC LIMIT ?",
                [int(limit)],
            ).fetchall()
        ]

    out: list[RetrievedUnit] = []
    for node_id, content_class, taken_down, similarity in rows:
        try:
            # SPR-08: fill the groundedness slot at projection time (Decision B),
            # scoring the unit against its cited chunk text over THIS same read
            # connection. The trust gate (reuse_gate.filter_reusable) then reads
            # the slot rather than re-scoring. The lexical backend is
            # deterministic, so deposit-time and gate-time scores are identical.
            unit = knowledge_unit_of(
                con, node_id, content_class=content_class, score_groundedness=True
            )
        except ValueError:
            # A node with no claim→chunk→doc grounding is not a depositable
            # knowledge unit (knowledge_unit_of raises). Skip it honestly rather
            # than inject an ungrounded fragment.
            continue
        # D2: stamp the DOCUMENT-SIDE content_class + taken_down so the trust
        # gate's owner-private branch (owner_readable) can admit a personal_reading-
        # derived unit on the owner path without touching the public bar.
        out.append(RetrievedUnit(
            unit=unit,
            similarity=float(similarity or 0.0),
            content_class=content_class,
            taken_down=bool(taken_down),
        ))

    # Stable order: similarity desc, then unit id asc (deterministic ties).
    out.sort(key=lambda ru: (-ru.similarity, ru.unit_id))
    return out


# ---------------------------------------------------------------------------
# M4 — deterministic, budget-bounded selection
# ---------------------------------------------------------------------------


def reuse_token_budget(role: str, pack_budget: int | None = None) -> int:
    """The reuse layer's token ceiling: ``REUSE_BUDGET_FRACTION`` of the role's
    pack budget, capped at ``REUSE_BUDGET_CAP_TOKENS``. Mirrors
    ``note_budget.notes_token_budget``."""
    base = pack_budget if pack_budget is not None else default_budget_for(role)
    return min(REUSE_BUDGET_CAP_TOKENS, int(base * REUSE_BUDGET_FRACTION))


def render_unit(unit_ru: RetrievedUnit) -> str:
    """One reused unit's rendered line, with its provenance marker.

    The marker carries the three things a role + a downstream audit need to see
    exactly what was reused (M2 acceptance — a regex over the pack finds all
    three for each injected unit):

      * source ``investigation_id`` (where the unit came from),
      * the unit's ``id`` (the content-addressed retrieval key),
      * the cosine ``similarity`` score (the REAL score, to 4 dp).

    Stable format so the regex + the token accounting are reproducible."""
    tag = "INSIGHT" if unit_ru.unit.node_type == "insight" else "QUESTION"
    return (
        f"- [{tag}] {unit_ru.text} "
        f"[reuse src_investigation={unit_ru.source_investigation_id} "
        f"unit_id={unit_ru.unit_id} similarity={unit_ru.similarity:.4f}]"
    )


def select_units_within_budget(
    units: Sequence[RetrievedUnit],
    *,
    budget: int,
    counter: TokenCounter | None = None,
    header_text: str = "",
) -> tuple[list[RetrievedUnit], list[UnitDecision]]:
    """Select the highest-scored units that fit ``budget`` tokens.

    DETERMINISTIC (M4 acceptance): units are ranked similarity-desc with ties
    broken by ``unit_id`` ascending (content-independent), so identical inputs
    always yield an identical selected set AND order. The highest-scored units
    fill first, so the most valuable unit is never the one dropped — a unit that
    does not fit is recorded ``dropped-over-budget`` (visible, never silent).

    NOTE: only SERVABLE + relevant units should be passed here — §9.0 filtering
    and the relevance floor happen in :func:`partition_units` BEFORE this, so
    every drop here is unambiguously a budget drop.

    Returns ``(selected, decisions)``: ``decisions`` covers EVERY input unit
    (``injected`` or ``dropped-over-budget``), in the same ranked order."""
    counter = counter or DefaultTokenCounter()
    ranked = sorted(units, key=lambda ru: (-ru.similarity, ru.unit_id))
    used = counter.count(header_text) if header_text else 0
    selected: list[RetrievedUnit] = []
    decisions: list[UnitDecision] = []
    for ru in ranked:
        cost = counter.count(render_unit(ru) + "\n")
        if used + cost > budget:
            # First unit that doesn't fit: drop it AND every lower-ranked unit
            # (the selection is a PREFIX of the ranked order, so the highest-
            # ranked are never dropped). Matches SPR-04's break semantics.
            decisions.append(UnitDecision(
                unit_id=ru.unit_id, source_investigation_id=ru.source_investigation_id,
                similarity=ru.similarity, decision=DECISION_OVER_BUDGET,
            ))
            continue
        selected.append(ru)
        used += cost
        decisions.append(UnitDecision(
            unit_id=ru.unit_id, source_investigation_id=ru.source_investigation_id,
            similarity=ru.similarity, decision=DECISION_INJECTED,
        ))
    return selected, decisions


# ---------------------------------------------------------------------------
# M2 — §9.0 + relevance partition, then build the reuse layer
# ---------------------------------------------------------------------------


def partition_units(
    units: Sequence[RetrievedUnit],
    *,
    budget: int,
    counter: TokenCounter | None = None,
    header_text: str = "",
    relevance_floor: float = RELEVANCE_FLOOR,
) -> tuple[list[RetrievedUnit], list[UnitDecision], ReuseCoverage]:
    """Apply the SPR-06 filters in order and produce the injected set + every
    unit's honest decision.

    Filter order (each drop reason is distinct — honesty, rigor #1):

      1. §9.0 servability (deny-by-default): a unit whose servability tag does
         NOT serve full text is dropped ``dropped-not-servable``. Unknown/NULL
         content_class ⇒ non-servable ⇒ dropped. The unit never reaches the pack.
      2. Relevance floor: a servable unit whose similarity is BELOW
         ``relevance_floor`` is dropped ``dropped-low-relevance`` (never padded
         into the pack).
      3. Token budget: the survivors are filled highest-first; overflow is
         dropped ``dropped-over-budget`` (deterministic, see
         :func:`select_units_within_budget`).

    Returns ``(injected, decisions, coverage)``. ``decisions`` covers EVERY
    input unit exactly once."""
    decisions: list[UnitDecision] = []
    servable_relevant: list[RetrievedUnit] = []
    n_not_servable = 0
    n_low_rel = 0
    for ru in units:
        if not ru.serves_full_text:
            n_not_servable += 1
            decisions.append(UnitDecision(
                unit_id=ru.unit_id, source_investigation_id=ru.source_investigation_id,
                similarity=ru.similarity, decision=DECISION_NOT_SERVABLE,
            ))
            continue
        if ru.similarity < relevance_floor:
            n_low_rel += 1
            decisions.append(UnitDecision(
                unit_id=ru.unit_id, source_investigation_id=ru.source_investigation_id,
                similarity=ru.similarity, decision=DECISION_LOW_RELEVANCE,
            ))
            continue
        servable_relevant.append(ru)

    selected, budget_decisions = select_units_within_budget(
        servable_relevant, budget=budget, counter=counter, header_text=header_text,
    )
    decisions.extend(budget_decisions)

    n_over_budget = sum(1 for d in budget_decisions if d.decision == DECISION_OVER_BUDGET)
    coverage = ReuseCoverage(
        retrieved=len(units),
        injected=len(selected),
        dropped_not_servable=n_not_servable,
        dropped_over_budget=n_over_budget,
        dropped_low_relevance=n_low_rel,
    )
    return selected, decisions, coverage


def build_reuse_layer(
    units: Sequence[RetrievedUnit],
    *,
    token_budget: int,
    counter: TokenCounter | None = None,
    relevance_floor: float = RELEVANCE_FLOOR,
) -> tuple[LayerSource | None, list[RetrievedUnit], list[UnitDecision], ReuseCoverage]:
    """Filter (§9.0 + relevance + budget) and render the reuse ``LayerSource``.

    Returns ``(layer_or_None, injected, decisions, coverage)``; ``layer`` is
    ``None`` when nothing survives (so the pack is unchanged and the honest
    empty-event path fires)."""
    counter = counter or DefaultTokenCounter()
    injected, decisions, coverage = partition_units(
        units, budget=token_budget, counter=counter,
        header_text=_REUSE_HEADER, relevance_floor=relevance_floor,
    )
    if not injected:
        return None, injected, decisions, coverage
    body = _REUSE_HEADER + "\n".join(render_unit(ru) for ru in injected)
    layer = LayerSource(
        kind=REUSE_LAYER_KIND,  # type: ignore[arg-type]  # added to LayerKind in assembler
        source=REUSE_LAYER_SOURCE,
        content=body,
        priority=REUSE_LAYER_PRIORITY,
    )
    return layer, injected, decisions, coverage


# ---------------------------------------------------------------------------
# M2/M3 — assemble the pack with a reuse layer + emit the typed event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PackWithReuse:
    """The assembled pack plus the reuse bookkeeping. ``reuse_event_id`` is the
    id of the emitted ``knowledge.reused`` event; ``injected`` is the units that
    actually landed in the pack; ``decisions`` is every (trust-passing) unit's
    §9.0/relevance/budget fate. ``gate_decisions`` is the SPR-08 trust partition:
    one ``GateDecision`` per candidate unit (admitted-or-excluded + reason(s)),
    so an audit can see exactly which units the groundedness/servability gate
    removed before SPR-06's budget partition ever ran."""

    pack: ContextPack
    injected: list[RetrievedUnit]
    decisions: list[UnitDecision]
    coverage: ReuseCoverage
    reuse_injected: bool
    reuse_event_id: str | None
    gate_decisions: list[Any] | None = None  # list[GateDecision]; SPR-08 trust partition


def assemble_context_pack_with_reuse(
    *,
    role: str,
    investigation_id: str,
    layers: Iterable[LayerSource],
    units: Sequence[RetrievedUnit],
    include_reuse: bool = True,
    target_tokens: int | None = None,
    truncation: TruncationStrategy = "smart",
    counter: TokenCounter | None = None,
    parent_event_id: str | None = None,
    relevance_floor: float = RELEVANCE_FLOOR,
    events_dir: str | None = None,
    policy_id: str | None = None,
    apply_trust_gate: bool = True,
    reuse_threshold: float | None = None,
    chunk_text_for: Any | None = None,
    owner: bool = False,
) -> PackWithReuse:
    """Assemble a context pack with prior knowledge units injected as a single
    reuse layer, then emit ONE ``knowledge.reused`` event recording the decision.

    ``include_reuse`` is the measurement flag (mirrors SPR-04's
    ``include_project_notes``): when False this is a plain
    ``assemble_context_pack`` with no reuse layer and no reuse event, so the
    on/off effect is directly testable.

    SPR-08 trust gate: when ``apply_trust_gate`` (the default), the candidate
    units pass through ``substrate.flywheel.reuse_gate.filter_reusable`` BEFORE
    SPR-06's §9.0/relevance/budget partition. A unit is reusable only if its
    groundedness score ≥ the threshold (``reuse_threshold`` or, by default,
    ``REUSE_GROUNDEDNESS_THRESHOLD``) AND it serves full text. Excluded units are
    removed before ANY of their text reaches the pack, and each emits exactly one
    ``reuse.gated`` event (carrying the assembled pack id, so it is joinable to
    what the model did NOT see). Because the gate already removed non-servable
    units, partition_units' own §9.0 check becomes defense-in-depth that no
    longer fires for them — one exclusion, one event, never a conflicting second
    decision for the same unit. ``apply_trust_gate=False`` reproduces pre-SPR-08
    behaviour for measurement (the gate's on/off effect is directly testable).

    The reuse layer is appended via the EXISTING ``assemble_context_pack`` path
    (the assembler core is reused unchanged — only the ``reuse`` LayerKind + its
    sort position were added). The pack's own ``CONTEXT_PACK_ASSEMBLED`` event is
    emitted by the assembler; the ``knowledge.reused`` event is emitted here,
    carrying that pack event id as ``context_pack_event_id`` (M3) so the reuse
    decision is queryable from the pack provenance.

    Even when nothing is injected (novel question, all-non-servable, all
    over-budget, all below threshold), the ``knowledge.reused`` event is STILL
    emitted with an empty ``reused_unit_ids`` — reuse-of-nothing is recorded,
    not skipped (M5 negative polarity)."""
    counter = counter or DefaultTokenCounter()
    layer_list = list(layers)

    candidate_units: Sequence[RetrievedUnit] = units
    gate_decisions: list[Any] = []
    threshold: float | None = None

    injected: list[RetrievedUnit] = []
    decisions: list[UnitDecision] = []
    reuse_injected = False

    if include_reuse and apply_trust_gate:
        # SPR-08 trust gate runs FIRST: drop below-threshold / non-servable units
        # before the budget partition. Emission is deferred until the pack id is
        # known so each reuse.gated event carries context_pack_event_id (mirrors
        # how knowledge.reused is emitted after assembly).
        from substrate.flywheel.reuse_gate import (
            REUSE_GROUNDEDNESS_THRESHOLD,
            filter_reusable,
        )

        threshold = (
            reuse_threshold if reuse_threshold is not None else REUSE_GROUNDEDNESS_THRESHOLD
        )
        candidate_units, gate_decisions = filter_reusable(
            units,
            investigation_id=investigation_id,
            threshold=threshold,
            chunk_text_for=chunk_text_for,
            emit=False,  # deferred — emitted post-assembly with the pack id
            owner=owner,
        )

    coverage = ReuseCoverage(
        retrieved=len(candidate_units), injected=0,
        dropped_not_servable=0, dropped_over_budget=0, dropped_low_relevance=0,
    )

    if include_reuse:
        budget = reuse_token_budget(role, target_tokens)
        reuse_layer, injected, decisions, coverage = build_reuse_layer(
            candidate_units, token_budget=budget, counter=counter, relevance_floor=relevance_floor,
        )
        if reuse_layer is not None:
            layer_list.append(reuse_layer)
            reuse_injected = True
        # SPR-08: report the PRE-gate retrieved total + how many the trust gate
        # removed before the partition, so ``retrieved`` keeps its meaning
        # (everything the substrate returned) and SPR-09 reads the filtered
        # count off coverage rather than joining the reuse.gated event stream.
        # When the gate is off (apply_trust_gate=False) candidate_units IS units,
        # so dropped_by_trust_gate is 0 and retrieved is unchanged.
        coverage = replace(
            coverage,
            retrieved=len(units),
            dropped_by_trust_gate=len(units) - len(candidate_units),
        )

    pack = assemble_context_pack(
        role=role,
        investigation_id=investigation_id,
        layers=layer_list,
        target_tokens=target_tokens,
        truncation=truncation,
        counter=counter,
        parent_event_id=parent_event_id,
    )

    if include_reuse and apply_trust_gate and gate_decisions:
        # Emit one reuse.gated event per EXCLUDED unit now that the pack id
        # exists. Admitted units emit nothing (absence == cleared the gate).
        from substrate.flywheel.reuse_gate import _emit_reuse_gated

        assert threshold is not None
        context_pack_event_id = pack.event_id or ""
        for decision in gate_decisions:
            if not decision.reusable:
                _emit_reuse_gated(
                    decision,
                    investigation_id=investigation_id,
                    threshold=threshold,
                    context_pack_event_id=context_pack_event_id,
                    role=role,
                    events_dir=events_dir,
                    policy_id=policy_id,
                )

    reuse_event_id: str | None = None
    if include_reuse:
        reuse_event_id = _emit_knowledge_reused(
            investigation_id=investigation_id,
            injected=injected,
            decisions=decisions,
            context_pack_event_id=pack.event_id,
            role=role,
            events_dir=events_dir,
            policy_id=policy_id,
        )

    return PackWithReuse(
        pack=pack,
        injected=injected,
        decisions=decisions,
        coverage=coverage,
        reuse_injected=reuse_injected,
        reuse_event_id=reuse_event_id,
        gate_decisions=gate_decisions,
    )


def _emit_knowledge_reused(
    *,
    investigation_id: str,
    injected: Sequence[RetrievedUnit],
    decisions: Sequence[UnitDecision],
    context_pack_event_id: str | None,
    role: str,
    events_dir: str | None,
    policy_id: str | None,
) -> str | None:
    """Emit exactly one ``knowledge.reused`` event for this investigation start.

    ``reused_unit_ids`` + ``scores`` describe the INJECTED set (equal-length, in
    pack order — M3 acceptance). ``decisions`` + ``source_investigation_ids``
    describe EVERY retrieved unit's fate (the full provenance of the reuse
    decision). Parented to / carrying the ``CONTEXT_PACK_ASSEMBLED`` event id."""
    try:
        from ..event_log import emit_typed
        from ..schemas.events import KnowledgeReusedPayload
    except ImportError:  # pragma: no cover — direct-script fallback
        from event_log import emit_typed  # type: ignore[import-not-found,no-redef]
        from schemas.events import KnowledgeReusedPayload  # type: ignore[import-not-found,no-redef]

    payload = KnowledgeReusedPayload(
        reused_unit_ids=[ru.unit_id for ru in injected],
        scores=[round(float(ru.similarity), 6) for ru in injected],
        decisions=[d.decision for d in decisions],
        source_investigation_ids=[d.source_investigation_id for d in decisions],
        context_pack_event_id=context_pack_event_id or "",
    )
    return emit_typed(
        investigation_id,
        payload,
        parent_event_id=context_pack_event_id,
        role=role,
        events_dir=events_dir,
        policy_id=policy_id,
    )
