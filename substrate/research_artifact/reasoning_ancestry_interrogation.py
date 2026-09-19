"""Immutable owner question over an exact completed reasoning-ancestry closure."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.authority import owner_qualified_id
from substrate.engagement_spine.collective_manifest import (
    CollectiveManifest,
    create_collective_manifest,
    preview_collective_manifest,
    read_collective_manifest,
)
from substrate.engagement_spine.store import AuthorizedEngagementStore

from .authority import ArtifactAuthority
from .reasoning_ancestry import ReasoningAncestryNode
from .schema import ResearchArtifactBody


class ReasoningAncestryInterrogationConflict(ValueError):
    """The command, immutable receipt, or current ancestry no longer agrees."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _question(value: str) -> str:
    if not isinstance(value, str):
        raise ReasoningAncestryInterrogationConflict("question is invalid")
    cleaned = unicodedata.normalize("NFC", value).strip()
    if (
        not cleaned
        or len(cleaned.encode("utf-8")) > 4_000
        or any(unicodedata.category(character) == "Cc" for character in cleaned)
    ):
        raise ReasoningAncestryInterrogationConflict("question is invalid")
    return cleaned


def _mutation_key(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 512
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        raise ReasoningAncestryInterrogationConflict("mutation key is invalid")
    return value


def _closure(
    nodes: tuple[ReasoningAncestryNode, ...], selected: tuple[int, ...]
) -> tuple[ReasoningAncestryNode, ...]:
    if (
        not 1 <= len(selected) <= 32
        or any(not isinstance(value, int) or isinstance(value, bool) for value in selected)
        or tuple(sorted(set(selected))) != selected
    ):
        raise ReasoningAncestryInterrogationConflict(
            "selected terminal ordinals are invalid"
        )
    by_ordinal = {node.iteration.ordinal: node for node in nodes}
    if any(
        ordinal not in by_ordinal or by_ordinal[ordinal].child_ordinals
        for ordinal in selected
    ):
        raise ReasoningAncestryInterrogationConflict(
            "selected reasoning branch is not terminal"
        )
    included: set[int] = set()
    pending = list(selected)
    while pending:
        ordinal = pending.pop()
        if ordinal in included:
            continue
        included.add(ordinal)
        pending.extend(by_ordinal[ordinal].parent_ordinals)
    closure = tuple(node for node in nodes if node.iteration.ordinal in included)
    if not closure or len(closure) > 32:
        raise ReasoningAncestryInterrogationConflict("ancestry closure is invalid")
    return closure


class ReasoningAncestryInterrogationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["reasoning_ancestry_interrogation"] = (
        "reasoning_ancestry_interrogation"
    )
    schema_version: Literal[1] = 1
    receipt_id: str = Field(min_length=1, max_length=512)
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    head_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_terminal_ordinals: tuple[int, ...] = Field(min_length=1, max_length=32)
    closure_ordinals: tuple[int, ...] = Field(min_length=1, max_length=32)
    transition_sha256s: tuple[str, ...]
    ancestry_sha256s: tuple[str, ...]
    ordered_session_ids: tuple[str, ...]
    ordered_spawn_ids: tuple[str, ...]
    question: str = Field(min_length=1, max_length=4_000)
    question_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_id: str = Field(min_length=1, max_length=512)
    manifest_id: str = Field(min_length=1, max_length=512)
    membership_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    permits_provider_call: Literal[False] = False
    permits_spend: Literal[False] = False
    permits_graph_admission: Literal[False] = False
    permits_write: Literal[False] = False
    permits_benchmark_feedback: Literal[False] = False
    permits_publication: Literal[False] = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> ReasoningAncestryInterrogationReceipt:
        width = len(self.closure_ordinals)
        sequences = (
            self.transition_sha256s,
            self.ancestry_sha256s,
            self.ordered_session_ids,
            self.ordered_spawn_ids,
        )
        if any(len(sequence) != width for sequence in sequences):
            raise ValueError("ancestry interrogation row widths disagree")
        if tuple(sorted(set(self.selected_terminal_ordinals))) != (
            self.selected_terminal_ordinals
        ) or tuple(sorted(set(self.closure_ordinals))) != self.closure_ordinals:
            raise ValueError("ancestry interrogation ordinals are not canonical")
        if not set(self.selected_terminal_ordinals).issubset(self.closure_ordinals):
            raise ValueError("ancestry interrogation terminal is outside closure")
        if _question(self.question) != self.question:
            raise ValueError("ancestry interrogation question is not canonical")
        if _text_digest(self.question) != self.question_sha256:
            raise ValueError("ancestry interrogation question digest mismatch")
        if self.receipt_sha256 != _digest(
            self.model_dump(exclude={"receipt_sha256"}, mode="json")
        ):
            raise ValueError("ancestry interrogation receipt digest mismatch")
        return self

    def document(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def build_reasoning_ancestry_interrogation(
    *,
    body: ResearchArtifactBody,
    claim_index: int,
    nodes: tuple[ReasoningAncestryNode, ...],
    selected_terminal_ordinals: list[int] | tuple[int, ...],
    question: str,
    mutation_key: str,
    artifact_authority: ArtifactAuthority,
    engagement_store: AuthorizedEngagementStore,
) -> tuple[ReasoningAncestryInterrogationReceipt, CollectiveManifest]:
    selected = tuple(selected_terminal_ordinals)
    closure = _closure(nodes, selected)
    effective = body.effective_owner_claim(claim_index)
    if effective is None:
        raise ReasoningAncestryInterrogationConflict("effective claim is unavailable")
    cleaned_question = _question(question)
    cleaned_key = _mutation_key(mutation_key)
    spawn_ids = tuple(node.iteration.review.spawn_id for node in closure)
    if len(set(spawn_ids)) != len(spawn_ids):
        raise ReasoningAncestryInterrogationConflict("ancestry spawn is duplicated")
    manifest = preview_collective_manifest(spawn_ids, store=engagement_store)
    mutation_hash = _text_digest(cleaned_key)
    receipt_id = owner_qualified_id(
        engagement_store.authority,
        "ancestry-interrogation",
        mutation_hash,
    )
    payload: dict[str, object] = {
        "kind": "reasoning_ancestry_interrogation",
        "schema_version": 1,
        "receipt_id": receipt_id,
        "owner_account_digest": engagement_store.authority.account_digest,
        "artifact_account_digest": artifact_authority.account_digest,
        "artifact_investigation_digest": artifact_authority.investigation_digest,
        "claim_index": claim_index,
        "artifact_content_hash": body.content_hash(),
        "head_transition_sha256": effective[1],
        "effective_claim_sha256": _text_digest(effective[0]),
        "selected_terminal_ordinals": selected,
        "closure_ordinals": tuple(node.iteration.ordinal for node in closure),
        "transition_sha256s": tuple(
            node.iteration.compensation.transition_sha256 for node in closure
        ),
        "ancestry_sha256s": tuple(node.ancestry_sha256 for node in closure),
        "ordered_session_ids": tuple(
            node.iteration.review.session_id for node in closure
        ),
        "ordered_spawn_ids": spawn_ids,
        "question": cleaned_question,
        "question_sha256": _text_digest(cleaned_question),
        "mutation_key_sha256": mutation_hash,
        "collective_id": manifest.collective_id,
        "manifest_id": manifest.manifest_id,
        "membership_sha256": manifest.membership_sha256,
        "archive_grounded": False,
        "grants_authority": False,
        "permits_provider_call": False,
        "permits_spend": False,
        "permits_graph_admission": False,
        "permits_write": False,
        "permits_benchmark_feedback": False,
        "permits_publication": False,
    }
    return (
        ReasoningAncestryInterrogationReceipt(
            **payload, receipt_sha256=_digest(payload)
        ),
        manifest,
    )


def accept_reasoning_ancestry_interrogation(
    receipt: ReasoningAncestryInterrogationReceipt,
    *,
    engagement_store: AuthorizedEngagementStore,
) -> ReasoningAncestryInterrogationReceipt:
    # Serialize the intent precheck with manifest-first persistence. Without this
    # lock, two different commands sharing a mutation key could both observe no
    # receipt and the loser could claim an orphan manifest before its conflict.
    with engagement_store.lock_document(receipt.receipt_id):
        existing = engagement_store.get_document_strict(receipt.receipt_id)
        if existing is not None:
            return read_reasoning_ancestry_interrogation(
                receipt.receipt_id, engagement_store=engagement_store, expected=receipt
            )
        manifest = create_collective_manifest(
            receipt.ordered_spawn_ids, store=engagement_store
        )
        if (
            manifest.manifest_id != receipt.manifest_id
            or manifest.collective_id != receipt.collective_id
            or manifest.membership_sha256 != receipt.membership_sha256
        ):
            raise ReasoningAncestryInterrogationConflict(
                "collective manifest identity changed"
            )
        if engagement_store.claim_document(receipt.receipt_id, receipt.document()):
            return receipt
        return read_reasoning_ancestry_interrogation(
            receipt.receipt_id, engagement_store=engagement_store, expected=receipt
        )


def read_reasoning_ancestry_interrogation(
    receipt_id: str,
    *,
    engagement_store: AuthorizedEngagementStore,
    expected: ReasoningAncestryInterrogationReceipt | None = None,
) -> ReasoningAncestryInterrogationReceipt:
    try:
        row = engagement_store.get_document_strict(receipt_id)
        if row is None:
            raise KeyError(receipt_id)
        envelope = {
            "engagement_authority_version",
            "owner_account_digest",
            "engagement_key_id",
            "display_document_id",
        }
        payload_fields = set(ReasoningAncestryInterrogationReceipt.model_fields)
        if set(row) - payload_fields - envelope:
            raise ValueError("ancestry interrogation receipt has unknown fields")
        receipt = ReasoningAncestryInterrogationReceipt.model_validate(
            {key: row[key] for key in payload_fields if key in row}
        )
    except KeyError:
        raise
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ReasoningAncestryInterrogationConflict(
            "ancestry interrogation receipt is unavailable"
        ) from exc
    if receipt.receipt_id != receipt_id or (
        expected is not None and receipt != expected
    ):
        raise ReasoningAncestryInterrogationConflict(
            "ancestry interrogation replay conflicts"
        )
    manifest = read_collective_manifest(
        receipt.manifest_id, store=engagement_store
    )
    if (
        manifest.collective_id != receipt.collective_id
        or manifest.membership_sha256 != receipt.membership_sha256
        or manifest.ordered_spawn_ids != receipt.ordered_spawn_ids
    ):
        raise ReasoningAncestryInterrogationConflict(
            "ancestry interrogation manifest conflicts"
        )
    return receipt


def validate_reasoning_ancestry_interrogation(
    receipt: ReasoningAncestryInterrogationReceipt,
    *,
    body: ResearchArtifactBody,
    nodes: tuple[ReasoningAncestryNode, ...],
    artifact_authority: ArtifactAuthority,
    engagement_store: AuthorizedEngagementStore,
) -> CollectiveManifest:
    effective = body.effective_owner_claim(receipt.claim_index)
    closure = _closure(nodes, receipt.selected_terminal_ordinals)
    if effective is None or (
        receipt.owner_account_digest != engagement_store.authority.account_digest
        or receipt.artifact_account_digest != artifact_authority.account_digest
        or receipt.artifact_investigation_digest
        != artifact_authority.investigation_digest
        or receipt.artifact_content_hash != body.content_hash()
        or receipt.head_transition_sha256 != effective[1]
        or receipt.effective_claim_sha256 != _text_digest(effective[0])
        or receipt.closure_ordinals
        != tuple(node.iteration.ordinal for node in closure)
        or receipt.transition_sha256s
        != tuple(node.iteration.compensation.transition_sha256 for node in closure)
        or receipt.ancestry_sha256s
        != tuple(node.ancestry_sha256 for node in closure)
        or receipt.ordered_session_ids
        != tuple(node.iteration.review.session_id for node in closure)
        or receipt.ordered_spawn_ids
        != tuple(node.iteration.review.spawn_id for node in closure)
    ):
        raise ReasoningAncestryInterrogationConflict(
            "ancestry interrogation no longer matches canonical reasoning"
        )
    manifest = read_collective_manifest(receipt.manifest_id, store=engagement_store)
    if (
        manifest.collective_id != receipt.collective_id
        or manifest.membership_sha256 != receipt.membership_sha256
        or manifest.ordered_spawn_ids != receipt.ordered_spawn_ids
    ):
        raise ReasoningAncestryInterrogationConflict(
            "ancestry interrogation manifest conflicts"
        )
    return manifest


__all__ = [
    "ReasoningAncestryInterrogationConflict",
    "ReasoningAncestryInterrogationReceipt",
    "accept_reasoning_ancestry_interrogation",
    "build_reasoning_ancestry_interrogation",
    "read_reasoning_ancestry_interrogation",
    "validate_reasoning_ancestry_interrogation",
]
