"""Injected, advisory-only boundary for collecting blinded judge evidence."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ..suite import TaskClass
from .blinding import CandidateArtifact, JudgeRequest, PrivateJoin, blind_candidates
from .journal import EvidenceJournal, EvidenceRecord
from .rubric import AxisJudgment, validate_judgments

JUDGE_POLICY_VERSION = "blinded-pair-v1"
JUDGE_RESPONSE_SCHEMA_VERSION = 1


class ReconciliationRequiredError(RuntimeError):
    """A durable claim exists without a settlement and must not be retried."""


@dataclass(frozen=True)
class JudgeResponse:
    rubric_version: str
    judgments: Mapping[str, AxisJudgment]
    schema_version: int = JUDGE_RESPONSE_SCHEMA_VERSION


class JudgeClient(Protocol):
    def judge(self, request: JudgeRequest) -> JudgeResponse: ...


@dataclass(frozen=True)
class JudgeRunResult:
    evidence: EvidenceRecord
    private_join: PrivateJoin


def collect_judge_evidence(
    *,
    enabled: bool,
    week_id: str,
    suite_version: str,
    item_id: str,
    task_context: str,
    task_class: TaskClass,
    candidates: tuple[CandidateArtifact, CandidateArtifact],
    judge_model: str,
    salt: str,
    client: JudgeClient,
    journal: EvidenceJournal,
    now_ms: int | None = None,
) -> JudgeRunResult | None:
    """Collect evidence once; this function has no dispatch or routing authority."""
    if not enabled:
        return None
    if not judge_model.strip():
        raise ValueError("judge_model is required")
    canonical_judge = judge_model.strip().casefold()
    if canonical_judge in {candidate.model_id.strip().casefold() for candidate in candidates}:
        raise ValueError("a candidate model may not judge its own output")
    request, private_join = blind_candidates(
        item_id=item_id,
        task_class=task_class,
        candidates=candidates,
        salt=salt,
        task_context=task_context,
    )
    current_ms = int(time.time() * 1_000) if now_ms is None else now_ms
    candidate_hashes = (request.candidates[0].content_hash, request.candidates[1].content_hash)
    blinded_order = (request.candidates[0].label, request.candidates[1].label)

    def record(*, status: str, **values: object) -> EvidenceRecord:
        return EvidenceRecord(
            week_id=week_id,
            suite_version=suite_version,
            item_id_hash=request.item_id_hash,
            task_class=task_class,
            rubric_version=request.rubric.version,
            judge_model=judge_model.strip(),
            candidate_hashes=candidate_hashes,
            task_context_hash="sha256:" + hashlib.sha256(request.task_context.encode()).hexdigest(),
            rubric_fingerprint=request.rubric.fingerprint,
            blinded_order=blinded_order,
            status=status,  # type: ignore[arg-type]
            claimed_at_ms=current_ms,
            **values,  # type: ignore[arg-type]
        )

    pending = record(status="pending")
    if not journal.claim(pending):
        existing = journal.lookup(pending.evidence_id)
        if existing is not None and existing.status == "pending":
            raise ReconciliationRequiredError(f"unsettled judge claim: {pending.evidence_id}")
        if existing is None:
            raise ReconciliationRequiredError(f"missing claimed evidence: {pending.evidence_id}")
        return JudgeRunResult(existing, private_join)
    started = time.monotonic()
    try:
        response = client.judge(request)
        if response.schema_version != JUDGE_RESPONSE_SCHEMA_VERSION:
            raise ValueError("unsupported judge response schema")
        validate_judgments(request.rubric, response.rubric_version, response.judgments)
        scores = tuple((axis, response.judgments[axis].score) for axis in request.rubric.axes)
        refs = tuple((axis, response.judgments[axis].evidence_refs) for axis in request.rubric.axes)
        settled = record(
            status="ok",
            scores=scores,
            evidence_refs=refs,
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    except Exception:  # external details must never cross the persistence boundary
        settled = record(
            status="failed",
            failure_code="invalid_or_failed_response",
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    journal.settle(settled)
    return JudgeRunResult(settled, private_join)
