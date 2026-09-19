"""One strict resolver for immutable reasoning-ancestry interrogations.

The caller owns HTTP authorization and error classification. This resolver owns
the receipt -> selected artifact version -> ancestry -> collective-manifest
parity chain so private reads, workspace continuity, and paid continuation
cannot drift into separate interpretations.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.collective_manifest import CollectiveManifest
from substrate.engagement_spine.store import AuthorizedEngagementStore
from substrate.floating_session.store import SessionStore

from .authority import ArtifactAuthority
from .import_notes import parse_body_from_html
from .reasoning_ancestry import ReasoningAncestryNode, project_reasoning_ancestry
from .reasoning_ancestry_interrogation import (
    ReasoningAncestryInterrogationReceipt,
    read_reasoning_ancestry_interrogation,
    validate_reasoning_ancestry_interrogation,
)
from .schema import ResearchArtifactBody
from .storage import FilesystemArtifactStore


@dataclass(frozen=True)
class ResolvedReasoningAncestryInterrogation:
    receipt: ReasoningAncestryInterrogationReceipt
    manifest: CollectiveManifest
    body: ResearchArtifactBody
    nodes: tuple[ReasoningAncestryNode, ...]
    stale: bool


def resolve_reasoning_ancestry_interrogation(
    *,
    authority: ArtifactAuthority,
    receipt_id: str,
    engagement_store: AuthorizedEngagementStore,
    session_store: SessionStore,
    artifact_store: FilesystemArtifactStore | None = None,
) -> ResolvedReasoningAncestryInterrogation:
    store = artifact_store or FilesystemArtifactStore()
    with store.mutation_lock(authority):
        receipt = read_reasoning_ancestry_interrogation(
            receipt_id, engagement_store=engagement_store
        )
        current = parse_body_from_html(store.read(authority))
        stale = current.content_hash() != receipt.artifact_content_hash
        body = (
            parse_body_from_html(
                store.read_history(
                    authority,
                    body_content_hash=receipt.artifact_content_hash,
                )
            )
            if stale
            else current
        )
        nodes = project_reasoning_ancestry(
            body=body,
            claim_index=receipt.claim_index,
            authority=authority,
            owner_account_digest=EngagementAuthority(
                authority.account_id
            ).account_digest,
            engagement_store=engagement_store,
            session_store=session_store,
        )
        manifest = validate_reasoning_ancestry_interrogation(
            receipt,
            body=body,
            nodes=nodes,
            artifact_authority=authority,
            engagement_store=engagement_store,
        )
    return ResolvedReasoningAncestryInterrogation(
        receipt=receipt,
        manifest=manifest,
        body=body,
        nodes=tuple(nodes),
        stale=stale,
    )


__all__ = [
    "ResolvedReasoningAncestryInterrogation",
    "resolve_reasoning_ancestry_interrogation",
]
