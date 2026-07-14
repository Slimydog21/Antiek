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
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from orchestration.interview.orchestrator import ConsentRequired
from runtime.db_lock import connect_write
from substrate.books.ingest import register_book
from substrate.books.model import TocItem
from substrate.event_log import append_event_once, prepare_typed_event, require_event_persistence
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import (
    content_addressed_id,
    insert_chunk,
    insert_document,
    update_section_prose,
)
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

speak_router = APIRouter(prefix="/speak", tags=["speak"])


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
        raise HTTPException(status_code=403, detail=str(e))
    except (PublishBlocked, DisbursementBlocked) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except AsrError as e:
        # Transcription couldn't run (no model provider configured, or the
        # provider failed). The honest answer is "we couldn't turn your
        # recording into words" — never a fabricated transcript. 503 because
        # it's a missing/temporarily-unavailable capability, not a bad token.
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail=f"{field} must be a decimal string")


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
    text: str = Field(..., min_length=1)
    interview_id: str | None = None
    about_subject: bool = False
    subject_ref: str | None = None
    speaker_is_subject: bool = False
    confidence: float = 0.5


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
        rows = con.execute(
            "SELECT p.project_id, ip.title, p.subject_ref, p.subject_status, "
            "p.invitation_mode, "
            "(SELECT count(*) FROM interviews i WHERE i.project_id = p.project_id) "
            ", (SELECT arg_max(d.document_id, sp.published_at) FROM documents d "
            "JOIN book_assets b ON b.document_id = d.document_id "
            "JOIN speak_publications sp ON sp.publication_id = "
            "json_extract_string(d.metadata, '$.publication_id') "
            "WHERE sp.project_id = p.project_id AND sp.served = TRUE "
            "AND sp.taken_down = FALSE "
            "AND json_extract_string(d.metadata, '$.provenance_class') = 'speak_derived' "
            "AND COALESCE(b.taken_down, FALSE) = FALSE) "
            "FROM speak_projects p "
            "JOIN interview_projects ip ON ip.project_id = p.project_id "
            "WHERE p.publish_intent = 'will_be_public' "
            "ORDER BY p.created_at DESC"
        ).fetchall()
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
async def record_interview_claim(interview_id: str, req: ClaimRequest) -> dict:
    """The answer→claim bridge: record an explicit claim attributed to
    the interviewee (about_subject / third-party tagging is a confirmed
    judgment, not an inference). Feeds corroboration + authoring +
    economics."""
    with _translate(), _write("speak/api:claim") as con:
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
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    require_event_persistence()
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

    investigation_id = f"speak-biography-{project_id}"
    for event_receipt in events:
        append_event_once(
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
        append_event_once(
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
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    require_event_persistence()
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
        append_event_once(
            prepare_typed_event(
                project_id,
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
    question_id: str
    transcript: str = Field(..., min_length=1)
    duration_seconds: float = 0.0


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


@speak_router.get("/invite/{token}")
async def invitee_landing(token: str) -> dict:
    """One call for the invitee's landing page: the project they've been
    invited to, the consent scopes the invite asks for, what they've
    already granted (so a returning invitee skips re-consent), and — once
    consented — the pending questions + transcript so far."""
    with _translate(), _write("speak/api:invite_landing") as con:
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
        interview_id, _ = _require_token(con, token)
        scopes = [ConsentScope(s) for s in req.scopes]
        state = consent_mod.record_consent(con, interview_id=interview_id, scopes=scopes)
    return {"interview_id": interview_id, "granted": sorted(s.value for s in state.granted)}


@speak_router.post("/invite/{token}/answer", status_code=201)
async def invitee_answer(token: str, req: InviteAnswerRequest) -> dict:
    with _translate(), _write("speak/api:invite_answer_resolve") as con:
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
        interview_id, _ = _require_token(con, token)
    # transcribe + submit acquire their own locks; do them OUTSIDE ours.
    with _translate():
        text = transcribe_voice(
            audio,
            filename=f"invite-voice.{ext}",
            transcriber=_INVITEE_TRANSCRIBER,
            language=language,
        )
        result = submit_answer(
            _db(), interview_id=interview_id, question_id=question_id,
            transcript=text, duration_seconds=duration_seconds,
        )
    return {
        "interview_id": result.interview_id, "question_id": result.question_id,
        "document_id": result.document_id, "skipped_reason": result.skipped_reason,
        "transcript": text,
    }


@speak_router.post("/invite/{token}/followups")
async def invitee_followups(token: str) -> dict[str, Any]:
    with _translate(), _write("speak/api:invite_followups_resolve") as con:
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
        interview_id, _ = _require_token(con, token)
    decline(_db(), interview_id)
    return {"interview_id": interview_id, "status": "declined"}
