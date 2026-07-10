"""Typed, authority-free qualitative judge boundary."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, runtime_checkable

from .blinding import BlindedJudgeRequest
from .journal import JudgeEvidenceJournal, JudgeEvidenceRecord, JudgeStatus
from .rubric import AxisScore, JudgeResult, RubricVersion, validate_scores


class JudgeReconciliationRequiredError(RuntimeError):
    """A prior judge call may have completed without durable settlement."""


@runtime_checkable
class JudgeClient(Protocol):
    def score(self, request: BlindedJudgeRequest, rubric: RubricVersion) -> JudgeResult: ...


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _persisted_scores(axis_scores: tuple[AxisScore, ...]) -> str:
    return json.dumps(
        [
            {
                "axis": score.axis,
                "score": score.score,
                "rationale_hash": _hash(score.rationale),
            }
            for score in axis_scores
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _evidence_hash(axis_scores: tuple[AxisScore, ...]) -> str:
    return _hash(_persisted_scores(axis_scores))


def _record(
    *,
    request: BlindedJudgeRequest,
    rubric: RubricVersion,
    week_id: str,
    suite_version: str,
    judge_model: str,
    status: JudgeStatus,
    latency_ms: int = 0,
    failure_code: str = "",
    scores: tuple[AxisScore, ...] = (),
) -> JudgeEvidenceRecord:
    candidate_a, candidate_b = request.candidates
    return JudgeEvidenceRecord(
        week_id=week_id,
        suite_version=suite_version,
        item_id=request.item_id,
        rubric_version=rubric.version,
        judge_model=judge_model,
        blinded_candidate_a=candidate_a.blinded_id,
        blinded_candidate_b=candidate_b.blinded_id,
        task_class=request.task_class,
        task_context_hash=_hash(request.task_context),
        rubric_fingerprint=rubric.fingerprint,
        candidate_a_hash=candidate_a.content_binding,
        candidate_b_hash=candidate_b.content_binding,
        status=status,
        axis_scores_json=_persisted_scores(scores) if scores else "",
        evidence_hash=_evidence_hash(scores) if scores else "",
        latency_ms=latency_ms,
        failure_code=failure_code,
    )


def score_and_persist(
    *,
    request: BlindedJudgeRequest,
    rubric: RubricVersion,
    client: JudgeClient,
    journal: JudgeEvidenceJournal,
    week_id: str,
    suite_version: str,
    judge_model: str,
    candidate_models: tuple[str, str],
) -> JudgeEvidenceRecord:
    """Claim, score, validate, and settle one exact blinded evaluation."""
    if request.rubric_version != rubric.version:
        raise ValueError("request and rubric versions differ")
    if request.task_class != rubric.task_class:
        raise ValueError("request and rubric task classes differ")
    if len(candidate_models) != 2 or len(set(candidate_models)) != 2:
        raise ValueError("exactly two distinct candidate models required")
    if judge_model in candidate_models:
        raise ValueError("candidate models may not judge themselves")

    pending = _record(
        request=request,
        rubric=rubric,
        week_id=week_id,
        suite_version=suite_version,
        judge_model=judge_model,
        status="pending",
    )
    if not journal.claim(pending):
        existing = journal.lookup(pending.computed_claim_id)
        if existing is None:
            raise RuntimeError("judge claim disappeared after duplicate detection")
        if existing.status == "pending":
            raise JudgeReconciliationRequiredError(existing.computed_claim_id)
        return existing

    try:
        result = client.score(request, rubric)
    except TimeoutError:
        settled = _record(
            request=request,
            rubric=rubric,
            week_id=week_id,
            suite_version=suite_version,
            judge_model=judge_model,
            status="timeout",
            failure_code="judge_timeout",
        )
    except Exception:
        settled = _record(
            request=request,
            rubric=rubric,
            week_id=week_id,
            suite_version=suite_version,
            judge_model=judge_model,
            status="failed",
            failure_code="judge_failure",
        )
    else:
        if result.failure_code:
            settled = _record(
                request=request,
                rubric=rubric,
                week_id=week_id,
                suite_version=suite_version,
                judge_model=judge_model,
                status="failed",
                latency_ms=result.latency_ms,
                failure_code=result.failure_code,
            )
        else:
            errors = validate_scores(rubric, result.axis_scores)
            if errors:
                settled = _record(
                    request=request,
                    rubric=rubric,
                    week_id=week_id,
                    suite_version=suite_version,
                    judge_model=judge_model,
                    status="schema_error",
                    latency_ms=result.latency_ms,
                    failure_code="invalid_judge_schema",
                )
            else:
                settled = _record(
                    request=request,
                    rubric=rubric,
                    week_id=week_id,
                    suite_version=suite_version,
                    judge_model=judge_model,
                    status="scored",
                    latency_ms=result.latency_ms,
                    scores=result.axis_scores,
                )

    if not journal.settle(settled):
        raise JudgeReconciliationRequiredError(pending.computed_claim_id)
    return settled
