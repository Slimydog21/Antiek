"""Recursive twin note-taker — pure generation core (ask #4 keystone).

The operator's keystone substrate: *"every information asset created on my
platform has a twin document with all the insights and questions proposed by
that information document written by an LLM as LLMs are perfect note takers,
then that substrate of information can be merged, referenced, and leveraged in
combining contexts or doing intelligent search."*

This module is the **generation core**: it reads an information asset's content
and a completed structured proposal, then produces a twin ``ResearchArtifactBody`` —
LLM-proposed insights (claims worth keeping) + open questions (gaps worth
chasing) — linked to the source asset. That twin is a first-class information
asset: it joins the graph, feeds the collective synthesizer (#1835), and is
itself searchable ("infinite information platform").

This core performs **no model dispatch**. It materializes only proposals carrying
an Ed25519-signed completion receipt minted after the authenticated budget
boundary has consumed execution authority. Replaying a receipt repeats a pure,
deterministic materialization, never a paid call. Without a valid receipt the
twin is **withheld**. Withholding is honest (``synthesis_withheld=True``), never
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
# A ceiling for the exact source payload authorized by the dispatch boundary.
MAX_CONTENT_CHARS = 200_000
MAX_INSIGHTS = 100
MAX_QUESTIONS = 100
MAX_PROPOSAL_ITEM_CHARS = 10_000
MAX_SYNTHESIS_CHARS = 50_000
MAX_TOTAL_PROPOSAL_CHARS = 200_000
MAX_IDENTIFIER_CHARS = 256
MAX_TITLE_CHARS = 1_000
MAX_CONTENT_CLASS_CHARS = 64
MAX_SOURCE_EVENTS = 100
MAX_SIGNATURE_CHARS = 128
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TwinGenerationError(ValueError):
    """Fail-closed: input that cannot produce an honest twin."""


@dataclass(frozen=True)
class AssetContent:
    """The source asset a twin is proposed from.

    ``content_text`` is the exact plain-text or HTML body authorized for model
    use. ``content_class`` (e.g. ``"book"``, ``"research"``, ``"paper"``)
    records what kind of asset produced the proposal.
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
    """Completed structured model output: proposed insights + questions.

    The dispatch boundary parses model output into this shape before signing a
    completion receipt; the materializer remains model-agnostic.
    """

    insights: tuple[ProposedInsight, ...]
    questions: tuple[ProposedQuestion, ...]
    synthesis_excerpt: str  # a one-paragraph "what this asset is about" summary


@dataclass(frozen=True)
class TwinGenerationReceipt:
    """Signed evidence that authorized proposal generation already completed.

    ``budget_authority_id`` identifies the approved paid hold or an explicit
    free/local grant consumed by the dispatch boundary. This core never spends.
    """

    receipt_id: str
    account_id: str
    asset_id: str
    model_id: str
    budget_authority_id: str
    source_content_hash: str
    source_asset_hash: str
    source_event_ids: tuple[str, ...]
    proposal_payload_hash: str
    expires_at_unix: int
    signature: str


@dataclass(frozen=True)
class TwinDocument:
    """The generated twin: a ResearchArtifactBody twin + honest accounting."""

    asset_id: str
    twin_investigation_id: str
    _body_json: str
    proposed_insights: tuple[str, ...]
    proposed_questions: tuple[str, ...]
    authority: str
    withheld: bool
    account_id: str | None
    model_id: str
    receipt_id: str | None
    budget_authority_id: str | None
    source_content_hash: str
    proposal_hash: str  # sha256 over canonical proposals (idempotency)

    @property
    def body(self) -> ResearchArtifactBody:
        """Return a detached body so callers cannot mutate signed document state."""
        return ResearchArtifactBody.model_validate_json(self._body_json)


@dataclass(frozen=True)
class _NormalizedProposal:
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    synthesis_excerpt: str


def _snapshot_asset(asset: AssetContent) -> AssetContent:
    if type(asset) is not AssetContent:
        raise TwinGenerationError("asset must be an AssetContent value")
    text_fields = (asset.asset_id, asset.title, asset.content_text, asset.content_class)
    if not all(type(value) is str for value in text_fields):
        raise TwinGenerationError("asset text fields must be exact strings")
    if type(asset.source_event_ids) is not tuple:
        raise TwinGenerationError("asset source events must be a tuple of exact strings")
    if len(asset.source_event_ids) > MAX_SOURCE_EVENTS:
        raise TwinGenerationError("source_event_ids exceeds its count ceiling")
    if any(type(event_id) is not str for event_id in asset.source_event_ids):
        raise TwinGenerationError("asset source events must be a tuple of exact strings")
    return AssetContent(
        asset_id=asset.asset_id,
        title=asset.title,
        content_text=asset.content_text,
        content_class=asset.content_class,
        source_event_ids=tuple(asset.source_event_ids),
    )


def _validate_source(asset: AssetContent) -> None:
    if not asset.asset_id.strip():
        raise TwinGenerationError("asset_id must be non-empty")
    if asset.asset_id != asset.asset_id.strip() or len(asset.asset_id) > MAX_IDENTIFIER_CHARS:
        raise TwinGenerationError("asset_id must be canonical and within its ceiling")
    if len(asset.title) > MAX_TITLE_CHARS:
        raise TwinGenerationError("asset title exceeds its ceiling")
    if (
        not asset.content_class.strip()
        or asset.content_class != asset.content_class.strip()
        or len(asset.content_class) > MAX_CONTENT_CLASS_CHARS
    ):
        raise TwinGenerationError("content_class must be canonical and within its ceiling")
    if len(asset.source_event_ids) > MAX_SOURCE_EVENTS:
        raise TwinGenerationError("source_event_ids exceeds its count ceiling")
    if not asset.source_event_ids or any(
        not _EVENT_ID_RE.fullmatch(event_id) for event_id in asset.source_event_ids
    ):
        raise TwinGenerationError("source_event_ids must contain event-shaped identifiers")
    if len(set(asset.source_event_ids)) != len(asset.source_event_ids):
        raise TwinGenerationError("source_event_ids must be unique")
    if len(asset.content_text) > MAX_CONTENT_CHARS:
        raise TwinGenerationError(
            f"asset content exceeds backstop ceiling ({len(asset.content_text)} > "
            f"{MAX_CONTENT_CHARS} chars)"
        )
    stripped = asset.content_text.strip()
    if len(stripped) < MIN_CONTENT_CHARS:
        raise TwinGenerationError(
            f"asset content too short to propose from ({len(stripped)} < "
            f"{MIN_CONTENT_CHARS} chars) — no honest twin from nothing"
        )


def _snapshot_proposal(proposal: TwinProposal) -> TwinProposal:
    if type(proposal) is not TwinProposal:
        raise TwinGenerationError("proposal must be a TwinProposal value")
    if type(proposal.insights) is not tuple or type(proposal.questions) is not tuple:
        raise TwinGenerationError("proposal collections must be tuples")
    if len(proposal.insights) > MAX_INSIGHTS:
        raise TwinGenerationError(f"proposal exceeds {MAX_INSIGHTS} insights")
    if len(proposal.questions) > MAX_QUESTIONS:
        raise TwinGenerationError(f"proposal exceeds {MAX_QUESTIONS} questions")
    if type(proposal.synthesis_excerpt) is not str:
        raise TwinGenerationError("synthesis excerpt must be an exact string")
    insights: list[ProposedInsight] = []
    for insight in proposal.insights:
        if type(insight) is not ProposedInsight:
            raise TwinGenerationError("proposal insights must be ProposedInsight values")
        if type(insight.text) is not str or type(insight.source_asset_id) is not str:
            raise TwinGenerationError("proposed insight fields must be exact strings")
        insights.append(ProposedInsight(insight.text, insight.source_asset_id))
    questions: list[ProposedQuestion] = []
    for question in proposal.questions:
        if type(question) is not ProposedQuestion or type(question.text) is not str:
            raise TwinGenerationError("proposed questions must contain exact strings")
        questions.append(ProposedQuestion(question.text))
    return TwinProposal(tuple(insights), tuple(questions), proposal.synthesis_excerpt)


def _snapshot_receipt(receipt: TwinGenerationReceipt) -> TwinGenerationReceipt:
    if type(receipt) is not TwinGenerationReceipt:
        raise TwinGenerationError("receipt must be a TwinGenerationReceipt value")
    string_fields = (
        receipt.receipt_id,
        receipt.account_id,
        receipt.asset_id,
        receipt.model_id,
        receipt.budget_authority_id,
        receipt.source_content_hash,
        receipt.source_asset_hash,
        receipt.proposal_payload_hash,
        receipt.signature,
    )
    if not all(type(value) is str for value in string_fields):
        raise TwinGenerationError("receipt string claims must be exact strings")
    if type(receipt.source_event_ids) is not tuple:
        raise TwinGenerationError("receipt source events must be a tuple of exact strings")
    if len(receipt.source_event_ids) > MAX_SOURCE_EVENTS:
        raise TwinGenerationError("receipt source events exceed their count ceiling")
    if any(type(event_id) is not str for event_id in receipt.source_event_ids):
        raise TwinGenerationError("receipt source events must be a tuple of exact strings")
    if type(receipt.expires_at_unix) is not int:
        raise TwinGenerationError("receipt expiry must be an integer timestamp")
    return TwinGenerationReceipt(
        receipt_id=receipt.receipt_id,
        account_id=receipt.account_id,
        asset_id=receipt.asset_id,
        model_id=receipt.model_id,
        budget_authority_id=receipt.budget_authority_id,
        source_content_hash=receipt.source_content_hash,
        source_asset_hash=receipt.source_asset_hash,
        source_event_ids=tuple(receipt.source_event_ids),
        proposal_payload_hash=receipt.proposal_payload_hash,
        expires_at_unix=receipt.expires_at_unix,
        signature=receipt.signature,
    )


def _source_content_hash(asset: AssetContent) -> str:
    return hashlib.sha256(asset.content_text.encode("utf-8")).hexdigest()


def _source_asset_hash(asset: AssetContent) -> str:
    payload = {
        "asset_id": asset.asset_id,
        "content_class": asset.content_class,
        "source_content_hash": _source_content_hash(asset),
        "source_event_ids": list(asset.source_event_ids),
        "title": asset.title,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _receipt_payload(receipt: TwinGenerationReceipt) -> bytes:
    claims = {
        "account_id": receipt.account_id,
        "asset_id": receipt.asset_id,
        "budget_authority_id": receipt.budget_authority_id,
        "expires_at_unix": receipt.expires_at_unix,
        "model_id": receipt.model_id,
        "proposal_payload_hash": receipt.proposal_payload_hash,
        "receipt_id": receipt.receipt_id,
        "source_content_hash": receipt.source_content_hash,
        "source_asset_hash": receipt.source_asset_hash,
        "source_event_ids": list(receipt.source_event_ids),
    }
    return json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_receipt(receipt: TwinGenerationReceipt) -> None:
    """Verify completion evidence against server configuration."""
    encoded_key = os.environ.get(AUTHORITY_VERIFY_KEY_ENV, "").strip()
    if not encoded_key:
        raise TwinGenerationError("twin receipt verification key is not configured")
    if receipt.expires_at_unix <= int(time.time()):
        raise TwinGenerationError("twin generation receipt has expired")
    try:
        verify_key = VerifyKey(base64.b64decode(encoded_key, validate=True))
        signature = base64.b64decode(receipt.signature, validate=True)
        verify_key.verify(_receipt_payload(receipt), signature)
    except (BadSignatureError, ValueError, binascii.Error) as exc:
        raise TwinGenerationError("twin generation receipt signature is invalid") from exc


def _canonical_proposal_hash(
    asset: AssetContent,
    proposal: _NormalizedProposal,
    *,
    model_id: str,
) -> str:
    payload = {
        "asset_id": asset.asset_id,
        "source_asset_hash": _source_asset_hash(asset),
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


def _normalized_payload_hash(proposal: _NormalizedProposal) -> str:
    blob = json.dumps(
        {
            "insights": list(proposal.insights),
            "questions": list(proposal.questions),
            "synthesis_excerpt": proposal.synthesis_excerpt,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def proposal_receipt_hash(asset: AssetContent, proposal: TwinProposal) -> str:
    """Canonical proposal digest the trusted dispatch boundary must sign."""
    source = _snapshot_asset(asset)
    _validate_source(source)
    completed = _snapshot_proposal(proposal)
    return _normalized_payload_hash(_normalize_proposal(source, completed))


def source_asset_receipt_hash(asset: AssetContent) -> str:
    """Canonical digest of every source field that can affect materialization."""
    source = _snapshot_asset(asset)
    _validate_source(source)
    return _source_asset_hash(source)


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
        if proposal.synthesis_excerpt:
            agent_notes.append(f"Proposed synthesis: {proposal.synthesis_excerpt}")

    return ResearchArtifactBody(
        investigation_id=f"twin-{asset.asset_id}",
        problem_question=f"Advisory twin notes: {asset.title or asset.asset_id}",
        insights=[],
        open_questions=[],
        synthesis_excerpt=None,
        synthesis_withheld=True,
        # Shape checks are not proof of graph existence or account ownership.
        # A later event-store boundary may promote validated provenance.
        source_event_ids=[],
        agent_notes=agent_notes,
    )


def generate_twin(
    asset: AssetContent,
    *,
    model_id: str,
    authenticated_account_id: str,
    proposal: TwinProposal | None = None,
    receipt: TwinGenerationReceipt | None = None,
) -> TwinDocument:
    """Materialize an advisory twin without performing model dispatch.

    A proposal is accepted only with a server-signed completion receipt bound to
    the authenticated account, source revision/events, model, budget authority,
    and normalized proposal digest. Replays are deterministic and spend-free.
    """
    source = _snapshot_asset(asset)
    _validate_source(source)
    if type(model_id) is not str or not model_id.strip():
        raise TwinGenerationError("model_id must be a non-empty exact string")
    if type(authenticated_account_id) is not str or not authenticated_account_id.strip():
        raise TwinGenerationError("authenticated_account_id must be a non-empty exact string")
    bounded_identifiers = {
        "model_id": model_id,
        "authenticated_account_id": authenticated_account_id,
    }
    for field, value in bounded_identifiers.items():
        if value != value.strip() or len(value) > MAX_IDENTIFIER_CHARS:
            raise TwinGenerationError(f"{field} must be canonical and within its ceiling")
    normalized = _NormalizedProposal(insights=(), questions=(), synthesis_excerpt="")
    account_id: str | None = None
    receipt_id: str | None = None
    budget_authority_id: str | None = None

    if (proposal is None) != (receipt is None):
        raise TwinGenerationError("proposal and completion receipt must be provided together")
    if proposal is not None and receipt is not None:
        completed = _snapshot_proposal(proposal)
        evidence = _snapshot_receipt(receipt)
        normalized = _normalize_proposal(source, completed)
        string_claims = (
            evidence.receipt_id,
            evidence.account_id,
            evidence.asset_id,
            evidence.model_id,
            evidence.budget_authority_id,
            evidence.source_content_hash,
            evidence.source_asset_hash,
            evidence.proposal_payload_hash,
            evidence.signature,
        )
        if not all(value.strip() for value in string_claims):
            raise TwinGenerationError("receipt fields must be non-empty")
        bounded_receipt_ids = (
            evidence.receipt_id,
            evidence.account_id,
            evidence.asset_id,
            evidence.model_id,
            evidence.budget_authority_id,
        )
        if any(
            value != value.strip() or len(value) > MAX_IDENTIFIER_CHARS
            for value in bounded_receipt_ids
        ):
            raise TwinGenerationError("receipt identifiers exceed their canonical ceiling")
        if len(evidence.signature) > MAX_SIGNATURE_CHARS:
            raise TwinGenerationError("receipt signature exceeds its ceiling")
        if (
            not _SHA256_RE.fullmatch(evidence.source_content_hash)
            or not _SHA256_RE.fullmatch(evidence.source_asset_hash)
            or not _SHA256_RE.fullmatch(evidence.proposal_payload_hash)
        ):
            raise TwinGenerationError("receipt hashes must be canonical sha256 digests")
        if len(evidence.source_event_ids) > MAX_SOURCE_EVENTS:
            raise TwinGenerationError("receipt source events exceed their count ceiling")
        if evidence.account_id != authenticated_account_id:
            raise TwinGenerationError("receipt belongs to a different authenticated account")
        if evidence.asset_id != source.asset_id:
            raise TwinGenerationError("receipt is bound to a different asset")
        if evidence.model_id != model_id:
            raise TwinGenerationError("receipt is bound to a different model")
        if evidence.source_content_hash != _source_content_hash(source):
            raise TwinGenerationError("receipt is bound to a different source revision")
        if evidence.source_asset_hash != _source_asset_hash(source):
            raise TwinGenerationError("receipt is bound to different source metadata")
        if evidence.source_event_ids != source.source_event_ids:
            raise TwinGenerationError("receipt is bound to different source events")
        if evidence.proposal_payload_hash != _normalized_payload_hash(normalized):
            raise TwinGenerationError("receipt is bound to a different proposal")
        _verify_receipt(evidence)
        account_id = evidence.account_id
        receipt_id = evidence.receipt_id
        budget_authority_id = evidence.budget_authority_id

    withheld = not bool(normalized.insights or normalized.questions or normalized.synthesis_excerpt)
    body = _build_body(source, normalized, withheld=withheld)
    source_content_hash = _source_content_hash(source)
    proposal_hash = _canonical_proposal_hash(source, normalized, model_id=model_id)

    return TwinDocument(
        asset_id=source.asset_id,
        twin_investigation_id=body.investigation_id,
        _body_json=body.model_dump_json(),
        proposed_insights=normalized.insights,
        proposed_questions=normalized.questions,
        authority=TWIN_AUTHORITY,
        withheld=withheld,
        account_id=account_id,
        model_id=model_id,
        receipt_id=receipt_id,
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
    "MAX_CONTENT_CLASS_CHARS",
    "MAX_IDENTIFIER_CHARS",
    "MAX_SIGNATURE_CHARS",
    "MAX_SOURCE_EVENTS",
    "MAX_TITLE_CHARS",
    "MIN_CONTENT_CHARS",
    "ProposedInsight",
    "ProposedQuestion",
    "TWIN_AUTHORITY",
    "TwinDocument",
    "TwinGenerationReceipt",
    "TwinGenerationError",
    "TwinProposal",
    "generate_twin",
    "proposal_receipt_hash",
    "source_asset_receipt_hash",
]
