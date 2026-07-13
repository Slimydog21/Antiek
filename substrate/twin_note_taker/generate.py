"""Recursive twin note-taker — pure generation core (ask #4 keystone).

The operator's keystone substrate: *"every information asset created on my
platform has a twin document with all the insights and questions proposed by
that information document written by an LLM as LLMs are perfect note takers,
then that substrate of information can be merged, referenced, and leveraged in
combining contexts or doing intelligent search."*

This module is the **generation core**: it reads an information asset's content
and, through an **injectable caller**, produces a twin ``ResearchArtifactBody`` —
LLM-proposed insights (claims worth keeping) + open questions (gaps worth
chasing) — linked to the source asset. That twin is a first-class information
asset: it joins the graph, feeds the collective synthesizer (#1835), and is
itself searchable ("infinite information platform").

**Pure except ONE injected seam: the ``TwinProposer``.** The module does no
networking, no credentials, no dispatch. The authorized layer (owns the budget
gate + operator consent) injects the real caller; tests inject a deterministic
fake. This mirrors #1835's ``SynthesisCaller`` and the bench runner's
``ModelCaller``: the boundary is the only place a real model is reached.

**Authority-gated on ``operator_ack``.** Without ack the twin is **withheld**
and the caller is NEVER invoked — this module is the single twin-generation
authority (matches #884 intent / #1000 Midnight Oil). Withholding is honest
(``synthesis_withheld=True``), never silent.

**The twin is advisory, not assertive.** Insights/questions are *proposed* by
the model (``authority="twin_note_taker_advisory"``); they are not asserted as
grounded truth. Downstream grounding/promotion (``substrate/graph/
insight_question.py``) is where proposed insights earn graph-node status via
evidence. This separation is the honesty keystone: a twin can seed a question
to chase, but it cannot fabricate a provenance the source asset doesn't have.

**Output** is a ``ResearchArtifactBody`` (the canonical on-main data model) so
the twin renders HTML-native via ``render_html`` (ask #6) and merges into the
collective synthesizer with zero adapter friction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)

# The advisory authority tag — twin insights/questions are PROPOSED, not grounded.
TWIN_AUTHORITY = "twin_note_taker_advisory"

# Sensible floor on content length: a twin of nothing is nothing. Below this the
# asset has no substance to propose from — fail-closed rather than invent.
MIN_CONTENT_CHARS = 24
# A ceiling so the caller doesn't receive a runaway transcript (the caller may
# budget its own context window; this is the generation-core's backstop).
MAX_CONTENT_CHARS = 200_000


class TwinGenerationError(ValueError):
    """Fail-closed: input that cannot produce an honest twin."""


@dataclass(frozen=True)
class AssetContent:
    """The source asset a twin is proposed from.

    ``content_text`` is the plain-text or HTML body the LLM reads. The caller
    decides how to weight HTML vs text; the core only requires non-empty
    substance to propose from. ``content_class`` (e.g. ``"book"``,
    ``"research"``, ``"paper"``) lets the caller tailor its proposal.
    """

    asset_id: str
    title: str
    content_text: str
    content_class: str = "asset"


@dataclass(frozen=True)
class ProposedInsight:
    """One LLM-proposed insight (a claim worth keeping). Advisory — not grounded."""

    text: str
    # Empty means "the input asset". A non-empty value is accepted only when it
    # exactly matches that asset; the untrusted proposer cannot mint provenance.
    source_asset_id: str


@dataclass(frozen=True)
class ProposedQuestion:
    """One LLM-proposed open question (a gap worth chasing). Advisory."""

    text: str


@dataclass(frozen=True)
class TwinProposal:
    """What the injected caller returns: proposed insights + questions.

    The caller is the LLM boundary; it returns STRUCTURED proposals (not prose),
    so the core stays model-agnostic and the data model is enforced here.
    """

    insights: tuple[ProposedInsight, ...]
    questions: tuple[ProposedQuestion, ...]
    synthesis_excerpt: str  # a one-paragraph "what this asset is about" summary
    model_id: str


class TwinProposer(Protocol):
    """The single dispatch seam. Implementations reach a real model; tests fake it."""

    def __call__(self, asset: AssetContent, *, model_id: str) -> TwinProposal: ...


@dataclass(frozen=True)
class TwinDocument:
    """The generated twin: a ResearchArtifactBody twin + honest accounting."""

    asset_id: str
    twin_investigation_id: str
    body: ResearchArtifactBody  # the canonical data model (renders HTML-native)
    authority: str
    withheld: bool
    model_id: str
    operator_ack: bool
    proposal_hash: str  # sha256 over canonical proposals (idempotency)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:12]


def _canonical_proposal_hash(asset: AssetContent, proposal: TwinProposal) -> str:
    payload = {
        "asset_id": asset.asset_id,
        "insights": [i.text for i in proposal.insights],
        "questions": [q.text for q in proposal.questions],
        "synthesis_excerpt": proposal.synthesis_excerpt,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _build_body(
    asset: AssetContent,
    proposal: TwinProposal,
    *,
    withheld: bool,
) -> ResearchArtifactBody:
    """Assemble the twin ResearchArtifactBody from structured proposals.

    Insight/question node ids are content-addressed (dedup by text). Every
    proposed insight is re-attributed to the SOURCE asset via
    ``source_document_id`` — so the twin never loses where each proposal came
    from, even after it joins the graph. ``synthesis_withheld`` carries the
    honest withhold flag (render_html shows the §9.0 guard).
    """
    seen_insights: set[str] = set()
    insights: list[ArtifactInsight] = []
    for ins in proposal.insights:
        clean = ins.text.strip()
        if not clean:
            continue
        claimed_source = ins.source_asset_id.strip()
        if claimed_source and claimed_source != asset.asset_id:
            raise TwinGenerationError("proposed insight source_asset_id must match the input asset")
        node_id = f"twin-insight-{_content_hash(clean)}"
        if node_id in seen_insights:
            continue
        seen_insights.add(node_id)
        # source_document_id is ALWAYS the input asset. The proposer can extract
        # a claim from supplied content, but it cannot create a new provenance
        # edge merely by returning another identifier.
        insights.append(
            ArtifactInsight(
                node_id=node_id,
                text=clean,
                source_document_id=asset.asset_id,
            )
        )

    seen_q: set[str] = set()
    questions: list[ArtifactQuestion] = []
    for q in proposal.questions:
        clean = q.text.strip()
        if not clean:
            continue
        node_id = f"twin-question-{_content_hash(clean)}"
        if node_id in seen_q:
            continue
        seen_q.add(node_id)
        questions.append(ArtifactQuestion(node_id=node_id, text=clean))

    excerpt = None if withheld else (proposal.synthesis_excerpt.strip() or None)

    return ResearchArtifactBody(
        investigation_id=f"twin-{asset.asset_id}",
        problem_question=asset.title or f"Twin notes for {asset.asset_id}",
        insights=insights,
        open_questions=questions,
        synthesis_excerpt=excerpt,
        synthesis_withheld=withheld,
        source_event_ids=[asset.asset_id],  # the twin traces to its source asset
        agent_notes=[],
    )


def generate_twin(
    asset: AssetContent,
    *,
    caller: TwinProposer,
    model_id: str,
    operator_ack: bool = False,
) -> TwinDocument:
    """Generate the twin note document for an information asset.

    Authority-gated: without ``operator_ack`` the twin is withheld and the
    caller is NEVER invoked (zero dispatch). With ack, the injected caller
    proposes insights + questions; an empty proposal is withheld honestly
    (never invented). The twin is advisory — it proposes, it does not assert.
    """
    if not asset.asset_id.strip():
        raise TwinGenerationError("asset_id must be non-empty")
    if not model_id.strip():
        raise TwinGenerationError("model_id must be non-empty")

    stripped = asset.content_text.strip()
    if len(stripped) < MIN_CONTENT_CHARS:
        raise TwinGenerationError(
            f"asset content too short to propose from ({len(stripped)} < "
            f"{MIN_CONTENT_CHARS} chars) — no honest twin from nothing"
        )
    if len(stripped) > MAX_CONTENT_CHARS:
        raise TwinGenerationError(
            f"asset content exceeds backstop ceiling ({len(stripped)} > "
            f"{MAX_CONTENT_CHARS} chars) — caller must pre-budget the context window"
        )

    withheld = True
    proposal: TwinProposal | None = None
    used_model = model_id

    if operator_ack:
        proposal = caller(asset, model_id=model_id)
        used_model = proposal.model_id or model_id
        has_content = bool(proposal.insights or proposal.questions) or bool(
            proposal.synthesis_excerpt.strip()
        )
        if has_content:
            withheld = False

    if proposal is None:
        # Withheld path: an empty proposal so _build_body produces an honest
        # "no synthesis" body without inventing anything.
        proposal = TwinProposal(
            insights=(), questions=(), synthesis_excerpt="", model_id=used_model
        )

    body = _build_body(asset, proposal, withheld=withheld)
    proposal_hash = _canonical_proposal_hash(asset, proposal)

    return TwinDocument(
        asset_id=asset.asset_id,
        twin_investigation_id=body.investigation_id,
        body=body,
        authority=TWIN_AUTHORITY,
        withheld=withheld,
        model_id=used_model,
        operator_ack=operator_ack,
        proposal_hash=proposal_hash,
    )


__all__ = [
    "AssetContent",
    "MAX_CONTENT_CHARS",
    "MIN_CONTENT_CHARS",
    "ProposedInsight",
    "ProposedQuestion",
    "TWIN_AUTHORITY",
    "TwinDocument",
    "TwinGenerationError",
    "TwinProposer",
    "TwinProposal",
    "generate_twin",
]
