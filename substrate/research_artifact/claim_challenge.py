"""Exact, authority-free identity receipt for a terminal-claim challenge."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArchivedInheritedSupport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit_id: str = Field(min_length=1, max_length=512)
    qualification_state: Literal[
        "complete", "partial", "unknown", "legacy_unqualified"
    ]
    source_investigation_id: str | None = Field(default=None, max_length=512)
    supporting_leaf_investigation_id: str = Field(min_length=1, max_length=512)


class ClaimChallengeReceipt(BaseModel):
    """Binds reserved work to immutable inputs; grants no read/spend authority."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1, 2, 3] = 1
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_asset_id: str = Field(min_length=1, max_length=512)
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    synthesis_event_id: str = Field(min_length=1, max_length=512)
    claim_index: int = Field(ge=0, le=100_000)
    claim_id: str = Field(min_length=1, max_length=512)
    claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_event_id: str | None = Field(default=None, min_length=1, max_length=512)
    scorer_id: str | None = Field(default=None, min_length=1, max_length=240)
    relation: Literal["entailed", "contradicted", "not_established"] | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_receipt_sha256s: tuple[str, ...] = Field(default=(), max_length=1000)
    model_id: str | None = Field(default=None, min_length=1, max_length=240)
    research_tier: Literal["fast", "deep", "wrestle"]
    goal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_kind: Literal["effective_owner_claim"] | None = None
    purpose: Literal["investigate_effective_owner_claim"] | None = None
    question_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    archived_claim: str | None = Field(default=None, min_length=1, max_length=20_000)
    archived_claim_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    effective_claim: str | None = Field(default=None, min_length=1, max_length=20_000)
    root_transition_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    head_transition_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    revision_transition_sha256s: tuple[str, ...] = Field(default=(), max_length=1001)
    revision_chain_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    mutation_key_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    archived_evaluation_event_id: str | None = Field(default=None, max_length=512)
    archived_scorer_id: str | None = Field(default=None, max_length=240)
    archived_relation: Literal["entailed", "contradicted", "not_established"] | None = None
    archived_score: float | None = Field(default=None, ge=0.0, le=1.0)
    archived_evidence_receipt_sha256s: tuple[str, ...] = Field(default=(), max_length=1000)
    archived_inherited_support: tuple[ArchivedInheritedSupport, ...] = Field(default=(), max_length=1000)
    archived_evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    archive_grounded: bool | None = None
    grants_authority: bool | None = None
    permits_provider_call: bool | None = None
    permits_spend: bool | None = None
    permits_graph_admission: bool | None = None
    permits_write: bool | None = None
    permits_benchmark_feedback: bool | None = None
    permits_publication: bool | None = None
    recursive_context_pack: dict[str, object] | None = None
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> ClaimChallengeReceipt:
        if len(set(self.evidence_receipt_sha256s)) != len(self.evidence_receipt_sha256s):
            raise ValueError("challenge evidence receipts must be unique")
        if any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
               for value in self.evidence_receipt_sha256s):
            raise ValueError("challenge evidence receipt digest is invalid")
        if self.schema_version == 1:
            if self.selection_kind is not None or self.revision_transition_sha256s:
                raise ValueError("legacy challenge receipt has owner-context fields")
            if (
                self.evaluation_event_id is None
                or self.scorer_id is None
                or self.score is None
            ):
                raise ValueError("legacy challenge evaluation is incomplete")
        else:
            required = (
                self.selection_kind,
                self.purpose,
                self.question_sha256,
                self.artifact_investigation_digest,
                self.archived_claim,
                self.archived_claim_sha256,
                self.effective_claim,
                self.root_transition_sha256,
                self.head_transition_sha256,
                self.revision_chain_sha256,
                self.mutation_key_sha256,
                self.archived_evaluation_event_id,
                self.archived_scorer_id,
                self.archived_evidence_sha256,
            )
            if any(value is None for value in required):
                raise ValueError("effective owner context receipt is incomplete")
            if not self.revision_transition_sha256s:
                raise ValueError("effective owner context revision chain is empty")
            if len(set(self.revision_transition_sha256s)) != len(
                self.revision_transition_sha256s
            ):
                raise ValueError("effective owner context revision chain is duplicated")
            archived_evidence_identity = {
                "evaluation_event_id": self.archived_evaluation_event_id,
                "scorer_id": self.archived_scorer_id,
                "relation": self.archived_relation,
                "score": self.archived_score,
                "direct_receipt_sha256s": list(
                    self.archived_evidence_receipt_sha256s
                ),
                "inherited_support": [
                    item.model_dump(mode="json")
                    for item in self.archived_inherited_support
                ],
            }
            if (
                self.revision_transition_sha256s[0] != self.root_transition_sha256
                or self.revision_transition_sha256s[-1]
                != self.head_transition_sha256
                or self.revision_chain_sha256
                != _receipt_sha256(list(self.revision_transition_sha256s))
                or self.claim_sha256
                != hashlib.sha256((self.effective_claim or "").encode("utf-8")).hexdigest()
                or self.archived_claim_sha256
                != hashlib.sha256((self.archived_claim or "").encode("utf-8")).hexdigest()
                or self.evidence_receipt_sha256s
                or self.evaluation_event_id is not None
                or self.scorer_id is not None
                or self.relation is not None
                or self.score is not None
                or self.archived_evidence_sha256
                != _receipt_sha256(archived_evidence_identity)
            ):
                raise ValueError("effective owner context revision chain mismatch")
            if any(
                value is not False
                for value in (
                    self.archive_grounded,
                    self.grants_authority,
                    self.permits_provider_call,
                    self.permits_spend,
                    self.permits_graph_admission,
                    self.permits_write,
                    self.permits_benchmark_feedback,
                    self.permits_publication,
                )
            ):
                raise ValueError("effective owner context grants hidden authority")
            if self.schema_version == 2 and self.recursive_context_pack is not None:
                raise ValueError("legacy effective context has recursive pack")
            if self.schema_version == 3:
                from .recursive_round_context import RecursiveRoundContextPackReceipt

                if self.recursive_context_pack is None:
                    raise ValueError("recursive effective context pack is missing")
                pack = RecursiveRoundContextPackReceipt.model_validate(
                    self.recursive_context_pack
                )
                if (
                    pack.owner_account_digest != self.owner_account_digest
                    or pack.artifact_investigation_digest
                    != self.artifact_investigation_digest
                    or pack.source_asset_id != self.source_asset_id
                    or pack.artifact_content_hash != self.artifact_content_hash
                    or pack.claim_index != self.claim_index
                    or pack.current_effective_claim != self.effective_claim
                    or pack.current_head_transition_sha256
                    != self.head_transition_sha256
                    or pack.mutation_key_sha256 != self.mutation_key_sha256
                    or self.question_sha256
                    != hashlib.sha256(
                        "\n".join(pack.follow_up_questions).encode("utf-8")
                    ).hexdigest()
                ):
                    raise ValueError("recursive effective context pack identity mismatch")
        identity = self.model_dump(exclude={"receipt_sha256"})
        if self.schema_version == 1:
            for field in (
                "selection_kind",
                "purpose",
                "question_sha256",
                "artifact_investigation_digest",
                "archived_claim",
                "archived_claim_sha256",
                "effective_claim",
                "root_transition_sha256",
                "head_transition_sha256",
                "revision_transition_sha256s",
                "revision_chain_sha256",
                "mutation_key_sha256",
                "archived_evaluation_event_id",
                "archived_scorer_id",
                "archived_relation",
                "archived_score",
                "archived_evidence_receipt_sha256s",
                "archived_inherited_support",
                "archived_evidence_sha256",
                "archive_grounded",
                "grants_authority",
                "permits_provider_call",
                "permits_spend",
                "permits_graph_admission",
                "permits_write",
                "permits_benchmark_feedback",
                "permits_publication",
                "recursive_context_pack",
            ):
                identity.pop(field, None)
        elif self.schema_version == 2:
            identity.pop("recursive_context_pack", None)
        if self.receipt_sha256 != _receipt_sha256(identity):
            raise ValueError("challenge receipt digest mismatch")
        return self


def _receipt_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_claim_challenge_receipt(
    *,
    owner_account_digest: str,
    source_asset_id: str,
    artifact_content_hash: str,
    synthesis_event_id: str,
    claim_index: int,
    claim_id: str,
    claim: str,
    evaluation_event_id: str,
    scorer_id: str,
    relation: str | None,
    score: float,
    evidence_receipt_sha256s: tuple[str, ...],
    model_id: str | None,
    research_tier: Literal["fast", "deep", "wrestle"],
    goal: str,
) -> ClaimChallengeReceipt:
    payload = {
        "schema_version": 1,
        "owner_account_digest": owner_account_digest,
        "source_asset_id": source_asset_id,
        "artifact_content_hash": artifact_content_hash,
        "synthesis_event_id": synthesis_event_id,
        "claim_index": claim_index,
        "claim_id": claim_id,
        "claim_sha256": hashlib.sha256(claim.encode("utf-8")).hexdigest(),
        "evaluation_event_id": evaluation_event_id,
        "scorer_id": scorer_id,
        "relation": relation,
        "score": score,
        "evidence_receipt_sha256s": evidence_receipt_sha256s,
        "model_id": model_id,
        "research_tier": research_tier,
        "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
    }
    return ClaimChallengeReceipt(**payload, receipt_sha256=_receipt_sha256(payload))


def build_recursive_owner_claim_context_receipt(
    *,
    ordinary_receipt: ClaimChallengeReceipt,
    recursive_context_pack: object,
    goal: str,
    question: str,
) -> ClaimChallengeReceipt:
    """Upgrade the ordinary effective-context receipt with one exact pack."""
    from .recursive_round_context import RecursiveRoundContextPackReceipt

    pack = RecursiveRoundContextPackReceipt.model_validate(recursive_context_pack)
    if ordinary_receipt.schema_version != 2:
        raise ValueError("recursive context requires an ordinary effective receipt")
    payload = ordinary_receipt.model_dump(
        mode="json", exclude={"receipt_sha256"}, exclude_none=False
    )
    payload["schema_version"] = 3
    payload["recursive_context_pack"] = pack.model_dump(mode="json")
    payload["goal_sha256"] = hashlib.sha256(goal.encode("utf-8")).hexdigest()
    payload["question_sha256"] = hashlib.sha256(question.encode("utf-8")).hexdigest()
    return ClaimChallengeReceipt(**payload, receipt_sha256=_receipt_sha256(payload))


def build_effective_owner_claim_context_receipt(
    *,
    owner_account_digest: str,
    source_asset_id: str,
    artifact_investigation_digest: str,
    artifact_content_hash: str,
    synthesis_event_id: str,
    claim_index: int,
    claim_id: str,
    archived_claim: str,
    effective_claim: str,
    root_transition_sha256: str,
    revision_transition_sha256s: tuple[str, ...],
    evaluation_event_id: str,
    scorer_id: str,
    relation: str | None,
    score: float,
    evidence_receipt_sha256s: tuple[str, ...],
    archived_inherited_support: tuple[ArchivedInheritedSupport, ...],
    model_id: str | None,
    research_tier: Literal["fast", "deep", "wrestle"],
    goal: str,
    question: str,
    mutation_key: str,
) -> ClaimChallengeReceipt:
    """Build an explicit owner-context selection with zero implied truth authority."""
    if not revision_transition_sha256s:
        raise ValueError("effective owner context revision chain is empty")
    archived_evidence_identity = {
        "evaluation_event_id": evaluation_event_id,
        "scorer_id": scorer_id,
        "relation": relation,
        "score": score,
        "direct_receipt_sha256s": list(evidence_receipt_sha256s),
        "inherited_support": [
            item.model_dump(mode="json") for item in archived_inherited_support
        ],
    }
    payload = {
        "schema_version": 2,
        "owner_account_digest": owner_account_digest,
        "source_asset_id": source_asset_id,
        "artifact_content_hash": artifact_content_hash,
        "synthesis_event_id": synthesis_event_id,
        "claim_index": claim_index,
        "claim_id": claim_id,
        "claim_sha256": hashlib.sha256(effective_claim.encode("utf-8")).hexdigest(),
        "evaluation_event_id": None,
        "scorer_id": None,
        "relation": None,
        "score": None,
        "evidence_receipt_sha256s": (),
        "model_id": model_id,
        "research_tier": research_tier,
        "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "selection_kind": "effective_owner_claim",
        "purpose": "investigate_effective_owner_claim",
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "artifact_investigation_digest": artifact_investigation_digest,
        "archived_claim": archived_claim,
        "archived_claim_sha256": hashlib.sha256(archived_claim.encode("utf-8")).hexdigest(),
        "effective_claim": effective_claim,
        "root_transition_sha256": root_transition_sha256,
        "head_transition_sha256": revision_transition_sha256s[-1],
        "revision_transition_sha256s": revision_transition_sha256s,
        "revision_chain_sha256": _receipt_sha256(list(revision_transition_sha256s)),
        "mutation_key_sha256": hashlib.sha256(mutation_key.encode("utf-8")).hexdigest(),
        "archived_evaluation_event_id": evaluation_event_id,
        "archived_scorer_id": scorer_id,
        "archived_relation": relation,
        "archived_score": score,
        "archived_evidence_receipt_sha256s": evidence_receipt_sha256s,
        "archived_inherited_support": tuple(
            item.model_dump(mode="json") for item in archived_inherited_support
        ),
        "archived_evidence_sha256": _receipt_sha256(archived_evidence_identity),
        "archive_grounded": False,
        "grants_authority": False,
        "permits_provider_call": False,
        "permits_spend": False,
        "permits_graph_admission": False,
        "permits_write": False,
        "permits_benchmark_feedback": False,
        "permits_publication": False,
    }
    return ClaimChallengeReceipt(**payload, receipt_sha256=_receipt_sha256(payload))


def parse_claim_challenge_receipt(
    value: object, *, expected_owner_account_digest: str | None = None
) -> ClaimChallengeReceipt | None:
    if value is None:
        return None
    receipt = ClaimChallengeReceipt.model_validate(value)
    if (
        expected_owner_account_digest is not None
        and receipt.owner_account_digest != expected_owner_account_digest
    ):
        raise ValueError("challenge receipt owner mismatch")
    return receipt


def validate_claim_challenge_transport(
    receipt: ClaimChallengeReceipt,
    *,
    goal: object,
    selection_text: object,
    source_asset_id: object,
    model_id: object,
    research_tier: object,
    view_mode: object,
    validate_view_mode: bool = False,
) -> None:
    """Bind persisted session/spawn transport bytes back to the receipt."""
    if (
        not isinstance(goal, str)
        or hashlib.sha256(goal.encode("utf-8")).hexdigest() != receipt.goal_sha256
        or not isinstance(selection_text, str)
        or hashlib.sha256(selection_text.encode("utf-8")).hexdigest()
        != receipt.claim_sha256
        or source_asset_id != receipt.source_asset_id
        or model_id != receipt.model_id
        or research_tier != receipt.research_tier
        or (
            validate_view_mode
            and receipt.schema_version == 3
            and (
                receipt.recursive_context_pack is None
                or view_mode != receipt.recursive_context_pack.get("view_mode")
            )
        )
    ):
        raise ValueError("challenge transport identity mismatch")
