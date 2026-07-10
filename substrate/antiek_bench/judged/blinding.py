"""Build judge inputs without revealing candidate routing identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..suite import TaskClass
from .rubric import Rubric, rubric_for


def _hash(salt: str, value: str) -> str:
    return "sha256:" + hashlib.sha256(f"{salt}\0{value}".encode()).hexdigest()


@dataclass(frozen=True)
class CandidateArtifact:
    content: str
    model_id: str
    provider_id: str = ""
    route_receipt_id: str = ""
    api_key: str = ""


@dataclass(frozen=True)
class BlindedCandidate:
    label: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class JudgeRequest:
    item_id_hash: str
    task_class: TaskClass
    task_context: str
    rubric: Rubric
    candidates: tuple[BlindedCandidate, BlindedCandidate]


@dataclass(frozen=True)
class PrivateCandidateBinding:
    """Private identity seam; response_hash is raw hex, blinded hash is prefixed."""

    label: str
    provider_id: str
    model_id: str
    response_hash: str
    blinded_candidate_hash: str


@dataclass(frozen=True)
class PrivateJoin:
    """Ephemeral mapping only; never send to a judge or public projection."""

    labels_to_candidates: tuple[PrivateCandidateBinding, PrivateCandidateBinding]


def blind_candidates(
    *,
    item_id: str,
    task_class: TaskClass,
    candidates: tuple[CandidateArtifact, CandidateArtifact],
    salt: str,
    task_context: str = "Qualitatively assess the two candidate artifacts.",
) -> tuple[JudgeRequest, PrivateJoin]:
    if not salt:
        raise ValueError("blinding salt is required")
    if len({candidate.model_id for candidate in candidates}) != 2:
        raise ValueError("candidate models must be distinct")
    if not task_context.strip() or len(task_context) > 2_000:
        raise ValueError("sanitized task_context must contain 1..2000 characters")
    hashes = tuple(_hash(salt, candidate.content) for candidate in candidates)
    swap_material = json.dumps([item_id, task_class, *hashes], separators=(",", ":"))
    order = (1, 0) if hashlib.sha256(f"{salt}:{swap_material}".encode()).digest()[0] & 1 else (0, 1)
    blinded = (
        BlindedCandidate("A", candidates[order[0]].content, hashes[order[0]]),
        BlindedCandidate("B", candidates[order[1]].content, hashes[order[1]]),
    )
    joins = (
        PrivateCandidateBinding(
            "A",
            candidates[order[0]].provider_id,
            candidates[order[0]].model_id,
            hashlib.sha256(candidates[order[0]].content.encode()).hexdigest(),
            hashes[order[0]],
        ),
        PrivateCandidateBinding(
            "B",
            candidates[order[1]].provider_id,
            candidates[order[1]].model_id,
            hashlib.sha256(candidates[order[1]].content.encode()).hexdigest(),
            hashes[order[1]],
        ),
    )
    return (
        JudgeRequest(
            _hash(salt, item_id), task_class, task_context, rubric_for(task_class), blinded
        ),
        PrivateJoin(joins),
    )
