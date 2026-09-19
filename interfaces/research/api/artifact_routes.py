"""ResearchArtifact export + outline blocks (ANT-AHT)."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import sys
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.dispatch.research_cost_envelope import (  # noqa: E402
    ResearchCostEnvelopeInvalid,
)
from substrate.event_log import trajectory_authorized  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.investigation_tenancy import InvestigationAuthority  # noqa: E402
from substrate.research_artifact import (  # noqa: E402
    export_research_artifact,
    import_agent_notes_html,
    list_outline_blocks,
    parse_body_from_html,
)
from substrate.research_artifact.authority import (  # noqa: E402
    ArtifactAuthority,
    operator_authority,
)
from substrate.research_artifact.effective_context_review import (  # noqa: E402
    EffectiveContextCompensationProposal,
    EffectiveContextReviewAcceptance,
)
from substrate.research_artifact.render import render_html  # noqa: E402
from substrate.research_artifact.rollout import read_canonical_artifact  # noqa: E402
from substrate.research_artifact.schema import (  # noqa: E402
    ArtifactClaimSupport,
    ResearchArtifactBody,
)
from substrate.research_artifact.storage import (  # noqa: E402
    FilesystemArtifactStore,
    UnsafeArtifactState,
)
from substrate.schemas.events import ActionType  # noqa: E402

from .investigation_access import (  # noqa: E402
    InvestigationAccessDenied,
    InvestigationAuthenticationRequired,
    authority_from_request,
    require_investigation_owner,
)

artifact_router = APIRouter(prefix="/research", tags=["research-artifact"])


def _private_artifact_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Cache-Control": "private, no-store"},
    )


def _private_artifact_exception(exc: HTTPException) -> HTTPException:
    headers = dict(exc.headers or {})
    headers["Cache-Control"] = "private, no-store"
    exc.headers = headers
    return exc


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


class BlockOut(BaseModel):
    node_id: str
    kind: str
    label: str
    investigation_id: str


class BlocksOut(BaseModel):
    investigation_id: str
    blocks: list[BlockOut]


class ExportOut(BaseModel):
    investigation_id: str
    view_url: str
    content_hash: str
    size_bytes: int
    event_id: str | None = None


class ClaimInheritedSupportOut(BaseModel):
    unit_id: str
    qualification_state: str
    source_investigation_id: str | None = None
    supporting_leaf_investigation_id: str


class ClaimDirectEvidenceOut(BaseModel):
    source_kind: str
    source_asset_id: str
    claim_id: str
    chunk_ids: list[str]
    document_id: str
    receipt_sha256: str


class ClaimEvaluationOut(BaseModel):
    advisory: bool = True
    event_id: str
    scorer_id: str
    backend: Literal["lexical", "nli", "llm_judge"]
    score: float
    supported: bool
    supported_threshold: float
    relation: Literal["entailed", "contradicted", "not_established"] | None = None


class ClaimSupportOut(BaseModel):
    claim_index: int
    claim: str
    supporting_chunk_ids: list[str]
    supporting_path_indices: list[int]
    inherited_support: list[ClaimInheritedSupportOut]
    direct_evidence: list[ClaimDirectEvidenceOut]
    evaluation: ClaimEvaluationOut | None = None
    reviews: list[ClaimReviewProjectionOut] = Field(default_factory=list)
    reconsiderations: list[ClaimReconsiderationOut] = Field(default_factory=list)
    owner_revision: ClaimOwnerRevisionOut | None = None


class ClaimReviewProjectionOut(BaseModel):
    schema_version: Literal[1] = 1
    status: Literal[
        "later_owner_accepted_counter_analysis",
        "later_owner_reversed_counter_analysis",
    ]
    challenge_receipt_sha256: str
    acceptance_receipt_sha256: str
    reversal_receipt_sha256: str | None = None
    session_id: str
    spawn_id: str
    candidate_sha256: str
    candidate_text: str
    evaluation_event_id: str
    evidence_receipt_sha256s: list[str]
    grants_authority: Literal[False] = False


class ClaimReconsiderationOut(BaseModel):
    schema_version: Literal[1] = 1
    status: Literal["owner_authored_reconsideration_proposal"]
    receipt_sha256: str
    selected_acceptance_receipt_sha256s: list[str]
    proposed_claim: str
    rationale: str
    grants_authority: Literal[False] = False


class ClaimOwnerRevisionOut(BaseModel):
    status: Literal["owner_accepted_claim_revision"]
    prior_artifact_content_hash: str
    proposal_receipt_sha256: str
    transition_sha256: str
    revised_claim: str
    rationale: str
    effective_claim: str
    head_transition_sha256: str
    compensations: list[ClaimOwnerCompensationOut] = Field(default_factory=list)
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False


class ClaimOwnerCompensationOut(BaseModel):
    operation: Literal["restore_archived_terminal", "supersede_owner_revision"]
    prior_artifact_content_hash: str
    supersedes_transition_sha256: str
    transition_sha256: str
    prior_effective_claim: str
    replacement_claim: str
    rationale: str
    source_context_receipt_sha256: str | None = None
    source_review_receipt_sha256: str | None = None
    source_proposal_receipt_sha256: str | None = None
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False


class ClaimSupportsOut(BaseModel):
    investigation_id: str
    content_hash: str
    claims: list[ClaimSupportOut]


class ClaimChallengeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    goal: str = Field(min_length=1, max_length=4000)
    view_mode: Literal["floating", "full"] = "floating"
    model_id: str | None = Field(default=None, max_length=240)
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


class ClaimChallengeOut(BaseModel):
    session_id: str
    spawn_id: str
    investigation_id: str
    parent_asset_id: str
    selection_text: str
    status: str
    view_mode: Literal["floating", "full"]
    model_id: str | None
    research_tier: str
    view_format: Literal["html"] = "html"
    claim_challenge: dict[str, object]


class EffectiveOwnerContextPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    goal: str = Field(min_length=1, max_length=4000)
    mutation_key: str = Field(min_length=1, max_length=512)
    view_mode: Literal["floating", "full"] = "floating"
    model_id: str | None = Field(default=None, max_length=240)
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


class EffectiveOwnerContextAcceptIn(EffectiveOwnerContextPreviewIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EffectiveOwnerContextPreviewOut(BaseModel):
    receipt_sha256: str
    artifact_content_hash: str
    archived_claim: str
    effective_claim: str
    head_transition_sha256: str
    view_mode: Literal["floating", "full"]
    preview_sha256: str
    revision_transition_sha256s: list[str]
    archived_evaluation: dict[str, object]
    archived_direct_evidence_receipt_sha256s: list[str]
    archived_inherited_support: list[dict[str, object]]
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    permits_provider_call: Literal[False] = False
    permits_spend: Literal[False] = False
    permits_graph_admission: Literal[False] = False
    permits_write: Literal[False] = False
    permits_benchmark_feedback: Literal[False] = False
    permits_publication: Literal[False] = False


class EffectiveOwnerContextCommandOut(BaseModel):
    status: Literal["candidate", "accepted"]
    preview: EffectiveOwnerContextPreviewOut | None = None
    reservation: ClaimChallengeOut | None = None


class RecursiveRoundContextPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_round_ordinals: list[int] = Field(default_factory=list, max_length=100)
    follow_up_questions: list[str] = Field(min_length=1, max_length=20)
    mutation_key: str = Field(min_length=1, max_length=512)
    view_mode: Literal["floating", "full"] = "floating"
    model_id: str | None = Field(default=None, max_length=240)
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


class RecursiveRoundContextAcceptIn(RecursiveRoundContextPreviewIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RecursiveRoundContextPreviewOut(BaseModel):
    receipt_sha256: str
    pack_sha256: str
    artifact_content_hash: str
    current_effective_claim: str
    current_head_transition_sha256: str
    selected_round_ordinals: list[int]
    selected_transition_sha256s: list[str]
    follow_up_questions: list[str]
    rows: list[dict[str, object]]
    pack_bytes: int
    view_mode: Literal["floating", "full"]
    preview_sha256: str
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    permits_provider_call: Literal[False] = False
    permits_spend: Literal[False] = False
    permits_graph_admission: Literal[False] = False
    permits_twin_promotion: Literal[False] = False
    permits_write: Literal[False] = False
    permits_benchmark_feedback: Literal[False] = False
    permits_publication: Literal[False] = False


class RecursiveRoundContextCommandOut(BaseModel):
    status: Literal["candidate", "accepted"]
    preview: RecursiveRoundContextPreviewOut | None = None
    reservation: ClaimChallengeOut | None = None


class ClaimReviewPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ClaimReviewAcceptIn(ClaimReviewPreviewIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mutation_key: str = Field(min_length=1, max_length=512)


class EffectiveContextReviewPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: Literal["retain_current", "propose_compensation"]
    rationale: str = Field(min_length=1, max_length=4_000)
    proposed_claim: str | None = Field(default=None, max_length=20_000)


class EffectiveContextReviewAcceptIn(EffectiveContextReviewPreviewIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mutation_key: str = Field(min_length=1, max_length=512)


class EffectiveContextReviewPreviewOut(BaseModel):
    status: Literal["candidate"]
    artifact_content_hash: str
    claim_index: int
    context_receipt_sha256: str
    head_transition_sha256: str
    archived_claim: str
    effective_claim: str
    candidate_sha256: str
    candidate_text: str
    archived_evaluation: dict[str, object]
    archived_direct_evidence_receipt_sha256s: list[str]
    archived_inherited_support: list[dict[str, object]]
    disposition: Literal["retain_current", "propose_compensation"]
    rationale: str
    proposed_claim: str | None
    preview_sha256: str
    html: str
    archive_grounded: Literal[False]
    grants_authority: Literal[False]
    permits_canonical_append: Literal[False]


class EffectiveContextReviewOut(BaseModel):
    status: Literal["candidate", "accepted"]
    preview: EffectiveContextReviewPreviewOut
    acceptance: EffectiveContextReviewAcceptance | None = None
    proposal: EffectiveContextCompensationProposal | None = None


class EffectiveContextReviewReadOut(BaseModel):
    status: Literal["accepted"]
    archived_claim: str
    archived_evaluation: dict[str, object]
    archived_direct_evidence_receipt_sha256s: list[str]
    archived_inherited_support: list[dict[str, object]]
    effective_claim: str
    candidate_text: str
    acceptance: EffectiveContextReviewAcceptance
    proposal: EffectiveContextCompensationProposal | None = None
    consumption: dict[str, object] | None = None


class EffectiveContextCompensationPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposal_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mutation_key: str = Field(min_length=1, max_length=512)


class EffectiveContextCompensationAcceptIn(EffectiveContextCompensationPreviewIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EffectiveClaimIterationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int
    prior_artifact_content_hash: str
    result_artifact_content_hash: str
    claim_index: int
    archived_claim: str
    prior_effective_claim: str
    candidate_text: str
    candidate_sha256: str
    review_rationale: str
    proposed_claim: str
    replacement_claim: str
    context_receipt_sha256: str
    review_receipt_sha256: str
    proposal_receipt_sha256: str
    transition_sha256: str
    session_id: str
    spawn_id: str
    question: str
    purpose: str
    model_id: str | None
    research_tier: str
    prior_html_url: str
    result_html_url: str
    result_is_current: bool
    archive_grounded: Literal[False]
    grants_authority: Literal[False]
    permits_graph_admission: Literal[False]
    permits_write: Literal[False]
    permits_benchmark_feedback: Literal[False]
    permits_publication: Literal[False]
    permits_provider_call: Literal[False]
    permits_spend: Literal[False]


class EffectiveClaimIterationsOut(BaseModel):
    investigation_id: str
    claim_index: int
    artifact_content_hash: str
    current_effective_claim: str
    current_head_transition_sha256: str
    next_round_eligible: bool
    rounds: list[EffectiveClaimIterationOut]


class ReasoningAncestryNodeOut(BaseModel):
    ordinal: int
    transition_sha256: str
    session_id: str
    spawn_id: str
    candidate_sha256: str
    parent_ordinals: list[int]
    child_ordinals: list[int]
    inherited_questions: list[str]
    depth: int
    is_root: bool
    is_recombination: bool
    recursive_pack_receipt_sha256: str | None
    recursive_context_pack: dict[str, object] | None
    ancestry_sha256: str
    prior_html_url: str
    result_html_url: str
    archive_grounded: Literal[False] = False
    grants_authority: Literal[False] = False
    permits_graph_admission: Literal[False] = False
    permits_write: Literal[False] = False
    permits_benchmark_feedback: Literal[False] = False
    permits_publication: Literal[False] = False
    permits_provider_call: Literal[False] = False
    permits_spend: Literal[False] = False


class ReasoningAncestryOut(BaseModel):
    investigation_id: str
    claim_index: int
    artifact_content_hash: str
    current_effective_claim: str
    current_head_transition_sha256: str
    graph_sha256: str
    nodes: list[ReasoningAncestryNodeOut]


class ReasoningAncestryInterrogationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_terminal_ordinals: list[int] = Field(min_length=1, max_length=32)
    question: str = Field(min_length=1, max_length=4_000)
    mutation_key: str = Field(min_length=1, max_length=512)


class ReasoningAncestryInterrogationAcceptIn(ReasoningAncestryInterrogationIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReasoningAncestryInterrogationOut(BaseModel):
    status: Literal["candidate", "accepted"]
    preview_sha256: str
    receipt: dict[str, object]
    manifest: dict[str, object]
    stale: bool = False


class AncestryRoleCostEnvelopeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal[
        "decomposer",
        "evidence_retriever",
        "parameter_extractor",
        "connector",
        "synthesizer",
        "knowledge_extractor",
    ]
    mandatory_calls: int = Field(ge=0)
    conditional_calls: int = Field(ge=0)
    max_calls: int = Field(gt=0)
    selected_route_only: bool
    route_max_usd: str
    role_max_usd: str
    pricing_fingerprints: tuple[str, ...]


class AncestryWholeRunEnvelopeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    projection_kind: Literal["admission_upper_bound"]
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    maximum_usd: str
    forecast_usd_low: None
    forecast_usd_high: None
    forecast_status: Literal["not_measured"]
    roles: tuple[AncestryRoleCostEnvelopeOut, ...]


class AncestryContinuationChoiceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["synthesizer"] = "synthesizer"
    projection_scope: Literal["selected_synthesizer_call_only"] = "selected_synthesizer_call_only"
    provider_id: str
    model_id: str
    fallback_index: int
    route_identity: str
    pricing_fingerprint: str
    estimated_usd_low: float
    estimated_usd_high: float
    remaining_after_high_usd: float | None
    would_exceed_budget: bool | None
    pricing_source_url: str
    pricing_verified_at: str
    pricing_expires_at: str
    boot_ready: bool
    available: bool
    reason: str
    whole_run_envelope: AncestryWholeRunEnvelopeOut


class AncestryContinuationOptionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    investigation_id: str
    receipt_id: str
    receipt_sha256: str
    context_sha256: str
    task_class: Literal["ancestry_collective_continuation"] = "ancestry_collective_continuation"
    stale: bool
    assumed_input_tokens: int
    whole_run_cost_projected: Literal[True] = True
    choices: list[AncestryContinuationChoiceOut]
    budget: dict[str, object]
    view_format: Literal["html"] = "html"
    action_authority: Literal[False] = False


class AncestryContinuationQuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_id: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=512)
    pricing_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    research_tier: Literal["fast", "deep", "wrestle"]
    approved_run_ceiling_usd: float = Field(gt=0.0, le=100.0)

    @field_validator("approved_run_ceiling_usd")
    @classmethod
    def _whole_cent_ceiling(cls, value: float) -> float:
        from decimal import Decimal

        decimal = Decimal(str(value))
        if decimal != decimal.quantize(Decimal("0.01")):
            raise ValueError("approved run ceiling must use whole cents")
        return value


class AncestryContinuationQuoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_token: str
    quote_id: str
    quote_payload_sha256: str
    route_manifest_fingerprint: str
    context_sha256: str
    receipt_sha256: str
    selected_driver_role: Literal["synthesizer"] = "synthesizer"
    selected_driver_provider: str
    selected_driver_model: str
    selected_driver_pricing_fingerprint: str
    workload_plan_sha256: str
    whole_run_maximum_usd: str
    approved_run_ceiling_usd: str
    issued_at_ms: int
    expires_at_ms: int
    view_format: Literal["html"] = "html"
    spend_performed: Literal[False] = False


class AncestryContinuationLaunchIn(AncestryContinuationQuoteIn):
    research_quote_token: str = Field(min_length=32, max_length=32_768)


class AncestryContinuationLaunchOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    status: Literal["started"] = "started"
    start_event_id: str
    parent_investigation_id: str
    ancestry_interrogation_receipt_id: str
    selected_driver_provider: str
    selected_driver_model: str
    view_format: Literal["html"] = "html"


class ClaimReviewReverseIn(ClaimReviewPreviewIn):
    acceptance_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=1, max_length=4000)
    mutation_key: str = Field(min_length=1, max_length=512)


class ClaimReviewOut(BaseModel):
    status: Literal["candidate", "accepted", "reversed"]
    preview: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None
    reversal: dict[str, Any] | None = None
    view_format: Literal["html"] = "html"


class ClaimReconsiderationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_receipt_sha256s: list[str] = Field(min_length=1, max_length=64)
    proposed_claim: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(min_length=1, max_length=20_000)


class ClaimReconsiderationCreateIn(ClaimReconsiderationIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mutation_key: str = Field(min_length=1, max_length=512)


class ClaimReconsiderationCommandOut(BaseModel):
    status: Literal["candidate", "created"]
    preview: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    view_format: Literal["html"] = "html"


class ClaimRevisionPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposal_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mutation_key: str = Field(min_length=1, max_length=512)


class ClaimRevisionAcceptIn(ClaimRevisionPreviewIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ClaimRevisionCommandOut(BaseModel):
    status: Literal["candidate", "accepted"]
    preview: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None
    view_format: Literal["html"] = "html"


class ClaimRevisionCompensationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    supersedes_transition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation: Literal["restore_archived_terminal", "supersede_owner_revision"]
    replacement_claim: str | None = Field(default=None, max_length=20_000)
    rationale: str = Field(min_length=1, max_length=20_000)
    mutation_key: str = Field(min_length=1, max_length=512)


class ClaimRevisionCompensationAcceptIn(ClaimRevisionCompensationIn):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ClaimRevisionCompensationCommandOut(BaseModel):
    status: Literal["candidate", "accepted"]
    preview: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None
    view_format: Literal["html"] = "html"


class ImportNotesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportNotesOut(BaseModel):
    investigation_id: str
    notes_imported: int
    notes_skipped_duplicate: int
    event_ids: list[str]


class AppendNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=100_000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("note must contain non-whitespace text")
        return normalized


def _authority(
    request: Request, investigation_id: str, *, allow_unauthenticated_local: bool = True
) -> ArtifactAuthority:
    user_id = getattr(request.state, "user_id", None)
    if not isinstance(user_id, str) or not user_id or user_id != user_id.strip():
        raise HTTPException(status_code=401, detail="authentication required")
    if (
        user_id == "__operator__"
        and getattr(request.state, "auth_method", None) == "unauthenticated_local"
    ):
        if not allow_unauthenticated_local:
            raise HTTPException(status_code=401, detail="authentication required")
        # Named compatibility adapter for historic single-operator artifacts.
        return operator_authority(investigation_id)
    try:
        access = authority_from_request(request, investigation_id)
        require_investigation_owner(access)
        authority = ArtifactAuthority(user_id, investigation_id)
    except InvestigationAuthenticationRequired as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    except (InvestigationAccessDenied, ValueError) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    return authority


def _claim_support_out(
    authority: ArtifactAuthority,
    item: ArtifactClaimSupport,
    *,
    content_hash: str,
    index: int,
    evaluation: ClaimEvaluationOut | None = None,
    owner_revision: object | None = None,
    owner_compensations: tuple[object, ...] = (),
) -> ClaimSupportOut:
    from .hosted_document_routes import resolve_citation_evidence_groups

    return ClaimSupportOut(
        claim_index=index,
        claim=item.claim,
        supporting_chunk_ids=list(item.supporting_chunk_ids),
        supporting_path_indices=list(item.supporting_path_indices),
        inherited_support=[
            ClaimInheritedSupportOut(**support.model_dump()) for support in item.inherited_support
        ],
        direct_evidence=[
            ClaimDirectEvidenceOut(**evidence.to_dict())
            for evidence in (
                resolve_citation_evidence_groups(
                    list(item.supporting_chunk_ids),
                    owner_id=authority.account_id,
                    source_asset_id=authority.investigation_id,
                    claim_id=f"artifact-v2:{content_hash}:{index}",
                )
                if item.supporting_chunk_ids
                else ()
            )
        ],
        evaluation=evaluation,
        owner_revision=(
            ClaimOwnerRevisionOut(
                status=owner_revision.status,
                prior_artifact_content_hash=owner_revision.prior_artifact_content_hash,
                proposal_receipt_sha256=owner_revision.proposal_receipt_sha256,
                transition_sha256=owner_revision.transition_sha256,
                revised_claim=owner_revision.revised_claim,
                rationale=owner_revision.rationale,
                effective_claim=(
                    owner_compensations[-1].replacement_claim
                    if owner_compensations
                    else owner_revision.revised_claim
                ),
                head_transition_sha256=(
                    owner_compensations[-1].transition_sha256
                    if owner_compensations
                    else owner_revision.transition_sha256
                ),
                compensations=[
                    ClaimOwnerCompensationOut(
                        operation=item.operation,
                        prior_artifact_content_hash=item.prior_artifact_content_hash,
                        supersedes_transition_sha256=item.supersedes_transition_sha256,
                        transition_sha256=item.transition_sha256,
                        prior_effective_claim=item.prior_effective_claim,
                        replacement_claim=item.replacement_claim,
                        rationale=item.rationale,
                        source_context_receipt_sha256=getattr(
                            item, "source_context_receipt_sha256", None
                        ),
                        source_review_receipt_sha256=getattr(
                            item, "source_review_receipt_sha256", None
                        ),
                        source_proposal_receipt_sha256=getattr(
                            item, "source_proposal_receipt_sha256", None
                        ),
                    )
                    for item in owner_compensations
                ],
            )
            if owner_revision is not None
            else None
        ),
    )


def _artifact_claim_evaluations(
    authority: ArtifactAuthority, artifact: object
) -> dict[int, ClaimEvaluationOut]:
    """Resolve advisory verdicts by exact event and exact ordered evidence.

    Absence is allowed for historical artifacts. Once a groundedness event is
    attached to the represented synthesis, ambiguity or structural drift is a
    refusal rather than a best-effort prose join.
    """
    investigation_authority = InvestigationAuthority(
        authority.account_id, authority.investigation_id
    )
    rows = trajectory_authorized(investigation_authority)
    synthesis_event_id = getattr(artifact, "synthesis_event_id", None)
    if synthesis_event_id is None:
        return {}
    delivered = [
        row
        for row in rows
        if row.get("event_id") == synthesis_event_id
        and row.get("action_type") == ActionType.SYNTHESIZE_DELIVERED.value
    ]
    if not delivered:
        raise ValueError("artifact synthesis event is unavailable")
    if len(delivered) != 1:
        raise ValueError("artifact synthesis event is ambiguous")
    scored = [
        row
        for row in rows
        if row.get("action_type") == ActionType.GROUNDEDNESS_SCORED.value
        and row.get("parent_event_id") == synthesis_event_id
    ]
    if not scored:
        return {}
    if len(scored) != 1:
        raise ValueError("artifact groundedness evaluation is ambiguous")
    payload = scored[0].get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("per_claim"), list):
        raise ValueError("artifact groundedness evaluation is malformed")
    if not {"scorer_id", "backend", "supported_threshold"} <= payload.keys():
        raise ValueError("artifact groundedness evaluation is incomplete")
    claims = getattr(artifact, "claim_support", ()) or ()
    result: dict[int, ClaimEvaluationOut] = {}
    for index, claim in enumerate(claims):
        matches = [
            verdict
            for verdict in payload["per_claim"]
            if isinstance(verdict, dict)
            and verdict.get("claim") == claim.claim
            and verdict.get("cited_chunk_ids") == list(claim.supporting_chunk_ids)
        ]
        if len(matches) != 1:
            raise ValueError("artifact groundedness verdict does not uniquely match claim evidence")
        verdict = matches[0]
        if not {"score", "supported"} <= verdict.keys():
            raise ValueError("artifact groundedness verdict is incomplete")
        result[index] = ClaimEvaluationOut(
            event_id=str(scored[0]["event_id"]),
            scorer_id=payload["scorer_id"],
            backend=payload["backend"],
            score=verdict["score"],
            supported=verdict["supported"],
            supported_threshold=payload["supported_threshold"],
            relation=verdict.get("relation"),
        )
    return result


def _attach_claim_reviews(
    authority: ArtifactAuthority,
    projection: ClaimSupportOut,
    *,
    content_hash: str,
    request: Request,
) -> ClaimSupportOut:
    if projection.evaluation is None:
        return projection
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_review import project_claim_reviews

    challenge_claim_id = f"artifact-v2:{content_hash}:{projection.claim_index}"
    reviews = project_claim_reviews(
        source_asset_id=authority.investigation_id,
        artifact_content_hash=content_hash,
        artifact_account_digest=authority.account_digest,
        artifact_investigation_digest=authority.investigation_digest,
        claim_index=projection.claim_index,
        claim_id=challenge_claim_id,
        claim_sha256=hashlib.sha256(projection.claim.encode("utf-8")).hexdigest(),
        evaluation_event_id=projection.evaluation.event_id,
        scorer_id=projection.evaluation.scorer_id,
        relation=projection.evaluation.relation,
        score=projection.evaluation.score,
        evidence_receipt_sha256s=tuple(
            evidence.receipt_sha256 for evidence in projection.direct_evidence
        ),
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        engagement_store=_eng_for(request),
        session_store=_sess_for(request),
    )
    projection.reviews = [
        ClaimReviewProjectionOut(**review.model_dump(mode="json")) for review in reviews
    ]
    from substrate.research_artifact.claim_reconsideration import (
        project_claim_reconsideration_proposal,
        read_claim_reconsideration_proposal,
    )

    engagement_store = _eng_for(request)
    proposal = read_claim_reconsideration_proposal(
        source_asset_id=authority.investigation_id,
        artifact_content_hash=content_hash,
        claim_index=projection.claim_index,
        store=engagement_store,
    )
    current_proposal = project_claim_reconsideration_proposal(
        proposal=proposal,
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        artifact_account_digest=authority.account_digest,
        artifact_investigation_digest=authority.investigation_digest,
        claim_id=challenge_claim_id,
        original_claim=projection.claim,
        reviews=reviews,
    )
    if current_proposal is not None:
        projection.reconsiderations = [
            ClaimReconsiderationOut(
                status=current_proposal.status,
                receipt_sha256=current_proposal.receipt_sha256,
                selected_acceptance_receipt_sha256s=[
                    item.acceptance_receipt_sha256 for item in current_proposal.selected_reviews
                ],
                proposed_claim=current_proposal.proposed_claim,
                rationale=current_proposal.rationale,
            )
        ]
    return projection


def _claim_supports(
    authority: ArtifactAuthority, *, request: Request | None = None
) -> ClaimSupportsOut:
    html_text, _ = read_canonical_artifact(authority)
    artifact = parse_body_from_html(html_text)
    content_hash = artifact.content_hash()
    evaluations = _artifact_claim_evaluations(authority, artifact)
    projections = [
        _claim_support_out(
            authority,
            item,
            content_hash=content_hash,
            index=index,
            evaluation=evaluations.get(index),
            owner_revision=next(
                (
                    revision
                    for revision in artifact.owner_claim_revisions
                    if revision.claim_index == index
                ),
                None,
            ),
            owner_compensations=tuple(
                compensation
                for compensation in artifact.owner_claim_compensations
                if compensation.claim_index == index
            ),
        )
        for index, item in enumerate(artifact.claim_support)
    ]
    if request is not None:
        projections = [
            _attach_claim_reviews(authority, projection, content_hash=content_hash, request=request)
            for projection in projections
        ]
    return ClaimSupportsOut(
        investigation_id=authority.investigation_id,
        content_hash=content_hash,
        claims=projections,
    )


@artifact_router.post("/{investigation_id}/artifact/export", response_model=ExportOut)
async def post_export_artifact(investigation_id: str, request: Request) -> ExportOut:
    authority = _authority(request, investigation_id)
    try:
        res = export_research_artifact(investigation_id, authority=authority, db_path=_db())
    except Exception as exc:  # pragma: no cover: sanitize the HTTP boundary
        raise HTTPException(status_code=500, detail="artifact export failed") from exc
    return ExportOut(
        investigation_id=res.investigation_id,
        view_url=str(request.url_for("get_artifact_view", investigation_id=investigation_id)),
        content_hash=res.content_hash,
        size_bytes=res.size_bytes,
        event_id=res.event_id,
    )


@artifact_router.post("/{investigation_id}/artifact/import-notes", response_model=ImportNotesOut)
async def post_import_notes(
    investigation_id: str, body: ImportNotesIn, request: Request
) -> ImportNotesOut:
    authority = _authority(request, investigation_id)
    try:
        path = authority.artifact_path()
        html_text, _ = read_canonical_artifact(authority)
        res = import_agent_notes_html(html_text, authority=authority, artifact_path=path)
    except (FileNotFoundError, UnsafeArtifactState) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="artifact import failed") from exc
    return ImportNotesOut(
        investigation_id=res.investigation_id,
        notes_imported=res.notes_imported,
        notes_skipped_duplicate=res.notes_skipped_duplicate,
        event_ids=res.event_ids,
    )


@artifact_router.get("/{investigation_id}/artifact/view", response_class=HTMLResponse)
async def get_artifact_view(investigation_id: str, request: Request) -> HTMLResponse:
    authority = _authority(request, investigation_id)
    try:
        html_text, _ = read_canonical_artifact(authority)
    except (FileNotFoundError, UnsafeArtifactState) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    return HTMLResponse(html_text, headers={"Cache-Control": "private, no-store"})


@artifact_router.get("/{investigation_id}/artifact/reviewed-view", response_class=HTMLResponse)
async def get_artifact_reviewed_view(
    investigation_id: str, request: Request, content_hash: str
) -> HTMLResponse:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        html_text, _ = read_canonical_artifact(authority)
        claims = _claim_supports(authority, request=request)
        if not hmac.compare_digest(claims.content_hash, content_hash):
            raise HTTPException(status_code=404, detail="artifact version not found")
        reviewed_html = html_text
        search_from = 0
        found_review = False
        for claim in claims.claims:
            marker = '<div class="card"><h3>' + html.escape(claim.claim, quote=True) + "</h3>"
            marker_at = reviewed_html.find(marker, search_from)
            if marker_at < 0:
                raise ValueError("canonical claim projection is malformed")
            insertion_at = marker_at + len(marker)
            cards: list[str] = []
            for review in claim.reviews:
                found_review = True
                state = (
                    "reversed — retained as immutable history"
                    if review.status == "later_owner_reversed_counter_analysis"
                    else "owner accepted as later counter-analysis"
                )
                cards.append(
                    '<article class="claim-review" data-epistemic-status="'
                    + html.escape(review.status, quote=True)
                    + '"><h3>Review of: '
                    + html.escape(claim.claim, quote=True)
                    + "</h3><p><strong>"
                    + html.escape(state, quote=True)
                    + "</strong></p><pre>"
                    + html.escape(review.candidate_text, quote=True)
                    + "</pre><p>Later review only — not provenance, verification, or authority.</p>"
                    + "</article>"
                )
            if cards:
                overlay = (
                    f'<aside id="claim-review-{claim.claim_index}" class="later-owner-reviews">'
                    "<h4>Later owner reviews</h4>" + "".join(cards) + "</aside>"
                )
                reviewed_html = (
                    reviewed_html[:insertion_at] + overlay + reviewed_html[insertion_at:]
                )
                search_from = insertion_at + len(overlay)
            else:
                search_from = insertion_at
        if not found_review:
            empty = '<section id="later-owner-reviews"><h2>Later owner reviews</h2><p class="empty">No accepted later reviews.</p></section>'
            if "</main>" not in reviewed_html:
                raise ValueError("canonical artifact HTML is malformed")
            reviewed_html = reviewed_html.replace("</main>", empty + "</main>", 1)
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "reviewed artifact not found") from exc
    return HTMLResponse(
        reviewed_html,
        headers={
            "Cache-Control": "private, no-store",
            "X-Antiek-Canonical-Content-Hash": claims.content_hash,
            "X-Antiek-Review-Overlay": "separate-later-analysis",
        },
    )


@artifact_router.get("/{investigation_id}/artifact/claims", response_model=ClaimSupportsOut)
async def get_artifact_claims(
    investigation_id: str, request: Request, response: Response
) -> ClaimSupportsOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
    except (ValueError, TypeError) as exc:
        raise _private_artifact_error(404, "artifact claim not found") from exc
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    try:
        result = _claim_supports(authority, request=request)
    except RuntimeError as exc:
        raise _private_artifact_error(409, "artifact review state is unavailable") from exc
    except (FileNotFoundError, UnsafeArtifactState, ValueError, TypeError) as exc:
        raise _private_artifact_error(404, "artifact not found") from exc
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    response.headers["Cache-Control"] = "private, no-store"
    return result


@artifact_router.get(
    "/{investigation_id}/artifact/claims/{claim_index}",
    response_model=ClaimSupportOut,
)
async def get_artifact_claim(
    investigation_id: str,
    claim_index: int,
    request: Request,
    response: Response,
    content_hash: str = Query(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$"),
) -> ClaimSupportOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    try:
        html_text, _ = read_canonical_artifact(authority)
        artifact = parse_body_from_html(html_text)
    except (FileNotFoundError, UnsafeArtifactState, ValueError, TypeError) as exc:
        raise _private_artifact_error(404, "artifact not found") from exc
    canonical_hash = artifact.content_hash()
    if canonical_hash != content_hash or not 0 <= claim_index < len(artifact.claim_support):
        raise _private_artifact_error(404, "artifact claim not found")
    try:
        evaluations = _artifact_claim_evaluations(authority, artifact)
        projection = _claim_support_out(
            authority,
            artifact.claim_support[claim_index],
            content_hash=canonical_hash,
            index=claim_index,
            evaluation=evaluations.get(claim_index),
            owner_revision=next(
                (
                    revision
                    for revision in artifact.owner_claim_revisions
                    if revision.claim_index == claim_index
                ),
                None,
            ),
            owner_compensations=tuple(
                compensation
                for compensation in artifact.owner_claim_compensations
                if compensation.claim_index == claim_index
            ),
        )
        projection = _attach_claim_reviews(
            authority, projection, content_hash=canonical_hash, request=request
        )
    except RuntimeError as exc:
        raise _private_artifact_error(409, "artifact review state is unavailable") from exc
    except (ValueError, TypeError) as exc:
        raise _private_artifact_error(404, "artifact claim not found") from exc
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    response.headers["Cache-Control"] = "private, no-store"
    return projection


def _claim_reconsideration_preview(
    *,
    authority: ArtifactAuthority,
    claim_index: int,
    body: ClaimReconsiderationIn,
    request: Request,
) -> tuple[dict[str, object], Any]:
    from interfaces.research.api.engagement_routes import _eng_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_reconsideration import (
        build_claim_reconsideration_preview,
    )
    from substrate.research_artifact.claim_review import ClaimReviewProjection

    supports = _claim_supports(authority, request=request)
    if supports.content_hash != body.content_hash or not 0 <= claim_index < len(supports.claims):
        raise ValueError("artifact claim not found")
    claim = supports.claims[claim_index]
    if claim.claim_index != claim_index:
        raise RuntimeError("artifact claim projection is corrupt")
    preview = build_claim_reconsideration_preview(
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        artifact_account_digest=authority.account_digest,
        artifact_investigation_digest=authority.investigation_digest,
        source_asset_id=authority.investigation_id,
        artifact_content_hash=supports.content_hash,
        claim_index=claim_index,
        claim_id=f"artifact-v2:{supports.content_hash}:{claim_index}",
        original_claim=claim.claim,
        reviews=tuple(
            ClaimReviewProjection.model_validate(review.model_dump(mode="json"))
            for review in claim.reviews
        ),
        acceptance_receipt_sha256s=tuple(body.acceptance_receipt_sha256s),
        proposed_claim=body.proposed_claim,
        rationale=body.rationale,
    )
    return preview, _eng_for(request)


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/reconsideration/preview",
    response_model=ClaimReconsiderationCommandOut,
)
def post_claim_reconsideration_preview(
    investigation_id: str,
    claim_index: int,
    body: ClaimReconsiderationIn,
    request: Request,
    response: Response,
) -> ClaimReconsiderationCommandOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            preview, _ = _claim_reconsideration_preview(
                authority=authority, claim_index=claim_index, body=body, request=request
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except (FileNotFoundError, UnsafeArtifactState, ValueError, TypeError, KeyError) as exc:
        raise _private_artifact_error(409, "claim reconsideration unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimReconsiderationCommandOut(status="candidate", preview=preview)


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/reconsideration/create",
    response_model=ClaimReconsiderationCommandOut,
)
def post_claim_reconsideration_create(
    investigation_id: str,
    claim_index: int,
    body: ClaimReconsiderationCreateIn,
    request: Request,
    response: Response,
) -> ClaimReconsiderationCommandOut:
    from substrate.research_artifact.claim_reconsideration import (
        ClaimReconsiderationConflict,
        create_claim_reconsideration_proposal,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            preview, engagement_store = _claim_reconsideration_preview(
                authority=authority, claim_index=claim_index, body=body, request=request
            )
            proposal = create_claim_reconsideration_proposal(
                preview=preview,
                expected_preview_sha256=body.preview_sha256,
                mutation_key=body.mutation_key,
                store=engagement_store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except ClaimReconsiderationConflict as exc:
        raise _private_artifact_error(409, "claim reconsideration conflict") from exc
    except (FileNotFoundError, UnsafeArtifactState, ValueError, TypeError, KeyError) as exc:
        raise _private_artifact_error(409, "claim reconsideration unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimReconsiderationCommandOut(
        status="created", proposal=proposal.model_dump(mode="json")
    )


def _claim_revision_preview(
    *,
    authority: ArtifactAuthority,
    claim_index: int,
    body: ClaimRevisionPreviewIn,
    request: Request,
    artifact_store: FilesystemArtifactStore,
) -> tuple[Any, str, Any, tuple[Any, ...]]:
    from interfaces.research.api.engagement_routes import _eng_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_reconsideration import (
        read_claim_reconsideration_proposal,
    )
    from substrate.research_artifact.claim_review import ClaimReviewProjection
    from substrate.research_artifact.claim_revision import build_claim_revision_preview

    prior_html = artifact_store.read(authority)
    prior_body = parse_body_from_html(prior_html)
    if prior_body.content_hash() != body.content_hash or not 0 <= claim_index < len(
        prior_body.claim_support
    ):
        raise ValueError("claim revision artifact is stale")
    supports = _claim_supports(authority, request=request)
    claim = supports.claims[claim_index]
    if not claim.reconsiderations:
        raise ValueError("claim reconsideration proposal is not currently actionable")
    if claim.reconsiderations[0].receipt_sha256 != body.proposal_receipt_sha256:
        raise ValueError("claim reconsideration proposal receipt is stale")
    proposal = read_claim_reconsideration_proposal(
        source_asset_id=authority.investigation_id,
        artifact_content_hash=body.content_hash,
        claim_index=claim_index,
        store=_eng_for(request),
    )
    if proposal is None or proposal.receipt_sha256 != body.proposal_receipt_sha256:
        raise ValueError("claim reconsideration proposal is unavailable")
    current_reviews = tuple(
        ClaimReviewProjection.model_validate(review.model_dump(mode="json"))
        for review in claim.reviews
    )
    preview = build_claim_revision_preview(
        authority=authority,
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        prior_body=prior_body,
        proposal=proposal,
        reviews=current_reviews,
        mutation_key=body.mutation_key,
    )
    return preview, prior_html, proposal, current_reviews


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/revision/preview",
    response_model=ClaimRevisionCommandOut,
)
def post_claim_revision_preview(
    investigation_id: str,
    claim_index: int,
    body: ClaimRevisionPreviewIn,
    request: Request,
    response: Response,
) -> ClaimRevisionCommandOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            preview, _, _, _ = _claim_revision_preview(
                authority=authority,
                claim_index=claim_index,
                body=body,
                request=request,
                artifact_store=artifact_store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "claim revision preview unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimRevisionCommandOut(status="candidate", preview=preview.public_dict())


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/revision/accept",
    response_model=ClaimRevisionCommandOut,
)
def post_claim_revision_accept(
    investigation_id: str,
    claim_index: int,
    body: ClaimRevisionAcceptIn,
    request: Request,
    response: Response,
) -> ClaimRevisionCommandOut:
    from interfaces.research.api.engagement_routes import _eng_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_reconsideration import (
        read_claim_reconsideration_proposal,
    )
    from substrate.research_artifact.claim_revision import (
        ClaimRevisionConflict,
        accept_claim_revision,
        rebuild_claim_revision_preview_for_replay,
        replay_claim_revision,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            current_html = artifact_store.read(authority)
            current_body = parse_body_from_html(current_html)
            replay = replay_claim_revision(
                body=current_body,
                prior_artifact_content_hash=body.content_hash,
                proposal_receipt_sha256=body.proposal_receipt_sha256,
                mutation_key=body.mutation_key,
                claim_index=claim_index,
            )
            if replay is not None:
                historical_html = artifact_store.read_history(
                    authority, body_content_hash=body.content_hash
                )
                historical_body = parse_body_from_html(historical_html)
                proposal = read_claim_reconsideration_proposal(
                    source_asset_id=authority.investigation_id,
                    artifact_content_hash=body.content_hash,
                    claim_index=claim_index,
                    store=_eng_for(request),
                )
                if proposal is None or proposal.receipt_sha256 != body.proposal_receipt_sha256:
                    raise ClaimRevisionConflict("claim revision proposal is unavailable")
                replay_preview = rebuild_claim_revision_preview_for_replay(
                    authority=authority,
                    owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                    prior_body=historical_body,
                    proposal=proposal,
                    mutation_key=body.mutation_key,
                )
                if (
                    replay_preview.preview_sha256 != body.preview_sha256
                    or replay_preview.transition_sha256 != body.transition_sha256
                    or replay_preview.prospective_body != current_body
                ):
                    raise ClaimRevisionConflict("claim revision replay is stale")
                acceptance = replay
            else:
                preview, _, proposal, current_reviews = _claim_revision_preview(
                    authority=authority,
                    claim_index=claim_index,
                    body=body,
                    request=request,
                    artifact_store=artifact_store,
                )
                acceptance = accept_claim_revision(
                    authority=authority,
                    owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                    proposal=proposal,
                    reviews=current_reviews,
                    mutation_key=body.mutation_key,
                    expected_proposal_receipt_sha256=body.proposal_receipt_sha256,
                    expected_preview_sha256=body.preview_sha256,
                    expected_transition_sha256=body.transition_sha256,
                    store=artifact_store,
                )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except ClaimRevisionConflict as exc:
        raise _private_artifact_error(409, "claim revision conflict") from exc
    except Exception as exc:
        raise _private_artifact_error(409, "claim revision unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimRevisionCommandOut(status="accepted", acceptance=acceptance)


def _claim_revision_compensation_preview(
    *,
    authority: ArtifactAuthority,
    claim_index: int,
    body: ClaimRevisionCompensationIn,
    artifact_store: FilesystemArtifactStore,
) -> Any:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_revision_compensation import (
        build_claim_revision_compensation_preview,
    )

    current_html = artifact_store.read(authority)
    current_body = parse_body_from_html(current_html)
    if current_body.content_hash() != body.content_hash:
        raise ValueError("claim compensation artifact is stale")
    return build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        prior_body=current_body,
        claim_index=claim_index,
        supersedes_transition_sha256=body.supersedes_transition_sha256,
        operation=body.operation,
        replacement_claim=body.replacement_claim,
        rationale=body.rationale,
        mutation_key=body.mutation_key,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/revision/compensation/preview",
    response_model=ClaimRevisionCompensationCommandOut,
)
def post_claim_revision_compensation_preview(
    investigation_id: str,
    claim_index: int,
    body: ClaimRevisionCompensationIn,
    request: Request,
    response: Response,
) -> ClaimRevisionCompensationCommandOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            preview = _claim_revision_compensation_preview(
                authority=authority,
                claim_index=claim_index,
                body=body,
                artifact_store=artifact_store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(
            409, "claim revision compensation preview unavailable"
        ) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimRevisionCompensationCommandOut(status="candidate", preview=preview.public_dict())


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/revision/compensation/accept",
    response_model=ClaimRevisionCompensationCommandOut,
)
def post_claim_revision_compensation_accept(
    investigation_id: str,
    claim_index: int,
    body: ClaimRevisionCompensationAcceptIn,
    request: Request,
    response: Response,
) -> ClaimRevisionCompensationCommandOut:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_revision_compensation import (
        ClaimRevisionCompensationConflict,
        accept_claim_revision_compensation,
        build_claim_revision_compensation_preview,
        compensation_acceptance,
        replay_claim_revision_compensation,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            current_body = parse_body_from_html(artifact_store.read(authority))
            replay = replay_claim_revision_compensation(
                body=current_body,
                prior_artifact_content_hash=body.content_hash,
                claim_index=claim_index,
                supersedes_transition_sha256=body.supersedes_transition_sha256,
                operation=body.operation,
                replacement_claim=body.replacement_claim,
                rationale=body.rationale,
                mutation_key=body.mutation_key,
            )
            if replay is not None:
                historical_html = artifact_store.read_history(
                    authority, body_content_hash=body.content_hash
                )
                historical_body = parse_body_from_html(historical_html)
                replay_preview = build_claim_revision_compensation_preview(
                    authority=authority,
                    owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                    prior_body=historical_body,
                    claim_index=claim_index,
                    supersedes_transition_sha256=body.supersedes_transition_sha256,
                    operation=body.operation,
                    replacement_claim=body.replacement_claim,
                    rationale=body.rationale,
                    mutation_key=body.mutation_key,
                )
                if (
                    replay_preview.preview_sha256 != body.preview_sha256
                    or replay_preview.compensation.transition_sha256 != body.transition_sha256
                ):
                    raise ClaimRevisionCompensationConflict("claim compensation replay is stale")
                acceptance = compensation_acceptance(
                    replay_preview.prospective_body, replay_preview.compensation
                )
            else:
                _ = _claim_revision_compensation_preview(
                    authority=authority,
                    claim_index=claim_index,
                    body=body,
                    artifact_store=artifact_store,
                )
                acceptance = accept_claim_revision_compensation(
                    authority=authority,
                    owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                    claim_index=claim_index,
                    supersedes_transition_sha256=body.supersedes_transition_sha256,
                    operation=body.operation,
                    replacement_claim=body.replacement_claim,
                    rationale=body.rationale,
                    mutation_key=body.mutation_key,
                    expected_preview_sha256=body.preview_sha256,
                    expected_transition_sha256=body.transition_sha256,
                    store=artifact_store,
                )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except ClaimRevisionCompensationConflict as exc:
        raise _private_artifact_error(409, "claim compensation conflict") from exc
    except Exception as exc:
        raise _private_artifact_error(409, "claim compensation unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimRevisionCompensationCommandOut(status="accepted", acceptance=acceptance)


@artifact_router.get(
    "/{investigation_id}/artifact/history/{content_hash}", response_class=HTMLResponse
)
def get_artifact_history(
    investigation_id: str, content_hash: str, request: Request
) -> HTMLResponse:
    try:
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ValueError("artifact history hash is invalid")
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        historical_html = FilesystemArtifactStore().read_history(
            authority, body_content_hash=content_hash
        )
        historical_body = parse_body_from_html(historical_html)
        if (
            historical_body.investigation_id != authority.investigation_id
            or historical_body.content_hash() != content_hash
        ):
            raise ValueError("artifact history body identity is corrupt")
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "artifact history not found") from exc
    return HTMLResponse(
        historical_html,
        headers={
            "Cache-Control": "private, no-store",
            "X-Antiek-Historical-Content-Hash": content_hash,
        },
    )


def _effective_owner_context_preview(
    *,
    authority: ArtifactAuthority,
    claim_index: int,
    command: EffectiveOwnerContextPreviewIn,
    artifact_store: FilesystemArtifactStore,
) -> tuple[object, ClaimSupportOut, dict[str, object]]:
    """Resolve every selected byte and authority input from locked server state."""
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_challenge import (
        ArchivedInheritedSupport,
        build_effective_owner_claim_context_receipt,
    )

    goal = command.goal.strip()
    mutation_key = command.mutation_key.strip()
    if (
        not goal
        or not mutation_key
        or any(ord(char) < 0x20 and char not in "\n\t" for char in goal)
    ):
        raise ValueError("effective owner context command is invalid")
    artifact = parse_body_from_html(artifact_store.read(authority))
    canonical_hash = artifact.content_hash()
    if canonical_hash != command.content_hash or not 0 <= claim_index < len(artifact.claim_support):
        raise ValueError("artifact claim not found")
    roots = [item for item in artifact.owner_claim_revisions if item.claim_index == claim_index]
    if len(roots) != 1 or artifact.synthesis_event_id is None:
        raise ValueError("effective owner claim is unavailable")
    root = roots[0]
    compensations = tuple(
        item for item in artifact.owner_claim_compensations if item.claim_index == claim_index
    )
    effective = artifact.effective_owner_claim(claim_index)
    if effective is None:
        raise ValueError("effective owner claim is unavailable")
    evaluations = _artifact_claim_evaluations(authority, artifact)
    projection = _claim_support_out(
        authority,
        artifact.claim_support[claim_index],
        content_hash=canonical_hash,
        index=claim_index,
        evaluation=evaluations.get(claim_index),
        owner_revision=root,
        owner_compensations=compensations,
    )
    if projection.evaluation is None:
        raise ValueError("artifact claim evaluation is unavailable")
    transition_hashes = (
        root.transition_sha256,
        *(item.transition_sha256 for item in compensations),
    )
    inherited_context = tuple(
        ArchivedInheritedSupport(**item.model_dump(mode="json"))
        for item in projection.inherited_support
    )
    context_goal = "\n".join(
        (
            "Purpose: investigate an explicitly selected owner-authored current claim.",
            f"Owner-authored current claim (not archive-grounded): {effective[0]}",
            f"Archived terminal evidence baseline (not current owner wording): {projection.claim}",
            "Archived direct evidence receipts: "
            + (", ".join(item.receipt_sha256 for item in projection.direct_evidence) or "none"),
            "Archived inherited support: "
            + (
                json.dumps(
                    [item.model_dump(mode="json") for item in inherited_context],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                or "[]"
            ),
            "Do not treat owner wording as verified evidence or replace the archive.",
            f"Question: {goal}",
        )
    )
    receipt = build_effective_owner_claim_context_receipt(
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        source_asset_id=authority.investigation_id,
        artifact_investigation_digest=authority.investigation_digest,
        artifact_content_hash=canonical_hash,
        synthesis_event_id=artifact.synthesis_event_id,
        claim_index=claim_index,
        claim_id=f"artifact-v2:{canonical_hash}:{claim_index}",
        archived_claim=projection.claim,
        effective_claim=effective[0],
        root_transition_sha256=root.transition_sha256,
        revision_transition_sha256s=transition_hashes,
        evaluation_event_id=projection.evaluation.event_id,
        scorer_id=projection.evaluation.scorer_id,
        relation=projection.evaluation.relation,
        score=projection.evaluation.score,
        evidence_receipt_sha256s=tuple(
            evidence.receipt_sha256 for evidence in projection.direct_evidence
        ),
        archived_inherited_support=inherited_context,
        model_id=(command.model_id or "").strip() or None,
        research_tier=command.research_tier,
        goal=context_goal,
        question=goal,
        mutation_key=mutation_key,
    )
    preview_identity = {
        "receipt_sha256": receipt.receipt_sha256,
        "artifact_content_hash": canonical_hash,
        "archived_claim": projection.claim,
        "effective_claim": effective[0],
        "head_transition_sha256": effective[1],
        "view_mode": command.view_mode,
    }
    preview_sha256 = hashlib.sha256(
        json.dumps(
            preview_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    return (
        receipt,
        projection,
        {
            **preview_identity,
            "preview_sha256": preview_sha256,
            "revision_transition_sha256s": list(transition_hashes),
            "archived_evaluation": {
                "event_id": projection.evaluation.event_id,
                "scorer_id": projection.evaluation.scorer_id,
                "relation": projection.evaluation.relation,
                "score": projection.evaluation.score,
            },
            "archived_direct_evidence_receipt_sha256s": [
                item.receipt_sha256 for item in projection.direct_evidence
            ],
            "archived_inherited_support": [
                item.model_dump(mode="json") for item in inherited_context
            ],
            "archive_grounded": False,
            "grants_authority": False,
            "permits_provider_call": False,
            "permits_spend": False,
            "permits_graph_admission": False,
            "permits_write": False,
            "permits_benchmark_feedback": False,
            "permits_publication": False,
        },
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-context/preview",
    response_model=EffectiveOwnerContextCommandOut,
)
def post_effective_owner_context_preview(
    investigation_id: str,
    claim_index: int,
    body: EffectiveOwnerContextPreviewIn,
    request: Request,
    response: Response,
) -> EffectiveOwnerContextCommandOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        store = FilesystemArtifactStore()
        with store.mutation_lock(authority):
            _, _, preview = _effective_owner_context_preview(
                authority=authority,
                claim_index=claim_index,
                command=body,
                artifact_store=store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "effective owner context unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return EffectiveOwnerContextCommandOut(status="candidate", preview=preview)


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-context/accept",
    response_model=EffectiveOwnerContextCommandOut,
)
def post_effective_owner_context_accept(
    investigation_id: str,
    claim_index: int,
    body: EffectiveOwnerContextAcceptIn,
    request: Request,
    response: Response,
) -> EffectiveOwnerContextCommandOut:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine import HighlightSelection
    from substrate.floating_session import open_from_highlight_with_references

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        store = FilesystemArtifactStore()
        with store.mutation_lock(authority):
            receipt, projection, preview = _effective_owner_context_preview(
                authority=authority,
                claim_index=claim_index,
                command=body,
                artifact_store=store,
            )
            if (
                preview["preview_sha256"] != body.preview_sha256
                or receipt.receipt_sha256 != body.receipt_sha256
            ):
                raise ValueError("effective owner context preview is stale")
            context_goal = "\n".join(
                (
                    "Purpose: investigate an explicitly selected owner-authored current claim.",
                    f"Owner-authored current claim (not archive-grounded): {receipt.effective_claim}",
                    f"Archived terminal evidence baseline (not current owner wording): {receipt.archived_claim}",
                    "Archived direct evidence receipts: "
                    + (", ".join(receipt.archived_evidence_receipt_sha256s) or "none"),
                    "Archived inherited support: "
                    + json.dumps(
                        [
                            item.model_dump(mode="json")
                            for item in receipt.archived_inherited_support
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ),
                    "Do not treat owner wording as verified evidence or replace the archive.",
                    f"Question: {body.goal.strip()}",
                )
            )
            selection = HighlightSelection(
                asset_id=investigation_id,
                selection_text=receipt.effective_claim or "",
                region_id=("effective-owner-context:" + (receipt.mutation_key_sha256 or "")),
                goal_hint=context_goal,
                claim_challenge=receipt.model_dump(mode="json"),
            )
            session = open_from_highlight_with_references(
                selection,
                engagement_store=_eng_for(request),
                session_store=_sess_for(request),
                model_id=receipt.model_id,
                view_mode=body.view_mode,
                research_tier=body.research_tier,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "effective owner context conflict") from exc
    response.headers["Cache-Control"] = "private, no-store"
    reservation = ClaimChallengeOut(
        session_id=session.session_id,
        spawn_id=session.spawn_id,
        investigation_id=session.investigation_id,
        parent_asset_id=session.parent_asset_id,
        selection_text=session.selection_text,
        status=session.status,
        view_mode=session.view_mode,
        model_id=session.model_id,
        research_tier=session.research_tier,
        claim_challenge=dict(session.claim_challenge or {}),
    )
    return EffectiveOwnerContextCommandOut(status="accepted", reservation=reservation)


def _recursive_round_context_preview(
    *,
    authority: ArtifactAuthority,
    claim_index: int,
    command: RecursiveRoundContextPreviewIn,
    request: Request,
    artifact_store: FilesystemArtifactStore,
) -> tuple[object, str, dict[str, object]]:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_challenge import (
        build_recursive_owner_claim_context_receipt,
    )
    from substrate.research_artifact.recursive_round_context import (
        build_recursive_round_context_pack,
        render_recursive_round_context_prompt,
    )

    questions = tuple(question.strip() for question in command.follow_up_questions)
    combined_question = "\n".join(questions)
    if len(combined_question) > 4000:
        raise ValueError("recursive context questions exceed reservation bound")
    ordinary_command = EffectiveOwnerContextPreviewIn(
        content_hash=command.content_hash,
        goal=combined_question,
        mutation_key=command.mutation_key,
        view_mode=command.view_mode,
        model_id=command.model_id,
        research_tier=command.research_tier,
    )
    ordinary_receipt, _, _ = _effective_owner_context_preview(
        authority=authority,
        claim_index=claim_index,
        command=ordinary_command,
        artifact_store=artifact_store,
    )
    artifact = parse_body_from_html(artifact_store.read(authority))
    pack = build_recursive_round_context_pack(
        body=artifact,
        claim_index=claim_index,
        selected_ordinals=tuple(command.selected_round_ordinals),
        follow_up_questions=questions,
        mutation_key=command.mutation_key,
        view_mode=command.view_mode,
        authority=authority,
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
        engagement_store=_eng_for(request),
        session_store=_sess_for(request),
    )
    prompt = render_recursive_round_context_prompt(pack)
    receipt = build_recursive_owner_claim_context_receipt(
        ordinary_receipt=ordinary_receipt,
        recursive_context_pack=pack,
        goal=prompt,
        question=combined_question,
    )
    pack_payload = pack.model_dump(mode="json")
    preview_identity = {
        "receipt_sha256": receipt.receipt_sha256,
        "pack_sha256": pack.pack_sha256,
        "artifact_content_hash": pack.artifact_content_hash,
        "current_effective_claim": pack.current_effective_claim,
        "current_head_transition_sha256": pack.current_head_transition_sha256,
        "selected_round_ordinals": list(pack.selected_ordinals),
        "selected_transition_sha256s": list(pack.selected_transition_sha256s),
        "follow_up_questions": list(pack.follow_up_questions),
        "view_mode": command.view_mode,
    }
    preview_sha256 = hashlib.sha256(
        json.dumps(
            preview_identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return (
        receipt,
        prompt,
        {
            **preview_identity,
            "rows": [row.model_dump(mode="json") for row in pack.rows],
            "pack_bytes": len(
                json.dumps(
                    pack_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ),
            "preview_sha256": preview_sha256,
            "archive_grounded": False,
            "grants_authority": False,
            "permits_provider_call": False,
            "permits_spend": False,
            "permits_graph_admission": False,
            "permits_twin_promotion": False,
            "permits_write": False,
            "permits_benchmark_feedback": False,
            "permits_publication": False,
        },
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/recursive-context/preview",
    response_model=RecursiveRoundContextCommandOut,
)
def post_recursive_round_context_preview(
    investigation_id: str,
    claim_index: int,
    body: RecursiveRoundContextPreviewIn,
    request: Request,
    response: Response,
) -> RecursiveRoundContextCommandOut:
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            _, _, preview = _recursive_round_context_preview(
                authority=authority,
                claim_index=claim_index,
                command=body,
                request=request,
                artifact_store=artifact_store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "recursive context unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return RecursiveRoundContextCommandOut(status="candidate", preview=preview)


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/recursive-context/accept",
    response_model=RecursiveRoundContextCommandOut,
)
def post_recursive_round_context_accept(
    investigation_id: str,
    claim_index: int,
    body: RecursiveRoundContextAcceptIn,
    request: Request,
    response: Response,
) -> RecursiveRoundContextCommandOut:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine import HighlightSelection
    from substrate.floating_session import open_from_highlight_with_references

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            receipt, prompt, preview = _recursive_round_context_preview(
                authority=authority,
                claim_index=claim_index,
                command=body,
                request=request,
                artifact_store=artifact_store,
            )
            if (
                preview["preview_sha256"] != body.preview_sha256
                or receipt.receipt_sha256 != body.receipt_sha256
            ):
                raise ValueError("recursive context preview is stale")
            pack = receipt.recursive_context_pack or {}
            selection = HighlightSelection(
                asset_id=investigation_id,
                selection_text=receipt.effective_claim or "",
                region_id="recursive-owner-context:" + str(pack.get("mutation_key_sha256", "")),
                goal_hint=prompt,
                claim_challenge=receipt.model_dump(mode="json"),
            )
            session = open_from_highlight_with_references(
                selection,
                engagement_store=_eng_for(request),
                session_store=_sess_for(request),
                model_id=receipt.model_id,
                view_mode=body.view_mode,
                research_tier=body.research_tier,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "recursive context conflict") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return RecursiveRoundContextCommandOut(
        status="accepted",
        reservation=ClaimChallengeOut(
            session_id=session.session_id,
            spawn_id=session.spawn_id,
            investigation_id=session.investigation_id,
            parent_asset_id=session.parent_asset_id,
            selection_text=session.selection_text,
            status=session.status,
            view_mode=session.view_mode,
            model_id=session.model_id,
            research_tier=session.research_tier,
            claim_challenge=dict(session.claim_challenge or {}),
        ),
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/challenge",
    response_model=ClaimChallengeOut,
)
async def post_artifact_claim_challenge(
    investigation_id: str,
    claim_index: int,
    body: ClaimChallengeIn,
    request: Request,
    response: Response,
) -> ClaimChallengeOut:
    """Reserve existing floating research against one exact artifact claim.

    All claim/evaluation/evidence inputs are server-resolved before either
    engagement store is requested. Reservation performs no provider call.
    """
    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    try:
        goal = body.goal.strip()
        if not goal or any(ord(char) < 0x20 and char not in "\n\t" for char in goal):
            raise ValueError("challenge goal is invalid")
        html_text, _ = read_canonical_artifact(authority)
        artifact = parse_body_from_html(html_text)
        canonical_hash = artifact.content_hash()
        if canonical_hash != body.content_hash or not 0 <= claim_index < len(
            artifact.claim_support
        ):
            raise ValueError("artifact claim not found")
        evaluations = _artifact_claim_evaluations(authority, artifact)
        projection = _claim_support_out(
            authority,
            artifact.claim_support[claim_index],
            content_hash=canonical_hash,
            index=claim_index,
            evaluation=evaluations.get(claim_index),
        )
        if projection.evaluation is None or artifact.synthesis_event_id is None:
            raise ValueError("artifact claim evaluation is unavailable")
        from substrate.engagement_spine.authority import EngagementAuthority
        from substrate.research_artifact.claim_challenge import (
            build_claim_challenge_receipt,
        )

        challenge_goal = f"Challenge this exact terminal claim: {goal}"
        challenge_model_id = (body.model_id or "").strip() or None
        challenge = build_claim_challenge_receipt(
            owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
            source_asset_id=investigation_id,
            artifact_content_hash=canonical_hash,
            synthesis_event_id=artifact.synthesis_event_id,
            claim_index=claim_index,
            claim_id=f"artifact-v2:{canonical_hash}:{claim_index}",
            claim=projection.claim,
            evaluation_event_id=projection.evaluation.event_id,
            scorer_id=projection.evaluation.scorer_id,
            relation=projection.evaluation.relation,
            score=projection.evaluation.score,
            evidence_receipt_sha256s=tuple(
                evidence.receipt_sha256 for evidence in projection.direct_evidence
            ),
            model_id=challenge_model_id,
            research_tier=body.research_tier,
            goal=challenge_goal,
        )
    except (FileNotFoundError, UnsafeArtifactState, ValueError, TypeError, KeyError) as exc:
        raise _private_artifact_error(404, "artifact claim not found") from exc
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None

    # Mutation begins only after every artifact and legal-read check above.
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine import HighlightSelection
    from substrate.floating_session import open_from_highlight_with_references

    selection = HighlightSelection(
        asset_id=investigation_id,
        selection_text=projection.claim,
        region_id=f"claim-challenge:{challenge.receipt_sha256}",
        goal_hint=challenge_goal,
        claim_challenge=challenge.model_dump(mode="json"),
    )
    try:
        session = open_from_highlight_with_references(
            selection,
            engagement_store=_eng_for(request),
            session_store=_sess_for(request),
            model_id=challenge_model_id,
            view_mode=body.view_mode,
            research_tier=body.research_tier,
        )
    except (ValueError, PermissionError) as exc:
        raise _private_artifact_error(409, "claim challenge reservation conflict") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimChallengeOut(
        session_id=session.session_id,
        spawn_id=session.spawn_id,
        investigation_id=session.investigation_id,
        parent_asset_id=session.parent_asset_id,
        selection_text=session.selection_text,
        status=session.status,
        view_mode=session.view_mode,
        model_id=session.model_id,
        research_tier=session.research_tier,
        claim_challenge=dict(session.claim_challenge or {}),
    )


def _claim_review_candidate(
    *,
    authority: ArtifactAuthority,
    session_id: str,
    request: Request,
    require_current_hash: str | None,
    artifact_store: FilesystemArtifactStore,
) -> tuple[Any, Any, Any]:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_review import resolve_claim_review_candidate

    session_store = _sess_for(request)
    engagement_store = _eng_for(request)
    session_row = session_store.get_session(session_id)
    if session_row is None:
        raise ValueError("claim review session is unavailable")
    spawn_id = session_row.get("spawn_id")
    if not isinstance(spawn_id, str):
        raise ValueError("claim review session is malformed")
    spawn_row = engagement_store.get_spawn(spawn_id)
    if spawn_row is None:
        raise ValueError("claim review spawn is unavailable")
    candidate = resolve_claim_review_candidate(
        session_row=session_row,
        spawn_row=spawn_row,
        owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
    )
    html_text, _ = read_canonical_artifact(authority, store=artifact_store)
    artifact = parse_body_from_html(html_text)
    if (
        artifact.investigation_id != authority.investigation_id
        or candidate.challenge.source_asset_id != authority.investigation_id
        or (
            require_current_hash is not None
            and (
                artifact.content_hash() != require_current_hash
                or candidate.challenge.artifact_content_hash != require_current_hash
            )
        )
    ):
        raise ValueError("claim review artifact identity is stale")
    return candidate, engagement_store, artifact


@artifact_router.post(
    "/{investigation_id}/artifact/owner-contexts/{session_id}/review/preview",
    response_model=EffectiveContextReviewOut,
)
def post_effective_context_review_preview(
    investigation_id: str,
    session_id: str,
    body: EffectiveContextReviewPreviewIn,
    request: Request,
    response: Response,
) -> EffectiveContextReviewOut:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.effective_context_review import (
        build_effective_context_review_preview,
        read_effective_context_proposal,
        read_effective_context_review,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            candidate, engagement_store, _ = _claim_review_candidate(
                authority=authority,
                session_id=session_id,
                request=request,
                require_current_hash=None,
                artifact_store=artifact_store,
            )
            artifact = parse_body_from_html(artifact_store.read(authority))
            if artifact.content_hash() != body.content_hash:
                raise ValueError("effective context review artifact is stale")
            existing = read_effective_context_review(
                candidate.challenge.receipt_sha256, store=engagement_store
            )
            preview = build_effective_context_review_preview(
                candidate,
                artifact=artifact,
                owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                artifact_account_digest=authority.account_digest,
                artifact_investigation_digest=authority.investigation_digest,
                disposition=body.disposition,
                rationale=body.rationale,
                proposed_claim=body.proposed_claim,
                review_state="candidate",
            )
            proposal = (
                read_effective_context_proposal(existing.receipt_sha256, store=engagement_store)
                if existing is not None
                else None
            )
            if existing is not None and (
                existing.artifact_content_hash != artifact.content_hash()
                or existing.claim_index != candidate.challenge.claim_index
                or existing.context_receipt_sha256 != candidate.challenge.receipt_sha256
                or existing.head_transition_sha256 != candidate.challenge.head_transition_sha256
                or existing.session_id != candidate.session_id
                or existing.spawn_id != candidate.spawn_id
                or existing.candidate_sha256 != candidate.candidate_sha256
                or existing.candidate_text != candidate.candidate_text
                or existing.disposition != body.disposition
                or existing.rationale != body.rationale
                or (
                    body.disposition == "propose_compensation"
                    and (
                        proposal is None
                        or proposal.proposed_claim != body.proposed_claim
                        or proposal.rationale != body.rationale
                    )
                )
                or (body.disposition == "retain_current" and proposal is not None)
            ):
                raise ValueError("effective context review command conflicts")
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "effective context review unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return EffectiveContextReviewOut(
        status="accepted" if existing else "candidate",
        preview=preview.public_dict(),
        acceptance=existing.model_dump(mode="json") if existing else None,
        proposal=proposal.model_dump(mode="json") if proposal else None,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/owner-contexts/{session_id}/review/accept",
    response_model=EffectiveContextReviewOut,
)
def post_effective_context_review_accept(
    investigation_id: str,
    session_id: str,
    body: EffectiveContextReviewAcceptIn,
    request: Request,
    response: Response,
) -> EffectiveContextReviewOut:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.effective_context_review import (
        accept_effective_context_review,
        build_effective_context_review_preview,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            candidate, engagement_store, _ = _claim_review_candidate(
                authority=authority,
                session_id=session_id,
                request=request,
                require_current_hash=None,
                artifact_store=artifact_store,
            )
            artifact = parse_body_from_html(artifact_store.read(authority))
            if artifact.content_hash() != body.content_hash:
                raise ValueError("effective context review artifact is stale")
            owner_digest = EngagementAuthority(authority.account_id).account_digest
            preview = build_effective_context_review_preview(
                candidate,
                artifact=artifact,
                owner_account_digest=owner_digest,
                artifact_account_digest=authority.account_digest,
                artifact_investigation_digest=authority.investigation_digest,
                disposition=body.disposition,
                rationale=body.rationale,
                proposed_claim=body.proposed_claim,
            )
            acceptance, proposal = accept_effective_context_review(
                preview,
                owner_account_digest=owner_digest,
                artifact_account_digest=authority.account_digest,
                artifact_investigation_digest=authority.investigation_digest,
                expected_preview_sha256=body.preview_sha256,
                mutation_key=body.mutation_key,
                store=engagement_store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "effective context review conflict") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return EffectiveContextReviewOut(
        status="accepted",
        preview=preview.public_dict(),
        acceptance=acceptance.model_dump(mode="json"),
        proposal=proposal.model_dump(mode="json") if proposal else None,
    )


@artifact_router.get(
    "/{investigation_id}/artifact/owner-contexts/{session_id}/review",
    response_model=EffectiveContextReviewReadOut,
)
def get_effective_context_review(
    investigation_id: str,
    session_id: str,
    request: Request,
    response: Response,
) -> EffectiveContextReviewReadOut:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_revision_compensation import (
        compensation_acceptance,
    )
    from substrate.research_artifact.effective_context_compensation import (
        validate_effective_context_proposal,
    )
    from substrate.research_artifact.effective_context_review import (
        read_effective_context_proposal,
        read_effective_context_review,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            candidate, engagement_store, _ = _claim_review_candidate(
                authority=authority,
                session_id=session_id,
                request=request,
                require_current_hash=None,
                artifact_store=artifact_store,
            )
            artifact = parse_body_from_html(artifact_store.read(authority))
            acceptance = read_effective_context_review(
                candidate.challenge.receipt_sha256, store=engagement_store
            )
            if acceptance is None:
                raise ValueError("effective context review is unavailable")
            proposal = read_effective_context_proposal(
                acceptance.receipt_sha256, store=engagement_store
            )
            if (acceptance.disposition == "propose_compensation" and proposal is None) or (
                acceptance.disposition == "retain_current" and proposal is not None
            ):
                raise RuntimeError("effective context review proposal parity is corrupt")
            if proposal is not None:
                validate_effective_context_proposal(
                    proposal=proposal,
                    review=acceptance,
                    authority=authority,
                    owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                )
            effective = artifact.effective_owner_claim(candidate.challenge.claim_index)
            consumed = (
                [
                    item
                    for item in artifact.owner_claim_compensations
                    if getattr(item, "source_proposal_receipt_sha256", None)
                    == proposal.receipt_sha256
                ]
                if proposal is not None
                else []
            )
            if (
                effective is None
                or acceptance.candidate_sha256 != candidate.candidate_sha256
                or acceptance.candidate_text != candidate.candidate_text
                or (
                    not consumed
                    and (
                        artifact.content_hash() != acceptance.artifact_content_hash
                        or effective[1] != acceptance.head_transition_sha256
                    )
                )
                or len(consumed) > 1
                or (
                    consumed
                    and (
                        proposal is None
                        or consumed[0].prior_artifact_content_hash
                        != acceptance.artifact_content_hash
                        or consumed[0].supersedes_transition_sha256
                        != acceptance.head_transition_sha256
                        or consumed[0].replacement_claim != proposal.proposed_claim
                        or consumed[0].rationale != proposal.rationale
                        or consumed[0].source_context_receipt_sha256
                        != proposal.context_receipt_sha256
                        or consumed[0].source_review_receipt_sha256
                        != proposal.review_receipt_sha256
                    )
                )
            ):
                raise ValueError("effective context review is stale")
            consumption = None
            if consumed:
                consumed_index = artifact.owner_claim_compensations.index(consumed[0])
                consumed_body = ResearchArtifactBody.model_validate(
                    {
                        **artifact.model_dump(mode="json"),
                        "owner_claim_compensations": [
                            item.model_dump(mode="json")
                            for item in artifact.owner_claim_compensations[: consumed_index + 1]
                        ],
                    }
                )
                consumption = compensation_acceptance(consumed_body, consumed[0])
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "effective context review not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return EffectiveContextReviewReadOut(
        status="accepted",
        archived_claim=candidate.challenge.archived_claim or "",
        archived_evaluation={
            "event_id": candidate.challenge.archived_evaluation_event_id,
            "scorer_id": candidate.challenge.archived_scorer_id,
            "relation": candidate.challenge.archived_relation,
            "score": candidate.challenge.archived_score,
        },
        archived_direct_evidence_receipt_sha256s=list(
            candidate.challenge.archived_evidence_receipt_sha256s
        ),
        archived_inherited_support=[
            item.model_dump(mode="json") for item in candidate.challenge.archived_inherited_support
        ],
        effective_claim=effective[0],
        candidate_text=candidate.candidate_text,
        acceptance=acceptance.model_dump(mode="json"),
        proposal=proposal.model_dump(mode="json") if proposal else None,
        consumption=consumption,
    )


def _effective_context_compensation_sources(
    *,
    authority: ArtifactAuthority,
    session_id: str,
    proposal_receipt_sha256: str,
    request: Request,
    artifact_store: FilesystemArtifactStore,
) -> tuple[Any, Any, Any]:
    from substrate.research_artifact.effective_context_review import (
        read_effective_context_proposal,
        read_effective_context_review,
    )

    candidate, engagement_store, _ = _claim_review_candidate(
        authority=authority,
        session_id=session_id,
        request=request,
        require_current_hash=None,
        artifact_store=artifact_store,
    )
    review = read_effective_context_review(
        candidate.challenge.receipt_sha256, store=engagement_store
    )
    if review is None:
        raise ValueError("effective context review is unavailable")
    proposal = read_effective_context_proposal(review.receipt_sha256, store=engagement_store)
    if (
        proposal is None
        or proposal.receipt_sha256 != proposal_receipt_sha256
        or review.session_id != session_id
        or review.candidate_sha256 != candidate.candidate_sha256
        or review.candidate_text != candidate.candidate_text
    ):
        raise ValueError("effective context proposal is unavailable")
    return candidate, review, proposal


@artifact_router.post(
    "/{investigation_id}/artifact/owner-contexts/{session_id}/review/compensation/preview",
    response_model=ClaimRevisionCompensationCommandOut,
)
def post_effective_context_compensation_preview(
    investigation_id: str,
    session_id: str,
    body: EffectiveContextCompensationPreviewIn,
    request: Request,
    response: Response,
) -> ClaimRevisionCompensationCommandOut:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.effective_context_compensation import (
        build_effective_context_compensation_preview,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            _, review, proposal = _effective_context_compensation_sources(
                authority=authority,
                session_id=session_id,
                proposal_receipt_sha256=body.proposal_receipt_sha256,
                request=request,
                artifact_store=artifact_store,
            )
            current = parse_body_from_html(artifact_store.read(authority))
            if current.content_hash() != body.content_hash:
                raise ValueError("effective context compensation artifact is stale")
            preview = build_effective_context_compensation_preview(
                proposal=proposal,
                review=review,
                authority=authority,
                owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                prior_body=current,
                mutation_key=body.mutation_key,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(
            409, "effective context compensation preview unavailable"
        ) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimRevisionCompensationCommandOut(status="candidate", preview=preview.public_dict())


@artifact_router.post(
    "/{investigation_id}/artifact/owner-contexts/{session_id}/review/compensation/accept",
    response_model=ClaimRevisionCompensationCommandOut,
)
def post_effective_context_compensation_accept(
    investigation_id: str,
    session_id: str,
    body: EffectiveContextCompensationAcceptIn,
    request: Request,
    response: Response,
) -> ClaimRevisionCompensationCommandOut:
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.claim_revision_compensation import (
        ClaimRevisionCompensationConflict,
        accept_claim_revision_compensation,
        compensation_acceptance,
    )
    from substrate.research_artifact.effective_context_compensation import (
        build_effective_context_compensation_preview,
        replay_effective_context_compensation,
        validate_effective_context_proposal,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        owner_digest = EngagementAuthority(authority.account_id).account_digest
        with artifact_store.mutation_lock(authority):
            _, review, proposal = _effective_context_compensation_sources(
                authority=authority,
                session_id=session_id,
                proposal_receipt_sha256=body.proposal_receipt_sha256,
                request=request,
                artifact_store=artifact_store,
            )
            validate_effective_context_proposal(
                proposal=proposal,
                review=review,
                authority=authority,
                owner_account_digest=owner_digest,
            )
            current = parse_body_from_html(artifact_store.read(authority))
            replay = replay_effective_context_compensation(
                body=current, proposal=proposal, mutation_key=body.mutation_key
            )
            if replay is not None:
                historical = parse_body_from_html(
                    artifact_store.read_history(
                        authority, body_content_hash=proposal.artifact_content_hash
                    )
                )
                replay_preview = build_effective_context_compensation_preview(
                    proposal=proposal,
                    review=review,
                    authority=authority,
                    owner_account_digest=owner_digest,
                    prior_body=historical,
                    mutation_key=body.mutation_key,
                )
                if (
                    replay_preview.preview_sha256 != body.preview_sha256
                    or replay_preview.compensation.transition_sha256 != body.transition_sha256
                ):
                    raise ClaimRevisionCompensationConflict(
                        "effective context compensation replay is stale"
                    )
                acceptance = compensation_acceptance(
                    replay_preview.prospective_body, replay_preview.compensation
                )
            else:
                if current.content_hash() != body.content_hash:
                    raise ClaimRevisionCompensationConflict(
                        "effective context compensation artifact is stale"
                    )
                acceptance = accept_claim_revision_compensation(
                    authority=authority,
                    owner_account_digest=owner_digest,
                    claim_index=proposal.claim_index,
                    supersedes_transition_sha256=proposal.head_transition_sha256,
                    operation="supersede_owner_revision",
                    replacement_claim=proposal.proposed_claim,
                    rationale=proposal.rationale,
                    mutation_key=body.mutation_key,
                    expected_preview_sha256=body.preview_sha256,
                    expected_transition_sha256=body.transition_sha256,
                    store=artifact_store,
                    source_context_receipt_sha256=proposal.context_receipt_sha256,
                    source_review_receipt_sha256=proposal.review_receipt_sha256,
                    source_proposal_receipt_sha256=proposal.receipt_sha256,
                )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except ClaimRevisionCompensationConflict as exc:
        raise _private_artifact_error(409, "effective context compensation conflict") from exc
    except Exception as exc:
        raise _private_artifact_error(409, "effective context compensation unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimRevisionCompensationCommandOut(status="accepted", acceptance=acceptance)


@artifact_router.get(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-iterations",
    response_model=EffectiveClaimIterationsOut,
)
def get_effective_claim_iterations(
    investigation_id: str,
    claim_index: int,
    request: Request,
    response: Response,
) -> EffectiveClaimIterationsOut:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.effective_claim_iterations import (
        project_effective_claim_iterations,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            artifact = parse_body_from_html(artifact_store.read(authority))
            effective = artifact.effective_owner_claim(claim_index)
            if effective is None:
                raise ValueError("effective owner claim is unavailable")
            projected = project_effective_claim_iterations(
                body=artifact,
                claim_index=claim_index,
                authority=authority,
                owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
                engagement_store=_eng_for(request),
                session_store=_sess_for(request),
            )
            current_hash = artifact.content_hash()
            rows = []
            for item in projected:
                row = item.public_dict()
                result_hash = item.result_body.content_hash()
                rows.append(
                    EffectiveClaimIterationOut(
                        **row,
                        prior_html_url=str(
                            request.url_for(
                                "get_artifact_history",
                                investigation_id=investigation_id,
                                content_hash=item.prior_body.content_hash(),
                            )
                        ),
                        result_html_url=str(
                            request.url_for(
                                "get_artifact_iteration_result",
                                investigation_id=investigation_id,
                                content_hash=result_hash,
                            )
                        ),
                        result_is_current=result_hash == current_hash,
                    )
                )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "effective claim iterations not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return EffectiveClaimIterationsOut(
        investigation_id=investigation_id,
        claim_index=claim_index,
        artifact_content_hash=current_hash,
        current_effective_claim=effective[0],
        current_head_transition_sha256=effective[1],
        next_round_eligible=len(artifact.owner_claim_compensations) < 1000,
        rounds=rows,
    )


@artifact_router.get(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-iterations/{ordinal}",
    response_model=EffectiveClaimIterationOut,
)
def get_effective_claim_iteration(
    investigation_id: str,
    claim_index: int,
    ordinal: int,
    request: Request,
    response: Response,
) -> EffectiveClaimIterationOut:
    """Return one fully reopenable round without weakening collection fencing."""
    projected = get_effective_claim_iterations(
        investigation_id=investigation_id,
        claim_index=claim_index,
        request=request,
        response=response,
    )
    if ordinal < 1 or ordinal > len(projected.rounds):
        raise _private_artifact_error(404, "effective claim iteration not found")
    response.headers["Cache-Control"] = "private, no-store"
    return projected.rounds[ordinal - 1]


@artifact_router.get(
    "/{investigation_id}/artifact/iteration-results/{content_hash}",
    response_class=HTMLResponse,
)
def get_artifact_iteration_result(
    investigation_id: str, content_hash: str, request: Request
) -> HTMLResponse:
    """Reopen exact iteration-result bytes whether they are current or historical."""
    try:
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ValueError("iteration result hash is invalid")
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            current_html = artifact_store.read(authority)
            current_body = parse_body_from_html(current_html)
            if current_body.content_hash() == content_hash:
                exact_html = current_html
            else:
                exact_html = artifact_store.read_history(authority, body_content_hash=content_hash)
            exact_body = parse_body_from_html(exact_html)
            if (
                exact_body.investigation_id != authority.investigation_id
                or exact_body.content_hash() != content_hash
            ):
                raise ValueError("iteration result identity is corrupt")
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "iteration result not found") from exc
    return HTMLResponse(
        exact_html,
        headers={
            "Cache-Control": "private, no-store",
            "X-Antiek-Iteration-Result-Content-Hash": content_hash,
        },
    )


def _reasoning_ancestry_response(
    *,
    investigation_id: str,
    claim_index: int,
    request: Request,
) -> ReasoningAncestryOut:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.reasoning_ancestry import (
        project_reasoning_ancestry,
    )

    authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
    artifact_store = FilesystemArtifactStore()
    with artifact_store.mutation_lock(authority):
        artifact = parse_body_from_html(artifact_store.read(authority))
        effective = artifact.effective_owner_claim(claim_index)
        if effective is None:
            raise ValueError("reasoning ancestry effective claim is unavailable")
        projected = project_reasoning_ancestry(
            body=artifact,
            claim_index=claim_index,
            authority=authority,
            owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
            engagement_store=_eng_for(request),
            session_store=_sess_for(request),
        )
        rows = []
        for node in projected:
            public = node.public_dict()
            prior_hash = node.iteration.prior_body.content_hash()
            result_hash = node.iteration.result_body.content_hash()
            rows.append(
                ReasoningAncestryNodeOut(
                    **public,
                    recursive_context_pack=(
                        dict(node.iteration.candidate.challenge.recursive_context_pack)
                        if node.iteration.candidate.challenge.recursive_context_pack
                        else None
                    ),
                    prior_html_url=str(
                        request.url_for(
                            "get_artifact_history",
                            investigation_id=investigation_id,
                            content_hash=prior_hash,
                        )
                    ),
                    result_html_url=str(
                        request.url_for(
                            "get_artifact_iteration_result",
                            investigation_id=investigation_id,
                            content_hash=result_hash,
                        )
                    ),
                )
            )
    graph_sha256 = hashlib.sha256(
        json.dumps(
            [
                {
                    "ordinal": row.ordinal,
                    "ancestry_sha256": row.ancestry_sha256,
                    "child_ordinals": row.child_ordinals,
                }
                for row in rows
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ReasoningAncestryOut(
        investigation_id=investigation_id,
        claim_index=claim_index,
        artifact_content_hash=artifact.content_hash(),
        current_effective_claim=effective[0],
        current_head_transition_sha256=effective[1],
        graph_sha256=graph_sha256,
        nodes=rows,
    )


@artifact_router.get(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-ancestry",
    response_model=ReasoningAncestryOut,
)
def get_reasoning_ancestry(
    investigation_id: str,
    claim_index: int,
    request: Request,
    response: Response,
) -> ReasoningAncestryOut:
    try:
        result = _reasoning_ancestry_response(
            investigation_id=investigation_id,
            claim_index=claim_index,
            request=request,
        )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "reasoning ancestry not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return result


@artifact_router.get(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-ancestry/{ordinal}",
    response_model=ReasoningAncestryNodeOut,
)
def get_reasoning_ancestry_node(
    investigation_id: str,
    claim_index: int,
    ordinal: int,
    request: Request,
    response: Response,
) -> ReasoningAncestryNodeOut:
    graph = get_reasoning_ancestry(
        investigation_id=investigation_id,
        claim_index=claim_index,
        request=request,
        response=response,
    )
    if ordinal < 1 or ordinal > len(graph.nodes):
        raise _private_artifact_error(404, "reasoning ancestry node not found")
    return graph.nodes[ordinal - 1]


@artifact_router.get(
    "/{investigation_id}/artifact/claims/{claim_index}/owner-ancestry/{ordinal}/path",
    response_model=ReasoningAncestryOut,
)
def get_reasoning_ancestry_path(
    investigation_id: str,
    claim_index: int,
    ordinal: int,
    request: Request,
    response: Response,
) -> ReasoningAncestryOut:
    graph = get_reasoning_ancestry(
        investigation_id=investigation_id,
        claim_index=claim_index,
        request=request,
        response=response,
    )
    if ordinal < 1 or ordinal > len(graph.nodes):
        raise _private_artifact_error(404, "reasoning ancestry path not found")
    included: set[int] = set()
    pending = [ordinal]
    while pending:
        current = pending.pop()
        if current in included:
            continue
        included.add(current)
        pending.extend(graph.nodes[current - 1].parent_ordinals)
    graph.nodes = [
        node.model_copy(
            update={"child_ordinals": [child for child in node.child_ordinals if child in included]}
        )
        for node in graph.nodes
        if node.ordinal in included
    ]
    graph.graph_sha256 = hashlib.sha256(
        json.dumps(
            [
                {
                    "ordinal": node.ordinal,
                    "ancestry_sha256": node.ancestry_sha256,
                    "child_ordinals": node.child_ordinals,
                }
                for node in graph.nodes
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return graph


def _ancestry_interrogation_projection(
    *,
    investigation_id: str,
    claim_index: int,
    body: ReasoningAncestryInterrogationIn,
    request: Request,
    accept: bool,
) -> ReasoningAncestryInterrogationOut:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.engagement_spine.authority import EngagementAuthority
    from substrate.research_artifact.reasoning_ancestry import (
        project_reasoning_ancestry,
    )
    from substrate.research_artifact.reasoning_ancestry_interrogation import (
        accept_reasoning_ancestry_interrogation,
        build_reasoning_ancestry_interrogation,
    )

    authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
    engagement_store = _eng_for(request)
    artifact_store = FilesystemArtifactStore()
    with artifact_store.mutation_lock(authority):
        artifact = parse_body_from_html(artifact_store.read(authority))
        if artifact.content_hash() != body.content_hash:
            raise ValueError("ancestry interrogation artifact is stale")
        nodes = project_reasoning_ancestry(
            body=artifact,
            claim_index=claim_index,
            authority=authority,
            owner_account_digest=EngagementAuthority(authority.account_id).account_digest,
            engagement_store=engagement_store,
            session_store=_sess_for(request),
        )
        receipt, manifest = build_reasoning_ancestry_interrogation(
            body=artifact,
            claim_index=claim_index,
            nodes=nodes,
            selected_terminal_ordinals=body.selected_terminal_ordinals,
            question=body.question,
            mutation_key=body.mutation_key,
            artifact_authority=authority,
            engagement_store=engagement_store,
        )
        receipt_document = receipt.document()
        preview_sha256 = hashlib.sha256(
            json.dumps(
                receipt_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if accept:
            if not isinstance(body, ReasoningAncestryInterrogationAcceptIn) or (
                body.preview_sha256 != preview_sha256
                or body.receipt_sha256 != receipt.receipt_sha256
            ):
                raise ValueError("ancestry interrogation preview is stale")
            receipt = accept_reasoning_ancestry_interrogation(
                receipt, engagement_store=engagement_store
            )
    return ReasoningAncestryInterrogationOut(
        status="accepted" if accept else "candidate",
        preview_sha256=preview_sha256,
        receipt=receipt.document(),
        manifest=manifest.receipt(),
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/ancestry-interrogation/preview",
    response_model=ReasoningAncestryInterrogationOut,
)
def post_reasoning_ancestry_interrogation_preview(
    investigation_id: str,
    claim_index: int,
    body: ReasoningAncestryInterrogationIn,
    request: Request,
    response: Response,
) -> ReasoningAncestryInterrogationOut:
    try:
        result = _ancestry_interrogation_projection(
            investigation_id=investigation_id,
            claim_index=claim_index,
            body=body,
            request=request,
            accept=False,
        )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "ancestry interrogation is unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return result


@artifact_router.post(
    "/{investigation_id}/artifact/claims/{claim_index}/ancestry-interrogation/accept",
    response_model=ReasoningAncestryInterrogationOut,
)
def post_reasoning_ancestry_interrogation_accept(
    investigation_id: str,
    claim_index: int,
    body: ReasoningAncestryInterrogationAcceptIn,
    request: Request,
    response: Response,
) -> ReasoningAncestryInterrogationOut:
    try:
        result = _ancestry_interrogation_projection(
            investigation_id=investigation_id,
            claim_index=claim_index,
            body=body,
            request=request,
            accept=True,
        )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(409, "ancestry interrogation was not accepted") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return result


@artifact_router.get(
    "/{investigation_id}/artifact/ancestry-interrogations/{receipt_id}",
    response_model=ReasoningAncestryInterrogationOut,
)
def get_reasoning_ancestry_interrogation(
    investigation_id: str,
    receipt_id: str,
    request: Request,
    response: Response,
) -> ReasoningAncestryInterrogationOut:
    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from substrate.research_artifact.reasoning_ancestry_interrogation_resolution import (
        resolve_reasoning_ancestry_interrogation,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        engagement_store = _eng_for(request)
        resolved = resolve_reasoning_ancestry_interrogation(
            authority=authority,
            receipt_id=receipt_id,
            engagement_store=engagement_store,
            session_store=_sess_for(request),
        )
        receipt_document = resolved.receipt.document()
        preview_sha256 = hashlib.sha256(
            json.dumps(
                receipt_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        raise _private_artifact_error(404, "ancestry interrogation not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ReasoningAncestryInterrogationOut(
        status="accepted",
        preview_sha256=preview_sha256,
        receipt=receipt_document,
        manifest=resolved.manifest.receipt(),
        stale=resolved.stale,
    )


@artifact_router.get(
    "/{investigation_id}/artifact/ancestry-interrogations/{receipt_id}/continuation-options",
    response_model=AncestryContinuationOptionsOut,
)
def get_reasoning_ancestry_continuation_options(
    investigation_id: str,
    receipt_id: str,
    request: Request,
    response: Response,
) -> AncestryContinuationOptionsOut:
    """Project exact executable model choices without issuing authority."""

    import math

    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from interfaces.research.api.settings_budget import (
        _dispatch_config_path,
        read_operator_budget,
    )
    from substrate.dispatch.daily_research_budget import (
        configured_daily_research_cap,
        read_daily_research_budget,
    )
    from substrate.dispatch.research_cost_envelope import (
        build_whole_run_cost_envelope,
    )
    from substrate.dispatch.research_quote import build_research_route_manifest
    from substrate.dispatch.router import DispatchConfig
    from substrate.engagement_spine.collective_manifest import (
        project_collective_manifest,
    )
    from substrate.research_artifact.reasoning_ancestry_interrogation_resolution import (
        resolve_reasoning_ancestry_interrogation,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        engagement_store = _eng_for(request)
        resolved = resolve_reasoning_ancestry_interrogation(
            authority=authority,
            receipt_id=receipt_id,
            engagement_store=engagement_store,
            session_store=_sess_for(request),
        )
        manifest, unit = project_collective_manifest(
            resolved.receipt.manifest_id, store=engagement_store
        )
        if manifest.manifest_id != resolved.manifest.manifest_id:
            raise ValueError("ancestry continuation manifest conflicts")
        context = f"## Interrogation question\n{resolved.receipt.question}\n\n{unit.prompt_block()}"
        context_sha256 = hashlib.sha256(context.encode("utf-8")).hexdigest()
        input_tokens = max(1, math.ceil(len(context.encode("utf-8")) / 4))
        route_manifest = build_research_route_manifest(
            DispatchConfig.from_yaml(_dispatch_config_path())
        )
        budget = read_operator_budget()
        daily_cap = configured_daily_research_cap()
        daily_snapshot = read_daily_research_budget(
            account_id=authority.account_id, cap_usd=daily_cap
        )
        budget.daily_cap_usd = float(daily_cap)
        budget.spent_usd = daily_snapshot.settled_cents / 100
        budget.remaining_usd = daily_snapshot.remaining_cents / 100
        budget.spent_status = "known"
        budget.notes.append(f"atomic research holds: ${daily_snapshot.held_cents / 100:.2f}")
        ready_raw = getattr(request.app.state, "registered_providers", None)
        ready = (
            {str(item) for item in ready_raw}
            if isinstance(ready_raw, (set, frozenset, list, tuple))
            else set()
        )
        choices: list[AncestryContinuationChoiceOut] = []
        for route in route_manifest.routes:
            if route.role != "synthesizer":
                continue
            base = (
                input_tokens * route.input_per_mtok
                + route.max_output_tokens * route.output_per_mtok
            ) / 1_000_000
            low = round(base * 0.8, 8)
            high = round(base * 1.2, 8)
            remaining_after = (
                round(budget.remaining_usd - high, 8) if budget.remaining_usd is not None else None
            )
            boot_ready = route.provider in ready
            route_identity = hashlib.sha256(
                json.dumps(
                    route.__dict__,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            whole_run = build_whole_run_cost_envelope(
                route_manifest,
                selected_driver_role="synthesizer",
                selected_driver_provider=route.provider,
                selected_driver_model=route.model,
                selected_driver_pricing_fingerprint=route.pricing_fingerprint,
            )
            choices.append(
                AncestryContinuationChoiceOut(
                    provider_id=route.provider,
                    model_id=route.model,
                    fallback_index=route.fallback_index,
                    route_identity=route_identity,
                    pricing_fingerprint=route.pricing_fingerprint,
                    estimated_usd_low=low,
                    estimated_usd_high=high,
                    remaining_after_high_usd=remaining_after,
                    would_exceed_budget=(
                        high > budget.remaining_usd if budget.remaining_usd is not None else None
                    ),
                    pricing_source_url=route.source_url,
                    pricing_verified_at=route.verified_at,
                    pricing_expires_at=route.expires_at,
                    boot_ready=boot_ready,
                    available=boot_ready,
                    reason=(
                        "boot-ready with fresh canonical pricing"
                        if boot_ready
                        else "provider adapter is not boot-ready"
                    ),
                    whole_run_envelope={
                        **whole_run.__dict__,
                        "roles": [row.__dict__ for row in whole_run.roles],
                    },
                )
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except KeyError as exc:
        raise _private_artifact_error(404, "ancestry interrogation not found") from exc
    except Exception as exc:
        raise _private_artifact_error(503, "ancestry continuation options unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return AncestryContinuationOptionsOut(
        investigation_id=investigation_id,
        receipt_id=receipt_id,
        receipt_sha256=resolved.receipt.receipt_sha256,
        context_sha256=context_sha256,
        stale=resolved.stale,
        assumed_input_tokens=input_tokens,
        choices=choices,
        budget=budget.model_dump(mode="json"),
    )


def _ancestry_continuation_command(
    *,
    investigation_id: str,
    receipt_id: str,
    receipt_sha256: str,
    context_sha256: str,
    provider_id: str,
    model_id: str,
    pricing_fingerprint: str,
    research_tier: str,
    approved_run_ceiling_usd: float,
    workload_plan_sha256: str,
    whole_run_maximum_usd: str,
) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "kind": "ancestry_collective_continuation",
            "investigation_id": investigation_id,
            "receipt_id": receipt_id,
            "receipt_sha256": receipt_sha256,
            "context_sha256": context_sha256,
            "selected_driver": {
                "role": "synthesizer",
                "provider": provider_id,
                "model": model_id,
                "pricing_fingerprint": pricing_fingerprint,
            },
            "research_tier": research_tier,
            "approved_run_ceiling_usd": f"{approved_run_ceiling_usd:.2f}",
            "workload_plan_sha256": workload_plan_sha256,
            "whole_run_maximum_usd": whole_run_maximum_usd,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _ancestry_whole_run_envelope(body: AncestryContinuationQuoteIn):
    from interfaces.research.api.settings_budget import _dispatch_config_path
    from substrate.dispatch.research_cost_envelope import (
        build_whole_run_cost_envelope,
    )
    from substrate.dispatch.research_quote import build_research_route_manifest
    from substrate.dispatch.router import DispatchConfig

    manifest = build_research_route_manifest(DispatchConfig.from_yaml(_dispatch_config_path()))
    envelope = build_whole_run_cost_envelope(
        manifest,
        selected_driver_role="synthesizer",
        selected_driver_provider=body.provider_id,
        selected_driver_model=body.model_id,
        selected_driver_pricing_fingerprint=body.pricing_fingerprint,
    )
    return manifest, envelope


def _require_ancestry_continuation_budget(account_id: str, approved_run_ceiling_usd: float) -> None:
    from substrate.dispatch.daily_research_budget import (
        configured_daily_research_cap,
        read_daily_research_budget,
    )

    cap = configured_daily_research_cap()
    budget = read_daily_research_budget(account_id=account_id, cap_usd=cap)
    if approved_run_ceiling_usd * 100 > budget.remaining_cents:
        raise ValueError("approved run ceiling exceeds known remaining budget")


@artifact_router.post(
    "/{investigation_id}/artifact/ancestry-interrogations/{receipt_id}/continuation/quote",
    response_model=AncestryContinuationQuoteOut,
)
def post_reasoning_ancestry_continuation_quote(
    investigation_id: str,
    receipt_id: str,
    body: AncestryContinuationQuoteIn,
    request: Request,
    response: Response,
) -> AncestryContinuationQuoteOut:
    """Issue exact short-lived authority; never reserve or dispatch."""

    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from interfaces.research.api.research_quote_authority import (
        issue_exact_research_quote,
    )
    from substrate.engagement_spine.collective_manifest import (
        project_collective_manifest,
    )
    from substrate.research_artifact.reasoning_ancestry_interrogation_resolution import (
        resolve_reasoning_ancestry_interrogation,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        engagement_store = _eng_for(request)
        resolved = resolve_reasoning_ancestry_interrogation(
            authority=authority,
            receipt_id=receipt_id,
            engagement_store=engagement_store,
            session_store=_sess_for(request),
        )
        if resolved.receipt.receipt_sha256 != body.expected_receipt_sha256:
            raise ValueError("ancestry continuation receipt changed after review")
        manifest, unit = project_collective_manifest(
            resolved.receipt.manifest_id, store=engagement_store
        )
        if manifest.manifest_id != resolved.manifest.manifest_id:
            raise ValueError("ancestry continuation manifest conflicts")
        context = f"## Interrogation question\n{resolved.receipt.question}\n\n{unit.prompt_block()}"
        context_sha256 = hashlib.sha256(context.encode("utf-8")).hexdigest()
        expected_manifest, whole_run = _ancestry_whole_run_envelope(body)
        command = _ancestry_continuation_command(
            investigation_id=investigation_id,
            receipt_id=receipt_id,
            receipt_sha256=resolved.receipt.receipt_sha256,
            context_sha256=context_sha256,
            provider_id=body.provider_id,
            model_id=body.model_id,
            pricing_fingerprint=body.pricing_fingerprint,
            research_tier=body.research_tier,
            approved_run_ceiling_usd=body.approved_run_ceiling_usd,
            workload_plan_sha256=whole_run.plan_sha256,
            whole_run_maximum_usd=whole_run.maximum_usd,
        )
        _require_ancestry_continuation_budget(authority.account_id, body.approved_run_ceiling_usd)
        token, quote, issued_manifest = issue_exact_research_quote(
            request=request,
            command=command,
            research_tier=body.research_tier,
            approved_run_ceiling_usd=body.approved_run_ceiling_usd,
            selected_driver_role="synthesizer",
            selected_driver_provider=body.provider_id,
            selected_driver_model=body.model_id,
            selected_driver_pricing_fingerprint=body.pricing_fingerprint,
        )
        if issued_manifest.fingerprint != expected_manifest.fingerprint:
            raise ValueError("ancestry continuation pricing changed during quote")
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except KeyError as exc:
        raise _private_artifact_error(404, "ancestry interrogation not found") from exc
    except ResearchCostEnvelopeInvalid as exc:
        raise _private_artifact_error(503, "ancestry continuation quote unavailable") from exc
    except ValueError as exc:
        raise _private_artifact_error(409, str(exc)) from exc
    except Exception as exc:
        raise _private_artifact_error(503, "ancestry continuation quote unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return AncestryContinuationQuoteOut(
        quote_token=token,
        quote_id=quote.quote_id,
        quote_payload_sha256=quote.payload_sha256,
        route_manifest_fingerprint=quote.route_manifest_fingerprint,
        context_sha256=context_sha256,
        receipt_sha256=resolved.receipt.receipt_sha256,
        selected_driver_provider=quote.selected_driver_provider or "",
        selected_driver_model=quote.selected_driver_model or "",
        selected_driver_pricing_fingerprint=(quote.selected_driver_pricing_fingerprint or ""),
        workload_plan_sha256=whole_run.plan_sha256,
        whole_run_maximum_usd=whole_run.maximum_usd,
        approved_run_ceiling_usd=quote.approved_run_ceiling_usd,
        issued_at_ms=quote.issued_at_ms,
        expires_at_ms=quote.expires_at_ms,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/ancestry-interrogations/{receipt_id}/continuation",
    response_model=AncestryContinuationLaunchOut,
    status_code=202,
)
async def post_reasoning_ancestry_continuation(
    investigation_id: str,
    receipt_id: str,
    body: AncestryContinuationLaunchIn,
    request: Request,
    response: Response,
) -> AncestryContinuationLaunchOut:
    """Accept one exact quote and publish one deterministic child start."""

    from datetime import UTC, datetime

    from interfaces.research.api.engagement_routes import _eng_for, _sess_for
    from interfaces.research.api.investigation_access import (
        bind_child_investigation,
        event_actor,
    )
    from interfaces.research.api.research_quote_authority import (
        verify_exact_research_quote,
    )
    from substrate.dispatch.daily_research_budget import (
        configured_daily_research_cap,
        hold_daily_research_budget,
        release_daily_research_budget,
    )
    from substrate.engagement_spine.collective_manifest import (
        project_collective_manifest,
    )
    from substrate.event_log import (
        append_event_once_authorized,
        prepare_typed_event,
        trajectory_authorized,
    )
    from substrate.research_artifact.reasoning_ancestry_interrogation_resolution import (
        resolve_reasoning_ancestry_interrogation,
    )
    from substrate.schemas import (
        Event,
        InvestigationSpawnedFromPayload,
        InvestigationStartRequestedPayload,
        ResearchQuotedRoute,
    )

    try:
        parent_access = authority_from_request(request, investigation_id)
        require_investigation_owner(parent_access)
        artifact_authority = _authority(
            request, investigation_id, allow_unauthenticated_local=False
        )
        engagement_store = _eng_for(request)
        resolved = resolve_reasoning_ancestry_interrogation(
            authority=artifact_authority,
            receipt_id=receipt_id,
            engagement_store=engagement_store,
            session_store=_sess_for(request),
        )
        if resolved.receipt.receipt_sha256 != body.expected_receipt_sha256:
            raise ValueError("ancestry continuation receipt changed after review")
        manifest, unit = project_collective_manifest(
            resolved.receipt.manifest_id, store=engagement_store
        )
        if manifest.manifest_id != resolved.manifest.manifest_id:
            raise ValueError("ancestry continuation manifest conflicts")
        context = f"## Interrogation question\n{resolved.receipt.question}\n\n{unit.prompt_block()}"
        context_sha256 = hashlib.sha256(context.encode("utf-8")).hexdigest()
        expected_manifest, whole_run = _ancestry_whole_run_envelope(body)
        command = _ancestry_continuation_command(
            investigation_id=investigation_id,
            receipt_id=receipt_id,
            receipt_sha256=resolved.receipt.receipt_sha256,
            context_sha256=context_sha256,
            provider_id=body.provider_id,
            model_id=body.model_id,
            pricing_fingerprint=body.pricing_fingerprint,
            research_tier=body.research_tier,
            approved_run_ceiling_usd=body.approved_run_ceiling_usd,
            workload_plan_sha256=whole_run.plan_sha256,
            whole_run_maximum_usd=whole_run.maximum_usd,
        )
        quote, route_manifest = verify_exact_research_quote(
            request=request,
            token=body.research_quote_token,
            command=command,
            research_tier=body.research_tier,
            approved_run_ceiling_usd=body.approved_run_ceiling_usd,
            selected_driver_role="synthesizer",
            selected_driver_provider=body.provider_id,
            selected_driver_model=body.model_id,
            selected_driver_pricing_fingerprint=body.pricing_fingerprint,
            # Expiry is relaxed only for recovery after the exact signed start
            # has already been durably persisted below. A first acceptance
            # still requires a currently valid quote.
            allow_expired=True,
        )
        if route_manifest.fingerprint != expected_manifest.fingerprint:
            raise ValueError("ancestry continuation pricing changed during launch")
        child_id = f"inv-ancestry-{quote.quote_id[:24]}"
        child_access = bind_child_investigation(parent_access, child_id)
        role, policy_id = event_actor(child_access)
        emitted_at = datetime.fromtimestamp(quote.issued_at_ms / 1000, tz=UTC)
        start_event_id = f"evt-ancestry-start-{quote.quote_id[:24]}"
        existing_rows = trajectory_authorized(child_access.authority)
        existing_start = next(
            (row for row in existing_rows if row.get("event_id") == start_event_id),
            None,
        )
        if time.time_ns() // 1_000_000 >= quote.expires_at_ms and existing_start is None:
            raise ValueError("research quote is not currently valid")
        daily_cap = configured_daily_research_cap()
        daily_snapshot = hold_daily_research_budget(
            account_id=parent_access.authority.account_id,
            hold_id=quote.quote_id,
            cap_usd=daily_cap,
            amount_usd=body.approved_run_ceiling_usd,
        )
        broadcaster = getattr(request.app.state, "broadcaster", None)
        if broadcaster is None or not hasattr(broadcaster, "broadcast_confirmed_command_once"):
            if existing_start is None:
                release_daily_research_budget(
                    account_id=parent_access.authority.account_id,
                    hold_id=quote.quote_id,
                    cap_usd=daily_cap,
                    amount_usd=body.approved_run_ceiling_usd,
                    date_stamp=daily_snapshot.date_stamp,
                )
            raise RuntimeError("ancestry continuation command bus is unavailable")
        start = prepare_typed_event(
            child_id,
            InvestigationStartRequestedPayload(
                question=resolved.receipt.question,
                context=unit.prompt_block(),
                parent_investigation_id=investigation_id,
                spawn_context=(
                    f"ancestry_interrogation:{receipt_id}:{resolved.receipt.receipt_sha256}"
                ),
                research_tier=body.research_tier,
                approved_run_ceiling_usd=body.approved_run_ceiling_usd,
                research_quote_id=quote.quote_id,
                research_quote_payload_sha256=quote.payload_sha256,
                research_route_manifest_fingerprint=(quote.route_manifest_fingerprint),
                research_quote_expires_at_ms=quote.expires_at_ms,
                research_route_manifest=tuple(
                    ResearchQuotedRoute(**row.__dict__) for row in route_manifest.routes
                ),
                selected_driver_role=quote.selected_driver_role,
                selected_driver_provider=quote.selected_driver_provider,
                selected_driver_model=quote.selected_driver_model,
                selected_driver_pricing_fingerprint=(quote.selected_driver_pricing_fingerprint),
                research_workload_plan_sha256=whole_run.plan_sha256,
                research_projected_max_cost_usd=float(whole_run.maximum_usd),
                research_daily_budget_hold_id=quote.quote_id,
                research_daily_budget_date_stamp=daily_snapshot.date_stamp,
                research_daily_budget_cap_usd=daily_snapshot.cap_cents / 100,
            ),
            event_id=start_event_id,
            role=role,
            policy_id=policy_id,
            emitted_at=emitted_at,
        )
        try:
            start_event_id = append_event_once_authorized(child_access.authority, start)
        except Exception:
            if existing_start is None:
                release_daily_research_budget(
                    account_id=parent_access.authority.account_id,
                    hold_id=quote.quote_id,
                    cap_usd=daily_cap,
                    amount_usd=body.approved_run_ceiling_usd,
                    date_stamp=daily_snapshot.date_stamp,
                )
            raise
        spawn = prepare_typed_event(
            child_id,
            InvestigationSpawnedFromPayload(
                parent_investigation_id=investigation_id,
                spawn_context=(
                    f"ancestry_interrogation:{receipt_id}:{resolved.receipt.receipt_sha256}"
                ),
            ),
            event_id=f"evt-ancestry-spawn-{quote.quote_id[:24]}",
            role=role,
            policy_id=policy_id,
            parent_event_id=start_event_id,
            emitted_at=emitted_at,
        )
        append_event_once_authorized(child_access.authority, spawn)
        for row in trajectory_authorized(child_access.authority):
            if row.get("event_id") == start_event_id:
                event = Event.model_validate(row)
                broadcaster.bind_event_authority(event.event_id, child_access.authority)
                await broadcaster.broadcast_confirmed_command_once(event)
                break
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except (
        InvestigationAccessDenied,
        InvestigationAuthenticationRequired,
        KeyError,
    ) as exc:
        raise _private_artifact_error(404, "ancestry interrogation not found") from exc
    except ValueError as exc:
        raise _private_artifact_error(409, str(exc)) from exc
    except Exception as exc:
        raise _private_artifact_error(503, "ancestry continuation launch unavailable") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return AncestryContinuationLaunchOut(
        investigation_id=child_id,
        start_event_id=start_event_id,
        parent_investigation_id=investigation_id,
        ancestry_interrogation_receipt_id=receipt_id,
        selected_driver_provider=body.provider_id,
        selected_driver_model=body.model_id,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claim-challenges/{session_id}/review/preview",
    response_model=ClaimReviewOut,
)
def post_claim_review_preview(
    investigation_id: str,
    session_id: str,
    body: ClaimReviewPreviewIn,
    request: Request,
    response: Response,
) -> ClaimReviewOut:
    from substrate.research_artifact.claim_review import (
        build_claim_review_preview,
        read_claim_review,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            candidate, engagement_store, _ = _claim_review_candidate(
                authority=authority,
                session_id=session_id,
                request=request,
                require_current_hash=body.content_hash,
                artifact_store=artifact_store,
            )
            acceptance, reversal = read_claim_review(
                candidate.challenge.receipt_sha256, store=engagement_store
            )
            preview = build_claim_review_preview(
                candidate,
                artifact_account_digest=authority.account_digest,
                artifact_investigation_digest=authority.investigation_digest,
                review_state=(
                    "reversed" if reversal else "accepted" if acceptance else "candidate"
                ),
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise _private_artifact_error(409, "claim review state is unavailable") from exc
        raise _private_artifact_error(404, "claim review candidate not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimReviewOut(
        status="reversed" if reversal else "accepted" if acceptance else "candidate",
        preview=preview,
        acceptance=acceptance.model_dump(mode="json") if acceptance else None,
        reversal=reversal.model_dump(mode="json") if reversal else None,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claim-challenges/{session_id}/review/accept",
    response_model=ClaimReviewOut,
)
def post_claim_review_accept(
    investigation_id: str,
    session_id: str,
    body: ClaimReviewAcceptIn,
    request: Request,
    response: Response,
) -> ClaimReviewOut:
    from substrate.research_artifact.claim_review import (
        ClaimReviewConflict,
        accept_claim_review,
        read_claim_review,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            candidate, engagement_store, _ = _claim_review_candidate(
                authority=authority,
                session_id=session_id,
                request=request,
                require_current_hash=body.content_hash,
                artifact_store=artifact_store,
            )
            acceptance = accept_claim_review(
                candidate,
                artifact_account_digest=authority.account_digest,
                artifact_investigation_digest=authority.investigation_digest,
                expected_preview_sha256=body.preview_sha256,
                mutation_key=body.mutation_key,
                store=engagement_store,
            )
            _, reversal = read_claim_review(
                candidate.challenge.receipt_sha256, store=engagement_store
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except ClaimReviewConflict as exc:
        raise _private_artifact_error(409, str(exc)) from exc
    except Exception as exc:
        raise _private_artifact_error(404, "claim review candidate not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimReviewOut(
        status="reversed" if reversal else "accepted",
        acceptance=acceptance.model_dump(mode="json"),
        reversal=reversal.model_dump(mode="json") if reversal else None,
    )


@artifact_router.post(
    "/{investigation_id}/artifact/claim-challenges/{session_id}/review/reverse",
    response_model=ClaimReviewOut,
)
def post_claim_review_reverse(
    investigation_id: str,
    session_id: str,
    body: ClaimReviewReverseIn,
    request: Request,
    response: Response,
) -> ClaimReviewOut:
    from substrate.research_artifact.claim_review import (
        ClaimReviewConflict,
        read_claim_review,
        reverse_claim_review,
    )

    try:
        authority = _authority(request, investigation_id, allow_unauthenticated_local=False)
        artifact_store = FilesystemArtifactStore()
        with artifact_store.mutation_lock(authority):
            candidate, engagement_store, _ = _claim_review_candidate(
                authority=authority,
                session_id=session_id,
                request=request,
                require_current_hash=None,
                artifact_store=artifact_store,
            )
            if body.content_hash != candidate.challenge.artifact_content_hash:
                raise ClaimReviewConflict("claim review artifact receipt is stale")
            acceptance, _ = read_claim_review(
                candidate.challenge.receipt_sha256, store=engagement_store
            )
            if acceptance is None:
                raise ClaimReviewConflict("claim review acceptance is unavailable")
            reversal = reverse_claim_review(
                acceptance,
                acceptance_receipt_sha256=body.acceptance_receipt_sha256,
                rationale=body.rationale,
                mutation_key=body.mutation_key,
                store=engagement_store,
            )
    except HTTPException as exc:
        raise _private_artifact_exception(exc) from None
    except ClaimReviewConflict as exc:
        raise _private_artifact_error(409, str(exc)) from exc
    except Exception as exc:
        raise _private_artifact_error(404, "claim review candidate not found") from exc
    response.headers["Cache-Control"] = "private, no-store"
    return ClaimReviewOut(
        status="reversed",
        acceptance=acceptance.model_dump(mode="json"),
        reversal=reversal.model_dump(mode="json"),
    )


@artifact_router.post("/{investigation_id}/artifact/append-note", response_model=ImportNotesOut)
async def post_append_note(
    investigation_id: str, body: AppendNoteIn, request: Request
) -> ImportNotesOut:
    authority = _authority(request, investigation_id)
    store = FilesystemArtifactStore()
    try:
        with store.mutation_lock(authority):
            html_text = store._read_locked(authority)
            artifact = parse_body_from_html(html_text)
            updated = artifact.model_copy(
                update={"agent_notes": [*artifact.agent_notes, body.note]}
            )
            updated_html = render_html(updated)
            path = authority.artifact_path()

            def persist_updated() -> None:
                store._write_locked(authority, updated_html)

            result = import_agent_notes_html(
                updated_html,
                authority=authority,
                artifact_path=path,
                before_emit=persist_updated,
            )
    except (FileNotFoundError, UnsafeArtifactState) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid artifact note") from exc
    return ImportNotesOut(
        investigation_id=result.investigation_id,
        notes_imported=result.notes_imported,
        notes_skipped_duplicate=result.notes_skipped_duplicate,
        event_ids=result.event_ids,
    )


@artifact_router.get("/{investigation_id}/artifact/blocks", response_model=BlocksOut)
async def get_artifact_blocks(investigation_id: str, request: Request) -> BlocksOut:
    authority = _authority(request, investigation_id)
    try:
        read_canonical_artifact(authority)
    except (FileNotFoundError, UnsafeArtifactState) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    blocks = list_outline_blocks(investigation_id, authority=authority, db_path=_db())
    return BlocksOut(
        investigation_id=investigation_id,
        blocks=[
            BlockOut(
                node_id=b.node_id,
                kind=b.kind,
                label=b.label,
                investigation_id=b.investigation_id,
            )
            for b in blocks
        ],
    )
