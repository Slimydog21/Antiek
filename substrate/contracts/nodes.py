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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# §9.0 servability vocabulary — imported (not restated) from the single owner,
# ``substrate/contracts/servable.py`` (Read SPR-01). The knowledge-unit's
# servability tag is typed against ``ContentClass`` so a deposited unit can
# carry the §9.0 classifier's answer WITHOUT this module re-deriving the
# deny-by-default rule. ``FULL_TEXT_SERVABLE`` is the allowlist; everything
# outside it (incl. NULL/unknown) is non-servable. See AFF SPR-04.
from .servable import FULL_TEXT_SERVABLE, ContentClass

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
    anchor_region_id: str | None = None


# ---------------------------------------------------------------------------
# AFF SPR-04 — the reusable knowledge-unit deposit contract.
#
# This is the flywheel's DEPOSIT half: the shape every investigation deposits
# and every downstream sprint trusts. It is an EXTENSION of the existing
# insight/question node contracts above — NOT a new atom and NOT a new module.
# DRW SPR-01 owns insight/question (``substrate/graph/insight_question.py``);
# forking a parallel node type would create a second atom and break the
# "one entity everywhere" moat. So this composes the existing reused fields
# (node_id / text / investigation_id / confidence — all shipped today) and
# ADDS exactly four things: (1) a surfaced stable retrieval key, (2) an
# explicit claim→chunk→doc provenance link, (3) a §9.0 servability tag typed
# against ``servable.py``, (4) a nullable groundedness-score slot (SPR-08).
#
# Field-by-field reused-vs-added provenance lives in
# ``docs/decisions/spr-04-knowledge-unit-contract.md``.
# ---------------------------------------------------------------------------


class ProvenanceLink(BaseModel):
    """The claim→chunk→doc grounding link a knowledge unit rests on.

    Surfaces, as a contract-level object, the same source attribution the
    ``supported_by`` edge already carries on the row (``insight_question.py``
    ``_add_provenance_edges`` L133, written to ``GraphEdgeInsertedPayload``'s
    ``source_document_id`` / ``chunk_id`` at ``events.py`` L1244-1245). Both
    fields are REQUIRED on the link: a unit with no chunk has nothing for
    SPR-06 retrieval to point at and nothing for §9.0 to gate per-chunk, so a
    missing ``chunk_id`` (or ``source_document_id``) is a conformance failure —
    which the AFF SPR-04 non-vacuity test relies on (drop a field → reds)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # claim end of the triple == the unit's own content-addressed node_id; the
    # chunk and document are the grounding source the edge attributes it to.
    source_document_id: str = Field(description="The grounding document (doc end of the triple).")
    chunk_id: str = Field(description="The grounding chunk (chunk end of the triple).")


class ServabilityTag(BaseModel):
    """The §9.0 servability ANSWER attached to a knowledge unit at deposit.

    This RECORDS the classifier's verdict (``substrate/contracts/servable.py``
    / ``substrate.books.servability``); it does NOT re-derive deny-by-default.
    ``content_class`` is typed against ``servable.py``'s ``ContentClass``
    Literal — NOT a free-form string — but it is ``Optional`` because a unit
    grounded on an unknown/unclassified source has NO class; a ``None`` (or any
    class outside the full-text allowlist) is non-servable, which the validator
    enforces. ``serves_full_text`` mirrors ``ServableEntryContract``'s derived
    property so a consumer reads the answer, never recomputes it. It routes no
    money — it is the §9.0 answer only (no coupling to payout/stripe)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content_class: ContentClass | None = Field(
        default=None,
        description="§9.0 content class from servable.py; None/unknown ⇒ non-servable.",
    )
    serves_full_text: bool = Field(
        default=False,
        description="The deny-by-default §9.0 answer; mirrors ServableEntryContract.serves_full_text.",
    )

    @model_validator(mode="after")
    def _deny_by_default(self) -> ServabilityTag:
        # Deny-by-default guard: a class outside the full-text allowlist (incl.
        # None/unknown) can NEVER be servable. We never assert servability — we
        # only refuse to let a non-allowlisted class claim it. The positive
        # direction (allowlisted class may still be non-servable, e.g. a
        # taken-down or speak_derived-pending entry) is left to the classifier.
        if self.serves_full_text and (
            self.content_class is None or self.content_class not in FULL_TEXT_SERVABLE
        ):
            raise ValueError(
                "servability deny-by-default: serves_full_text=True is invalid "
                f"for content_class={self.content_class!r} (not in the §9.0 "
                "full-text allowlist). NULL/unknown ⇒ non-servable."
            )
        return self


class KnowledgeUnitContract(BaseModel):
    """A reusable, provenance-carrying knowledge atom — the flywheel's deposit
    unit. An EXTENSION of ``InsightNodeContract`` / ``QuestionNodeContract``
    (same content-addressed identity, same ``investigation_id`` scope, same
    confidence vocabulary), surfacing the fields downstream sprints depend on:

    * ``retrieval_key`` — the stable, content-addressed key SPR-06 retrieval
      points at. Equal to ``node_id`` by construction (validated); surfaced
      under a named field so retrieval has a contract-level handle that does
      not depend on the node-row column name.
    * ``provenance`` — the claim→chunk→doc link (``node_id → chunk_id →
      source_document_id``) so SPR-07 dedup and the §9.0 gate have a per-chunk
      anchor; a prose blob cannot carry this, which is why structured units
      win (see decision doc, rigor #2).
    * ``servability`` — the §9.0 answer recorded at deposit (deny-by-default).
    * ``groundedness_score`` — a NULLABLE slot, ``None`` until SPR-08 populates
      it. Present in the contract now so SPR-08 lands a value without
      re-cutting this contract; conformance tolerates ``None`` (it is a slot,
      not a required signal). This is distinct from the per-synthesis
      ``GroundednessScoredPayload.groundedness_score`` event (events.py L1465),
      which scores a whole synthesis, not a single deposited unit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # — reused from the existing node contracts (see decision doc) —
    node_id: str = Field(description="Content-addressed; stable across re-emission (reused).")
    node_type: Literal["insight", "question"]
    text: str = Field(description="The node's canonical_label (reused).")
    # REQUIRED and NON-EMPTY. SPR-07 dedup is keyed on investigation scope, so a
    # unit deposited under a real investigation MUST carry that id — an empty
    # string would silently mis-bucket the unit into a global "no-investigation"
    # pool. ``min_length=1`` makes a missing/empty id fail LOUD (conformance red)
    # at the contract boundary instead of conforming silently. See AFF SPR-04
    # BLOCKER 2: the projection now sources investigation_id from the node
    # metadata mirror (stamped by promote_insight/promote_question), so a real
    # deposit always yields a real id and this guard only bites a genuine gap.
    investigation_id: str = Field(
        min_length=1,
        description="The deposit's investigation scope; REQUIRED non-empty (SPR-07 keys dedup on it).",
    )
    graph_scope: Literal["depth"] = "depth"
    confidence: ConfidenceLevel = "unknown"

    # — added (1): the stable retrieval key, surfaced. == node_id. —
    retrieval_key: str = Field(
        description="Stable retrieval key for SPR-06; equals node_id by construction."
    )

    # — added (2): the claim→chunk→doc provenance link. —
    provenance: ProvenanceLink

    # — added (3): the §9.0 servability tag (records servable.py's answer). —
    servability: ServabilityTag

    # — added (4): nullable groundedness slot, None until SPR-08. —
    groundedness_score: float | None = Field(
        default=None,
        description="Nullable; stays None until SPR-08 populates it. Not yet required.",
    )

    @model_validator(mode="after")
    def _retrieval_key_is_node_id(self) -> KnowledgeUnitContract:
        if self.retrieval_key != self.node_id:
            raise ValueError(
                "retrieval_key must equal node_id (the content-addressed key); "
                f"got retrieval_key={self.retrieval_key!r} node_id={self.node_id!r}"
            )
        return self
