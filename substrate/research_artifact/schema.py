"""ResearchArtifact v0 — canonical JSON body (HTML is a rendered view)."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.source_coverage import ArtifactInheritedReuse, ArtifactSourceCoverage

SCHEMA_VERSION: Literal[2] = 2


class ArtifactInsight(BaseModel):
    node_id: str
    text: str
    source_document_id: str | None = None
    confidence: str | None = None


class ArtifactQuestion(BaseModel):
    node_id: str
    text: str
    escalated: bool = False
    reserved_child_investigation_id: str | None = None


class ArtifactClaimInheritedSupport(BaseModel):
    unit_id: str = Field(min_length=1, max_length=512)
    qualification_state: Literal["complete", "partial", "unknown", "legacy_unqualified"]
    source_investigation_id: str | None = None
    supporting_leaf_investigation_id: str


class ArtifactClaimSupport(BaseModel):
    claim: str = Field(min_length=1)
    supporting_chunk_ids: tuple[str, ...] = Field(default=(), max_length=1000)
    supporting_path_indices: tuple[int, ...] = Field(default=(), max_length=100)
    inherited_support: tuple[ArtifactClaimInheritedSupport, ...] = Field(
        default=(), max_length=100
    )


class ArtifactOwnerClaimRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: Literal["owner_accepted_claim_revision"] = "owner_accepted_claim_revision"
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    claim_id: str = Field(min_length=1, max_length=1024)
    original_claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_claim: str = Field(min_length=1)
    revised_claim: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    proposal_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_acceptance_receipt_sha256s: tuple[str, ...] = Field(
        min_length=1, max_length=64
    )
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_transition(self) -> ArtifactOwnerClaimRevision:
        if hashlib.sha256(self.original_claim.encode("utf-8")).hexdigest() != (
            self.original_claim_sha256
        ):
            raise ValueError("owner claim revision original digest mismatch")
        receipts = list(self.selected_acceptance_receipt_sha256s)
        if len(receipts) != len(set(receipts)):
            raise ValueError("owner claim revision receipts contain duplicates")
        payload = self.model_dump(exclude={"transition_sha256"}, mode="json")
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != self.transition_sha256:
            raise ValueError("owner claim revision transition digest mismatch")
        return self


class ArtifactOwnerClaimCompensation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: Literal["owner_claim_revision_compensation"] = (
        "owner_claim_revision_compensation"
    )
    operation: Literal[
        "restore_archived_terminal", "supersede_owner_revision"
    ]
    owner_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_account_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_investigation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_index: int = Field(ge=0, le=100_000)
    supersedes_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_effective_claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_effective_claim: str = Field(min_length=1)
    replacement_claim: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    mutation_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_transition(self) -> ArtifactOwnerClaimCompensation:
        if hashlib.sha256(self.prior_effective_claim.encode("utf-8")).hexdigest() != (
            self.prior_effective_claim_sha256
        ):
            raise ValueError("owner claim compensation prior digest mismatch")
        payload = self.model_dump(exclude={"transition_sha256"}, mode="json")
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != self.transition_sha256:
            raise ValueError("owner claim compensation transition digest mismatch")
        return self


class ArtifactOwnerClaimProposalCompensation(ArtifactOwnerClaimCompensation):
    """Canonical compensation that consumes one immutable reviewed proposal."""

    schema_version: Literal[2] = 2
    source_context_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_review_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_proposal_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


ArtifactOwnerClaimCompensationRecord = Annotated[
    ArtifactOwnerClaimCompensation | ArtifactOwnerClaimProposalCompensation,
    Field(discriminator="schema_version"),
]


class ResearchArtifactBody(BaseModel):
    """Machine channel for Profile B transport (ANT-AHT)."""

    schema_version: Literal[2, 3, 4] = SCHEMA_VERSION
    investigation_id: str
    problem_question: str
    insights: list[ArtifactInsight] = Field(default_factory=list)
    open_questions: list[ArtifactQuestion] = Field(default_factory=list)
    synthesis_excerpt: str | None = None
    synthesis_withheld: bool = False
    # Exact delivered synthesis represented by this artifact. Additive and
    # nullable so historical v2 artifacts remain readable without inference.
    synthesis_event_id: str | None = None
    source_event_ids: list[str] = Field(default_factory=list)
    source_coverage: ArtifactSourceCoverage | None = None
    inherited_reuse: ArtifactInheritedReuse | None = None
    claim_support: list[ArtifactClaimSupport] = Field(default_factory=list)
    owner_claim_revisions: list[ArtifactOwnerClaimRevision] = Field(default_factory=list)
    owner_claim_compensations: list[ArtifactOwnerClaimCompensationRecord] = Field(
        default_factory=list, max_length=1000
    )
    # Append-only agent transport (import via import_agent_notes; never graph insights).
    agent_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_owner_revision_channel(self) -> ResearchArtifactBody:
        if self.owner_claim_revisions and self.schema_version not in (3, 4):
            raise ValueError("owner claim revisions require artifact schema v3+")
        if self.owner_claim_compensations and self.schema_version != 4:
            raise ValueError("owner claim compensations require artifact schema v4")
        indices = [item.claim_index for item in self.owner_claim_revisions]
        if len(indices) != len(set(indices)):
            raise ValueError("artifact has multiple owner revisions for one claim")
        for revision in self.owner_claim_revisions:
            if not 0 <= revision.claim_index < len(self.claim_support):
                raise ValueError("owner claim revision index is unavailable")
            claim = self.claim_support[revision.claim_index].claim
            if revision.original_claim != claim:
                raise ValueError("owner claim revision original claim mismatch")
        roots = {revision.claim_index: revision for revision in self.owner_claim_revisions}
        heads = {
            index: (revision.transition_sha256, revision.revised_claim)
            for index, revision in roots.items()
        }
        transitions = {revision.transition_sha256 for revision in roots.values()}
        consumed_proposals: set[str] = set()
        full_payload = self.model_dump(mode="json")
        compensation_prefix: list[dict[str, object]] = []
        for compensation in self.owner_claim_compensations:
            if isinstance(compensation, ArtifactOwnerClaimProposalCompensation):
                if compensation.operation != "supersede_owner_revision":
                    raise ValueError("proposal compensation must supersede owner wording")
                if compensation.source_proposal_receipt_sha256 in consumed_proposals:
                    raise ValueError("effective context proposal is consumed more than once")
                consumed_proposals.add(compensation.source_proposal_receipt_sha256)
            prior_payloads: list[dict[str, object]] = []
            if compensation_prefix:
                prior_payload = dict(full_payload)
                prior_payload["schema_version"] = 4
                prior_payload["owner_claim_compensations"] = compensation_prefix
                prior_payloads.append(prior_payload)
            else:
                # The first append may upgrade a canonical v3 body or append to
                # an already-v4 body whose compensation channel is still empty.
                v3_payload = dict(full_payload)
                v3_payload["schema_version"] = 3
                v3_payload.pop("owner_claim_compensations", None)
                prior_payloads.append(v3_payload)
                v4_payload = dict(full_payload)
                v4_payload["schema_version"] = 4
                v4_payload["owner_claim_compensations"] = []
                prior_payloads.append(v4_payload)
            expected_prior_hashes = {
                hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ).hexdigest()
                for payload in prior_payloads
            }
            if compensation.prior_artifact_content_hash not in expected_prior_hashes:
                raise ValueError("owner claim compensation prior artifact is not contiguous")
            root = roots.get(compensation.claim_index)
            head = heads.get(compensation.claim_index)
            if root is None or head is None:
                raise ValueError("owner claim compensation has no root revision")
            if (
                compensation.owner_account_digest != root.owner_account_digest
                or compensation.artifact_account_digest
                != root.artifact_account_digest
                or compensation.artifact_investigation_digest
                != root.artifact_investigation_digest
            ):
                raise ValueError("owner claim compensation lineage mismatch")
            if compensation.transition_sha256 in transitions:
                raise ValueError("owner claim transition is duplicated")
            if (
                compensation.supersedes_transition_sha256 != head[0]
                or compensation.prior_effective_claim != head[1]
                or compensation.prior_effective_claim_sha256
                != hashlib.sha256(head[1].encode("utf-8")).hexdigest()
            ):
                raise ValueError("owner claim compensation chain is not contiguous")
            if (
                compensation.operation == "restore_archived_terminal"
                and compensation.replacement_claim != root.original_claim
            ):
                raise ValueError("owner claim restoration is not server-authored")
            heads[compensation.claim_index] = (
                compensation.transition_sha256,
                compensation.replacement_claim,
            )
            transitions.add(compensation.transition_sha256)
            compensation_prefix.append(compensation.model_dump(mode="json"))
        return self

    def effective_owner_claim(self, claim_index: int) -> tuple[str, str] | None:
        roots = [
            revision
            for revision in self.owner_claim_revisions
            if revision.claim_index == claim_index
        ]
        if not roots:
            return None
        text = roots[0].revised_claim
        transition = roots[0].transition_sha256
        for compensation in self.owner_claim_compensations:
            if compensation.claim_index == claim_index:
                text = compensation.replacement_claim
                transition = compensation.transition_sha256
        return text, transition

    def content_hash(self) -> str:
        canonical = self.model_dump(mode="json")
        # Schema-v2 hashes predate the additive owner revision channel. Keep
        # historical identities stable when old JSON is parsed by newer code.
        if self.schema_version == 2 and not self.owner_claim_revisions:
            canonical.pop("owner_claim_revisions", None)
        if self.schema_version <= 3 and not self.owner_claim_compensations:
            canonical.pop("owner_claim_compensations", None)
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
    model_config = ConfigDict(extra="forbid")
