"""Append-only owner review for a completed exact-claim challenge candidate."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore
from substrate.floating_session.store import SessionStore

from .claim_challenge import ClaimChallengeReceipt, parse_claim_challenge_receipt

MAX_CANDIDATE_BYTES = 200_000
MAX_RATIONALE_BYTES = 4_000


class ClaimReviewConflict(ValueError):
    """The requested review command conflicts with immutable current state."""


class ClaimReviewAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    kind: Literal["claim_challenge_acceptance"] = "claim_challenge_acceptance"
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_asset_id: str = Field(min_length=1, max_length=512)
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    challenge_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str = Field(min_length=1, max_length=512)
    spawn_id: str = Field(min_length=1, max_length=512)
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_text: str = Field(min_length=1)
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ClaimReviewAcceptance:
        if len(self.candidate_text.encode("utf-8")) > MAX_CANDIDATE_BYTES:
            raise ValueError("claim review candidate is too large")
        if _sha(self.candidate_text) != self.candidate_sha256:
            raise ValueError("claim review candidate digest mismatch")
        if self.receipt_sha256 != _digest(self.model_dump(exclude={"receipt_sha256"})):
            raise ValueError("claim review acceptance digest mismatch")
        return self


class ClaimReviewReversal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    kind: Literal["claim_challenge_reversal"] = "claim_challenge_reversal"
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    acceptance_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=1)
    rationale_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ClaimReviewReversal:
        if len(self.rationale.encode("utf-8")) > MAX_RATIONALE_BYTES:
            raise ValueError("claim review reversal rationale is too large")
        if _sha(self.rationale) != self.rationale_sha256:
            raise ValueError("claim review reversal rationale digest mismatch")
        if self.receipt_sha256 != _digest(self.model_dump(exclude={"receipt_sha256"})):
            raise ValueError("claim review reversal digest mismatch")
        return self


class ClaimReviewProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: Literal[
        "later_owner_accepted_counter_analysis",
        "later_owner_reversed_counter_analysis",
    ]
    challenge_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acceptance_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reversal_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    session_id: str = Field(min_length=1, max_length=512)
    spawn_id: str = Field(min_length=1, max_length=512)
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_text: str = Field(min_length=1)
    evaluation_event_id: str = Field(min_length=1, max_length=512)
    evidence_receipt_sha256s: tuple[str, ...]
    grants_authority: Literal[False] = False


@dataclass(frozen=True)
class ClaimReviewCandidate:
    challenge: ClaimChallengeReceipt
    session_id: str
    spawn_id: str
    candidate_text: str
    candidate_sha256: str


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_command(value: str, *, field: str, max_bytes: int) -> str:
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned.encode("utf-8")) > max_bytes
        or any(ord(char) < 0x20 and char not in "\n\t" for char in cleaned)
    ):
        raise ValueError(f"{field} is invalid")
    return cleaned


def _exact_candidate(value: str) -> str:
    if (
        not value.strip()
        or len(value.encode("utf-8")) > MAX_CANDIDATE_BYTES
        or any(ord(char) < 0x20 and char not in "\n\t" for char in value)
    ):
        raise ValueError("claim review candidate is invalid")
    return value


def _strict_document(store: EngagementStore, document_id: str) -> dict[str, Any] | None:
    strict = getattr(store, "get_document_strict", None)
    return strict(document_id) if callable(strict) else store.get_document(document_id)


def review_spawn_lock_document_id(spawn_id: str) -> str:
    """Opaque immutable index used to fence generic rewrites by spawn identity."""
    return "claim-review-spawn-lock:" + _sha(spawn_id)


def read_spawn_claim_review_acceptance(
    spawn_id: str, *, store: EngagementStore
) -> ClaimReviewAcceptance | None:
    row = _strict_document(store, review_spawn_lock_document_id(spawn_id))
    if row is None:
        return None
    try:
        if row.get("kind") != "claim_challenge_acceptance":
            raise ValueError("claim review spawn lock kind mismatch")
        acceptance = ClaimReviewAcceptance.model_validate(row.get("acceptance"))
        if acceptance.spawn_id != spawn_id:
            raise ValueError("claim review spawn lock identity mismatch")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored claim review spawn lock is corrupt") from exc
    return acceptance


def resolve_claim_review_candidate(
    *,
    session_row: dict[str, Any],
    spawn_row: dict[str, Any],
    owner_account_digest: str,
) -> ClaimReviewCandidate:
    challenge = parse_claim_challenge_receipt(
        session_row.get("claim_challenge"),
        expected_owner_account_digest=owner_account_digest,
    )
    spawn_challenge = parse_claim_challenge_receipt(
        spawn_row.get("claim_challenge"),
        expected_owner_account_digest=owner_account_digest,
    )
    if challenge is None or spawn_challenge != challenge:
        raise ValueError("claim review challenge identity mismatch")
    if (
        not isinstance(session_row.get("session_id"), str)
        or not session_row["session_id"]
        or not isinstance(spawn_row.get("spawn_id"), str)
        or not spawn_row["spawn_id"]
        or session_row.get("spawn_id") != spawn_row.get("spawn_id")
        or session_row.get("parent_asset_id") != spawn_row.get("parent_asset_id")
        or challenge.source_asset_id != spawn_row.get("parent_asset_id")
    ):
        raise ValueError("claim review session identity mismatch")
    if session_row.get("status") != "complete" or spawn_row.get("status") != "complete":
        raise ClaimReviewConflict("claim challenge candidate is not complete")
    raw = spawn_row.get("output_text")
    if not isinstance(raw, str):
        raise ValueError("claim review candidate is unavailable")
    candidate = _exact_candidate(raw)
    return ClaimReviewCandidate(
        challenge=challenge,
        session_id=str(session_row["session_id"]),
        spawn_id=str(spawn_row["spawn_id"]),
        candidate_text=candidate,
        candidate_sha256=_sha(candidate),
    )


def review_document_id(challenge_receipt_sha256: str) -> str:
    return f"claim-review-accept-{challenge_receipt_sha256}"


def reversal_document_id(acceptance_receipt_sha256: str) -> str:
    return f"claim-review-reverse-{acceptance_receipt_sha256}"


def build_claim_review_preview(
    candidate: ClaimReviewCandidate,
    *,
    artifact_account_digest: str,
    artifact_investigation_digest: str,
    review_state: Literal["candidate", "accepted", "reversed"] = "candidate",
) -> dict[str, Any]:
    if candidate.challenge.schema_version != 1:
        raise ClaimReviewConflict(
            "legacy claim review cannot consume an effective-owner context receipt"
        )
    identity = {
        "schema_version": 1,
        "owner_account_digest": candidate.challenge.owner_account_digest,
        "artifact_account_digest": artifact_account_digest,
        "artifact_investigation_digest": artifact_investigation_digest,
        "source_asset_id": candidate.challenge.source_asset_id,
        "artifact_content_hash": candidate.challenge.artifact_content_hash,
        "challenge_receipt_sha256": candidate.challenge.receipt_sha256,
        "session_id": candidate.session_id,
        "spawn_id": candidate.spawn_id,
        "candidate_sha256": candidate.candidate_sha256,
        "review_state": review_state,
    }
    preview_sha256 = _digest(identity)
    escaped = html.escape(candidate.candidate_text, quote=True)
    return {
        **identity,
        "preview_sha256": preview_sha256,
        "candidate_text": candidate.candidate_text,
        "html": (
            '<article data-view-format="html" data-claim-review="candidate">'
            "<h1>Claim challenge review candidate</h1>"
            "<p>This is later counter-analysis, not a replacement for terminal truth.</p>"
            f"<pre>{escaped}</pre></article>"
        ),
        "view_format": "html",
    }


def _acceptance_request(
    preview: dict[str, Any], *, expected_preview_sha256: str, mutation_key: str
) -> dict[str, Any]:
    key = _clean_command(mutation_key, field="mutation key", max_bytes=512)
    if expected_preview_sha256 != preview["preview_sha256"]:
        raise ClaimReviewConflict("claim review preview is stale")
    return {
        "preview_sha256": expected_preview_sha256,
        "mutation_key_sha256": _sha(key),
        "challenge_receipt_sha256": preview["challenge_receipt_sha256"],
        "candidate_sha256": preview["candidate_sha256"],
    }


def accept_claim_review(
    candidate: ClaimReviewCandidate,
    *,
    artifact_account_digest: str,
    artifact_investigation_digest: str,
    expected_preview_sha256: str,
    mutation_key: str,
    store: EngagementStore,
) -> ClaimReviewAcceptance:
    preview = build_claim_review_preview(
        candidate,
        artifact_account_digest=artifact_account_digest,
        artifact_investigation_digest=artifact_investigation_digest,
    )
    request = _acceptance_request(
        preview,
        expected_preview_sha256=expected_preview_sha256,
        mutation_key=mutation_key,
    )
    payload = {
        "schema_version": 1,
        "kind": "claim_challenge_acceptance",
        "owner_account_digest": candidate.challenge.owner_account_digest,
        "artifact_account_digest": artifact_account_digest,
        "artifact_investigation_digest": artifact_investigation_digest,
        "source_asset_id": candidate.challenge.source_asset_id,
        "artifact_content_hash": candidate.challenge.artifact_content_hash,
        "challenge_receipt_sha256": candidate.challenge.receipt_sha256,
        "session_id": candidate.session_id,
        "spawn_id": candidate.spawn_id,
        "candidate_sha256": candidate.candidate_sha256,
        "candidate_text": candidate.candidate_text,
        "preview_sha256": preview["preview_sha256"],
        "mutation_key_sha256": request["mutation_key_sha256"],
        "request_sha256": _digest(request),
    }
    acceptance = ClaimReviewAcceptance(
        **payload, receipt_sha256=_digest(payload)
    )
    document_id = review_document_id(candidate.challenge.receipt_sha256)
    row = {"kind": "claim_challenge_acceptance", "acceptance": acceptance.model_dump()}
    lock_id = review_spawn_lock_document_id(candidate.spawn_id)
    if not store.claim_document(lock_id, row):
        locked = read_spawn_claim_review_acceptance(candidate.spawn_id, store=store)
        if locked != acceptance:
            raise ClaimReviewConflict(
                "claim review spawn is already locked by another command"
            )
    if store.claim_document(document_id, row):
        return acceptance
    existing = _strict_document(store, document_id)
    try:
        if (existing or {}).get("kind") != "claim_challenge_acceptance":
            raise ValueError("claim review acceptance kind mismatch")
        persisted = ClaimReviewAcceptance.model_validate((existing or {}).get("acceptance"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored claim review acceptance is corrupt") from exc
    if persisted.request_sha256 != acceptance.request_sha256 or persisted != acceptance:
        raise ClaimReviewConflict("claim review acceptance already exists with another command")
    return persisted


def reverse_claim_review(
    acceptance: ClaimReviewAcceptance,
    *,
    acceptance_receipt_sha256: str,
    rationale: str,
    mutation_key: str,
    store: EngagementStore,
) -> ClaimReviewReversal:
    if acceptance_receipt_sha256 != acceptance.receipt_sha256:
        raise ClaimReviewConflict("claim review acceptance receipt is stale")
    cleaned_rationale = _clean_command(
        rationale, field="reversal rationale", max_bytes=MAX_RATIONALE_BYTES
    )
    cleaned_key = _clean_command(mutation_key, field="mutation key", max_bytes=512)
    request = {
        "acceptance_receipt_sha256": acceptance.receipt_sha256,
        "rationale_sha256": _sha(cleaned_rationale),
        "mutation_key_sha256": _sha(cleaned_key),
    }
    payload = {
        "schema_version": 1,
        "kind": "claim_challenge_reversal",
        "owner_account_digest": acceptance.owner_account_digest,
        "acceptance_receipt_sha256": acceptance.receipt_sha256,
        "rationale": cleaned_rationale,
        "rationale_sha256": request["rationale_sha256"],
        "mutation_key_sha256": request["mutation_key_sha256"],
        "request_sha256": _digest(request),
    }
    reversal = ClaimReviewReversal(**payload, receipt_sha256=_digest(payload))
    document_id = reversal_document_id(acceptance.receipt_sha256)
    row = {"kind": "claim_challenge_reversal", "reversal": reversal.model_dump()}
    if store.claim_document(document_id, row):
        return reversal
    existing = _strict_document(store, document_id)
    try:
        if (existing or {}).get("kind") != "claim_challenge_reversal":
            raise ValueError("claim review reversal kind mismatch")
        persisted = ClaimReviewReversal.model_validate((existing or {}).get("reversal"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored claim review reversal is corrupt") from exc
    if persisted.request_sha256 != reversal.request_sha256 or persisted != reversal:
        raise ClaimReviewConflict("claim review reversal already exists with another command")
    return persisted


def read_claim_review(
    challenge_receipt_sha256: str, *, store: EngagementStore
) -> tuple[ClaimReviewAcceptance | None, ClaimReviewReversal | None]:
    accepted_row = _strict_document(store, review_document_id(challenge_receipt_sha256))
    if accepted_row is None:
        return None, None
    try:
        if accepted_row.get("kind") != "claim_challenge_acceptance":
            raise ValueError("claim review acceptance kind mismatch")
        acceptance = ClaimReviewAcceptance.model_validate(accepted_row.get("acceptance"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored claim review acceptance is corrupt") from exc
    if acceptance.challenge_receipt_sha256 != challenge_receipt_sha256:
        raise RuntimeError("stored claim review acceptance lineage is corrupt")
    reversed_row = _strict_document(store, reversal_document_id(acceptance.receipt_sha256))
    if reversed_row is None:
        return acceptance, None
    try:
        if reversed_row.get("kind") != "claim_challenge_reversal":
            raise ValueError("claim review reversal kind mismatch")
        reversal = ClaimReviewReversal.model_validate(reversed_row.get("reversal"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored claim review reversal is corrupt") from exc
    if reversal.acceptance_receipt_sha256 != acceptance.receipt_sha256:
        raise RuntimeError("stored claim review reversal lineage is corrupt")
    return acceptance, reversal


def project_claim_reviews(
    *,
    source_asset_id: str,
    artifact_content_hash: str,
    artifact_account_digest: str,
    artifact_investigation_digest: str,
    claim_index: int,
    claim_id: str,
    claim_sha256: str,
    evaluation_event_id: str,
    scorer_id: str,
    relation: str | None,
    score: float,
    evidence_receipt_sha256s: tuple[str, ...],
    owner_account_digest: str,
    engagement_store: EngagementStore,
    session_store: SessionStore,
) -> tuple[ClaimReviewProjection, ...]:
    rows = engagement_store.list_spawns(source_asset_id)
    if len(rows) > 1000:
        raise RuntimeError("claim review projection spawn bound exceeded")
    projected: list[ClaimReviewProjection] = []
    for spawn_row in rows:
        spawn_id = spawn_row.get("spawn_id")
        if not isinstance(spawn_id, str) or not spawn_id:
            raise RuntimeError("claim review projection spawn identity is corrupt")
        strict_spawn = getattr(engagement_store, "get_spawn_strict", None)
        spawn_row = (
            strict_spawn(spawn_id)
            if callable(strict_spawn)
            else engagement_store.get_spawn(spawn_id)
        )
        if spawn_row is None:
            raise RuntimeError("claim review projection spawn disappeared")
        raw_challenge = spawn_row.get("claim_challenge")
        if raw_challenge is None:
            continue
        # Relevance is decided from the untrusted envelope before strict parsing so
        # stale versions and foreign assets cannot make the current projection fail.
        # Once an envelope claims this exact artifact, every field is validated and
        # malformed or foreign-owner state fails closed below.
        if not isinstance(raw_challenge, dict):
            continue
        if (
            raw_challenge.get("source_asset_id") != source_asset_id
            or raw_challenge.get("artifact_content_hash") != artifact_content_hash
        ):
            continue
        challenge = parse_claim_challenge_receipt(
            raw_challenge,
            expected_owner_account_digest=owner_account_digest,
        )
        assert challenge is not None
        if (
            challenge.source_asset_id != source_asset_id
            or challenge.artifact_content_hash != artifact_content_hash
            or challenge.claim_index != claim_index
            or challenge.claim_id != claim_id
            or challenge.claim_sha256 != claim_sha256
        ):
            continue
        if (
            challenge.evaluation_event_id != evaluation_event_id
            or challenge.scorer_id != scorer_id
            or challenge.relation != relation
            or challenge.score != score
            or challenge.evidence_receipt_sha256s != evidence_receipt_sha256s
        ):
            continue
        acceptance, reversal = read_claim_review(
            challenge.receipt_sha256, store=engagement_store
        )
        if acceptance is None:
            continue
        session_row = session_store.get_session(acceptance.session_id)
        if session_row is None:
            raise RuntimeError("claim review session lineage is unavailable")
        candidate = resolve_claim_review_candidate(
            session_row=session_row,
            spawn_row=spawn_row,
            owner_account_digest=owner_account_digest,
        )
        if (
            acceptance.owner_account_digest != owner_account_digest
            or acceptance.artifact_account_digest != artifact_account_digest
            or acceptance.artifact_investigation_digest != artifact_investigation_digest
            or acceptance.source_asset_id != source_asset_id
            or acceptance.artifact_content_hash != artifact_content_hash
            or acceptance.challenge_receipt_sha256 != challenge.receipt_sha256
            or acceptance.session_id != candidate.session_id
            or acceptance.spawn_id != candidate.spawn_id
            or acceptance.candidate_sha256 != candidate.candidate_sha256
            or acceptance.candidate_text != candidate.candidate_text
        ):
            raise RuntimeError("claim review acceptance lineage is corrupt")
        projected.append(
            ClaimReviewProjection(
                status=(
                    "later_owner_reversed_counter_analysis"
                    if reversal is not None
                    else "later_owner_accepted_counter_analysis"
                ),
                challenge_receipt_sha256=challenge.receipt_sha256,
                acceptance_receipt_sha256=acceptance.receipt_sha256,
                reversal_receipt_sha256=(
                    reversal.receipt_sha256 if reversal is not None else None
                ),
                session_id=acceptance.session_id,
                spawn_id=acceptance.spawn_id,
                candidate_sha256=acceptance.candidate_sha256,
                candidate_text=acceptance.candidate_text,
                evaluation_event_id=challenge.evaluation_event_id,
                evidence_receipt_sha256s=challenge.evidence_receipt_sha256s,
            )
        )
    return tuple(sorted(projected, key=lambda item: item.acceptance_receipt_sha256))
