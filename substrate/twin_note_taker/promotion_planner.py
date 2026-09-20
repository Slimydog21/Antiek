"""Pure, bounded promotion plans derived only from sealed twin documents.

Twin notes are model proposals, not graph truth.  This module therefore emits
an advisory plan and never writes to the graph.  The only accepted source is an
exact, materialized :class:`TwinDocument`; callers cannot supply findings or
provenance separately from the signed generation boundary.

The execution contract is deliberately narrow.  A non-empty batch is restricted
to one signed account.  A consumer may pass canonical entries to
``promote_insight`` / ``promote_question`` only with the plan's account-derived
``identity_scope`` and ``owner_user_id``, plus ``dedup=False``.  Under those
arguments the writers' content-addressed identifiers equal each entry's
``node_id``.  An executor must abort if a writer ever returns a different
identifier.  Semantic dedup is a different operation because it can return an
existing survivor identifier.

Repeated canonical text remains auditable in ``duplicate_observations`` but is
not executable a second time.  This makes "promote once" structural rather than
an instruction a downstream loop can accidentally ignore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypeVar, final

from substrate.graph.insight_question import (
    canonical_text,
    insight_node_id,
    question_node_id,
)

from .generate import (
    MAX_IDENTIFIER_CHARS,
    MAX_INSIGHTS,
    MAX_PROPOSAL_ITEM_CHARS,
    MAX_QUESTIONS,
    MAX_TOTAL_PROPOSAL_CHARS,
    TWIN_AUTHORITY,
    TwinDocument,
    TwinGenerationError,
    verify_twin_document,
)

PromotionKind = Literal["insight", "question"]

MAX_PROMOTION_DOCUMENTS = 100
MAX_PROMOTION_FINDINGS = MAX_PROMOTION_DOCUMENTS * (MAX_INSIGHTS + MAX_QUESTIONS)
MAX_PROMOTION_TOTAL_CHARS = 5_000_000

_VALID_KINDS = frozenset({"insight", "question"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_T = TypeVar("_T")


class TwinPromotionError(ValueError):
    """A promotion-planning input violates a load-bearing invariant."""


def _canonical_identifier(name: str, value: object) -> str:
    if type(value) is not str:
        raise TwinPromotionError(f"{name} must be an exact string")
    if len(value) > MAX_IDENTIFIER_CHARS or not value or value != value.strip():
        raise TwinPromotionError(f"{name} must be canonical and within its ceiling")
    return value


def _sha256(name: str, value: object) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise TwinPromotionError(f"{name} must be a canonical sha256 digest")
    return value


def predicted_node_id(kind: str, text: str, *, identity_scope: str) -> str:
    """Return the exact default writer ID for a bounded, non-blank finding.

    This prediction is execution-faithful only under the plan's explicit
    ``identity_scope`` and ``semantic_dedup=False`` contract.
    """

    if type(kind) is not str or kind not in _VALID_KINDS:
        raise TwinPromotionError("kind must be exactly 'insight' or 'question'")
    if type(text) is not str:
        raise TwinPromotionError("text must be an exact string")
    if len(text) > MAX_PROPOSAL_ITEM_CHARS or not text.strip():
        raise TwinPromotionError("text must be non-blank and within its ceiling")
    scope = _canonical_identifier("identity_scope", identity_scope)
    if kind == "insight":
        return insight_node_id(text, identity_scope=scope)
    return question_node_id(text, identity_scope=scope)


@final
@dataclass(frozen=True, init=False)
class PromotionSource:
    """Signed generation claims carried with one advisory finding."""

    asset_id: str
    account_id: str
    twin_investigation_id: str
    authority: str
    model_id: str
    receipt_id: str
    budget_authority_id: str
    source_content_hash: str
    proposal_hash: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TwinPromotionError("PromotionSource values come only from sealed twins")


@final
@dataclass(frozen=True, init=False)
class PromotableFinding:
    """One canonical finding that may be executed exactly once."""

    kind: PromotionKind
    text: str
    node_id: str
    source: PromotionSource

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TwinPromotionError("PromotableFinding values come only from promotion plans")


@final
@dataclass(frozen=True, init=False)
class DuplicateObservation:
    """A repeated proposal retained for audit, never for execution."""

    kind: PromotionKind
    text: str
    node_id: str
    duplicate_of_node_id: str
    source: PromotionSource
    canonical_source_asset_id: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TwinPromotionError("DuplicateObservation values come only from promotion plans")


@final
@dataclass(frozen=True, init=False)
class TwinPromotionPlan:
    """Immutable advisory batch with an explicit graph-writer contract."""

    canonical_insights: tuple[PromotableFinding, ...]
    canonical_questions: tuple[PromotableFinding, ...]
    duplicate_observations: tuple[DuplicateObservation, ...]
    document_count: int
    identity_scope: str | None
    owner_user_id: str | None
    semantic_dedup: bool
    authority: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TwinPromotionError("construct plans with plan_twin_promotion")

    @property
    def total_promotable(self) -> int:
        return len(self.canonical_insights) + len(self.canonical_questions)

    @property
    def duplicates_observed(self) -> int:
        return len(self.duplicate_observations)

    @property
    def is_empty(self) -> bool:
        return self.total_promotable == 0


def _sealed_value(cls: type[_T], **values: object) -> _T:  # noqa: UP047
    value: _T = object.__new__(cls)
    for name, item in values.items():
        object.__setattr__(value, name, item)
    return value


def _validate_document(document: TwinDocument) -> str:
    if type(document) is not TwinDocument:
        raise TwinPromotionError("documents must be exact TwinDocument values")
    try:
        verify_twin_document(document)
    except TwinGenerationError as exc:
        raise TwinPromotionError(str(exc)) from exc
    if type(document.withheld) is not bool or document.withheld:
        raise TwinPromotionError("withheld twins cannot enter a promotion plan")
    if document.authority != TWIN_AUTHORITY:
        raise TwinPromotionError("twin authority must remain advisory")
    _canonical_identifier("asset_id", document.asset_id)
    account_id = _canonical_identifier("account_id", document.account_id)
    _canonical_identifier("twin_investigation_id", document.twin_investigation_id)
    _canonical_identifier("model_id", document.model_id)
    _canonical_identifier("receipt_id", document.receipt_id)
    _canonical_identifier("budget_authority_id", document.budget_authority_id)
    _sha256("source_content_hash", document.source_content_hash)
    _sha256("proposal_hash", document.proposal_hash)
    if type(document.proposed_insights) is not tuple:
        raise TwinPromotionError("proposed insights must be an exact tuple")
    if type(document.proposed_questions) is not tuple:
        raise TwinPromotionError("proposed questions must be an exact tuple")
    if len(document.proposed_insights) > MAX_INSIGHTS:
        raise TwinPromotionError("twin exceeds the insight count ceiling")
    if len(document.proposed_questions) > MAX_QUESTIONS:
        raise TwinPromotionError("twin exceeds the question count ceiling")
    total_chars = 0
    for text in (*document.proposed_insights, *document.proposed_questions):
        if type(text) is not str:
            raise TwinPromotionError("twin items must be exact strings")
        if len(text) > MAX_PROPOSAL_ITEM_CHARS:
            raise TwinPromotionError("twin item exceeds the per-item ceiling")
        if not text or text != text.strip():
            raise TwinPromotionError("twin items must be non-empty canonical strings")
        total_chars += len(text)
    if total_chars > MAX_TOTAL_PROPOSAL_CHARS:
        raise TwinPromotionError("twin items exceed the signed aggregate ceiling")
    return account_id


def _source(document: TwinDocument, *, account_id: str) -> PromotionSource:
    return _sealed_value(
        PromotionSource,
        asset_id=document.asset_id,
        account_id=account_id,
        twin_investigation_id=document.twin_investigation_id,
        authority=document.authority,
        model_id=document.model_id,
        receipt_id=document.receipt_id,
        budget_authority_id=document.budget_authority_id,
        source_content_hash=document.source_content_hash,
        proposal_hash=document.proposal_hash,
    )


def _finding(
    *, kind: PromotionKind, text: str, source: PromotionSource
) -> PromotableFinding:
    return _sealed_value(
        PromotableFinding,
        kind=kind,
        text=text,
        node_id=predicted_node_id(kind, text, identity_scope=source.account_id),
        source=source,
    )


def plan_twin_promotion(
    documents: list[TwinDocument] | tuple[TwinDocument, ...],
    /,
) -> TwinPromotionPlan:
    """Build a bounded promote-once plan from signed twin documents only."""

    if type(documents) not in (list, tuple):
        raise TwinPromotionError("documents must be an exact list or tuple")
    if len(documents) > MAX_PROMOTION_DOCUMENTS:
        raise TwinPromotionError("document count exceeds the promotion ceiling")
    snapshot = tuple(documents)

    canonical: dict[str, PromotableFinding] = {}
    insights: list[PromotableFinding] = []
    questions: list[PromotableFinding] = []
    duplicates: list[DuplicateObservation] = []
    finding_count = 0
    total_chars = 0
    account_id: str | None = None

    for document in snapshot:
        document_account_id = _validate_document(document)
        if account_id is None:
            account_id = document_account_id
        elif document_account_id != account_id:
            raise TwinPromotionError("promotion batches must contain exactly one account")
        source = _source(document, account_id=document_account_id)
        collections: tuple[tuple[PromotionKind, tuple[str, ...]], ...] = (
            ("insight", document.proposed_insights),
            ("question", document.proposed_questions),
        )
        for kind, texts in collections:
            for text in texts:
                finding_count += 1
                total_chars += len(text)
                if finding_count > MAX_PROMOTION_FINDINGS:
                    raise TwinPromotionError("finding count exceeds the promotion ceiling")
                if total_chars > MAX_PROMOTION_TOTAL_CHARS:
                    raise TwinPromotionError("twin text exceeds the batch promotion ceiling")
                candidate = _finding(kind=kind, text=text, source=source)
                prior = canonical.get(candidate.node_id)
                if prior is not None:
                    duplicates.append(
                        _sealed_value(
                            DuplicateObservation,
                            kind=kind,
                            text=text,
                            node_id=candidate.node_id,
                            duplicate_of_node_id=prior.node_id,
                            source=source,
                            canonical_source_asset_id=prior.source.asset_id,
                        )
                    )
                    continue
                canonical[candidate.node_id] = candidate
                (insights if kind == "insight" else questions).append(candidate)

    return _sealed_value(
        TwinPromotionPlan,
        canonical_insights=tuple(insights),
        canonical_questions=tuple(questions),
        duplicate_observations=tuple(duplicates),
        document_count=len(snapshot),
        identity_scope=account_id,
        owner_user_id=account_id,
        semantic_dedup=False,
        authority="advisory",
    )


__all__ = [
    "MAX_PROMOTION_DOCUMENTS",
    "MAX_PROMOTION_FINDINGS",
    "MAX_PROMOTION_TOTAL_CHARS",
    "DuplicateObservation",
    "PromotionKind",
    "PromotionSource",
    "PromotableFinding",
    "TwinPromotionError",
    "TwinPromotionPlan",
    "canonical_text",
    "plan_twin_promotion",
    "predicted_node_id",
]
