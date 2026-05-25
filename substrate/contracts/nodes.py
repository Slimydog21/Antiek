"""Insight / question node contracts — the atom of the flywheel.

Owned by **DRW SPR-01** (``substrate/graph/insight_question.py``). These are
the typed *interfaces* the four workflows build and test against; they carry
field shapes only — no DB calls, no embedding, no promotion logic. The real
writer is ``promote_insight`` / ``promote_question`` (the only sanctioned
writers of ``node_type='insight'|'question'`` rows).

An insight created in Research is the same node when Read surfaces it, Write
drags it into an outline, and Speak deepens it. That "one entity everywhere"
property is the whole moat — so the contract pins the *identity* fields
(``node_id`` is content-addressed and stable across re-emission) and the
controlled *edge vocabulary*, not a per-workflow copy.

Field shapes verified against the live implementation:

* ``node_id`` — ``content_addressed_id(node_type, canonical_text)``; SHA-256
  truncated to 16 hex chars (``insight_question.py`` docstring + ``ops.py``).
* ``text`` — the node's ``canonical_label`` (``insight_question.py`` L239/L297).
* ``confidence`` — one of the four ``ConfidenceLevel`` values
  (``roles/note_taker/parser.py`` ``_VALID_CONFIDENCE``).
* edge relations — the controlled vocabulary in
  ``substrate.constants.INSIGHT_QUESTION_RELATIONS`` (verified L225-255).

The embedding is stored inline on the node row, but it is *derived data*
(rebuildable from text via the claim-embedding path); the contract exposes
``has_embedding`` rather than the vector so a consumer never depends on the
embedding's storage representation.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# The four-value confidence vocabulary, shared with the note-taker and the
# synthesizer's claims. Stated inline (not imported) so the contract package
# has zero dependency on role internals.
ConfidenceLevel = Literal["high", "moderate", "low", "unknown"]

# The controlled edge vocabulary an insight/question node may carry. Mirrors
# ``substrate.constants.INSIGHT_QUESTION_RELATIONS`` — DRW SPR-01 owns the
# authoritative tuple; this restates the *names* so a consumer can validate an
# edge without importing graph internals. A relation outside this set is a
# bug (``validate_insight_question_edge`` raises).
InsightRelation = Literal["supported_by", "contradicts", "refines"]
QuestionRelation = Literal["asks_about", "resolved_by"]

INSIGHT_RELATIONS: tuple[str, ...] = ("supported_by", "contradicts", "refines")
QUESTION_RELATIONS: tuple[str, ...] = ("asks_about", "resolved_by")


class InsightNodeContract(BaseModel):
    """A first-class ``insight`` graph node. ``node_id`` is content-addressed
    and therefore stable: re-emitting the same insight resolves to the same
    node, which is what lets one insight be *the same entity* across all four
    workflows (the SPR-06 no-duplicate invariant rests on this)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str = Field(description="Content-addressed; stable across re-emission.")
    node_type: Literal["insight"] = "insight"
    text: str = Field(description="The node's canonical_label.")
    investigation_id: str
    graph_scope: Literal["depth"] = "depth"
    confidence: ConfidenceLevel = "unknown"
    has_embedding: bool = True
    # node ids this insight rests on (``supported_by`` edge targets). The
    # originating document/chunk rides on the edge, not the node.
    supported_by: tuple[str, ...] = ()


class QuestionNodeContract(BaseModel):
    """A first-class ``question`` graph node. ``asks_about`` targets any
    substantive node or an insight; ``resolved_by`` targets the insight(s)
    that answer it. SPR-07 gap-detection reads these to find unanswered
    questions and contradictions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    node_type: Literal["question"] = "question"
    text: str
    investigation_id: str
    graph_scope: Literal["depth"] = "depth"
    has_embedding: bool = True
    asks_about: tuple[str, ...] = ()
    resolved_by: tuple[str, ...] = ()
    anchor_region_id: Optional[str] = None
