"""Evidence Retriever environment — verifier-shaped scaffold."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from skills.verification.rubric import VERIFIABLE, RubricResult  # noqa: E402
from substrate.schemas import EvidenceRetrieveDeliveredPayload  # noqa: E402


@dataclass
class EvidenceRetrieverTask:
    task_id: str
    sub_question: str
    category: str = "technology_risk"
    evidence_type_required: str = "quantitative"
    chunks_block: str = ""
    subgraph_block: str = ""
    canonical_chunk_ids: list[str] = field(default_factory=list)
    canonical_edge_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceRetrieverRollout:
    task: EvidenceRetrieverTask
    raw_output: str
    parsed_output: dict[str, Any] | None
    policy_id: str
    error: str | None = None


@dataclass
class EvidenceRetrieverReward:
    total: float
    passed_all_verifiable: bool
    breakdown: list[RubricResult] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)


PolicyFn = Callable[["EvidenceRetrieverTask", dict[str, Any]], tuple[str, str]]


class EvidenceRetrieverEnvironment:
    """Verifier-shaped environment for the Evidence Retriever role."""

    DEFAULT_WEIGHTS: dict[str, float] = {
        "verifiable.evidence_retriever.schema_validity": 0.30,
        "verifiable.evidence_retriever.sub_question_echo": 0.20,
        "verifiable.evidence_retriever.claim_citations": 0.25,
        "verifiable.evidence_retriever.insufficient_evidence_coherence": 0.15,
        # 10% headroom for judged evidence quality.
    }

    def __init__(
        self,
        policy_fn: PolicyFn | None = None,
        tasks: list[EvidenceRetrieverTask] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.policy_fn = policy_fn
        self._tasks = list(tasks or [])
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self._extra_rubrics: list[Any] = []

    def add_task(self, task: EvidenceRetrieverTask) -> None:
        self._tasks.append(task)

    def tasks(self) -> list[EvidenceRetrieverTask]:
        return list(self._tasks)

    def rollout(self, task: EvidenceRetrieverTask) -> EvidenceRetrieverRollout:
        if self.policy_fn is None:
            raise RuntimeError(
                "EvidenceRetrieverEnvironment.rollout: no policy_fn provided. "
                "Inject one when constructing the env."
            )
        raw, policy_id = self.policy_fn(task, {"task_id": task.task_id})
        parsed: dict[str, Any] | None = None
        err: str | None = None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            err = f"json parse failed: {exc!r}"
        return EvidenceRetrieverRollout(
            task=task,
            raw_output=raw,
            parsed_output=parsed,
            policy_id=policy_id,
            error=err,
        )

    def reward(
        self,
        rollout: EvidenceRetrieverRollout,
    ) -> EvidenceRetrieverReward:
        breakdown: list[RubricResult] = []

        schema_ok = False
        schema_error = rollout.error
        if rollout.parsed_output is not None and rollout.error is None:
            try:
                EvidenceRetrieveDeliveredPayload.model_validate(
                    rollout.parsed_output,
                )
            except Exception as exc:
                schema_error = repr(exc)
            else:
                schema_ok = True
        breakdown.append(_result(
            "verifiable.evidence_retriever.schema_validity",
            schema_ok,
            rollout.policy_id,
            {"parse_error": schema_error},
        ))

        breakdown.append(_score_sub_question_echo(rollout))
        breakdown.append(_score_claim_citations(rollout))
        breakdown.append(_score_insufficient_evidence_coherence(rollout))

        for rubric in self._extra_rubrics:
            try:
                result = rubric.score(
                    rollout.parsed_output,
                    context={"task": rollout.task},
                )
            except Exception as exc:
                result = RubricResult(
                    rubric_id=getattr(rubric, "rubric_id", "unknown"),
                    kind=getattr(rubric, "kind", VERIFIABLE),
                    score=0.0,
                    passed=False,
                    details={"scoring_error": repr(exc)},
                    policy_id_scored=rollout.policy_id,
                )
            else:
                result.policy_id_scored = rollout.policy_id
            breakdown.append(result)

        total = 0.0
        used_weight = 0.0
        for result in breakdown:
            weight = self.weights.get(result.rubric_id, 0.0)
            total += weight * result.score
            used_weight += weight
        if used_weight > 0:
            total = total / used_weight

        verifiable_passed = all(
            result.passed
            for result in breakdown
            if result.kind == VERIFIABLE and result.passed is not None
        )
        return EvidenceRetrieverReward(
            total=total,
            passed_all_verifiable=verifiable_passed,
            breakdown=breakdown,
            weights=dict(self.weights),
        )

    def add_rubric(self, rubric: Any, *, weight: float = 0.0) -> None:
        self._extra_rubrics.append(rubric)
        if weight:
            self.weights[rubric.rubric_id] = weight


def _result(
    rubric_id: str,
    passed: bool,
    policy_id: str,
    details: dict[str, Any],
) -> RubricResult:
    return RubricResult(
        rubric_id=rubric_id,
        kind=VERIFIABLE,
        score=1.0 if passed else 0.0,
        passed=passed,
        details=details,
        policy_id_scored=policy_id,
    )


def _claims(parsed: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        claim
        for claim in (parsed or {}).get("supporting_claims", []) or []
        if isinstance(claim, dict)
    ]


def _score_sub_question_echo(rollout: EvidenceRetrieverRollout) -> RubricResult:
    actual = (rollout.parsed_output or {}).get("sub_question")
    passed = actual == rollout.task.sub_question
    return _result(
        "verifiable.evidence_retriever.sub_question_echo",
        passed,
        rollout.policy_id,
        {
            "expected_sub_question": rollout.task.sub_question,
            "actual_sub_question": actual,
        },
    )


def _score_claim_citations(rollout: EvidenceRetrieverRollout) -> RubricResult:
    claims = _claims(rollout.parsed_output)
    canonical_chunks = set(rollout.task.canonical_chunk_ids)
    canonical_edges = set(rollout.task.canonical_edge_ids)
    uncited: list[str] = []
    invalid_chunks: list[str] = []
    invalid_edges: list[str] = []
    for claim in claims:
        claim_text = str(claim.get("claim") or "<unknown>")
        chunks = claim.get("chunk_ids") or []
        edges = claim.get("edge_ids") or []
        if claim.get("evidence_type") != "gap" and not chunks:
            uncited.append(claim_text)
        if canonical_chunks:
            invalid_chunks.extend(str(ref) for ref in chunks if ref not in canonical_chunks)
        if canonical_edges:
            invalid_edges.extend(str(ref) for ref in edges if ref not in canonical_edges)
    passed = bool(claims) and not uncited and not invalid_chunks and not invalid_edges
    if (rollout.parsed_output or {}).get("insufficient_evidence"):
        passed = not invalid_chunks and not invalid_edges
    return _result(
        "verifiable.evidence_retriever.claim_citations",
        passed,
        rollout.policy_id,
        {
            "n_claims": len(claims),
            "uncited_claims": uncited,
            "invalid_chunk_refs": invalid_chunks,
            "invalid_edge_refs": invalid_edges,
        },
    )


def _score_insufficient_evidence_coherence(
    rollout: EvidenceRetrieverRollout,
) -> RubricResult:
    parsed = rollout.parsed_output or {}
    insufficient = bool(parsed.get("insufficient_evidence"))
    claims = _claims(parsed)
    gaps = parsed.get("evidentiary_gaps") or []
    passed = not claims and bool(gaps) if insufficient else bool(claims)
    return _result(
        "verifiable.evidence_retriever.insufficient_evidence_coherence",
        passed,
        rollout.policy_id,
        {
            "insufficient_evidence": insufficient,
            "n_claims": len(claims),
            "n_gaps": len(gaps),
        },
    )


__all__ = [
    "EvidenceRetrieverEnvironment",
    "EvidenceRetrieverReward",
    "EvidenceRetrieverRollout",
    "EvidenceRetrieverTask",
]
