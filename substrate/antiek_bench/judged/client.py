"""Typed judge client boundary and evidence persistence.

The JudgeClient protocol accepts blinded requests and returns schema-validated
axis scores.  The caller persists only scores, evidence hashes, timing, and
fixed failure codes — never prompt/response bodies, candidate identities, or
secrets.  JudgeClient has no dispatch, model-selection, or install authority.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Protocol, runtime_checkable

from .blinding import BlindedJudgeRequest
from .journal import JudgeEvidenceJournal, JudgeEvidenceRecord
from .rubric import AxisScore, JudgeResult, RubricVersion, validate_scores


@runtime_checkable
class JudgeClient(Protocol):
    """Injected judge that scores blinded candidates on a rubric.

    The caller owns the blinding, journal, and evidence persistence.  The
    client owns only the inference call.  It has no authority over dispatch,
    model selection, or budget.
    """

    def score(
        self, request: BlindedJudgeRequest, rubric: RubricVersion
    ) -> JudgeResult: ...


def _evidence_hash(axis_scores: tuple[AxisScore, ...]) -> str:
    """Deterministic hash of axis scores for evidence integrity."""
    material = json.dumps(
        [{"axis": s.axis, "score": s.score, "rationale": s.rationale} for s in axis_scores],
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


def score_and_persist(
    *,
    request: BlindedJudgeRequest,
    rubric: RubricVersion,
    client: JudgeClient,
    journal: JudgeEvidenceJournal,
    week_id: str,
    suite_version: str,
    judge_model: str,
    stale_ttl_ms: int = 600_000,
    now_ms: int | None = None,
) -> JudgeEvidenceRecord | None:
    """Score a blinded request and persist evidence to the journal.

    The claim/settle protocol prevents concurrent duplicate external calls:
    - claim() checks for an existing claim_id atomically
    - Only the first claim proceeds to call the judge
    - Settlement persists only scores, hashes, timing, and failure codes

    Returns the settled record, or None if the claim was a duplicate.
    """
    candidate_a, candidate_b = request.candidates
    cid = JudgeEvidenceRecord(
        week_id=week_id,
        suite_version=suite_version,
        item_id=request.item_id,
        rubric_version=rubric.version,
        judge_model=judge_model,
        blinded_candidate_a=candidate_a.blinded_id,
        blinded_candidate_b=candidate_b.blinded_id,
        status="pending",
    ).computed_claim_id

    # Attempt to claim.  If the claim_id already exists, this is a duplicate.
    pending = JudgeEvidenceRecord(
        week_id=week_id,
        suite_version=suite_version,
        item_id=request.item_id,
        rubric_version=rubric.version,
        judge_model=judge_model,
        blinded_candidate_a=candidate_a.blinded_id,
        blinded_candidate_b=candidate_b.blinded_id,
        status="pending",
    )
    if not journal.claim(pending):
        return None  # duplicate claim; caller must not make external call

    start_ms = int(time.time() * 1000) if now_ms is None else now_ms
    try:
        result = client.score(request, rubric)
        elapsed = max(0, int(time.time() * 1000) - start_ms) if now_ms is None else result.latency_ms

        # Judge-reported failure takes precedence over schema validation:
        # if the judge already signalled failure, persist that signal.
        if result.failure_code:
            settled = JudgeEvidenceRecord(
                week_id=week_id,
                suite_version=suite_version,
                item_id=request.item_id,
                rubric_version=rubric.version,
                judge_model=judge_model,
                blinded_candidate_a=candidate_a.blinded_id,
                blinded_candidate_b=candidate_b.blinded_id,
                status="failed",
                latency_ms=elapsed,
                failure_code=result.failure_code,
            )
        else:
            # Validate scores against rubric before persisting.
            errors = validate_scores(rubric, result.axis_scores)
            if errors:
                settled = JudgeEvidenceRecord(
                    week_id=week_id,
                    suite_version=suite_version,
                    item_id=request.item_id,
                    rubric_version=rubric.version,
                    judge_model=judge_model,
                    blinded_candidate_a=candidate_a.blinded_id,
                    blinded_candidate_b=candidate_b.blinded_id,
                    status="schema_error",
                    latency_ms=elapsed,
                    failure_code="; ".join(errors),
                )
            else:
                settled = JudgeEvidenceRecord(
                    week_id=week_id,
                    suite_version=suite_version,
                    item_id=request.item_id,
                    rubric_version=rubric.version,
                    judge_model=judge_model,
                    blinded_candidate_a=candidate_a.blinded_id,
                    blinded_candidate_b=candidate_b.blinded_id,
                    status="scored",
                    axis_scores_json=json.dumps(
                        [s.__dict__ for s in result.axis_scores],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    evidence_hash=_evidence_hash(result.axis_scores),
                    latency_ms=elapsed,
                )
    except TimeoutError:
        elapsed = max(0, int(time.time() * 1000) - start_ms) if now_ms is None else 0
        settled = JudgeEvidenceRecord(
            week_id=week_id,
            suite_version=suite_version,
            item_id=request.item_id,
            rubric_version=rubric.version,
            judge_model=judge_model,
            blinded_candidate_a=candidate_a.blinded_id,
            blinded_candidate_b=candidate_b.blinded_id,
            status="timeout",
            latency_ms=elapsed,
            failure_code="judge_timeout",
        )
    except Exception:
        elapsed = max(0, int(time.time() * 1000) - start_ms) if now_ms is None else 0
        settled = JudgeEvidenceRecord(
            week_id=week_id,
            suite_version=suite_version,
            item_id=request.item_id,
            rubric_version=rubric.version,
            judge_model=judge_model,
            blinded_candidate_a=candidate_a.blinded_id,
            blinded_candidate_b=candidate_b.blinded_id,
            status="failed",
            latency_ms=elapsed,
            failure_code="judge_failure",
        )

    if not journal.settle(settled, stale_ttl_ms=stale_ttl_ms):
        # Settlement failed: the claim went stale or was already settled.
        existing = journal.lookup(cid)
        return existing if existing is not None else settled
    return settled
