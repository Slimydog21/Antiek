"""Immutable server-built context packs over completed effective-claim rounds."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore
from substrate.floating_session.store import SessionStore

from .authority import ArtifactAuthority
from .effective_claim_iterations import (
    EffectiveClaimIteration,
    project_effective_claim_iterations,
)
from .schema import ResearchArtifactBody

MAX_SELECTED_ROUNDS = 100
MAX_FOLLOW_UP_QUESTIONS = 20
MAX_CONTEXT_PACK_BYTES = 256_000


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RecursiveRoundContextRow(BaseModel):
    """One exact prior reasoning round; explicitly not an evidence record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=1, le=1000)
    claim_index: int = Field(ge=0, le=100_000)
    session_id: str = Field(min_length=1, max_length=512)
    spawn_id: str = Field(min_length=1, max_length=512)
    transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    archived_claim: str = Field(min_length=1, max_length=20_000)
    prior_effective_claim: str = Field(min_length=1, max_length=20_000)
    candidate_text: str = Field(min_length=1, max_length=100_000)
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_rationale: str = Field(min_length=1, max_length=20_000)
    proposed_claim: str = Field(min_length=1, max_length=20_000)
    replacement_claim: str = Field(min_length=1, max_length=20_000)
    context_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_question: str = Field(min_length=1, max_length=4000)
    source_purpose: str = Field(min_length=1, max_length=240)
    model_id: str | None = Field(default=None, max_length=240)
    research_tier: Literal["fast", "deep", "wrestle"]
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    row_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_digest(self) -> RecursiveRoundContextRow:
        identity = self.model_dump(mode="json", exclude={"row_sha256"})
        if self.row_sha256 != _digest(identity):
            raise ValueError("recursive context row digest mismatch")
        return self


class RecursiveRoundContextPackReceipt(BaseModel):
    """Canonical selected-round prompt substrate with zero execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_asset_id: str = Field(min_length=1, max_length=512)
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    current_effective_claim: str = Field(min_length=1, max_length=20_000)
    current_head_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    view_mode: Literal["floating", "full"]
    selected_ordinals: tuple[int, ...] = Field(max_length=MAX_SELECTED_ROUNDS)
    selected_transition_sha256s: tuple[str, ...] = Field(max_length=MAX_SELECTED_ROUNDS)
    follow_up_questions: tuple[str, ...] = Field(
        min_length=1, max_length=MAX_FOLLOW_UP_QUESTIONS
    )
    rows: tuple[RecursiveRoundContextRow, ...] = Field(max_length=MAX_SELECTED_ROUNDS)
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    permits_provider_call: Literal[False] = False
    permits_spend: Literal[False] = False
    permits_graph_admission: Literal[False] = False
    permits_twin_promotion: Literal[False] = False
    permits_write: Literal[False] = False
    permits_benchmark_feedback: Literal[False] = False
    permits_publication: Literal[False] = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> RecursiveRoundContextPackReceipt:
        if tuple(sorted(set(self.selected_ordinals))) != self.selected_ordinals:
            raise ValueError("recursive context ordinals must be unique and ordered")
        if len(self.rows) != len(self.selected_ordinals):
            raise ValueError("recursive context row selection is incomplete")
        if tuple(row.ordinal for row in self.rows) != self.selected_ordinals:
            raise ValueError("recursive context row order mismatch")
        if tuple(row.transition_sha256 for row in self.rows) != (
            self.selected_transition_sha256s
        ):
            raise ValueError("recursive context transition selection mismatch")
        if len(set(self.follow_up_questions)) != len(self.follow_up_questions):
            raise ValueError("recursive context questions must be unique")
        if any(question != question.strip() for question in self.follow_up_questions):
            raise ValueError("recursive context question is not normalized")
        pack_identity = {
            "selected_ordinals": list(self.selected_ordinals),
            "selected_transition_sha256s": list(self.selected_transition_sha256s),
            "follow_up_questions": list(self.follow_up_questions),
            "rows": [row.model_dump(mode="json") for row in self.rows],
        }
        if self.pack_sha256 != _digest(pack_identity):
            raise ValueError("recursive context pack digest mismatch")
        if len(
            json.dumps(
                pack_identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ) > MAX_CONTEXT_PACK_BYTES:
            raise ValueError("recursive context pack exceeds byte bound")
        identity = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != _digest(identity):
            raise ValueError("recursive context receipt digest mismatch")
        return self


def _normalize_questions(values: tuple[str, ...]) -> tuple[str, ...]:
    questions = tuple(value.strip() for value in values)
    if (
        not questions
        or any(
            not question
            or len(question) > 4000
            or any(ord(char) < 0x20 and char not in "\n\t" for char in question)
            for question in questions
        )
        or len(set(questions)) != len(questions)
    ):
        raise ValueError("recursive context questions are invalid")
    return questions


def recursive_context_row_from_iteration(
    item: EffectiveClaimIteration,
) -> RecursiveRoundContextRow:
    """Canonical row encoding shared by pack creation and ancestry parity."""
    public = item.public_dict()
    row_identity = {
        "ordinal": item.ordinal,
        "claim_index": item.compensation.claim_index,
        "session_id": item.review.session_id,
        "spawn_id": item.review.spawn_id,
        "transition_sha256": item.compensation.transition_sha256,
        "prior_artifact_content_hash": item.prior_body.content_hash(),
        "result_artifact_content_hash": item.result_body.content_hash(),
        "archived_claim": public["archived_claim"],
        "prior_effective_claim": public["prior_effective_claim"],
        "candidate_text": public["candidate_text"],
        "candidate_sha256": public["candidate_sha256"],
        "review_rationale": public["review_rationale"],
        "proposed_claim": public["proposed_claim"],
        "replacement_claim": public["replacement_claim"],
        "context_receipt_sha256": public["context_receipt_sha256"],
        "review_receipt_sha256": public["review_receipt_sha256"],
        "proposal_receipt_sha256": public["proposal_receipt_sha256"],
        "source_question": public["question"],
        "source_purpose": public["purpose"],
        "model_id": public["model_id"],
        "research_tier": public["research_tier"],
        "archive_grounded": False,
        "grants_authority": False,
    }
    return RecursiveRoundContextRow(**row_identity, row_sha256=_digest(row_identity))


def build_recursive_round_context_pack(
    *,
    body: ResearchArtifactBody,
    claim_index: int,
    selected_ordinals: tuple[int, ...],
    follow_up_questions: tuple[str, ...],
    mutation_key: str,
    view_mode: Literal["floating", "full"],
    authority: ArtifactAuthority,
    owner_account_digest: str,
    engagement_store: EngagementStore,
    session_store: SessionStore,
) -> RecursiveRoundContextPackReceipt:
    """Strictly reproject selected canonical rounds; accept no reasoning bytes."""
    if (
        tuple(sorted(set(selected_ordinals))) != selected_ordinals
        or len(selected_ordinals) > MAX_SELECTED_ROUNDS
    ):
        raise ValueError("recursive context ordinals must be unique and ordered")
    normalized_questions = _normalize_questions(follow_up_questions)
    normalized_key = mutation_key.strip()
    if not normalized_key or len(normalized_key) > 512:
        raise ValueError("recursive context mutation key is invalid")
    effective = body.effective_owner_claim(claim_index)
    if effective is None:
        raise ValueError("recursive context effective claim is unavailable")
    iterations = project_effective_claim_iterations(
        body=body,
        claim_index=claim_index,
        authority=authority,
        owner_account_digest=owner_account_digest,
        engagement_store=engagement_store,
        session_store=session_store,
    )
    by_ordinal = {item.ordinal: item for item in iterations}
    if any(ordinal not in by_ordinal for ordinal in selected_ordinals):
        raise ValueError("recursive context round is unavailable")
    rows: list[RecursiveRoundContextRow] = []
    for ordinal in selected_ordinals:
        item = by_ordinal[ordinal]
        rows.append(recursive_context_row_from_iteration(item))
    pack_identity = {
        "selected_ordinals": list(selected_ordinals),
        "selected_transition_sha256s": [row.transition_sha256 for row in rows],
        "follow_up_questions": list(normalized_questions),
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    payload = {
        "schema_version": 1,
        "owner_account_digest": owner_account_digest,
        "artifact_investigation_digest": authority.investigation_digest,
        "source_asset_id": authority.investigation_id,
        "artifact_content_hash": body.content_hash(),
        "claim_index": claim_index,
        "current_effective_claim": effective[0],
        "current_head_transition_sha256": effective[1],
        "view_mode": view_mode,
        **pack_identity,
        "mutation_key_sha256": hashlib.sha256(
            normalized_key.encode("utf-8")
        ).hexdigest(),
        "pack_sha256": _digest(pack_identity),
        "archive_grounded": False,
        "grants_authority": False,
        "permits_provider_call": False,
        "permits_spend": False,
        "permits_graph_admission": False,
        "permits_twin_promotion": False,
        "permits_write": False,
        "permits_benchmark_feedback": False,
        "permits_publication": False,
    }
    return RecursiveRoundContextPackReceipt(
        **payload, receipt_sha256=_digest(payload)
    )


def render_recursive_round_context_prompt(
    pack: RecursiveRoundContextPackReceipt,
) -> str:
    """Render exact owner-reasoning context with explicit epistemic labels."""
    canonical_pack_json = json.dumps(
        pack.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    sections = [
        "Purpose: investigate the current owner claim using explicitly selected prior reasoning.",
        "Selected prior rounds are owner-authored reasoning history, not evidence or source authority.",
        "Exact canonical recursive context pack JSON follows:",
        canonical_pack_json,
    ]
    sections.append(
        "Do not treat prior owner reasoning as verified evidence, mutate the archive, or infer downstream authority."
    )
    sections.append("Question: " + "\n".join(pack.follow_up_questions))
    rendered = "\n".join(sections)
    if len(rendered.encode("utf-8")) > MAX_CONTEXT_PACK_BYTES:
        raise ValueError("recursive context prompt exceeds byte bound")
    return rendered
