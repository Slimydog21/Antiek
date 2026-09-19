"""Strict read-only reasoning DAG projected from canonical completed rounds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from substrate.engagement_spine.store import EngagementStore
from substrate.floating_session.store import SessionStore

from .authority import ArtifactAuthority
from .effective_claim_iterations import (
    EffectiveClaimIteration,
    project_effective_claim_iterations,
)
from .recursive_round_context import (
    RecursiveRoundContextPackReceipt,
    recursive_context_row_from_iteration,
)
from .schema import ResearchArtifactBody


class ReasoningAncestryConflict(ValueError):
    """Canonical rounds and embedded recursive parents are inconsistent."""


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ReasoningAncestryNode:
    iteration: EffectiveClaimIteration
    parent_ordinals: tuple[int, ...]
    child_ordinals: tuple[int, ...]
    inherited_questions: tuple[str, ...]
    depth: int
    recursive_pack_receipt_sha256: str | None
    ancestry_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.iteration.ordinal,
            "transition_sha256": self.iteration.compensation.transition_sha256,
            "session_id": self.iteration.review.session_id,
            "spawn_id": self.iteration.review.spawn_id,
            "candidate_sha256": self.iteration.candidate.candidate_sha256,
            "parent_ordinals": list(self.parent_ordinals),
            "child_ordinals": list(self.child_ordinals),
            "inherited_questions": list(self.inherited_questions),
            "depth": self.depth,
            "is_root": not self.parent_ordinals,
            "is_recombination": len(self.parent_ordinals) > 1,
            "recursive_pack_receipt_sha256": self.recursive_pack_receipt_sha256,
            "ancestry_sha256": self.ancestry_sha256,
            "archive_grounded": False,
            "grants_authority": False,
            "permits_graph_admission": False,
            "permits_write": False,
            "permits_benchmark_feedback": False,
            "permits_publication": False,
            "permits_provider_call": False,
            "permits_spend": False,
        }


def project_reasoning_ancestry(
    *,
    body: ResearchArtifactBody,
    claim_index: int,
    authority: ArtifactAuthority,
    owner_account_digest: str,
    engagement_store: EngagementStore,
    session_store: SessionStore,
) -> tuple[ReasoningAncestryNode, ...]:
    """Reconstruct a bounded DAG; canonical round order is the sole root."""
    iterations = project_effective_claim_iterations(
        body=body,
        claim_index=claim_index,
        authority=authority,
        owner_account_digest=owner_account_digest,
        engagement_store=engagement_store,
        session_store=session_store,
    )
    by_ordinal = {item.ordinal: item for item in iterations}
    parents: dict[int, tuple[int, ...]] = {}
    questions: dict[int, tuple[str, ...]] = {}
    pack_receipts: dict[int, str | None] = {}
    for item in iterations:
        challenge = item.candidate.challenge
        if challenge.schema_version == 2:
            parents[item.ordinal] = ()
            questions[item.ordinal] = ()
            pack_receipts[item.ordinal] = None
            continue
        if challenge.schema_version != 3 or challenge.recursive_context_pack is None:
            raise ReasoningAncestryConflict("reasoning ancestry challenge is unsupported")
        try:
            pack = RecursiveRoundContextPackReceipt.model_validate(
                challenge.recursive_context_pack
            )
        except (TypeError, ValueError) as exc:
            raise ReasoningAncestryConflict("reasoning ancestry pack is corrupt") from exc
        selected = pack.selected_ordinals
        if any(parent >= item.ordinal for parent in selected):
            raise ReasoningAncestryConflict("reasoning ancestry edge is not historical")
        if len(set(selected)) != len(selected):
            raise ReasoningAncestryConflict("reasoning ancestry parent is duplicated")
        for embedded_row in pack.rows:
            parent = by_ordinal.get(embedded_row.ordinal)
            if parent is None or recursive_context_row_from_iteration(parent) != embedded_row:
                raise ReasoningAncestryConflict("reasoning ancestry parent row is stale")
        if (
            pack.artifact_content_hash != item.prior_body.content_hash()
            or pack.claim_index != claim_index
            or pack.current_effective_claim
            != item.compensation.prior_effective_claim
            or pack.current_head_transition_sha256
            != item.candidate.challenge.head_transition_sha256
        ):
            raise ReasoningAncestryConflict("reasoning ancestry child context is stale")
        parents[item.ordinal] = selected
        questions[item.ordinal] = pack.follow_up_questions
        pack_receipts[item.ordinal] = pack.receipt_sha256
    children: dict[int, list[int]] = {ordinal: [] for ordinal in by_ordinal}
    for child, selected in parents.items():
        for parent in selected:
            if parent not in children:
                raise ReasoningAncestryConflict("reasoning ancestry parent is missing")
            children[parent].append(child)
    depths: dict[int, int] = {}
    ancestry_digests: dict[int, str] = {}
    nodes: list[ReasoningAncestryNode] = []
    for item in iterations:
        ordinal = item.ordinal
        selected = parents[ordinal]
        depth = 0 if not selected else max(depths[parent] for parent in selected) + 1
        identity = {
            "ordinal": ordinal,
            "transition_sha256": item.compensation.transition_sha256,
            "parent_ordinals": list(selected),
            "parent_ancestry_sha256s": [ancestry_digests[parent] for parent in selected],
            "inherited_questions": list(questions[ordinal]),
            "recursive_pack_receipt_sha256": pack_receipts[ordinal],
            "depth": depth,
        }
        ancestry_sha256 = _digest(identity)
        depths[ordinal] = depth
        ancestry_digests[ordinal] = ancestry_sha256
        nodes.append(
            ReasoningAncestryNode(
                iteration=item,
                parent_ordinals=selected,
                child_ordinals=tuple(children[ordinal]),
                inherited_questions=questions[ordinal],
                depth=depth,
                recursive_pack_receipt_sha256=pack_receipts[ordinal],
                ancestry_sha256=ancestry_sha256,
            )
        )
    return tuple(nodes)
