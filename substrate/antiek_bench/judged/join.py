"""Operator-private binding between live calls and blinded judge evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass, replace

from ..live.journal import LiveCallRecord
from .blinding import PrivateJoin
from .journal import EvidenceRecord
from .runner import JUDGE_POLICY_VERSION

PRIVATE_JOIN_SCHEMA_VERSION = 1
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class PrivateResponseBinding:
    label: str
    live_call_id: str
    provider_id: str
    model_id: str
    live_response_hash: str
    blinded_candidate_hash: str


@dataclass(frozen=True)
class PrivateJoinEnvelope:
    week_id: str
    suite_version: str
    item_id: str
    task_class: str
    prompt_hash: str
    evidence_id: str
    evidence_item_id_hash: str
    judge_model: str
    rubric_fingerprint: str
    judge_policy_version: str
    bindings: tuple[PrivateResponseBinding, PrivateResponseBinding]
    signature: str = ""
    schema_version: int = PRIVATE_JOIN_SCHEMA_VERSION

    def signing_payload(self) -> bytes:
        # Retain the field name with an empty value so the complete schema is signed.
        data = asdict(replace(self, signature=""))
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    @property
    def public_digest(self) -> str:
        """Provenance reference only; integrity requires ``verify_private_join``."""
        return "sha256:" + hashlib.sha256(self.signing_payload()).hexdigest()


@dataclass(frozen=True)
class VerifiedJudgedJoin:
    """Public-safe result; contains no provider/model join mapping."""

    envelope_digest: str
    evidence_id: str
    week_id: str
    suite_version: str
    item_id: str
    task_class: str
    prompt_hash: str
    rubric_fingerprint: str
    judge_model: str
    schema_version: int = 1


def seal_private_join(
    *,
    evidence: EvidenceRecord,
    private_join: PrivateJoin,
    live_records: tuple[LiveCallRecord, LiveCallRecord],
    item_id: str,
    prompt_hash: str,
    signing_key: bytes,
) -> PrivateJoinEnvelope:
    """Create a keyed envelope while physical identity is still available.

    ``evidence.item_id_hash`` is intentionally salted and cannot be recomputed
    from ``item_id`` after the blinding salt is discarded. Exact item identity
    is instead proven by the HMAC envelope plus the matched live call contract.
    """
    if len(signing_key) < 32:
        raise ValueError("private join signing key must contain at least 32 bytes")
    by_identity = {
        (row.actual_provider, row.actual_model, row.response_hash): row for row in live_records
    }
    bindings: list[PrivateResponseBinding] = []
    for candidate in private_join.labels_to_candidates:
        row = by_identity.get((candidate.provider_id, candidate.model_id, candidate.response_hash))
        if row is None:
            raise ValueError("private candidate does not match an exact live response")
        bindings.append(
            PrivateResponseBinding(
                label=candidate.label,
                live_call_id=row.call_id,
                provider_id=candidate.provider_id,
                model_id=candidate.model_id,
                live_response_hash=candidate.response_hash,
                blinded_candidate_hash=candidate.blinded_candidate_hash,
            )
        )
    envelope = PrivateJoinEnvelope(
        week_id=evidence.week_id,
        suite_version=evidence.suite_version,
        item_id=item_id,
        task_class=evidence.task_class,
        prompt_hash=prompt_hash,
        evidence_id=evidence.evidence_id,
        evidence_item_id_hash=evidence.item_id_hash,
        judge_model=evidence.judge_model,
        rubric_fingerprint=evidence.rubric_fingerprint,
        judge_policy_version=JUDGE_POLICY_VERSION,
        bindings=(bindings[0], bindings[1]),
    )
    signature = hmac.new(signing_key, envelope.signing_payload(), hashlib.sha256).hexdigest()
    return replace(envelope, signature="hmac-sha256:" + signature)


def verify_private_join(
    *,
    envelope: PrivateJoinEnvelope,
    evidence: EvidenceRecord,
    live_records: tuple[LiveCallRecord, LiveCallRecord],
    signing_key: bytes,
) -> VerifiedJudgedJoin:
    """Fail closed unless every private and public evidence seam matches exactly."""
    if envelope.schema_version != PRIVATE_JOIN_SCHEMA_VERSION:
        raise ValueError("unsupported private join schema")
    if len(signing_key) < 32:
        raise ValueError("private join signing key must contain at least 32 bytes")
    expected_signature = (
        "hmac-sha256:"
        + hmac.new(signing_key, envelope.signing_payload(), hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(envelope.signature, expected_signature):
        raise ValueError("private join signature does not match")
    if (
        envelope.week_id,
        envelope.suite_version,
        envelope.task_class,
        envelope.evidence_id,
        envelope.evidence_item_id_hash,
        envelope.judge_model,
        envelope.rubric_fingerprint,
        envelope.judge_policy_version,
    ) != (
        evidence.week_id,
        evidence.suite_version,
        evidence.task_class,
        evidence.evidence_id,
        evidence.item_id_hash,
        evidence.judge_model,
        evidence.rubric_fingerprint,
        JUDGE_POLICY_VERSION,
    ):
        raise ValueError("private join does not match judged evidence")
    if not _PREFIXED_SHA256.fullmatch(envelope.prompt_hash):
        raise ValueError("prompt_hash must be an exact SHA-256 reference")
    if tuple(binding.label for binding in envelope.bindings) != evidence.blinded_order:
        raise ValueError("private join label order does not match evidence")
    if tuple(binding.blinded_candidate_hash for binding in envelope.bindings) != (
        evidence.candidate_hashes
    ):
        raise ValueError("private join candidate order does not match evidence")
    if len({binding.model_id for binding in envelope.bindings}) != 2:
        raise ValueError("private join candidate models must be distinct")
    rows_by_id = {row.call_id: row for row in live_records}
    if len(rows_by_id) != 2:
        raise ValueError("private join requires exactly two distinct live calls")
    for binding in envelope.bindings:
        row = rows_by_id.get(binding.live_call_id)
        if row is None or row.status != "ok":
            raise ValueError("private join live call is missing or unsuccessful")
        if (
            row.week_id,
            row.suite_version,
            row.item_id,
            row.task_class,
            row.prompt_hash,
            row.actual_provider,
            row.actual_model,
            row.response_hash,
        ) != (
            envelope.week_id,
            envelope.suite_version,
            envelope.item_id,
            envelope.task_class,
            envelope.prompt_hash,
            binding.provider_id,
            binding.model_id,
            binding.live_response_hash,
        ):
            raise ValueError("private join live call contract does not match")
        if _HEX_SHA256.fullmatch(binding.live_response_hash) is None:
            raise ValueError("live response hash must be an exact SHA-256 digest")
        if _PREFIXED_SHA256.fullmatch(binding.blinded_candidate_hash) is None:
            raise ValueError("blinded candidate hash must be an exact SHA-256 reference")
    return VerifiedJudgedJoin(
        envelope_digest=envelope.public_digest,
        evidence_id=evidence.evidence_id,
        week_id=evidence.week_id,
        suite_version=evidence.suite_version,
        item_id=envelope.item_id,
        task_class=evidence.task_class,
        prompt_hash=envelope.prompt_hash,
        rubric_fingerprint=evidence.rubric_fingerprint,
        judge_model=evidence.judge_model,
    )
