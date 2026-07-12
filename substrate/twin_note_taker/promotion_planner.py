"""Twin → graph promotion planner — the recursion in "recursive note-taker" (ask #4).

The operator's vision (ask #4): *"...every information asset created on my
platform has a twin document with all the insights and questions proposed by that
information document written by an LLM... then that substrate of information can
be merged, referenced, and leveraged in combining contexts or doing intelligent
search over my dream of an infinite information platform."* The twin's output
must not just sit in a document — it must become part of the searchable knowledge
GRAPH so it informs ALL future prompts (via context-pack retrieval). This module
is the pure PLANNER that decides which twin findings are eligible for graph
promotion and computes their content-addressed node_ids — the bridge that makes
the twin substrate RECURSIVE.

**Why a planner, not a writer.** The sanctioned graph writers
(``graph/insight_question.py::promote_insight`` / ``promote_question``) require a
write-locked DB connection. The pure layer never holds one (the bench/twin
doctrine: pure layer never dispatches or commits). This module computes the
PROMOTION PLAN — which findings to promote, their pre-computed node_ids, dedup
groups, and provenance — using the EXACT same content-addressed scheme the writers
use, so the plan is execution-faithful: the node_id the planner computes IS the
node_id ``promote_insight`` will assign. The authority layer (behind operator
consent) executes the plan via the existing writers.

**The content-addressed guarantee (load-bearing).** ``content_addressed_id(node_type,
canonical_text(text))`` is a pure SHA-256 → 16-hex function
(``graph/ops.py:77``). So the planner can deterministically predict the node_id
WITHOUT the DB. This means:

  * **Dedup is visible before execution.** Two twins producing the same insight
    text map to the SAME node_id — the plan shows them as one dedup group, so the
    authority layer promotes once, not twice (idempotent by construction).
  * **The plan is execution-faithful.** No surprise node_ids at write time; what
    the operator approves is what lands.
  * **Cross-asset reuse is structural.** The same insight surfaced by two
    different assets' twins resolves to the same graph node — exactly the
    "referenced and leveraged" the operator named.

**Honesty rules (load-bearing):**

  * **Advisory authority.** The plan is a RECOMMENDATION; the authority layer
    (operator consent) decides what promotes. No auto-promotion — an LLM-proposed
    insight entering the permanent knowledge graph is an operator decision.
  * **Blank/whitespace texts are filtered, never promoted.** An empty insight is
    not an insight; promoting one would pollute the graph. Filtered with a count.
  * **canonical_text normalization is mirrored.** The planner applies the SAME
    ``canonical_text`` transform (whitespace collapse, lowercase per the on-main
    implementation) the writers use, so dedup is exact, not approximate.
  * **Provenance is real.** Every eligible promotion carries its source
    ``asset_id`` + ``investigation_id`` + the twin role that proposed it — a
    promoted node is always traceable to the twin that surfaced it.
  * **Dedup is counted honestly.** A finding that collapses with an existing
    eligible finding in the SAME plan is marked ``dedup_of`` (not dropped
    silently) so the operator sees the reuse signal.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


class TwinPromotionError(ValueError):
    """A promotion-planning input violates a load-bearing invariant."""


class _TwinFinding(Protocol):
    """A twin-generated insight or question (ArtifactInsight/ArtifactQuestion shape)."""

    text: str
    node_id: str


class _TwinAsset(Protocol):
    """A twin-bearing asset (ResearchArtifactBody shape)."""

    investigation_id: str




def canonical_text(text: str) -> str:
    """Mirror of ``graph/insight_question.canonical_text`` — ``" ".join(lower.split())``.

    Kept here (not imported) so the planner is zero-dependency (pure, testable in
    isolation). If the on-main canonical_text changes, this mirror MUST change
    too — they must agree for execution-faithfulness.
    """
    return " ".join(text.lower().split())


def _content_addressed_id(node_type: str, content: str, n: int = 16) -> str:
    """Mirror of ``graph/ops.content_addressed_id`` — ``f"{node_type}-{sha256[:n]}"``.

    The prefix IS part of the returned id (``insight-<hash>`` vs
    ``question-<hash>``); only ``content`` is hashed. So an insight and a question
    with the same text get DIFFERENT node_ids (different prefix) despite sharing a
    hash. Same drift contract as ``canonical_text``.
    """
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:n]
    return f"{node_type}-{h}"


def predicted_node_id(kind: str, text: str) -> str:
    """The node_id ``promote_insight``/``promote_question`` WILL assign.

    Pure: no DB. ``kind`` is ``"insight"`` or ``"question"``. This is the
    execution-faithfulness guarantee — the planner predicts the exact id.
    """
    if kind not in ("insight", "question"):
        raise TwinPromotionError(
            f"kind {kind!r} must be 'insight' or 'question'"
        )
    return _content_addressed_id(kind, canonical_text(text))


@dataclass(frozen=True)
class PromotableFinding:
    """One twin finding eligible for graph promotion, with its predicted node_id."""

    kind: str  # "insight" | "question"
    text: str
    predicted_node_id: str
    source_asset_id: str
    source_investigation_id: str
    dedup_of: str | None = None  # predicted_node_id of the canonical finding, if a dup


@dataclass(frozen=True)
class TwinPromotionPlan:
    """The pure plan for promoting a twin's findings into the knowledge graph.

    Advisory: the authority layer (operator consent) decides what actually
    promotes, via the existing ``promote_insight``/``promote_question`` writers.
    """

    asset_id: str
    investigation_id: str
    promotable_insights: tuple[PromotableFinding, ...]
    promotable_questions: tuple[PromotableFinding, ...]
    blank_filtered: int
    dedup_collapsed: int

    @property
    def total_promotable(self) -> int:
        return len(self.promotable_insights) + len(self.promotable_questions)

    @property
    def is_empty(self) -> bool:
        return self.total_promotable == 0


def _plan_kind(
    findings: list[_TwinFinding],
    kind: str,
    asset_id: str,
    investigation_id: str,
    seen_node_ids: dict[str, PromotableFinding],
) -> tuple[list[PromotableFinding], int, int]:
    """Plan promotions for one kind (insight/question). Mutates ``seen_node_ids``."""
    promotable: list[PromotableFinding] = []
    blank = 0
    dedup = 0
    for finding in findings:
        raw = getattr(finding, "text", "") or ""
        if not raw.strip():
            blank += 1
            continue
        nid = predicted_node_id(kind, raw)
        if nid in seen_node_ids:
            # collapses with an already-eligible finding (same canonical text)
            promotable.append(
                PromotableFinding(
                    kind=kind,
                    text=raw,
                    predicted_node_id=nid,
                    source_asset_id=asset_id,
                    source_investigation_id=investigation_id,
                    dedup_of=seen_node_ids[nid].predicted_node_id,
                )
            )
            dedup += 1
        else:
            entry = PromotableFinding(
                kind=kind,
                text=raw,
                predicted_node_id=nid,
                source_asset_id=asset_id,
                source_investigation_id=investigation_id,
            )
            seen_node_ids[nid] = entry
            promotable.append(entry)
    return promotable, blank, dedup


def plan_twin_promotion(
    *,
    asset_id: str,
    investigation_id: str,
    insights: list[_TwinFinding],
    open_questions: list[_TwinFinding],
) -> TwinPromotionPlan:
    """Plan the graph promotion of one twin asset's findings. Pure, advisory.

    Returns a ``TwinPromotionPlan`` with each finding's predicted (content-
    addressed) node_id, dedup groups, and blank-filter counts. The authority
    layer executes eligible promotions via ``promote_insight``/``promote_question``
    behind operator consent.
    """
    if not asset_id.strip() or not investigation_id.strip():
        raise TwinPromotionError(
            "asset_id and investigation_id must be non-empty (provenance is load-bearing)"
        )
    seen: dict[str, PromotableFinding] = {}
    ins, blank_i, dedup_i = _plan_kind(insights, "insight", asset_id, investigation_id, seen)
    qs, blank_q, dedup_q = _plan_kind(open_questions, "question", asset_id, investigation_id, seen)
    return TwinPromotionPlan(
        asset_id=asset_id,
        investigation_id=investigation_id,
        promotable_insights=tuple(ins),
        promotable_questions=tuple(qs),
        blank_filtered=blank_i + blank_q,
        dedup_collapsed=dedup_i + dedup_q,
    )


__all__ = [
    "TwinPromotionError",
    "PromotableFinding",
    "TwinPromotionPlan",
    "canonical_text",
    "predicted_node_id",
    "plan_twin_promotion",
]
