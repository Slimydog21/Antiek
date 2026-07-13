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

``TwinProposer`` is the only injected model boundary. Operator authority is an
Ed25519-signed receipt minted by the authenticated budget boundary and verified
inside this module against server configuration; callers cannot inject their
own verifier. Without a valid receipt the twin is **withheld** and the proposer
is never invoked. Withholding is honest (``synthesis_withheld=True``), never
silent.

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

import base64
import binascii
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Protocol

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from substrate.graph.insight_question import canonical_text
from substrate.research_artifact.schema import ResearchArtifactBody

# The advisory authority tag — twin insights/questions are PROPOSED, not grounded.
TWIN_AUTHORITY = "twin_note_taker_advisory"
AUTHORITY_VERIFY_KEY_ENV = "ANTIEK_TWIN_AUTHORITY_VERIFY_KEY"
_EVENT_ID_RE = re.compile(r"^evt-[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")

# Sensible floor on content length: a twin of nothing is nothing. Below this the
# asset has no substance to propose from — fail-closed rather than invent.
MIN_CONTENT_CHARS = 24
# A ceiling so the caller doesn't receive a runaway transcript (the caller may
# budget its own context window; this is the generation-core's backstop).
MAX_CONTENT_CHARS = 200_000
MAX_INSIGHTS = 100
MAX_QUESTIONS = 100
MAX_PROPOSAL_ITEM_CHARS = 10_000
MAX_SYNTHESIS_CHARS = 50_000
MAX_TOTAL_PROPOSAL_CHARS = 200_000


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
    source_event_ids: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class TwinAuthorization:
    """Operator-bound authority minted and verified outside the pure core.

    ``budget_authority_id`` identifies the approved paid hold or an explicit
    free/local execution grant. It is evidence, not a caller-supplied boolean.
    """

    authorization_id: str
    account_id: str
    asset_id: str
    model_id: str
    budget_authority_id: str
    source_content_hash: str
    source_event_ids: tuple[str, ...]
    expires_at_unix: int
    signature: str


class TwinProposer(Protocol):
    """The single dispatch seam. Implementations reach a real model; tests fake it."""

    def __call__(
        self,
        asset: AssetContent,
        *,
        authorization: TwinAuthorization,
    ) -> TwinProposal: ...


@dataclass(frozen=True)
class TwinDocument:
    """The generated twin: a ResearchArtifactBody twin + honest accounting."""

    asset_id: str
    twin_investigation_id: str
    body: ResearchArtifactBody  # the canonical data model (renders HTML-native)
    proposed_insights: tuple[str, ...]
    proposed_questions: tuple[str, ...]
    authority: str
    withheld: bool
    model_id: str
    authorization_id: str | None
    budget_authority_id: str | None
    source_content_hash: str
    proposal_hash: str  # sha256 over canonical proposals (idempotency)


@dataclass(frozen=True)
class _NormalizedProposal:
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    synthesis_excerpt: str


def _source_content_hash(asset: AssetContent) -> str:
    return hashlib.sha256(asset.content_text.encode("utf-8")).hexdigest()


def _authorization_payload(authorization: TwinAuthorization) -> bytes:
    claims = {
        "account_id": authorization.account_id,
        "asset_id": authorization.asset_id,
        "authorization_id": authorization.authorization_id,
        "budget_authority_id": authorization.budget_authority_id,
        "expires_at_unix": authorization.expires_at_unix,
        "model_id": authorization.model_id,
        "source_content_hash": authorization.source_content_hash,
        "source_event_ids": list(authorization.source_event_ids),
    }
    return json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_authorization(authorization: TwinAuthorization) -> None:
    """Verify signed authority against server configuration, never caller code."""
    encoded_key = os.environ.get(AUTHORITY_VERIFY_KEY_ENV, "").strip()
    if not encoded_key:
        raise TwinGenerationError("twin authorization verification key is not configured")
    if authorization.expires_at_unix <= int(time.time()):
        raise TwinGenerationError("twin authorization has expired")
    try:
        verify_key = VerifyKey(base64.b64decode(encoded_key, validate=True))
        signature = base64.b64decode(authorization.signature, validate=True)
        verify_key.verify(_authorization_payload(authorization), signature)
    except (BadSignatureError, ValueError, binascii.Error) as exc:
        raise TwinGenerationError("twin authorization signature is invalid") from exc


def _canonical_proposal_hash(
    asset: AssetContent,
    proposal: _NormalizedProposal,
    *,
    model_id: str,
) -> str:
    payload = {
        "asset_id": asset.asset_id,
        "content_class": asset.content_class,
        "source_content_hash": _source_content_hash(asset),
        "title": asset.title,
        "model_id": model_id,
        "insights": list(proposal.insights),
        "questions": list(proposal.questions),
        "synthesis_excerpt": proposal.synthesis_excerpt,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _normalize_proposal(asset: AssetContent, proposal: TwinProposal) -> _NormalizedProposal:
    """Validate and canonicalize untrusted model output before materialization."""
    if not isinstance(proposal, TwinProposal):
        raise TwinGenerationError("proposer must return TwinProposal")
    if not isinstance(proposal.synthesis_excerpt, str):
        raise TwinGenerationError("synthesis excerpt must be text")
    if not isinstance(proposal.insights, tuple) or not isinstance(proposal.questions, tuple):
        raise TwinGenerationError("proposal collections must be tuples")
    if len(proposal.insights) > MAX_INSIGHTS:
        raise TwinGenerationError(f"proposal exceeds {MAX_INSIGHTS} insights")
    if len(proposal.questions) > MAX_QUESTIONS:
        raise TwinGenerationError(f"proposal exceeds {MAX_QUESTIONS} questions")

    total_chars = 0
    seen_insights: set[str] = set()
    insights: list[str] = []
    for insight in proposal.insights:
        if not isinstance(insight, ProposedInsight):
            raise TwinGenerationError("proposal insights must be ProposedInsight values")
        if not isinstance(insight.text, str) or not isinstance(insight.source_asset_id, str):
            raise TwinGenerationError("proposed insight fields must be text")
        clean = insight.text.strip()
        if not clean:
            continue
        if len(clean) > MAX_PROPOSAL_ITEM_CHARS:
            raise TwinGenerationError("proposed insight exceeds the per-item ceiling")
        claimed_source = insight.source_asset_id.strip()
        if claimed_source and claimed_source != asset.asset_id:
            raise TwinGenerationError("proposed insight source_asset_id must match the input asset")
        identity = canonical_text(clean)
        if identity in seen_insights:
            continue
        seen_insights.add(identity)
        insights.append(clean)
        total_chars += len(clean)

    seen_questions: set[str] = set()
    questions: list[str] = []
    for question in proposal.questions:
        if not isinstance(question, ProposedQuestion):
            raise TwinGenerationError("proposal questions must be ProposedQuestion values")
        if not isinstance(question.text, str):
            raise TwinGenerationError("proposed question text must be text")
        clean = question.text.strip()
        if not clean:
            continue
        if len(clean) > MAX_PROPOSAL_ITEM_CHARS:
            raise TwinGenerationError("proposed question exceeds the per-item ceiling")
        identity = canonical_text(clean)
        if identity in seen_questions:
            continue
        seen_questions.add(identity)
        questions.append(clean)
        total_chars += len(clean)

    synthesis = proposal.synthesis_excerpt.strip()
    if len(synthesis) > MAX_SYNTHESIS_CHARS:
        raise TwinGenerationError("synthesis excerpt exceeds its ceiling")
    total_chars += len(synthesis)
    if total_chars > MAX_TOTAL_PROPOSAL_CHARS:
        raise TwinGenerationError("proposal exceeds the aggregate output ceiling")

    return _NormalizedProposal(
        insights=tuple(insights),
        questions=tuple(questions),
        synthesis_excerpt=synthesis,
    )


def _build_body(
    asset: AssetContent,
    proposal: _NormalizedProposal,
    *,
    withheld: bool,
) -> ResearchArtifactBody:
    """Assemble the twin ResearchArtifactBody from structured proposals.

    All model proposals stay in ``agent_notes``, the canonical non-graph field.
    Neither proposed claims nor proposed questions can masquerade as graph
    findings/gaps before evidence-backed promotion.
    """
    agent_notes: list[str] = []
    if not withheld:
        agent_notes.append(
            f"Authority: {TWIN_AUTHORITY}. Proposals are ungrounded until evidence-backed promotion."
        )
        agent_notes.append(f"Source asset: {asset.asset_id}")
        agent_notes.extend(f"Proposed insight: {insight}" for insight in proposal.insights)
        agent_notes.extend(f"Proposed question: {question}" for question in proposal.questions)

    excerpt = (
        None
        if withheld or not proposal.synthesis_excerpt
        else f"Advisory model summary: {proposal.synthesis_excerpt}"
    )

    return ResearchArtifactBody(
        investigation_id=f"twin-{asset.asset_id}",
        problem_question=f"Advisory twin notes: {asset.title or asset.asset_id}",
        insights=[],
        open_questions=[],
        synthesis_excerpt=excerpt,
        synthesis_withheld=withheld,
        source_event_ids=list(asset.source_event_ids),
        agent_notes=agent_notes,
    )


def generate_twin(
    asset: AssetContent,
    *,
    caller: TwinProposer,
    model_id: str,
    authorization: TwinAuthorization | None = None,
) -> TwinDocument:
    """Generate the twin note document for an information asset.

    Authority-gated: without a verified authorization the twin is withheld and
    the caller is NEVER invoked. A receipt is bound to account, asset, model,
    and budget authority; a caller-controlled boolean cannot trigger dispatch.
    """
    if not asset.asset_id.strip():
        raise TwinGenerationError("asset_id must be non-empty")
    if not model_id.strip():
        raise TwinGenerationError("model_id must be non-empty")
    if not asset.source_event_ids or any(
        not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id)
        for event_id in asset.source_event_ids
    ):
        raise TwinGenerationError("source_event_ids must contain real event identifiers")

    stripped = asset.content_text.strip()
    if len(stripped) < MIN_CONTENT_CHARS:
        raise TwinGenerationError(
            f"asset content too short to propose from ({len(stripped)} < "
            f"{MIN_CONTENT_CHARS} chars) — no honest twin from nothing"
        )
    if len(asset.content_text) > MAX_CONTENT_CHARS:
        raise TwinGenerationError(
            f"asset content exceeds backstop ceiling ({len(asset.content_text)} > "
            f"{MAX_CONTENT_CHARS} chars) — caller must pre-budget the context window"
        )

    normalized = _NormalizedProposal(insights=(), questions=(), synthesis_excerpt="")
    authorization_id: str | None = None
    budget_authority_id: str | None = None

    if authorization is not None:
        if not isinstance(authorization, TwinAuthorization):
            raise TwinGenerationError("authorization must be a TwinAuthorization receipt")
        if not isinstance(authorization.expires_at_unix, int) or isinstance(
            authorization.expires_at_unix, bool
        ):
            raise TwinGenerationError("authorization expiry must be an integer timestamp")
        if not isinstance(authorization.source_event_ids, tuple) or any(
            not isinstance(event_id, str) for event_id in authorization.source_event_ids
        ):
            raise TwinGenerationError("authorization source events must be a tuple of text")
        string_claims = (
            authorization.authorization_id,
            authorization.account_id,
            authorization.asset_id,
            authorization.model_id,
            authorization.budget_authority_id,
            authorization.source_content_hash,
            authorization.signature,
        )
        if not all(isinstance(value, str) for value in string_claims):
            raise TwinGenerationError("authorization string claims must be text")
        if not all(value.strip() for value in string_claims):
            raise TwinGenerationError("authorization fields must be non-empty")
        if authorization.asset_id != asset.asset_id:
            raise TwinGenerationError("authorization is bound to a different asset")
        if authorization.model_id != model_id:
            raise TwinGenerationError("authorization is bound to a different model")
        if authorization.source_content_hash != _source_content_hash(asset):
            raise TwinGenerationError("authorization is bound to a different source revision")
        if authorization.source_event_ids != asset.source_event_ids:
            raise TwinGenerationError("authorization is bound to different source events")
        _verify_authorization(authorization)
        authorization_id = authorization.authorization_id
        budget_authority_id = authorization.budget_authority_id
        normalized = _normalize_proposal(
            asset,
            caller(asset, authorization=authorization),
        )

    withheld = not bool(normalized.insights or normalized.questions or normalized.synthesis_excerpt)
    body = _build_body(asset, normalized, withheld=withheld)
    source_content_hash = _source_content_hash(asset)
    proposal_hash = _canonical_proposal_hash(asset, normalized, model_id=model_id)

    return TwinDocument(
        asset_id=asset.asset_id,
        twin_investigation_id=body.investigation_id,
        body=body,
        proposed_insights=normalized.insights,
        proposed_questions=normalized.questions,
        authority=TWIN_AUTHORITY,
        withheld=withheld,
        model_id=model_id,
        authorization_id=authorization_id,
        budget_authority_id=budget_authority_id,
        source_content_hash=source_content_hash,
        proposal_hash=proposal_hash,
    )


__all__ = [
    "AUTHORITY_VERIFY_KEY_ENV",
    "AssetContent",
    "MAX_INSIGHTS",
    "MAX_PROPOSAL_ITEM_CHARS",
    "MAX_QUESTIONS",
    "MAX_SYNTHESIS_CHARS",
    "MAX_TOTAL_PROPOSAL_CHARS",
    "MAX_CONTENT_CHARS",
    "MIN_CONTENT_CHARS",
    "ProposedInsight",
    "ProposedQuestion",
    "TWIN_AUTHORITY",
    "TwinAuthorization",
    "TwinDocument",
    "TwinGenerationError",
    "TwinProposer",
    "TwinProposal",
    "generate_twin",
]
