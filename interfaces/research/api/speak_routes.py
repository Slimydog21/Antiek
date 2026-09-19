"""Speak workflow — the REST surface.

A standalone ``APIRouter`` wiring the ``substrate/speak`` substrate into
the FastAPI app. Kept in its own module (not inlined into the 5k-line
``app.py`` factory) for the reason CLAUDE.md names: ``app.py`` is a hot,
concurrently-edited file. This router is included with ONE line —
``app.include_router(speak_router)`` — near the end of ``create_app``,
and is fully testable on its own (a throwaway ``FastAPI`` + ``TestClient``
need not touch ``app.py``).

Conventions matched from ``app.py``:
  • db path via ``substrate.graph.default_db_path`` + ``ensure_initialized``;
  • writes through ``runtime.db_lock.connect_write`` (single-writer);
  • reads through a read-only DuckDB connection;
  • auth is the app's global middleware — these handlers carry none.

Domain exceptions map to HTTP status via ``_translate``:
  • consent / G7 ecosystem refusals → 403;
  • publish-gate / disbursement refusals → 409;
  • not-found / bad-input → 404 / 400.

The answer→claim bridge (M-gap closed here): a submitted voice-note
answer produces a voice-note document + graph nodes (``submit_answer``),
but whether an utterance asserts a third-party claim ABOUT THE SUBJECT
is a judgment the system must not guess (SPR-01 rigor: don't infer
identity from free text). So claims are recorded EXPLICITLY via
``POST /speak/interviews/{id}/claims`` — by an extraction pass the
operator confirms — which is what feeds corroboration → authoring →
economics.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from orchestration.interview.orchestrator import ConsentRequired
from runtime.db_lock import connect_read, connect_write
from substrate.books.ingest import register_book
from substrate.books.model import TocItem
from substrate.event_log import (
    append_event_once_authorized,
    prepare_typed_event,
    require_event_persistence,
)
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import (
    content_addressed_id,
    insert_chunk,
    insert_document,
    update_section_prose,
)
from substrate.interviews.store import InterviewStateConflict
from substrate.investigation_streams import resolve_writable_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import (
    OutlineBlockPlacedPayload,
    SeamSpeakToReadPayload,
    SeamSpeakToWritePayload,
)
from substrate.speak import (
    biography,
    biography_composition,
    corroboration,
    economics_mode,
    gate_status,
    invitations,
    payout_verifier,
    physical_book,
    third_party,
)
from substrate.speak import (
    consent as consent_mod,
)
from substrate.speak import (
    contributor as contributor_mod,
)
from substrate.speak import (
    project as project_mod,
)
from substrate.speak import (
    publish as publish_mod,
)
from substrate.speak import (
    subject_consent as subject_consent_mod,
)
from substrate.speak import (
    takedown as takedown_mod,
)
from substrate.speak.async_interview import (
    AsrError,
    decline,
    next_followups,
    resume,
    submit_answer,
)
from substrate.speak.async_interview import (
    transcribe as transcribe_voice,
)
from substrate.speak.consent import ConsentScope, ScopedConsentRequired
from substrate.speak.contributor import DisbursementBlocked
from substrate.speak.invitations import PublicEcosystemGated
from substrate.speak.publish_gate import PublishBlocked
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.write_composer import WriteOutlineComposer


def _request_event_authority(
    request: Request, investigation_id: str
) -> InvestigationAuthority:
    from .investigation_access import authority_from_request

    authority = authority_from_request(request, investigation_id).authority
    resolve_writable_investigation_stream(authority)
    return authority


async def _legacy_speak_partition_guard(request: Request) -> None:
    """Keep global legacy Speak paths local-only until their sidecars migrate."""
    if request.url.path.startswith("/speak/invite/"):
        return
    canonical_claim_write = (
        request.method == "POST"
        and request.url.path.startswith("/speak/interviews/")
        and request.url.path.endswith("/claims")
    )
    canonical_claim_read = (
        request.method == "GET"
        and request.url.path.startswith("/speak/projects/")
        and request.url.path.endswith("/claims")
    )
    canonical_cluster_write = (
        request.method == "POST"
        and request.url.path.startswith("/speak/projects/")
        and request.url.path.endswith("/claim-clusters")
    )
    canonical_draft_route = (
        request.url.path.startswith("/speak/projects/")
        and "/html-drafts" in request.url.path
        and request.method in {"GET", "POST"}
    )
    canonical_contributor_route = (
        request.url.path.startswith("/speak/projects/")
        and "/contributor-attribution" in request.url.path
        and request.method in {"GET", "POST"}
    )
    canonical_private_write_route = (
        (request.url.path == "/speak/private-write" or (
            request.url.path.startswith("/speak/projects/")
            and "/private-write/" in request.url.path
        ))
        and request.method in {"GET", "POST"}
    )
    if (
        canonical_claim_write or canonical_claim_read or canonical_cluster_write
        or canonical_draft_route or canonical_contributor_route
        or canonical_private_write_route
    ):
        return
    state = getattr(request, "state", None)
    if getattr(state, "user_claims", None) is None:
        raise HTTPException(status_code=404, detail="Speak resource not found")
    from interfaces.research.api.interview_access import interview_account_authority_from_request

    authority = interview_account_authority_from_request(request)
    if not authority.local_operator_compatibility:
        raise HTTPException(status_code=404, detail="Speak resource not found")


speak_router = APIRouter(
    prefix="/speak", tags=["speak"], dependencies=[Depends(_legacy_speak_partition_guard)]
)


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _db() -> str:
    """Resolve + initialize the graph DB (base schema). Speak tables are
    ensured per write under the lock."""
    path = default_db_path()
    ensure_initialized(path)
    return path


@contextmanager
def _write(purpose: str) -> Iterator[Any]:
    db = _db()
    con = connect_write(db, purpose=purpose)
    try:
        ensure_speak_schema(con)
        yield con
    finally:
        con.close()


@contextmanager
def _transaction(con: Any) -> Iterator[None]:
    con.execute("BEGIN TRANSACTION")
    try:
        yield
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


@contextmanager
def _translate() -> Iterator[None]:
    """Map Speak domain exceptions onto HTTP status codes."""
    try:
        yield
    except (ScopedConsentRequired, ConsentRequired, PublicEcosystemGated) as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except (PublishBlocked, DisbursementBlocked) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InterviewStateConflict as e:
        status = 403 if "consent" in str(e).lower() else 409
        raise HTTPException(status_code=status, detail=str(e)) from e
    except AsrError as e:
        # Honest unavailable-provider response; never fabricate a transcript.
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"{field} must be a decimal string"
        ) from exc


def _validated_command_id(value: str) -> str:
    command_id = value.strip()
    if not command_id or len(command_id) > 200:
        raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
    return command_id


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    subject_ref: str | None = None
    subject_status: str = "unknown"
    publish_intent: str = "private_never_published"
    topic_description: str | None = None


class ProjectResponse(BaseModel):
    project_id: str
    title: str
    subject_ref: str | None
    subject_status: str
    publish_intent: str
    invitation_mode: str


class CreateBiographyRequest(BaseModel):
    """SPR-11 — provision a biography TEMPLATE over the three surfaces.

    ``investigation_id`` is the Research folder the frontend already
    created via ``POST /investigations`` (the one-graph identity). This
    endpoint wires the Write deliverable + the Speak project to it and
    records the shared composition link event — it creates NO new store.
    """

    investigation_id: str = Field(..., min_length=1)
    subject_name: str = Field(..., min_length=1, max_length=300)
    title: str | None = None
    subject_status: str = "unknown"
    publish_intent: str = "private_never_published"


class BiographyCompositionResponse(BaseModel):
    """The three surface ids a biography wires together — NO biography_id
    (a biography is the composition of the three, not its own entity)."""

    investigation_id: str
    deliverable_id: str
    project_id: str
    composition_event_id: str | None


class InviteRequest(BaseModel):
    informant_email: str | None = None
    informant_handle: str | None = None


class InviteResponse(BaseModel):
    invite_id: str
    interview_id: str
    link: str
    required_consent_scopes: list[str]
    status: str


class ConsentRequestModel(BaseModel):
    scopes: list[str] = Field(..., min_length=1)


class AnswerRequest(BaseModel):
    question_id: str
    transcript: str = Field(..., min_length=1)
    duration_seconds: float = 0.0


class ClaimRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    interview_id: str | None = None
    question_id: str | None = Field(default=None, min_length=1, max_length=512)
    source_document_id: str | None = Field(default=None, min_length=1, max_length=512)
    about_subject: bool = False
    subject_ref: str | None = None
    speaker_is_subject: bool = False
    independence_key: str | None = Field(default=None, min_length=1, max_length=512)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_explicit_subject_identity(self) -> ClaimRequest:
        if self.about_subject and not self.subject_ref:
            raise ValueError("about_subject requires an explicit subject_ref")
        return self


class CorroborationMemberRequest(BaseModel):
    claim_id: str = Field(..., min_length=1, max_length=512)
    stance: Literal["attests", "contradicts"] = "attests"


class CorroborationRequest(BaseModel):
    canonical_claim_id: str = Field(..., min_length=1, max_length=512)
    members: list[CorroborationMemberRequest] = Field(..., min_length=1, max_length=100)


class PrivateCompositionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    claim_ids: list[str] = Field(..., min_length=1, max_length=500)


class ContributorAttributionRequest(BaseModel):
    contributor_ref: str = Field(..., min_length=1, max_length=512)
    display_label: str = Field(..., min_length=1, max_length=500)
    evidence_basis: Literal[
        "self_reported", "operator_verified", "contractual_record"
    ]
    evidence_ref: str = Field(..., min_length=1, max_length=2048)


class ContributorRevocationRequest(BaseModel):
    target_event_id: str = Field(..., min_length=1, max_length=512)


class CompositionProposalRequest(BaseModel):
    base_revision: Any
    instruction: Any
    provider_id: Any
    model_id: Any
    projected_max_cents: Any
    approved_ceiling_cents: Any


class WriteReviewRequest(BaseModel):
    action: Literal["accept", "reject"]
    base_revision: int = Field(..., ge=0)
    rationale: str | None = Field(default=None, max_length=5_000)


class WriteUndoRequest(BaseModel):
    target_event_id: str = Field(..., min_length=1, max_length=512)
    base_revision: int = Field(..., ge=1)


class WriteEditRequest(BaseModel):
    base_revision: Any
    base_html_sha256: Any
    html: Any
    summary: Any = None


class WriteRestoreRequest(BaseModel):
    base_revision: Any = None
    base_html_sha256: Any = None
    target_revision: Any = None


class NativeWriteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=300)


class WriteCitationEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_kind: Literal["synthesis_claim"]
    source_asset_id: str = Field(..., min_length=1, max_length=512)
    claim_id: str = Field(..., min_length=1, max_length=512)
    chunk_ids: list[str] = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=512)
    receipt_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class WriteEvidencePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(..., ge=1)
    base_html_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    citation_evidence: WriteCitationEvidenceRequest


class WriteEvidenceApplyRequest(WriteEvidencePreviewRequest):
    preview_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    proposed_html_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class WriteEvidenceBundleItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citation_evidence: WriteCitationEvidenceRequest
    relationship: Literal["supports", "contradicts", "context", "unresolved"]
    operator_label: str | None = Field(default=None, min_length=1, max_length=200)


class WriteEvidenceBundlePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(..., ge=1)
    base_html_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    items: list[WriteEvidenceBundleItemRequest] = Field(..., min_length=2, max_length=32)


class WriteEvidenceBundleApplyRequest(WriteEvidenceBundlePreviewRequest):
    preview_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    proposed_html_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class EvidenceBundleSynthesisProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: Any
    instruction: Any
    provider_id: Any
    model_id: Any
    approved_ceiling_cents: Any
    expected_output_tokens: int = Field(default=4_000, ge=256, le=32_000)


class EvidenceBundleSynthesisProjectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: Any
    provider_id: Any
    model_id: Any
    expected_output_tokens: int = Field(default=4_000, ge=256, le=32_000)


class EvidenceSynthesisWritePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(..., ge=1)
    base_html_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class EvidenceSynthesisWriteApplyRequest(EvidenceSynthesisWritePreviewRequest):
    preview_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    proposed_html_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class SynthesisKnowledgeCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_index: int = Field(..., ge=0, le=31)
    kind: Literal["insight", "question"]
    text: str = Field(..., min_length=1, max_length=20_000)


class SynthesisKnowledgePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_investigation_id: str = Field(..., min_length=1, max_length=512)
    items: list[SynthesisKnowledgeCandidateRequest] = Field(..., min_length=1, max_length=32)


class SynthesisKnowledgeApplyRequest(SynthesisKnowledgePreviewRequest):
    preview_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class SubjectConsentRequest(BaseModel):
    subject_ref: str
    subject_status: str
    consent_granted: bool
    rationale: str | None = None


class ContributorRequest(BaseModel):
    interview_id: str
    ip_holder_id: str | None = None
    display_name: str | None = None
    legal_contact_email: str | None = None


class TakedownRequestModel(BaseModel):
    target_kind: str
    target_id: str
    requested_by: str | None = None
    reason: str | None = None


class DraftRequest(BaseModel):
    public: bool = False


class PublishRequest(BaseModel):
    deliverable_id: str | None = None
    subject_ref: str | None = None
    ad_revenue_usd: str = "0"
    quality_scores: dict[str, float] | None = None


class BookOrderRequest(BaseModel):
    book_format: str
    page_count: int = Field(..., ge=1)
    publication_id: str | None = None


class GradeInterviewRequest(BaseModel):
    """The REQUESTER's information goal — what they want covered + the money
    bounds. The grade itself is produced by the AI verifier, NOT here."""

    information_goal: str = Field(..., min_length=1)
    must_cover: list[str] = Field(default_factory=list)
    budget_usd: str = "0"
    per_interview_cap_usd: str = "0"


class ReleasePayoutRequest(BaseModel):
    information_goal: str = Field(..., min_length=1)
    budget_usd: str = "0"
    per_interview_cap_usd: str = "0"
    ad_revenue_usd: str = "0"
    publication_id: str | None = None


# ---------------------------------------------------------------------------
# Operator: project lifecycle
# ---------------------------------------------------------------------------


@speak_router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(req: CreateProjectRequest) -> ProjectResponse:
    with _translate(), _write("speak/api:create_project") as con:
        p = project_mod.create_project(
            con, title=req.title, subject_ref=req.subject_ref,
            subject_status=req.subject_status, publish_intent=req.publish_intent,
            topic_description=req.topic_description,
        )
    return ProjectResponse(**p.__dict__)


@speak_router.post(
    "/biography", response_model=BiographyCompositionResponse, status_code=201
)
async def create_biography(req: CreateBiographyRequest) -> BiographyCompositionResponse:
    """SPR-11 — compose a biography TEMPLATE over Research + Write + Speak.

    The Research folder (``investigation_id``) is created upstream
    (``POST /investigations``); this wires the Write deliverable + the
    Speak project to that SAME identity and records the shared composition
    event. No new store/table — the §16 one-graph guard
    (``test_biography_creates_no_new_store``) asserts this mechanically.
    """
    with _translate(), _write("speak/api:create_biography") as con:
        comp = biography_composition.create_biography(
            con,
            investigation_id=req.investigation_id,
            subject_name=req.subject_name,
            title=req.title,
            subject_status=req.subject_status,
            publish_intent=req.publish_intent,
        )
    return BiographyCompositionResponse(
        investigation_id=comp.investigation_id,
        deliverable_id=comp.deliverable_id,
        project_id=comp.project_id,
        composition_event_id=comp.composition_event_id,
    )


@speak_router.get("/projects")
async def list_projects() -> dict:
    """List Speak projects (the operator's project index). Uses a write
    lock only to ensure the Speak schema exists on a fresh DB; the query
    itself is a read."""
    with _translate(), _write("speak/api:list_projects") as con:
        rows = con.execute(
            "SELECT p.project_id, ip.title, p.subject_ref, p.subject_status, "
            "p.publish_intent, p.invitation_mode, "
            "(SELECT count(*) FROM interviews i WHERE i.project_id = p.project_id), "
            "strftime(p.created_at, '%Y-%m-%dT%H:%M:%S') "
            "FROM speak_projects p "
            "JOIN interview_projects ip ON ip.project_id = p.project_id "
            "ORDER BY p.created_at DESC"
        ).fetchall()
    return {
        "count": len(rows),
        "projects": [
            {"project_id": r[0], "title": r[1], "subject_ref": r[2],
             "subject_status": r[3], "publish_intent": r[4],
             "invitation_mode": r[5], "interview_count": r[6], "created_at": r[7]}
            for r in rows
        ],
    }


@speak_router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    with _translate(), _write("speak/api:get_project") as con:
        p = project_mod.get_project(con, project_id)
    return ProjectResponse(**p.__dict__)


@speak_router.get("/projects/{project_id}/economics")
async def get_economics(project_id: str) -> dict:
    with _translate(), _write("speak/api:economics") as con:
        policy = economics_mode.policy_for_project(con, project_id)
    # The G2/G3 gate STATE, read-only (gate_status.py). The UI shows these
    # as "gated / not yet activated" — there is no flip/close affordance
    # here; closing a gate is an operator action, never a code path.
    publishing = gate_status.public_publishing_allowed()
    disbursement = gate_status.disbursement_allowed()
    return {
        "cell": policy.cell,
        "inference_margin": str(policy.inference_margin),
        "split_applies": policy.split_applies,
        "creator_carries_cost": policy.creator_carries_cost,
        "requires_publish_consent": policy.requires_publish_consent,
        # Operator-gate state, READ-ONLY. Deny-by-default; the UI surfaces
        # these gated, never offering to close them.
        "public_publishing_allowed": publishing.allowed,
        "public_publishing_reason": publishing.reason,
        "disbursement_allowed": disbursement.allowed,
        "disbursement_reason": disbursement.reason,
    }


@speak_router.get("/feed")
async def public_feed() -> dict:
    """The browsable PUBLIC feed (M1): projects whose intent is public —
    the surface a visitor scrolls and can 'interview-with'/chime in on.
    Honest when empty (returns ``[]``). Distinct from ``GET /projects``,
    which is the operator's full index (their private dashboard)."""
    with _translate(), _write("speak/api:feed") as con:
        if os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1":
            rows = [
                (*row, None)
                for row in con.execute(
                    "SELECT p.project_id, ip.title, p.subject_ref, p.subject_status, "
                    "p.invitation_mode, (SELECT count(*) FROM interviews i "
                    "WHERE i.project_id = p.project_id) FROM speak_projects p "
                    "JOIN interview_projects ip ON ip.project_id = p.project_id "
                    "WHERE p.publish_intent = 'will_be_public' "
                    "ORDER BY p.created_at DESC"
                ).fetchall()
            ]
        else:
            from substrate.legal_gate.read import legacy_speak_public_feed

            rows = legacy_speak_public_feed(con)
    return {
        "count": len(rows),
        "projects": [
            {"project_id": r[0], "title": r[1], "subject_ref": r[2],
             "subject_status": r[3], "invitation_mode": r[4],
             "interview_count": r[5], "document_id": r[6]}
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Operator: invitations
# ---------------------------------------------------------------------------


@speak_router.post("/projects/{project_id}/invites", response_model=InviteResponse, status_code=201)
async def invite(project_id: str, req: InviteRequest) -> InviteResponse:
    if not (req.informant_email or req.informant_handle):
        raise HTTPException(status_code=400, detail="informant_email or informant_handle required")
    with _translate(), _write("speak/api:invite") as con:
        iv = invitations.invite_stakeholder(
            con, project_id=project_id,
            informant_email=req.informant_email, informant_handle=req.informant_handle,
        )
    return InviteResponse(
        invite_id=iv.invite_id, interview_id=iv.interview_id, link=iv.link,
        required_consent_scopes=[s.value for s in iv.required_consent_scopes],
        status=iv.status,
    )


@speak_router.get("/projects/{project_id}/invites")
async def list_invites(project_id: str) -> dict:
    with _translate(), _write("speak/api:list_invites") as con:
        rows = invitations.lifecycle(con, project_id)
    return {"count": len(rows), "invites": rows}


@speak_router.get("/invites/resolve")
async def resolve_invite(token: str) -> InviteResponse:
    with _translate(), _write("speak/api:resolve") as con:
        iv = invitations.resolve_token(con, token)
    if iv is None:
        raise HTTPException(status_code=404, detail="unknown or expired invite token")
    return InviteResponse(
        invite_id=iv.invite_id, interview_id=iv.interview_id, link=iv.link,
        required_consent_scopes=[s.value for s in iv.required_consent_scopes],
        status=iv.status,
    )


@speak_router.post("/projects/{project_id}/open-public", status_code=200)
async def open_public(project_id: str) -> dict:
    # Gated on G7 — refuses (403) unless ANTIEK_SPEAK_PUBLIC_ECOSYSTEM.
    with _translate(), _write("speak/api:open_public") as con:
        invitations.open_public_contribution(con, project_id)
    return {"project_id": project_id, "invitation_mode": "public"}


# ---------------------------------------------------------------------------
# Invitee: consent + interview
# ---------------------------------------------------------------------------


@speak_router.post("/interviews/{interview_id}/consent", status_code=200)
async def record_consent(interview_id: str, req: ConsentRequestModel) -> dict:
    with _translate(), _write("speak/api:consent") as con:
        scopes = [ConsentScope(s) for s in req.scopes]
        state = consent_mod.record_consent(con, interview_id=interview_id, scopes=scopes)
    return {"interview_id": interview_id, "granted": sorted(s.value for s in state.granted)}


@speak_router.get("/interviews/{interview_id}")
async def get_interview(interview_id: str) -> dict:
    with _translate():
        session = resume(_db(), interview_id)
    return {
        "interview_id": session.interview_id,
        "project_id": session.project_id,
        "status": session.status,
        "transcript": session.turns,
        "pending_questions": session.pending_questions(),
    }


@speak_router.post("/interviews/{interview_id}/answers", status_code=201)
async def submit_interview_answer(interview_id: str, req: AnswerRequest) -> dict:
    with _translate():
        result = submit_answer(
            _db(), interview_id=interview_id, question_id=req.question_id,
            transcript=req.transcript, duration_seconds=req.duration_seconds,
        )
    return {
        "interview_id": result.interview_id, "question_id": result.question_id,
        "document_id": result.document_id, "skipped_reason": result.skipped_reason,
    }


@speak_router.post("/interviews/{interview_id}/followups")
async def interview_followups(interview_id: str) -> dict:
    with _translate():
        fus = next_followups(_db(), interview_id=interview_id)
    return {"followups": [
        {"question_id": f.question_id, "text": f.text,
         "follow_up_for_prior_turn": f.follow_up_for_prior_turn}
        for f in fus
    ]}


@speak_router.post("/interviews/{interview_id}/claims", status_code=201)
async def record_interview_claim(
    interview_id: str, req: ClaimRequest, request: Request
) -> dict:
    """The answer→claim bridge: record an explicit claim attributed to
    the interviewee (about_subject / third-party tagging is a confirmed
    judgment, not an inference). Feeds corroboration + authoring +
    economics."""
    with _translate(), _write("speak/api:claim") as con:
        from interfaces.research.api.interview_access import (
            interview_account_authority_from_request,
        )
        from substrate.interviews.claims import ClaimConflict, record_claim

        authority = interview_account_authority_from_request(request)
        canonical = con.execute(
            "SELECT 1 FROM interviews_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND interview_id = ?",
            [authority.account_digest, authority.account_id, interview_id],
        ).fetchone()
        if canonical is not None:
            if req.question_id is None or req.source_document_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="canonical claims require question_id and source_document_id",
                )
            try:
                claim = record_claim(
                    con, authority, interview_id=interview_id,
                    question_id=req.question_id,
                    source_document_id=req.source_document_id, text=req.text,
                    about_subject=req.about_subject, subject_ref=req.subject_ref,
                    speaker_is_subject=req.speaker_is_subject,
                    independence_key=req.independence_key,
                    confidence=req.confidence,
                )
            except ClaimConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {
                "claim_id": claim.claim_id,
                "is_third_party": claim.is_third_party,
                "verification": claim.verification,
                "source_document_id": claim.source_document_id,
                "independence_key": claim.independence_key,
            }
        if not authority.local_operator_compatibility:
            raise HTTPException(status_code=404, detail="interview not found")
        row = con.execute(
            "SELECT project_id FROM interviews WHERE interview_id = ?", [interview_id]
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"interview {interview_id} not found")
        claim = third_party.record_claim(
            con, project_id=row[0], interview_id=interview_id, text=req.text,
            about_subject=req.about_subject, subject_ref=req.subject_ref,
            speaker_is_subject=req.speaker_is_subject, confidence=req.confidence,
        )
    return {"claim_id": claim.claim_id, "is_third_party": claim.is_third_party,
            "verification": claim.verification}


@speak_router.get("/projects/{project_id}/claims")
async def list_project_claims(project_id: str, request: Request) -> dict:
    """List only the caller's canonical claims and their evidence posture."""
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.claims import list_claims

    authority = interview_account_authority_from_request(request)
    with connect_write(_db(), purpose="speak/api:list_claims") as con:
        canonical = con.execute(
            "SELECT 1 FROM interview_projects_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND project_id = ?",
            [authority.account_digest, authority.account_id, project_id],
        ).fetchone()
        if canonical is None:
            raise HTTPException(status_code=404, detail="project not found")
        claims = list_claims(con, authority, project_id=project_id)
    return {"claims": [
        {
            "claim_id": claim.claim_id,
            "interview_id": claim.interview_id,
            "question_id": claim.question_id,
            "source_document_id": claim.source_document_id,
            "text": claim.text,
            "about_subject": claim.about_subject,
            "is_third_party": claim.is_third_party,
            "subject_ref": claim.subject_ref,
            "speaker_is_subject": claim.speaker_is_subject,
            "independence_key": claim.independence_key,
            "verification": claim.verification,
            "confidence": claim.confidence,
        }
        for claim in claims
    ]}


# ---------------------------------------------------------------------------
# Operator: corroboration, consent, economics, authoring, publishing
# ---------------------------------------------------------------------------


@speak_router.post("/projects/{project_id}/corroborate")
async def corroborate(project_id: str) -> dict:
    with _translate(), _write("speak/api:corroborate") as con:
        clusters = corroboration.corroborate_project(con, project_id)
    return {"clusters": [
        # canonical_text is the actual remembered statement the "what everyone
        # agrees on" view shows; without it the surface falls back to the
        # machine label ("multiply_attested"). Serialize it (SPR-08 sharpen).
        {"cluster_id": c.cluster_id, "label": c.label,
         "canonical_text": c.canonical_text, "confidence": c.confidence,
         "independent_attesters": c.independent_attesters,
         "member_claim_ids": c.member_claim_ids}
        for c in clusters
    ]}


@speak_router.post("/projects/{project_id}/claim-clusters", status_code=201)
async def record_claim_cluster(
    project_id: str, req: CorroborationRequest, request: Request
) -> dict:
    """Record explicit equivalence/contradiction judgments over canonical claims."""
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.corroboration import (
        CorroborationConflict,
        CorroborationMember,
        record_corroboration,
    )

    authority = interview_account_authority_from_request(request)
    with connect_write(_db(), purpose="speak/api:claim_cluster") as con:
        try:
            cluster = record_corroboration(
                con, authority, project_id=project_id,
                canonical_claim_id=req.canonical_claim_id,
                members=[
                    CorroborationMember(claim_id=member.claim_id, stance=member.stance)
                    for member in req.members
                ],
            )
        except CorroborationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "cluster_id": cluster.cluster_id,
        "canonical_claim_id": cluster.canonical_claim_id,
        "canonical_text": cluster.canonical_text,
        "label": cluster.label,
        "confidence": cluster.confidence,
        "independent_attesters": cluster.independent_attesters,
        "members": [
            {"claim_id": member.claim_id, "stance": member.stance}
            for member in cluster.members
        ],
    }


@speak_router.post("/projects/{project_id}/html-drafts", status_code=201)
async def create_private_html_draft(
    project_id: str,
    req: PrivateCompositionRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition import (
        CompositionConflict,
        create_private_draft,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    with connect_write(_db(), purpose="speak/api:private_html_draft") as con:
        try:
            draft = create_private_draft(
                con, authority, project_id=project_id, command_id=idempotency_key,
                title=req.title, claim_ids=req.claim_ids,
            )
        except CompositionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "draft_id": draft.draft_id, "project_id": draft.project_id,
        "title": draft.title, "manifest": draft.manifest,
        "manifest_sha256": draft.manifest_sha256, "html": draft.body_html,
        "body_sha256": draft.body_sha256, "visibility": draft.visibility,
    }


@speak_router.get("/projects/{project_id}/html-drafts/{draft_id}")
async def get_private_html_draft(
    project_id: str, draft_id: str, request: Request, response: Response
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition import CompositionConflict, get_private_draft

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    with connect_write(_db(), purpose="speak/api:get_private_html_draft") as con:
        try:
            draft = get_private_draft(con, authority, draft_id=draft_id)
        except CompositionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if draft.project_id != project_id:
            raise HTTPException(status_code=404, detail="private composition draft not found")
    return {
        "draft_id": draft.draft_id, "project_id": draft.project_id,
        "title": draft.title, "manifest": draft.manifest,
        "manifest_sha256": draft.manifest_sha256, "html": draft.body_html,
        "body_sha256": draft.body_sha256, "visibility": draft.visibility,
    }


def _composition_proposal_response(proposal: Any) -> dict:
    return {
        "proposal_id": proposal.proposal_id, "draft_id": proposal.draft_id,
        "project_id": proposal.project_id, "revision": proposal.revision,
        "base_revision": proposal.base_revision,
        "source_manifest_sha256": proposal.source_manifest_sha256,
        "source_body_sha256": proposal.source_body_sha256,
        "provider_id": proposal.provider_id, "model_id": proposal.model_id,
        "projected_max_cents": proposal.projected_max_cents,
        "approved_ceiling_cents": proposal.approved_ceiling_cents,
        "instruction": proposal.instruction, "state": proposal.state,
    }


def _registered_composition_models() -> frozenset[tuple[str, str]]:
    from substrate.model_registration import list_operator_models

    return frozenset(
        (str(row.get("provider_id")), str(row.get("model_id")))
        for row in list_operator_models().get("models", [])
        if row.get("enabled") is True
    )


def _proposal_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"}
    )


def _composition_execution_response(execution: Any) -> dict:
    return {
        "proposal_id": execution.proposal_id, "attempt_id": execution.attempt_id,
        "run_id": execution.run_id, "state": execution.state,
        "prompt_sha256": execution.prompt_sha256,
        "route_sha256": execution.route_sha256, "hold_id": execution.hold_id,
        "actual_cents": execution.actual_cents, "html": execution.result_html,
        "html_sha256": execution.result_html_sha256,
        "rejection_reason": execution.rejection_reason,
        "visibility": "private",
    }


@speak_router.post(
    "/projects/{project_id}/html-drafts/{draft_id}/ai-proposals", status_code=201
)
async def create_composition_proposal(
    project_id: str,
    draft_id: str,
    req: CompositionProposalRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition import CompositionConflict, get_private_draft
    from substrate.interviews.composition_proposals import (
        CompositionProposalConflict,
        create_proposal,
        validate_proposal_inputs,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    allowed_models = _registered_composition_models()
    try:
        validate_proposal_inputs(
            base_revision=req.base_revision, instruction=req.instruction,
            provider_id=req.provider_id, model_id=req.model_id,
            projected_max_cents=req.projected_max_cents,
            approved_ceiling_cents=req.approved_ceiling_cents,
            allowed_model_pairs=allowed_models,
        )
    except ValueError as exc:
        raise _proposal_error(400, str(exc)) from exc
    try:
        with connect_read(_db()) as con:
            draft = get_private_draft(con, authority, draft_id=draft_id)
            if draft.project_id != project_id:
                raise ValueError("composition proposal draft not found")
    except CompositionConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    with connect_write(
        _db(), purpose="speak/api:composition_proposal", log_on_close=False
    ) as con:
        try:
            proposal = create_proposal(
                con, authority, project_id=project_id, draft_id=draft_id,
                mutation_key=idempotency_key,
                base_revision=req.base_revision, instruction=req.instruction,
                provider_id=req.provider_id, model_id=req.model_id,
                projected_max_cents=req.projected_max_cents,
                approved_ceiling_cents=req.approved_ceiling_cents,
                allowed_model_pairs=allowed_models,
            )
        except CompositionProposalConflict as exc:
            raise _proposal_error(409, str(exc)) from exc
        except ValueError as exc:
            raise _proposal_error(404, str(exc)) from exc
    return _composition_proposal_response(proposal)


@speak_router.get(
    "/projects/{project_id}/html-drafts/{draft_id}/ai-proposals/{proposal_id}"
)
async def get_composition_proposal(
    project_id: str, draft_id: str, proposal_id: str, request: Request, response: Response
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_proposals import (
        CompositionProposalConflict,
        get_proposal,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    with connect_read(_db()) as con:
        try:
            proposal = get_proposal(con, authority, proposal_id=proposal_id)
        except CompositionProposalConflict as exc:
            raise _proposal_error(409, str(exc)) from exc
        except ValueError as exc:
            raise _proposal_error(404, str(exc)) from exc
        if proposal.project_id != project_id or proposal.draft_id != draft_id:
            raise _proposal_error(404, "composition proposal not found")
    return _composition_proposal_response(proposal)


@speak_router.post(
    "/projects/{project_id}/html-drafts/{draft_id}/ai-proposals/{proposal_id}/execute"
)
async def execute_composition_proposal(
    project_id: str, draft_id: str, proposal_id: str, request: Request,
    response: Response, idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_execution import (
        CompositionExecutionConflict,
        execute_proposal,
    )
    from substrate.interviews.composition_proposals import get_proposal

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    executor = getattr(request.app.state, "composition_executor", None)
    if (getattr(request.app.state, "composition_execution_enabled", False) is not True
            or executor is None):
        raise _proposal_error(503, "composition execution is not boot-attested")
    try:
        with connect_read(_db()) as con:
            proposal = get_proposal(con, authority, proposal_id=proposal_id)
            if proposal.project_id != project_id or proposal.draft_id != draft_id:
                raise ValueError("composition proposal not found")
        execution = execute_proposal(
            _db(), authority, proposal_id=proposal_id, attempt_id=idempotency_key,
            route_sha256=str(getattr(executor, "route_sha256", "")), executor=executor,
        )
    except CompositionExecutionConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return _composition_execution_response(execution)


@speak_router.get(
    "/projects/{project_id}/html-drafts/{draft_id}/ai-proposals/{proposal_id}/execution"
)
async def get_composition_execution(
    project_id: str, draft_id: str, proposal_id: str, request: Request, response: Response
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_execution import (
        CompositionExecutionConflict,
        get_execution,
    )
    from substrate.interviews.composition_proposals import get_proposal

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        with connect_read(_db()) as con:
            proposal = get_proposal(con, authority, proposal_id=proposal_id)
            if proposal.project_id != project_id or proposal.draft_id != draft_id:
                raise ValueError("composition execution not found")
        execution = get_execution(_db(), authority, proposal_id=proposal_id)
    except CompositionExecutionConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return _composition_execution_response(execution)


@speak_router.post(
    "/projects/{project_id}/html-drafts/{draft_id}/ai-proposals/{proposal_id}/reconcile"
)
async def reconcile_composition_execution(
    project_id: str, draft_id: str, proposal_id: str, request: Request, response: Response
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_execution import (
        CompositionExecutionConflict,
        reconcile_checkpointed,
    )
    from substrate.interviews.composition_proposals import get_proposal

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        with connect_read(_db()) as con:
            proposal = get_proposal(con, authority, proposal_id=proposal_id)
            if proposal.project_id != project_id or proposal.draft_id != draft_id:
                raise ValueError("composition execution not found")
        execution = reconcile_checkpointed(_db(), authority, proposal_id=proposal_id)
    except CompositionExecutionConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return _composition_execution_response(execution)


def _write_review_response(decision: Any) -> dict:
    return {
        "event_id": decision.event_id, "action": decision.action,
        "write_document_id": decision.write_document_id,
        "project_id": decision.project_id, "proposal_id": decision.proposal_id,
        "revision": decision.revision, "prior_revision": decision.prior_revision,
        "result_html_sha256": decision.result_html_sha256,
        "replayed": decision.replayed, "visibility": "private",
    }


@speak_router.post(
    "/projects/{project_id}/html-drafts/{draft_id}/ai-proposals/{proposal_id}/review"
)
async def review_composition_result(
    project_id: str, draft_id: str, proposal_id: str, req: WriteReviewRequest,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_proposals import get_proposal
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        review_result,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        with connect_read(_db()) as con:
            proposal = get_proposal(con, authority, proposal_id=proposal_id)
            if proposal.project_id != project_id or proposal.draft_id != draft_id:
                raise ValueError("composition result not found")
        decision = review_result(
            _db(), authority, proposal_id=proposal_id, mutation_key=idempotency_key,
            action=req.action, base_revision=req.base_revision, rationale=req.rationale,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return _write_review_response(decision)


@speak_router.get(
    "/private-write"
)
async def list_private_write(
    request: Request, response: Response,
    after_document_id: Any = Query(default=""), limit: Any = Query(default="100"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        list_private_write_documents,
    )

    response.headers["Cache-Control"] = "no-store"
    try:
        from interfaces.research.api.notebook_access import NotebookAuthenticationRequired

        authority = interview_account_authority_from_request(request)
        if not isinstance(after_document_id, str) or not isinstance(limit, str):
            raise ValueError("invalid private Write pagination")
        parsed_limit = int(limit)
        if str(parsed_limit) != limit:
            raise ValueError("invalid private Write limit")
        documents = list_private_write_documents(
            _db(), authority, after_document_id=after_document_id, limit=parsed_limit,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except NotebookAuthenticationRequired as exc:
        raise _proposal_error(401, "authentication required") from exc
    except (ValueError, TypeError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    items = [{
        "write_document_id": item.write_document_id,
        "project_id": item.project_id,
        "title": item.title,
        "revision": item.revision,
        "html_sha256": item.body_sha256,
        "visibility": item.visibility,
        "updated_at": item.updated_at,
        "origin_kind": item.origin_kind,
    } for item in documents]
    return {
        "documents": items,
        "next_after_document_id": items[-1]["write_document_id"]
        if len(items) == parsed_limit else None,
    }


@speak_router.post("/private-write", status_code=201)
async def create_native_private_write_document(
    req: NativeWriteCreateRequest, request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        create_native_private_write,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        decision = create_native_private_write(
            _db(), authority, title=req.title, mutation_key=idempotency_key,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "event_id": decision.event_id,
        "write_document_id": decision.write_document_id,
        "project_id": decision.project_id, "title": decision.title,
        "revision": decision.revision, "html_sha256": decision.body_sha256,
        "visibility": "private", "origin_kind": "owner_native",
        "replayed": decision.replayed,
    }


def _write_evidence_source(
    req: WriteCitationEvidenceRequest, owner_id: str, *, legal_con: Any | None = None,
):
    from interfaces.research.api.hosted_document_routes import (
        resolve_legal_citation_insertion_source,
    )
    from substrate.engagement_spine.citation_evidence import parse_citation_evidence
    from substrate.interviews.write_acceptance import EvidenceInsertionSource

    value = req.model_dump()
    supplied_receipt = value.pop("receipt_sha256")
    try:
        evidence = parse_citation_evidence(value)
    except ValueError:
        raise _proposal_error(404, "cited evidence is unavailable") from None
    if evidence is None or evidence.receipt_sha256 != supplied_receipt:
        raise _proposal_error(404, "cited evidence is unavailable")
    title, source_sha, excerpt = resolve_legal_citation_insertion_source(
        evidence.document_id, list(evidence.chunk_ids), owner_id=owner_id, con=legal_con,
    )
    return EvidenceInsertionSource(
        citation_receipt_sha256=evidence.receipt_sha256,
        source_asset_id=evidence.source_asset_id, claim_id=evidence.claim_id,
        source_document_id=evidence.document_id, chunk_ids=evidence.chunk_ids,
        source_title=title, source_content_sha256=source_sha, excerpt_text=excerpt,
    )


def _write_evidence_preview_secret() -> str:
    secret = os.getenv("ANTIEK_AUTH_SECRET", "")
    if len(secret.encode()) < 32:
        raise _proposal_error(503, "evidence insertion preview authority unavailable")
    return secret


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-insertions/preview"
)
async def preview_private_write_evidence_insertion(
    project_id: str, write_document_id: str, req: WriteEvidencePreviewRequest,
    request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
        preview_native_evidence_insertion,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id,
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
        source = _write_evidence_source(req.citation_evidence, authority.account_id)
        preview = preview_native_evidence_insertion(
            _db(), authority, write_document_id=write_document_id,
            base_revision=req.base_revision,
            base_body_sha256=req.base_html_sha256, source=source,
            preview_secret=_write_evidence_preview_secret(),
        )
        if preview.project_id != project_id:
            raise ValueError("private Write document not found")
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(404, str(exc)) from exc
    return {
        "write_document_id": preview.write_document_id,
        "project_id": preview.project_id, "base_revision": preview.base_revision,
        "base_html_sha256": preview.base_body_sha256,
        "proposed_html": preview.proposed_html,
        "proposed_html_sha256": preview.proposed_html_sha256,
        "excerpt_sha256": preview.excerpt_sha256,
        "source_title": preview.source_title,
        "citation_receipt_sha256": preview.citation_receipt_sha256,
        "preview_sha256": preview.preview_sha256,
        "visibility": "private", "origin_kind": "owner_native",
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-insertions"
)
async def apply_private_write_evidence_insertion(
    project_id: str, write_document_id: str, req: WriteEvidenceApplyRequest,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        apply_native_evidence_insertion,
        get_private_write_document,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id,
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
        source = _write_evidence_source(req.citation_evidence, authority.account_id)
        decision = apply_native_evidence_insertion(
            _db(), authority, write_document_id=write_document_id,
            mutation_key=idempotency_key, base_revision=req.base_revision,
            base_body_sha256=req.base_html_sha256, source=source,
            preview_sha256=req.preview_sha256,
            proposed_html_sha256=req.proposed_html_sha256,
            preview_secret=_write_evidence_preview_secret(),
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "event_id": decision.event_id, "write_document_id": decision.write_document_id,
        "project_id": decision.project_id, "prior_revision": decision.prior_revision,
        "revision": decision.revision, "html_sha256": decision.body_sha256,
        "replayed": decision.replayed, "operation": decision.operation,
        "visibility": "private", "origin_kind": "owner_native",
    }


def _write_evidence_bundle_items(
    values: list[WriteEvidenceBundleItemRequest], owner_id: str,
):
    from substrate.interviews.write_acceptance import EvidenceBundleItem

    return tuple(
        EvidenceBundleItem(
            source=_write_evidence_source(item.citation_evidence, owner_id),
            relationship=item.relationship, operator_label=item.operator_label,
        )
        for item in values
    )


def _hydrate_evidence_bundle(bundle_id: str, authority: Any, *, con: Any | None = None):
    from substrate.interviews.write_acceptance import EvidenceBundleItem

    owned_connection = con is None
    if owned_connection:
        con = connect_read(_db())
    assert con is not None
    try:
        rows = con.execute(
            "SELECT relationship, operator_label, citation_receipt_sha256, "
            "source_asset_id, claim_id, source_document_id, chunk_ids_json FROM "
            "interview_write_evidence_bundle_units_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND bundle_id = ? ORDER BY ordinal",
            [authority.account_digest, authority.account_id, bundle_id],
        ).fetchall()
    finally:
        if owned_connection:
            con.close()
    values: list[WriteEvidenceBundleItemRequest] = []
    for row in rows:
        try:
            chunks = json.loads(str(row[6]))
        except json.JSONDecodeError:
            raise _proposal_error(409, "evidence synthesis bundle is corrupt") from None
        values.append(WriteEvidenceBundleItemRequest(
            citation_evidence=WriteCitationEvidenceRequest(
                source_kind="synthesis_claim", source_asset_id=str(row[3]),
                claim_id=str(row[4]), chunk_ids=chunks, document_id=str(row[5]),
                receipt_sha256=str(row[2]),
            ),
            relationship=str(row[0]), operator_label=None if row[1] is None else str(row[1]),
        ))
    if not 2 <= len(values) <= 32:
        raise _proposal_error(404, "evidence synthesis bundle not found")
    if con is None:
        raise RuntimeError("evidence synthesis authority connection is unavailable")
    return tuple(
        EvidenceBundleItem(
            source=_write_evidence_source(
                item.citation_evidence, authority.account_id,
                legal_con=None if owned_connection else con,
            ),
            relationship=item.relationship, operator_label=item.operator_label,
        )
        for item in values
    )


def _project_evidence_bundle_synthesis(
    *, instruction: str, provider_id: str, model_id: str,
    expected_output_tokens: int, items: tuple[Any, ...],
) -> int:
    import math

    from interfaces.research.api.settings_budget import (
        PromptCostEstimateRequest,
        estimate_prompt_cost,
        read_operator_budget,
    )

    input_chars = len(instruction) + 2_000 + sum(
        len(item.source.excerpt_text) + len(item.source.source_title)
        + len(item.operator_label or "") + 300
        for item in items
    )
    estimate = estimate_prompt_cost(
        PromptCostEstimateRequest(
            provider=provider_id, model=model_id, tier=None,
            input_chars=input_chars, expected_output_tokens=expected_output_tokens,
        ),
        budget=read_operator_budget(),
    )
    if (not estimate.pricing_known or estimate.estimated_usd_high is None
            or estimate.provider != provider_id or estimate.model != model_id):
        raise _proposal_error(409, "evidence synthesis pricing is unavailable")
    return max(1, math.ceil(estimate.estimated_usd_high * 100))


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/preview"
)
async def preview_private_write_evidence_bundle(
    project_id: str, write_document_id: str, req: WriteEvidenceBundlePreviewRequest,
    request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
        preview_native_evidence_bundle,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id,
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
        items = _write_evidence_bundle_items(req.items, authority.account_id)
        preview = preview_native_evidence_bundle(
            _db(), authority, write_document_id=write_document_id,
            base_revision=req.base_revision, base_body_sha256=req.base_html_sha256,
            items=items, preview_secret=_write_evidence_preview_secret(),
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "write_document_id": preview.write_document_id,
        "project_id": preview.project_id, "base_revision": preview.base_revision,
        "base_html_sha256": preview.base_body_sha256,
        "proposed_html": preview.proposed_html,
        "proposed_html_sha256": preview.proposed_html_sha256,
        "manifest_sha256": preview.manifest_sha256,
        "preview_sha256": preview.preview_sha256,
        "items": list(preview.items), "visibility": "private",
        "origin_kind": "owner_native", "operation": "evidence_bundle",
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles"
)
async def apply_private_write_evidence_bundle(
    project_id: str, write_document_id: str, req: WriteEvidenceBundleApplyRequest,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        apply_native_evidence_bundle,
        get_private_write_document,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id,
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
        items = _write_evidence_bundle_items(req.items, authority.account_id)
        decision = apply_native_evidence_bundle(
            _db(), authority, write_document_id=write_document_id,
            mutation_key=idempotency_key, base_revision=req.base_revision,
            base_body_sha256=req.base_html_sha256, items=items,
            preview_sha256=req.preview_sha256,
            manifest_sha256=req.manifest_sha256,
            proposed_html_sha256=req.proposed_html_sha256,
            preview_secret=_write_evidence_preview_secret(),
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    with connect_read(_db()) as con:
        bundle = con.execute(
            "SELECT bundle_id FROM interview_write_evidence_bundles_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND native_event_id = ?",
            [authority.account_digest, authority.account_id, decision.event_id],
        ).fetchone()
    if bundle is None:
        raise _proposal_error(409, "private Write evidence bundle receipt is missing")
    return {
        "event_id": decision.event_id, "write_document_id": decision.write_document_id,
        "project_id": decision.project_id, "prior_revision": decision.prior_revision,
        "revision": decision.revision, "html_sha256": decision.body_sha256,
        "replayed": decision.replayed, "operation": decision.operation,
        "visibility": "private", "origin_kind": "owner_native",
        "bundle_id": str(bundle[0]),
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/projection"
)
async def project_evidence_bundle_synthesis_route(
    project_id: str, write_document_id: str, bundle_id: str,
    req: EvidenceBundleSynthesisProjectionRequest, request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from interfaces.research.api.settings_budget import read_operator_budget
    from substrate.interviews.composition_proposals import validate_proposal_inputs
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id,
        )
        if document.project_id != project_id:
            raise ValueError("evidence synthesis bundle not found")
    except (ValueError, WriteAcceptanceConflict) as exc:
        raise _proposal_error(404, "evidence synthesis bundle not found") from exc
    try:
        validate_proposal_inputs(
            base_revision=0, instruction=req.instruction,
            provider_id=req.provider_id, model_id=req.model_id,
            projected_max_cents=1, approved_ceiling_cents=1,
            allowed_model_pairs=_registered_composition_models(),
        )
        hydrated = _hydrate_evidence_bundle(bundle_id, authority)
        projected = _project_evidence_bundle_synthesis(
            instruction=req.instruction, provider_id=req.provider_id,
            model_id=req.model_id, expected_output_tokens=req.expected_output_tokens,
            items=hydrated,
        )
    except ValueError as exc:
        raise _proposal_error(400, str(exc)) from exc
    budget = read_operator_budget()
    return {
        "source_kind": "evidence_bundle", "bundle_id": bundle_id,
        "write_document_id": write_document_id, "project_id": project_id,
        "provider_id": req.provider_id, "model_id": req.model_id,
        "projected_max_cents": projected,
        "expected_output_tokens": req.expected_output_tokens,
        "item_count": len(hydrated),
        "budget": budget.model_dump(), "visibility": "private",
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals",
    status_code=201,
)
async def create_evidence_bundle_synthesis_proposal_route(
    project_id: str, write_document_id: str, bundle_id: str,
    req: EvidenceBundleSynthesisProposalRequest, request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_proposals import validate_proposal_inputs
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        create_evidence_bundle_synthesis_proposal,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    allowed_models = _registered_composition_models()
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id,
        )
        if document.project_id != project_id:
            raise ValueError("evidence synthesis bundle not found")
    except (ValueError, WriteAcceptanceConflict) as exc:
        raise _proposal_error(404, "evidence synthesis bundle not found") from exc
    try:
        validate_proposal_inputs(
            base_revision=req.base_revision, instruction=req.instruction,
            provider_id=req.provider_id, model_id=req.model_id,
            projected_max_cents=1,
            approved_ceiling_cents=req.approved_ceiling_cents,
            allowed_model_pairs=allowed_models,
        )
        hydrated = _hydrate_evidence_bundle(bundle_id, authority)
        projected_max_cents = _project_evidence_bundle_synthesis(
            instruction=req.instruction, provider_id=req.provider_id,
            model_id=req.model_id, expected_output_tokens=req.expected_output_tokens,
            items=hydrated,
        )
        with connect_write(
            _db(), purpose="speak/api:evidence_bundle_synthesis_proposal",
            log_on_close=False,
        ) as con:
            # Legal/source mutations use the same canonical writer lock. Re-resolving
            # after acquiring it closes the hydration-to-freeze custody race.
            locked_hydrated = _hydrate_evidence_bundle(bundle_id, authority, con=con)
            if locked_hydrated != hydrated:
                raise EvidenceBundleSynthesisConflict(
                    "evidence synthesis source changed during proposal staging"
                )
            proposal = create_evidence_bundle_synthesis_proposal(
                con, authority, bundle_id=bundle_id, write_document_id=write_document_id,
                project_id=project_id, mutation_key=idempotency_key,
                base_revision=req.base_revision, instruction=req.instruction,
                provider_id=req.provider_id, model_id=req.model_id,
                projected_max_cents=projected_max_cents,
                approved_ceiling_cents=req.approved_ceiling_cents,
                allowed_model_pairs=allowed_models, hydrated_items=hydrated,
            )
    except EvidenceBundleSynthesisConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "proposal_id": proposal.proposal_id, "source_kind": "evidence_bundle",
        "bundle_id": proposal.bundle_id, "write_document_id": proposal.write_document_id,
        "project_id": proposal.project_id, "revision": proposal.revision,
        "base_revision": proposal.base_revision,
        "source_manifest_sha256": proposal.source_manifest_sha256,
        "source_content_sha256": proposal.source_content_sha256,
        "source_receipt_sha256": proposal.source_receipt_sha256,
        "provider_id": proposal.provider_id, "model_id": proposal.model_id,
        "projected_max_cents": proposal.projected_max_cents,
        "approved_ceiling_cents": proposal.approved_ceiling_cents,
        "instruction": proposal.instruction, "state": proposal.state,
        "item_count": len(proposal.inputs), "visibility": "private",
    }


def _evidence_synthesis_revalidator(authority: Any, bundle_id: str):
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        assert_evidence_bundle_synthesis_custody,
    )

    def revalidate(con: Any, proposal: Any) -> None:
        if proposal.bundle_id != bundle_id:
            raise EvidenceBundleSynthesisConflict("evidence synthesis bundle changed")
        assert_evidence_bundle_synthesis_custody(
            proposal, _hydrate_evidence_bundle(bundle_id, authority, con=con),
        )

    return revalidate


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/execute"
)
async def execute_evidence_bundle_synthesis_proposal_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_execution import (
        CompositionExecutionConflict,
        execute_proposal,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        get_evidence_bundle_synthesis_proposal,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    executor = getattr(request.app.state, "composition_executor", None)
    if (getattr(request.app.state, "composition_execution_enabled", False) is not True
            or executor is None):
        raise _proposal_error(503, "composition execution is not boot-attested")
    revalidator = _evidence_synthesis_revalidator(authority, bundle_id)
    try:
        with connect_read(_db()) as con:
            proposal = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=proposal_id,
            )
            if (proposal.project_id != project_id
                    or proposal.write_document_id != write_document_id
                    or proposal.bundle_id != bundle_id):
                raise ValueError("evidence synthesis proposal not found")
        execution = execute_proposal(
            _db(), authority, proposal_id=proposal_id, attempt_id=idempotency_key,
            route_sha256=str(getattr(executor, "route_sha256", "")), executor=executor,
            source_revalidator=revalidator,
        )
    except (CompositionExecutionConflict, EvidenceBundleSynthesisConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return _composition_execution_response(execution)


@speak_router.get(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/execution"
)
async def get_evidence_bundle_synthesis_execution_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_execution import (
        CompositionExecutionConflict,
        get_execution,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        get_evidence_bundle_synthesis_proposal,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            proposal = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=proposal_id,
            )
            if (proposal.project_id != project_id
                    or proposal.write_document_id != write_document_id
                    or proposal.bundle_id != bundle_id):
                raise ValueError("evidence synthesis execution not found")
        execution = get_execution(
            _db(), authority, proposal_id=proposal_id,
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
    except (CompositionExecutionConflict, EvidenceBundleSynthesisConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, "evidence synthesis execution not found") from exc
    return _composition_execution_response(execution)


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/reconcile"
)
async def reconcile_evidence_bundle_synthesis_execution_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.composition_execution import (
        CompositionExecutionConflict,
        reconcile_checkpointed,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        get_evidence_bundle_synthesis_proposal,
    )

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            proposal = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=proposal_id,
            )
            if (proposal.project_id != project_id
                    or proposal.write_document_id != write_document_id
                    or proposal.bundle_id != bundle_id):
                raise ValueError("evidence synthesis execution not found")
        execution = reconcile_checkpointed(
            _db(), authority, proposal_id=proposal_id,
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
    except (CompositionExecutionConflict, EvidenceBundleSynthesisConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, "evidence synthesis execution not found") from exc
    return _composition_execution_response(execution)


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/write-preview"
)
async def preview_evidence_synthesis_write_acceptance_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    req: EvidenceSynthesisWritePreviewRequest, request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        get_evidence_bundle_synthesis_proposal,
    )
    from substrate.interviews.evidence_synthesis_acceptance import (
        preview_evidence_synthesis_acceptance,
    )
    from substrate.interviews.write_acceptance import WriteAcceptanceConflict

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            bound = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=proposal_id,
            )
            if (bound.project_id != project_id or bound.write_document_id != write_document_id
                    or bound.bundle_id != bundle_id):
                raise ValueError("evidence synthesis proposal not found")
        preview = preview_evidence_synthesis_acceptance(
            _db(), authority, proposal_id=proposal_id,
            write_document_id=write_document_id, base_revision=req.base_revision,
            base_html_sha256=req.base_html_sha256,
            preview_secret=_write_evidence_preview_secret(),
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
        if preview.project_id != project_id or preview.bundle_id != bundle_id:
            raise ValueError("evidence synthesis proposal not found")
    except (WriteAcceptanceConflict, EvidenceBundleSynthesisConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return {
        **preview.__dict__, "visibility": "private", "origin_kind": "owner_native",
        "operation": "synthesis_accept",
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/write-acceptance"
)
async def apply_evidence_synthesis_write_acceptance_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    req: EvidenceSynthesisWriteApplyRequest, request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
        get_evidence_bundle_synthesis_proposal,
    )
    from substrate.interviews.evidence_synthesis_acceptance import (
        apply_evidence_synthesis_acceptance,
    )
    from substrate.interviews.write_acceptance import WriteAcceptanceConflict

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            bound = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=proposal_id,
            )
            if (bound.project_id != project_id or bound.write_document_id != write_document_id
                    or bound.bundle_id != bundle_id):
                raise ValueError("evidence synthesis proposal not found")
        decision = apply_evidence_synthesis_acceptance(
            _db(), authority, proposal_id=proposal_id,
            write_document_id=write_document_id, mutation_key=idempotency_key,
            base_revision=req.base_revision, base_html_sha256=req.base_html_sha256,
            preview_sha256=req.preview_sha256,
            proposed_html_sha256=req.proposed_html_sha256,
            preview_secret=_write_evidence_preview_secret(),
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
        if decision.edit.project_id != project_id or decision.bundle_id != bundle_id:
            raise ValueError("evidence synthesis proposal not found")
    except (WriteAcceptanceConflict, EvidenceBundleSynthesisConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return {
        "acceptance_id": decision.acceptance_id,
        "event_id": decision.edit.event_id, "proposal_id": decision.proposal_id,
        "bundle_id": decision.bundle_id, "execution_run_id": decision.execution_run_id,
        "write_document_id": decision.edit.write_document_id,
        "project_id": decision.edit.project_id,
        "prior_revision": decision.edit.prior_revision,
        "revision": decision.edit.revision, "html_sha256": decision.edit.body_sha256,
        "receipt_sha256": decision.receipt_sha256, "replayed": decision.edit.replayed,
        "visibility": "private", "origin_kind": "owner_native",
        "operation": "synthesis_accept",
    }


def _synthesis_knowledge_candidates(items: list[SynthesisKnowledgeCandidateRequest]):
    from substrate.interviews.synthesis_knowledge_admission import (
        SynthesisKnowledgeCandidate,
    )

    return tuple(
        SynthesisKnowledgeCandidate(
            unit_index=item.unit_index, kind=item.kind, text=item.text,
        )
        for item in items
    )


def _synthesis_knowledge_items(items: Any) -> list[dict[str, Any]]:
    return [{
        "ordinal": item.ordinal, "unit_index": item.unit_index, "kind": item.kind,
        "original_text_sha256": item.original_text_sha256,
        "admitted_text": item.admitted_text,
        "admitted_text_sha256": item.admitted_text_sha256,
        "canonical_text": item.canonical_text, "graph_node_id": item.graph_node_id,
        "disposition": item.disposition, "evidence_sha256": item.evidence_sha256,
        "item_receipt_sha256": item.item_receipt_sha256,
        "evidence": list(item.evidence),
    } for item in items]


@speak_router.get(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/acceptances/{acceptance_id}/"
    "knowledge-candidates"
)
async def list_synthesis_knowledge_candidates_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    acceptance_id: str, request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
    )
    from substrate.interviews.synthesis_knowledge_admission import (
        SynthesisKnowledgeAdmissionConflict,
        list_synthesis_knowledge_candidates,
    )
    from substrate.interviews.write_acceptance import WriteAcceptanceConflict

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            bound = con.execute(
                "SELECT project_id, bundle_id, proposal_id, write_document_id FROM "
                "interview_write_synthesis_acceptances_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND acceptance_id = ?",
                [authority.account_digest, authority.account_id, acceptance_id],
            ).fetchone()
        if bound is None or tuple(map(str, bound)) != (
            project_id, bundle_id, proposal_id, write_document_id,
        ):
            raise ValueError("synthesis knowledge source not found")
        units = list_synthesis_knowledge_candidates(
            _db(), authority, acceptance_id=acceptance_id, proposal_id=proposal_id,
            write_document_id=write_document_id,
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
    except (WriteAcceptanceConflict, EvidenceBundleSynthesisConflict,
            SynthesisKnowledgeAdmissionConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (RuntimeError, TypeError, ValueError) as exc:
        raise _proposal_error(404, "synthesis knowledge source not found") from exc
    return {
        "acceptance_id": acceptance_id, "proposal_id": proposal_id,
        "units": [{
            "unit_index": unit.unit_index, "text": unit.text,
            "original_text_sha256": unit.original_text_sha256,
            "evidence": list(unit.evidence),
        } for unit in units],
        "epistemic_status": "model_proposed", "verification": "unverified",
        "visibility": "private",
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/acceptances/{acceptance_id}/"
    "knowledge-preview"
)
async def preview_synthesis_knowledge_admission_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    acceptance_id: str, req: SynthesisKnowledgePreviewRequest,
    request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
    )
    from substrate.interviews.synthesis_knowledge_admission import (
        SynthesisKnowledgeAdmissionConflict,
        preview_synthesis_knowledge_admission,
    )
    from substrate.interviews.write_acceptance import WriteAcceptanceConflict

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            bound = con.execute(
                "SELECT project_id, bundle_id, proposal_id, write_document_id FROM "
                "interview_write_synthesis_acceptances_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND acceptance_id = ?",
                [authority.account_digest, authority.account_id, acceptance_id],
            ).fetchone()
        if bound is None or tuple(map(str, bound)) != (
            project_id, bundle_id, proposal_id, write_document_id,
        ):
            raise ValueError("synthesis knowledge source not found")
        target = _request_event_authority(request, req.target_investigation_id)
        preview = preview_synthesis_knowledge_admission(
            _db(), authority, acceptance_id=acceptance_id, proposal_id=proposal_id,
            write_document_id=write_document_id, target=target,
            candidates=_synthesis_knowledge_candidates(req.items),
            preview_secret=_write_evidence_preview_secret(),
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
        if preview.proposal_id != proposal_id or preview.acceptance_id != acceptance_id:
            raise ValueError("synthesis knowledge source not found")
    except (WriteAcceptanceConflict, EvidenceBundleSynthesisConflict,
            SynthesisKnowledgeAdmissionConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (RuntimeError, TypeError, ValueError) as exc:
        raise _proposal_error(404, "synthesis knowledge source not found") from exc
    return {
        "acceptance_id": preview.acceptance_id, "proposal_id": preview.proposal_id,
        "target_investigation_id": preview.target_investigation_id,
        "target_investigation_digest": preview.target_investigation_digest,
        "item_manifest_sha256": preview.item_manifest_sha256,
        "preview_sha256": preview.preview_sha256,
        "items": _synthesis_knowledge_items(preview.items),
        "epistemic_status": "model_proposed_operator_admitted",
        "verification": "unverified", "visibility": "private",
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/evidence-bundles/"
    "{bundle_id}/ai-proposals/{proposal_id}/acceptances/{acceptance_id}/"
    "knowledge-admission"
)
async def apply_synthesis_knowledge_admission_route(
    project_id: str, write_document_id: str, bundle_id: str, proposal_id: str,
    acceptance_id: str, req: SynthesisKnowledgeApplyRequest,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.evidence_bundle_synthesis import (
        EvidenceBundleSynthesisConflict,
    )
    from substrate.interviews.synthesis_knowledge_admission import (
        SynthesisKnowledgeAdmissionConflict,
        apply_synthesis_knowledge_admission,
    )
    from substrate.interviews.write_acceptance import WriteAcceptanceConflict

    response.headers["Cache-Control"] = "no-store"
    authority = interview_account_authority_from_request(request)
    try:
        with connect_read(_db()) as con:
            bound = con.execute(
                "SELECT project_id, bundle_id, proposal_id, write_document_id FROM "
                "interview_write_synthesis_acceptances_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND acceptance_id = ?",
                [authority.account_digest, authority.account_id, acceptance_id],
            ).fetchone()
        if bound is None or tuple(map(str, bound)) != (
            project_id, bundle_id, proposal_id, write_document_id,
        ):
            raise ValueError("synthesis knowledge source not found")
        target = _request_event_authority(request, req.target_investigation_id)
        decision = apply_synthesis_knowledge_admission(
            _db(), authority, acceptance_id=acceptance_id, proposal_id=proposal_id,
            write_document_id=write_document_id, target=target,
            candidates=_synthesis_knowledge_candidates(req.items),
            preview_sha256=req.preview_sha256, mutation_key=idempotency_key,
            preview_secret=_write_evidence_preview_secret(),
            source_revalidator=_evidence_synthesis_revalidator(authority, bundle_id),
        )
        if decision.acceptance_id != acceptance_id:
            raise ValueError("synthesis knowledge source not found")
    except (WriteAcceptanceConflict, EvidenceBundleSynthesisConflict,
            SynthesisKnowledgeAdmissionConflict) as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (RuntimeError, TypeError, ValueError) as exc:
        raise _proposal_error(404, "synthesis knowledge source not found") from exc
    return {
        "admission_id": decision.admission_id, "acceptance_id": decision.acceptance_id,
        "proposal_id": proposal_id, "bundle_id": bundle_id,
        "write_document_id": write_document_id, "project_id": project_id,
        "target_investigation_id": decision.target_investigation_id,
        "receipt_sha256": decision.receipt_sha256, "replayed": decision.replayed,
        "items": _synthesis_knowledge_items(decision.items),
        "epistemic_status": "model_proposed_operator_admitted",
        "verification": "unverified", "visibility": "private",
    }


@speak_router.get(
    "/projects/{project_id}/private-write/{write_document_id}"
)
async def get_private_write(
    project_id: str, write_document_id: str, request: Request, response: Response
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return {
        "write_document_id": document.write_document_id,
        "project_id": document.project_id, "title": document.title,
        "revision": document.revision, "html": document.body_html,
        "html_sha256": document.body_sha256, "visibility": document.visibility,
        "origin_kind": document.origin_kind,
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/undo"
)
async def undo_private_write_acceptance(
    project_id: str, write_document_id: str, req: WriteUndoRequest,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        undo_acceptance,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        with connect_read(_db()) as con:
            target = con.execute(
                "SELECT write_document_id, project_id FROM "
                "interview_write_review_events_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND event_id = ? AND action = 'accept'",
                [authority.account_digest, authority.account_id, req.target_event_id],
            ).fetchone()
            if target is None or (str(target[0]), str(target[1])) != (
                write_document_id, project_id
            ):
                raise ValueError("accepted Write review event not found")
        decision = undo_acceptance(
            _db(), authority, target_event_id=req.target_event_id,
            mutation_key=idempotency_key, base_revision=req.base_revision,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return _write_review_response(decision)


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/edits"
)
async def edit_private_write_document(
    project_id: str, write_document_id: str, req: WriteEditRequest,
    request: Request, response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        edit_private_write,
        get_private_write_document,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    try:
        decision = edit_private_write(
            _db(), authority, write_document_id=write_document_id,
            mutation_key=idempotency_key, base_revision=req.base_revision,
            base_body_sha256=req.base_html_sha256, body_html=req.html,
            summary=req.summary,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "event_id": decision.event_id,
        "write_document_id": decision.write_document_id,
        "project_id": decision.project_id,
        "revision": decision.revision,
        "prior_revision": decision.prior_revision,
        "html_sha256": decision.body_sha256,
        "replayed": decision.replayed,
        "visibility": "private",
    }


def _private_write_revision_response(revision: Any, *, include_html: bool) -> dict:
    value = {
        "revision": revision.revision, "operation": revision.operation,
        "event_id": revision.event_id, "html_sha256": revision.body_sha256,
        "prior_html_sha256": revision.prior_body_sha256,
        "root_acceptance_event_id": revision.root_acceptance_event_id,
        "proposal_id": revision.proposal_id,
        "target_revision": revision.target_revision,
        "target_html_sha256": revision.target_body_sha256,
        "created_at": revision.created_at, "has_summary": revision.has_summary,
        "origin_kind": revision.origin_kind,
    }
    if include_html:
        value["html"] = revision.body_html
    return value


def _private_write_query_int(value: Any, label: str) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    raise ValueError(f"private Write {label} is invalid")


@speak_router.get(
    "/projects/{project_id}/private-write/{write_document_id}/history"
)
async def list_private_write_history(
    project_id: str, write_document_id: str, request: Request, response: Response,
    after_revision: Any = Query(default=0),
    limit: Any = Query(default=100),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
        list_private_write_revisions,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    try:
        after_revision = _private_write_query_int(after_revision, "history cursor")
        limit = _private_write_query_int(limit, "history limit")
        revisions = list_private_write_revisions(
            _db(), authority, write_document_id=write_document_id,
            after_revision=after_revision, limit=limit,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "write_document_id": write_document_id, "project_id": project_id,
        "current_revision": document.revision,
        "origin_kind": document.origin_kind,
        "revisions": [
            _private_write_revision_response(item, include_html=False)
            for item in revisions
        ],
    }


@speak_router.get(
    "/projects/{project_id}/private-write/{write_document_id}/revisions/{revision}"
)
async def get_private_write_historical_revision(
    project_id: str, write_document_id: str, revision: Any,
    request: Request, response: Response,
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
        get_private_write_revision,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        revision = _private_write_query_int(revision, "revision")
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
        historical = get_private_write_revision(
            _db(), authority, write_document_id=write_document_id, revision=revision
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    return {
        "write_document_id": write_document_id, "project_id": project_id,
        "is_current": revision == document.revision,
        **_private_write_revision_response(historical, include_html=True),
    }


@speak_router.post(
    "/projects/{project_id}/private-write/{write_document_id}/restores"
)
async def restore_private_write_document(
    project_id: str, write_document_id: str, req: WriteRestoreRequest,
    request: Request, response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.write_acceptance import (
        WriteAcceptanceConflict,
        get_private_write_document,
        restore_private_write_revision,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        document = get_private_write_document(
            _db(), authority, write_document_id=write_document_id
        )
        if document.project_id != project_id:
            raise ValueError("private Write document not found")
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _proposal_error(404, str(exc)) from exc
    try:
        decision = restore_private_write_revision(
            _db(), authority, write_document_id=write_document_id,
            mutation_key=idempotency_key, base_revision=req.base_revision,
            base_body_sha256=req.base_html_sha256,
            target_revision=req.target_revision,
        )
    except WriteAcceptanceConflict as exc:
        raise _proposal_error(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise _proposal_error(400, str(exc)) from exc
    return {
        "event_id": decision.event_id,
        "write_document_id": decision.write_document_id,
        "project_id": decision.project_id, "revision": decision.revision,
        "prior_revision": decision.prior_revision,
        "html_sha256": decision.body_sha256, "replayed": decision.replayed,
        "operation": "restore", "target_revision": req.target_revision,
        "visibility": "private",
    }


@speak_router.post(
    "/projects/{project_id}/interviews/{interview_id}/contributor-attribution",
    status_code=201,
)
async def bind_canonical_contributor(
    project_id: str,
    interview_id: str,
    req: ContributorAttributionRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.contributor import (
        ContributorAttributionConflict,
        record_attribution,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    with connect_write(_db(), purpose="speak/api:contributor_attribution") as con:
        try:
            attribution = record_attribution(
                con, authority, project_id=project_id, interview_id=interview_id,
                command_id=idempotency_key, contributor_ref=req.contributor_ref,
                display_label=req.display_label, evidence_basis=req.evidence_basis,
                evidence_ref=req.evidence_ref,
            )
        except ContributorAttributionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "event_id": attribution.event_id, "project_id": attribution.project_id,
        "interview_id": attribution.interview_id,
        "contributor_ref": attribution.contributor_ref,
        "display_label": attribution.display_label,
        "evidence_basis": attribution.evidence_basis,
        "evidence_ref": attribution.evidence_ref,
        "consent_event_ids": list(attribution.consent_event_ids),
        "active": attribution.active,
    }


@speak_router.get(
    "/projects/{project_id}/interviews/{interview_id}/contributor-attribution"
)
async def get_canonical_contributor(
    project_id: str, interview_id: str, request: Request, response: Response
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.contributor import (
        ContributorAttributionConflict,
        get_active_attribution,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    with connect_write(_db(), purpose="speak/api:get_contributor_attribution") as con:
        try:
            attribution = get_active_attribution(
                con, authority, project_id=project_id, interview_id=interview_id
            )
        except ContributorAttributionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if attribution is None:
        raise HTTPException(status_code=404, detail="contributor attribution not found")
    return {
        "event_id": attribution.event_id, "project_id": attribution.project_id,
        "interview_id": attribution.interview_id,
        "contributor_ref": attribution.contributor_ref,
        "display_label": attribution.display_label,
        "evidence_basis": attribution.evidence_basis,
        "evidence_ref": attribution.evidence_ref,
        "consent_event_ids": list(attribution.consent_event_ids),
        "active": attribution.active,
    }


@speak_router.post(
    "/projects/{project_id}/interviews/{interview_id}/contributor-attribution/revoke"
)
async def revoke_canonical_contributor(
    project_id: str,
    interview_id: str,
    req: ContributorRevocationRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    from interfaces.research.api.interview_access import (
        interview_account_authority_from_request,
    )
    from substrate.interviews.contributor import (
        ContributorAttributionConflict,
        revoke_attribution,
    )

    authority = interview_account_authority_from_request(request)
    response.headers["Cache-Control"] = "no-store"
    with connect_write(_db(), purpose="speak/api:revoke_contributor_attribution") as con:
        try:
            event_id = revoke_attribution(
                con, authority, project_id=project_id, interview_id=interview_id,
                command_id=idempotency_key, target_event_id=req.target_event_id,
            )
        except ContributorAttributionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"event_id": event_id, "revoked_event_id": req.target_event_id}


@speak_router.post("/projects/{project_id}/subject-consent", status_code=200)
async def set_subject_consent(project_id: str, req: SubjectConsentRequest) -> dict:
    with _translate(), _write("speak/api:subject_consent") as con:
        subject_consent_mod.record_subject_consent(
            con, project_id=project_id, subject_ref=req.subject_ref,
            subject_status=req.subject_status, consent_granted=req.consent_granted,
            rationale=req.rationale,
        )
    return {"project_id": project_id, "subject_ref": req.subject_ref}


@speak_router.post("/projects/{project_id}/contributors", status_code=201)
async def map_contributor(project_id: str, req: ContributorRequest) -> dict:
    with _translate(), _write("speak/api:contributor") as con:
        m = contributor_mod.map_contributor(
            con, interview_id=req.interview_id, project_id=project_id,
            ip_holder_id=req.ip_holder_id, display_name=req.display_name,
            legal_contact_email=req.legal_contact_email,
        )
    return {"interview_id": m.interview_id, "ip_holder_id": m.ip_holder_id,
            "holding_bucket": m.holding_bucket}


@speak_router.post("/projects/{project_id}/takedowns", status_code=201)
async def request_takedown(project_id: str, req: TakedownRequestModel) -> dict:
    with _translate(), _write("speak/api:takedown") as con:
        tid = takedown_mod.request_takedown(
            con, project_id=project_id, target_kind=req.target_kind,
            target_id=req.target_id, requested_by=req.requested_by, reason=req.reason,
        )
    return {"takedown_id": tid, "status": "active"}


_SPEAK_TO_WRITE_COMMANDS_SQL = """
CREATE TABLE IF NOT EXISTS speak_to_write_handoff_commands (
    command_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    events_json TEXT NOT NULL
)
"""


@speak_router.post("/projects/{project_id}/draft")
async def draft(
    project_id: str,
    req: DraftRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    require_event_persistence()
    event_stream_id = f"seam-speak-{project_id}"
    authority = _request_event_authority(request, event_stream_id)
    command_id = _validated_command_id(idempotency_key)
    fingerprint = content_addressed_id(
        "cmd", f"speak-to-write|{project_id}|public={req.public}"
    )
    with _translate(), _write("speak/api:draft") as con:  # noqa: SIM117
        with _transaction(con):
            con.execute(_SPEAK_TO_WRITE_COMMANDS_SQL)
            receipt = con.execute(
                "SELECT fingerprint, response_json, events_json "
                "FROM speak_to_write_handoff_commands WHERE command_id = ?",
                [command_id],
            ).fetchone()
            if receipt is not None and receipt[0] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different draft",
                )
            if receipt is None:
                investigation_id = f"speak-biography-{project_id}"
                outline = biography.assemble_outline(
                    con,
                    project_id=project_id,
                    composer=WriteOutlineComposer(
                        con,
                        investigation_id=investigation_id,
                        emit_events=False,
                    ),
                )
                d = biography.generate_draft(
                    con, project_id=project_id, outline=outline, public=req.public
                )
                update_section_prose(
                    con,
                    section_id=outline.section_id,
                    prose_text=d.prose_text,
                    prose_provenance={
                        str(k): v for k, v in d.prose_provenance.items()
                    },
                )
                response = {
                    "deliverable_id": outline.deliverable_id,
                    "prose_text": d.prose_text,
                    "cited_interview_ids": list(d.cited_interview_ids),
                    "excluded_claim_ids": list(d.excluded_claim_ids),
                    "unverified_marked_claim_ids": list(d.unverified_marked_claim_ids),
                    "voice_style_score": d.voice_style_score,
                    "voice_style_ok": d.voice_style_ok,
                }
                placed_claims = {
                    row[0]: (row[1], int(row[2]))
                    for row in con.execute(
                        "SELECT source_block_id, outline_block_id, block_index "
                        "FROM outline_blocks "
                        "WHERE section_id = ? AND source_block_kind = 'speak_claim'",
                        [outline.section_id],
                    ).fetchall()
                }
                emitted_at = datetime.now(UTC).isoformat()
                events = [
                    {
                        "event_id": content_addressed_id(
                            "evt", f"speak-to-write|{command_id}|{block.block_id}"
                        ),
                        "placement_event_id": content_addressed_id(
                            "evt",
                            f"speak-write-placement|{command_id}|{block.block_id}",
                        ),
                        "emitted_at": emitted_at,
                        "claim_id": block.block_id,
                        "outline_block_id": placed_claims[block.block_id][0],
                        "block_index": placed_claims[block.block_id][1],
                        "deliverable_id": outline.deliverable_id,
                        "section_id": outline.section_id,
                        "contributor_interview_ids": list(
                            block.contributor_interview_ids
                        ),
                    }
                    for block in outline.blocks
                    if block.block_id in placed_claims
                ]
                con.execute(
                    "INSERT INTO speak_to_write_handoff_commands VALUES (?, ?, ?, ?)",
                    [
                        command_id,
                        fingerprint,
                        json.dumps(response, sort_keys=True),
                        json.dumps(events, sort_keys=True),
                    ],
                )
            else:
                response = json.loads(receipt[1])
                events = json.loads(receipt[2])

    investigation_id = event_stream_id
    for event_receipt in events:
        append_event_once_authorized(
            authority,
            prepare_typed_event(
                investigation_id,
                SeamSpeakToWritePayload(
                    entity_id=event_receipt["claim_id"],
                    provenance_ref=event_receipt["claim_id"],
                    contributor_interview_ids=event_receipt[
                        "contributor_interview_ids"
                    ],
                ),
                event_id=event_receipt["event_id"],
                emitted_at=event_receipt["emitted_at"],
                role="speak_biography",
            )
        )
        append_event_once_authorized(
            authority,
            prepare_typed_event(
                investigation_id,
                OutlineBlockPlacedPayload(
                    outline_block_id=event_receipt["outline_block_id"],
                    deliverable_id=event_receipt["deliverable_id"],
                    section_id=event_receipt["section_id"],
                    block_kind="synthesized",
                    provenance_kind="synthesized",
                    node_id=None,
                    block_index=event_receipt["block_index"],
                ),
                event_id=event_receipt["placement_event_id"],
                emitted_at=event_receipt["emitted_at"],
                role="write_composition",
            )
        )
    return response


_SPEAK_TO_READ_COMMANDS_SQL = """
CREATE TABLE IF NOT EXISTS speak_to_read_handoff_commands (
    command_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    seam_event_id TEXT,
    seam_emitted_at TEXT
)
"""


@speak_router.post("/projects/{project_id}/publish", status_code=201)
async def publish(
    project_id: str,
    req: PublishRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    require_event_persistence()
    event_stream_id = f"seam-speak-{project_id}"
    authority = _request_event_authority(request, event_stream_id)
    command_id = _validated_command_id(idempotency_key)
    ad_revenue = _decimal(req.ad_revenue_usd, "ad_revenue_usd")
    fingerprint = content_addressed_id(
        "cmd",
        "speak-to-read|"
        + json.dumps(
            {
                "project_id": project_id,
                "deliverable_id": req.deliverable_id,
                "subject_ref": req.subject_ref,
                "ad_revenue_usd": str(ad_revenue),
                "quality_scores": req.quality_scores,
            },
            sort_keys=True,
        ),
    )
    with _translate(), _write("speak/api:publish") as con:  # noqa: SIM117
        with _transaction(con):
            con.execute(_SPEAK_TO_READ_COMMANDS_SQL)
            receipt = con.execute(
                "SELECT fingerprint, response_json, seam_event_id, seam_emitted_at "
                "FROM speak_to_read_handoff_commands WHERE command_id = ?",
                [command_id],
            ).fetchone()
            if receipt is not None and receipt[0] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different publication",
                )
            if receipt is None:
                publication_id = content_addressed_id(
                    "pub", f"speak-publication|{command_id}"
                )
                result = publish_mod.publish(
                    con,
                    project_id=project_id,
                    deliverable_id=req.deliverable_id,
                    subject_ref=req.subject_ref,
                    ad_revenue_usd=ad_revenue,
                    quality_scores=req.quality_scores,
                    publication_id=publication_id,
                    emit_events=False,
                )
                document_id = None
                seam_event_id = None
                seam_emitted_at = None
                if result.served:
                    if not req.deliverable_id:
                        raise HTTPException(
                            status_code=409,
                            detail="assemble the story before publishing it",
                        )
                    deliverable = con.execute(
                        "SELECT title FROM deliverables WHERE deliverable_id = ?",
                        [req.deliverable_id],
                    ).fetchone()
                    sections = con.execute(
                        "SELECT section_id, title, prose_text FROM deliverable_sections "
                        "WHERE deliverable_id = ? ORDER BY section_index",
                        [req.deliverable_id],
                    ).fetchall()
                    if deliverable is None or not sections or not any(
                        str(row[2] or "").strip() for row in sections
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="assembled story has no publishable prose",
                        )
                    claim_counts = con.execute(
                        "SELECT count(*), count(c.claim_id) FROM outline_blocks b "
                        "JOIN deliverable_sections s ON s.section_id = b.section_id "
                        "LEFT JOIN speak_claims c ON c.claim_id = b.source_block_id "
                        "AND c.project_id = ? "
                        "WHERE s.deliverable_id = ? "
                        "AND b.source_block_kind = 'speak_claim'",
                        [project_id, req.deliverable_id],
                    ).fetchone()
                    if claim_counts[0] == 0 or claim_counts[0] != claim_counts[1]:
                        raise HTTPException(
                            status_code=409,
                            detail="assembled story does not belong to this Speak project",
                        )
                    document_id = content_addressed_id(
                        "doc", f"speak-publication|{command_id}"
                    )
                    body_parts = [f"# {deliverable[0]}"]
                    for _section_id, section_title, prose_text in sections:
                        prose = str(prose_text or "").strip()
                        if not prose:
                            continue
                        if section_title:
                            body_parts.append(f"## {section_title}")
                        body_parts.append(prose)
                    raw_text = "\n\n".join(body_parts)
                    insert_document(
                        con,
                        document_id=document_id,
                        source_tier=1,
                        document_type="book",
                        title=deliverable[0],
                        investigation_id=f"speak-biography-{project_id}",
                        raw_text=raw_text,
                        content_class=result.content_class,
                        metadata={
                            "publication_id": publication_id,
                            "project_id": project_id,
                            "deliverable_id": req.deliverable_id,
                            "provenance_class": "speak_derived",
                            "view_format": "html",
                        },
                    )
                    readable_sections = [
                        (str(section_title or "Biography"), str(prose_text or "").strip())
                        for _section_id, section_title, prose_text in sections
                        if str(prose_text or "").strip()
                    ]
                    toc = [
                        TocItem(
                            title=section_title,
                            page_index=chunk_index,
                        )
                        for chunk_index, (section_title, _prose) in enumerate(readable_sections)
                    ]
                    # Register before inserting chunks: DuckDB cannot update a
                    # referenced document row once chunk foreign keys exist.
                    register_book(
                        con,
                        document_id=document_id,
                        content_class=result.content_class,
                        toc=toc,
                        page_count=max(1, len(readable_sections)),
                        pagination_scheme="html_section",
                        provenance=f"Speak project {project_id}",
                        license_basis="consent and verification gates passed",
                    )
                    for chunk_index, (section_title, prose) in enumerate(readable_sections):
                        insert_chunk(
                            con,
                            chunk_id=content_addressed_id(
                                "chunk", f"{document_id}|{chunk_index}|{prose}"
                            ),
                            document_id=document_id,
                            chunk_index=chunk_index,
                            section_path=section_title,
                            text=prose,
                        )
                    seam_event_id = content_addressed_id(
                        "evt", f"speak-to-read|{command_id}"
                    )
                    seam_emitted_at = datetime.now(UTC).isoformat()
                response = {
                    "publication_id": result.publication_id,
                    "document_id": document_id,
                    "visibility": result.visibility,
                    "served": result.served,
                    "servability": result.servability,
                    "content_class": result.content_class,
                    "accrual_lines": [
                        {
                            "interview_id": line.interview_id,
                            "ip_holder_id": line.ip_holder_id,
                            "share_fraction": line.share_fraction,
                            "amount_usd": str(line.amount_usd),
                            "slop_gated": line.slop_gated,
                        }
                        for line in result.accrual_lines
                    ],
                }
                con.execute(
                    "INSERT INTO speak_to_read_handoff_commands VALUES (?, ?, ?, ?, ?)",
                    [
                        command_id,
                        fingerprint,
                        json.dumps(response, sort_keys=True),
                        seam_event_id,
                        seam_emitted_at,
                    ],
                )
            else:
                response = json.loads(receipt[1])
                seam_event_id, seam_emitted_at = receipt[2], receipt[3]

    if seam_event_id:
        append_event_once_authorized(
            authority,
            prepare_typed_event(
                event_stream_id,
                SeamSpeakToReadPayload(
                    entity_id=response["document_id"],
                    provenance_ref=response["publication_id"],
                    publish_gate_passed=True,
                ),
                event_id=seam_event_id,
                emitted_at=seam_emitted_at,
                role="speak_publishing",
                document_id=response["document_id"],
            )
        )
    return response


@speak_router.post("/interviews/{interview_id}/grade", status_code=201)
async def grade_interview(interview_id: str, req: GradeInterviewRequest) -> dict:
    """AI-grade one interview against the requester's information goal
    (SPR-10 M3). The grade is produced by the verifier (here: the honest
    deterministic rubric, since no ``dispatch_fn`` is injected on this
    route — production would pass ``substrate.dispatch.dispatch``), NOT by
    the requester. The grade is persisted (kept, even when it fails) and
    returned with its honest/gamed labels. NO money moves here."""
    with _translate(), _write("speak/api:grade") as con:
        prow = con.execute(
            "SELECT project_id FROM interviews WHERE interview_id = ?", [interview_id]
        ).fetchone()
        if prow is None:
            raise HTTPException(status_code=404, detail=f"interview {interview_id} not found")
        goal = payout_verifier.InterviewGoal(
            information_goal=req.information_goal,
            must_cover=tuple(req.must_cover),
            budget_usd=_decimal(req.budget_usd, "budget_usd"),
            per_interview_cap_usd=_decimal(req.per_interview_cap_usd, "per_interview_cap_usd"),
        )
        grade = payout_verifier.grade_interview(
            con, project_id=prow[0], interview_id=interview_id, goal=goal,
        )
    return {
        "interview_id": grade.interview_id, "score": grade.score,
        "passed": grade.passed, "honest": grade.honest,
        "gamed_risk": grade.gamed_risk, "rationale": grade.rationale,
        "graded_by": grade.graded_by,
    }


@speak_router.post("/projects/{project_id}/release-payout", status_code=201)
async def release_payout(project_id: str, req: ReleasePayoutRequest) -> dict:
    """Release graded payout for a project (SPR-10 M3), routed through §9
    (``accrue_contributions``) into ESCROW — never disbursed. Enforces the
    requester's budget + per-interview cap. With zero ad buyers this
    accrues $0 while still tracking the §9-weighted share fractions; money
    only leaves escrow post-G2/G3 (which this never triggers)."""
    with _translate(), _write("speak/api:release_payout") as con:
        goal = payout_verifier.InterviewGoal(
            information_goal=req.information_goal,
            budget_usd=_decimal(req.budget_usd, "budget_usd"),
            per_interview_cap_usd=_decimal(req.per_interview_cap_usd, "per_interview_cap_usd"),
        )
        release = payout_verifier.release_payout(
            con, project_id=project_id, goal=goal,
            ad_revenue_usd=_decimal(req.ad_revenue_usd, "ad_revenue_usd"),
            publication_id=req.publication_id,
        )
    return {
        "spent_usd": str(release.spent_usd),
        "budget_usd": str(release.budget_usd),
        "budget_exhausted": release.budget_exhausted,
        "capped_interview_ids": list(release.capped_interview_ids),
        "accrual_lines": [
            {"interview_id": a.interview_id, "share_fraction": a.share_fraction,
             "amount_usd": str(a.amount_usd), "slop_gated": a.slop_gated}
            for a in release.accrual_lines
        ],
    }


@speak_router.post("/projects/{project_id}/book-orders", status_code=201)
async def order_book(project_id: str, req: BookOrderRequest) -> dict:
    with _translate(), _write("speak/api:book_order") as con:
        quote = physical_book.order_physical_book(
            con, project_id=project_id, book_format=req.book_format,
            page_count=req.page_count, publication_id=req.publication_id,
        )
    return {"order_id": quote.order_id, "book_format": quote.book_format,
            "provider": quote.provider, "cost_usd": str(quote.cost_usd),
            "payer": quote.payer, "fulfilled": quote.fulfilled}


# ---------------------------------------------------------------------------
# Invitee surface — TOKEN-AUTHORIZED, unauthenticated.
#
# The invitee (a subject's friend or family member) is a SOURCE, not an
# account — that line is what keeps v1 inside the single-operator
# constraint, and real contributor accounts are gated on G7. Their link
# carries a token, and the token IS their credential. So these endpoints:
#   • are keyed by TOKEN, never by a caller-supplied interview_id;
#   • verify the token resolves (404 otherwise) and operate ONLY on that
#     one interview;
#   • live under the /speak/invite/ prefix, which the operator-auth
#     middleware treats as an open path (the token, not an operator
#     session, authorizes the request).
# This is a deliberately separate surface from the operator /speak/...
# endpoints above; an invitee never touches an operator-authed route.
# ---------------------------------------------------------------------------


class InviteConsentRequest(BaseModel):
    scopes: list[str] = Field(..., min_length=1)


class InviteAnswerRequest(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=512)
    transcript: str = Field(..., min_length=1)
    duration_seconds: float = Field(default=0.0, ge=0.0, le=86_400)


# Injectable transcriber seam for the token-gated voice route. ``None`` (the
# default) means ``async_interview.transcribe`` builds the real
# ``WhisperTranscriber`` — which raises (→ AsrError → 503) when no model
# provider is configured. Tests set this to a stub so the voice→answer bridge
# is exercisable hermetically, the same injection point the operator voice
# path and ``async_interview.transcribe`` already use. Never a second pipeline.
_INVITEE_TRANSCRIBER: Any | None = None


def _require_token(con: Any, token: str) -> tuple[str, str]:
    """Resolve an invite token to (interview_id, project_id) or 404. The
    token is the invitee's credential — a bad/expired token is the only
    thing standing between a stranger and this interview, so we fail
    closed."""
    iv = invitations.resolve_token(con, token)
    if iv is None:
        raise HTTPException(status_code=404, detail="unknown or expired invite link")
    return iv.interview_id, iv.project_id


def _canonical_capability(con: Any, token: str):
    from substrate.interviews.capability import resolve_invite

    return resolve_invite(con, token)


@speak_router.get("/invite/{token}")
async def invitee_landing(token: str) -> dict:
    """One call for the invitee's landing page: the project they've been
    invited to, the consent scopes the invite asks for, what they've
    already granted (so a returning invitee skips re-consent), and — once
    consented — the pending questions + transcript so far."""
    with _translate(), _write("speak/api:invite_landing") as con:
        capability = _canonical_capability(con, token)
        if capability is not None:
            row = con.execute(
                "SELECT i.status, i.transcript_turns, p.title "
                "FROM interviews_authority i JOIN interview_projects_authority p "
                "ON p.account_digest = i.account_digest AND p.owner_user_id = i.owner_user_id "
                "AND p.project_id = i.project_id WHERE i.account_digest = ? "
                "AND i.owner_user_id = ? AND i.interview_id = ?",
                [capability.authority.account_digest, capability.authority.account_id,
                 capability.interview_id],
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="unknown or expired invite link")
            from substrate.interviews.consent import consent_state as canonical_consent_state

            granted = canonical_consent_state(
                con, capability.authority, interview_id=capability.interview_id
            )
            try:
                transcript = json.loads(row[1]) if row[1] and "record" in granted else []
            except (TypeError, ValueError):
                transcript = []
            return {
                "interview_id": capability.interview_id,
                "project_id": capability.project_id,
                "project_title": row[2],
                "subject_ref": None,
                "subject_status": None,
                "required_consent_scopes": list(capability.required_scopes),
                "granted_consent_scopes": sorted(granted),
                "status": row[0],
                "pending_questions": [],
                "transcript": transcript,
            }
        iv = invitations.resolve_token(con, token)
        if iv is None:
            raise HTTPException(status_code=404, detail="unknown or expired invite link")
        interview_id, project_id = iv.interview_id, iv.project_id
        required = [s.value for s in iv.required_consent_scopes]
        prow = con.execute(
            "SELECT ip.title, p.subject_ref, p.subject_status "
            "FROM speak_projects p JOIN interview_projects ip ON ip.project_id = p.project_id "
            "WHERE p.project_id = ?", [project_id],
        ).fetchone()
        granted = sorted(s.value for s in consent_mod.consent_state(con, interview_id).granted)
    # resume() acquires its OWN lock — call it AFTER releasing ours (no nesting).
    session = resume(_db(), interview_id)
    return {
        "interview_id": interview_id,
        "project_id": project_id,
        "project_title": prow[0] if prow else project_id,
        "subject_ref": prow[1] if prow else None,
        "subject_status": prow[2] if prow else None,
        "required_consent_scopes": required,
        "granted_consent_scopes": granted,
        "status": session.status,
        "pending_questions": session.pending_questions(),
        "transcript": session.turns,
    }


@speak_router.post("/invite/{token}/consent", status_code=200)
async def invitee_consent(token: str, req: InviteConsentRequest) -> dict:
    with _translate(), _write("speak/api:invite_consent") as con:
        capability = _canonical_capability(con, token)
        if capability is not None:
            requested = set(req.scopes)
            if not requested or not requested <= set(capability.required_scopes):
                raise HTTPException(status_code=400, detail="invalid consent scopes")
            from substrate.interviews.consent import record_consent_events

            granted = record_consent_events(
                con, capability.authority, interview_id=capability.interview_id,
                scopes=requested, granted=True, actor_kind="invitee_capability",
                invite_id=capability.invite_id,
            )
            return {
                "interview_id": capability.interview_id,
                "granted": sorted(granted),
            }
        interview_id, _ = _require_token(con, token)
        scopes = [ConsentScope(s) for s in req.scopes]
        state = consent_mod.record_consent(con, interview_id=interview_id, scopes=scopes)
    return {"interview_id": interview_id, "granted": sorted(s.value for s in state.granted)}


@speak_router.post("/invite/{token}/answer", status_code=201)
async def invitee_answer(token: str, req: InviteAnswerRequest) -> dict:
    with _translate(), _write("speak/api:invite_answer_resolve") as con:
        capability = _canonical_capability(con, token)
        if capability is not None:
            from substrate.interviews.derivation import intent_for
            from substrate.interviews.store import append_turn

            append_turn(
                con, capability.authority, interview_id=capability.interview_id,
                role="informant", text=req.transcript, question_id=req.question_id,
                duration_seconds=req.duration_seconds, actor_kind="invitee_capability",
            )
            intent = intent_for(
                con, capability.authority, interview_id=capability.interview_id,
                question_id=req.question_id,
            )
            return {
                "interview_id": capability.interview_id,
                "question_id": req.question_id,
                "document_id": None,
                "skipped_reason": (
                    "canonical_derivation_staged" if intent else "derivation_target_unbound"
                ),
            }
        interview_id, _ = _require_token(con, token)
    # submit_answer acquires its own lock(s); call outside ours.
    with _translate():
        result = submit_answer(
            _db(), interview_id=interview_id, question_id=req.question_id,
            transcript=req.transcript, duration_seconds=req.duration_seconds,
        )
    return {"interview_id": result.interview_id, "question_id": result.question_id,
            "document_id": result.document_id, "skipped_reason": result.skipped_reason}


@speak_router.post("/invite/{token}/voice", status_code=201)
async def invitee_voice(
    token: str,
    request: Request,
    question_id: str = Query(..., min_length=1),
    duration_seconds: float = Query(default=0.0, ge=0.0),
    language: str | None = Query(default=None),
) -> dict:
    """Phone-first, voice-first invitee answer (Product Depth SPR-08 M3).

    The headline invitee fix: a non-power-user on a phone taps to talk and
    their voice — not typed text — becomes their answer. The browser POSTs
    the recorded blob as the raw request body (``Content-Type: audio/*``);
    ``?question_id=`` + ``?duration_seconds=`` ride the query string (no
    python-multipart for a single-field upload). This IS the single voice
    upload owner — the operator-side ``/voice/sessions/{id}/upload`` scaffold
    that once mirrored this shape was deleted (AGH SPR-02) as an
    audio-discarding dead end; operator-side capture, if ever needed, revives
    through this same transcribe path, not a second pipeline.

    It does NOT build a second voice pipeline. It reuses the SINGLE voice
    owner end-to-end:
      • the token is the credential (``_require_token`` — fail-closed 404);
      • ``async_interview.transcribe`` runs the same ``WhisperTranscriber``
        the operator path uses (the one voice owner);
      • ``submit_answer`` is the same answer→claim bridge the typed
        ``/invite/{token}/answer`` route uses — same single-writer lock,
        same consent gate, same distil-from-the-text discipline.

    Honest no-key behaviour: with no model provider, ``transcribe`` raises
    ``AsrError`` → 503 here. There is NO path that fabricates a transcript
    or silently distils a misheard one — the invitee is told their
    recording couldn't be turned into words, and the text fallback stands.
    """
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="empty audio body")
    content_type = request.headers.get("content-type", "audio/webm")
    # Derive a filename hint from the content-type so Whisper picks the
    # right decoder (webm/opus from MediaRecorder, by default).
    ext = "webm"
    if "/" in content_type:
        sub = content_type.split("/", 1)[1].split(";", 1)[0].strip()
        if sub:
            ext = sub
    with _translate(), _write("speak/api:invite_voice_resolve") as con:
        capability = _canonical_capability(con, token)
        if capability is None:
            interview_id, _ = _require_token(con, token)
        else:
            interview_id = capability.interview_id
    # transcribe + submit acquire their own locks; do them OUTSIDE ours.
    with _translate():
        text = transcribe_voice(
            audio,
            filename=f"invite-voice.{ext}",
            transcriber=_INVITEE_TRANSCRIBER,
            language=language,
        )
        if capability is not None:
            from substrate.interviews.store import append_turn

            with _write("speak/api:invite_voice_append") as con:
                current = _canonical_capability(con, token)
                if current is None or current.invite_id != capability.invite_id:
                    raise HTTPException(status_code=404, detail="unknown or expired invite link")
                append_turn(
                    con, current.authority, interview_id=interview_id,
                    role="informant", text=text, question_id=question_id,
                    duration_seconds=duration_seconds, actor_kind="invitee_capability",
                )
                from substrate.interviews.derivation import intent_for

                intent = intent_for(
                    con, current.authority, interview_id=interview_id,
                    question_id=question_id,
                )
            result = None
        else:
            result = submit_answer(
                _db(), interview_id=interview_id, question_id=question_id,
                transcript=text, duration_seconds=duration_seconds,
            )
    return {
        "interview_id": interview_id, "question_id": question_id,
        "document_id": result.document_id if result else None,
        "skipped_reason": result.skipped_reason if result else (
            "canonical_derivation_staged" if intent else "derivation_target_unbound"
        ),
        "transcript": text,
    }


@speak_router.post("/invite/{token}/followups")
async def invitee_followups(token: str) -> dict[str, Any]:
    with _translate(), _write("speak/api:invite_followups_resolve") as con:
        capability = _canonical_capability(con, token)
        if capability is not None:
            return {"followups": []}
        interview_id, _ = _require_token(con, token)
    with _translate():
        fus = next_followups(_db(), interview_id=interview_id)
    return {"followups": [
        {"question_id": f.question_id, "text": f.text,
         "follow_up_for_prior_turn": f.follow_up_for_prior_turn}
        for f in fus
    ]}


@speak_router.post("/invite/{token}/decline", status_code=200)
async def invitee_decline(token: str) -> dict[str, Any]:
    with _translate(), _write("speak/api:invite_decline_resolve") as con:
        capability = _canonical_capability(con, token)
        if capability is not None:
            from substrate.interviews.store import decline as decline_canonical

            decline_canonical(
                con, capability.authority, interview_id=capability.interview_id
            )
            return {"interview_id": capability.interview_id, "status": "declined"}
        interview_id, _ = _require_token(con, token)
    decline(_db(), interview_id)
    return {"interview_id": interview_id, "status": "declined"}
