"""Authenticated account workspace resume transport."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from substrate.engagement_spine.authority import owner_qualified_id
from substrate.engagement_spine.collective_council import council_result_sha256, get_council_plan
from substrate.engagement_spine.collective_manifest import (
    CollectiveManifestNotFound,
    CollectiveManifestUnavailable,
    read_collective_manifest,
)
from substrate.event_log.events import IdempotencyConflict
from substrate.floating_session.resume_projection import (
    DeepResearchSessionNotFound,
    DeepResearchSessionProjection,
    DeepResearchSessionUnavailable,
    resolve_deep_research_session,
)
from substrate.research_artifact.authority import ArtifactAuthority, operator_authority
from substrate.research_artifact.rollout import read_canonical_artifact
from substrate.research_artifact.storage import UnsafeArtifactState
from substrate.schemas.events import WorkspaceResumeEntry
from substrate.workspace_resume import (
    WorkspaceRevisionConflict,
    account_workspace_authority,
    append_workspace_checkpoint,
    read_workspace_checkpoint,
)

from .html_document_refs import (
    HtmlDocumentReferenceNotFound,
    HtmlDocumentReferenceUnavailable,
    resolve_html_document_reference,
    validate_html_document_identifier,
)
from .investigation_access import (
    InvestigationAccessDenied,
    InvestigationAuthenticationRequired,
    authority_from_request,
    require_investigation_owner,
)

workspace_resume_router = APIRouter(prefix="/account", tags=["workspace-resume"])


class _Exact(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BareEntry(_Exact):
    kind: Literal["stats", "library"]


class SubactionEntry(_Exact):
    kind: Literal["subaction"]
    workflow: Literal["research", "read", "write", "speak"]


class ResearchArtifactEntry(_Exact):
    kind: Literal["research_artifact"]
    investigation_id: str = Field(min_length=1, max_length=512)


class HostedHtmlDocumentEntry(_Exact):
    kind: Literal["hosted_html_document"]
    resolver: Literal["hosted_document", "engagement_document"]
    document_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _valid_document_id(self) -> HostedHtmlDocumentEntry:
        validate_html_document_identifier(self.document_id)
        return self


class DeepResearchSessionEntry(_Exact):
    kind: Literal["deep_research_session"]
    session_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _valid_session_id(self) -> DeepResearchSessionEntry:
        from interfaces.research.api.html_document_refs import validate_html_document_identifier

        validate_html_document_identifier(self.session_id)
        return self


class CollectiveUnitEntry(_Exact):
    kind: Literal["collective_unit"]
    manifest_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _valid_manifest_id(self) -> CollectiveUnitEntry:
        validate_html_document_identifier(self.manifest_id)
        return self


class AncestryInterrogationEntry(_Exact):
    kind: Literal["ancestry_interrogation"]
    investigation_id: str = Field(min_length=1, max_length=512)
    manifest_id: str = Field(min_length=1, max_length=512)
    receipt_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _valid_ids(self) -> AncestryInterrogationEntry:
        validate_html_document_identifier(self.investigation_id)
        validate_html_document_identifier(self.manifest_id)
        validate_html_document_identifier(self.receipt_id)
        return self


class CollectiveCouncilEntry(_Exact):
    kind: Literal["collective_council"]
    plan_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _valid_plan_id(self) -> CollectiveCouncilEntry:
        validate_html_document_identifier(self.plan_id)
        return self


CheckpointEntry = Annotated[
    BareEntry
    | SubactionEntry
    | ResearchArtifactEntry
    | HostedHtmlDocumentEntry
    | DeepResearchSessionEntry
    | CollectiveUnitEntry
    | AncestryInterrogationEntry
    | CollectiveCouncilEntry,
    Field(discriminator="kind"),
]
_ENTRY_ADAPTER = TypeAdapter(CheckpointEntry)


class WorkspacePut(_Exact):
    schema_version: Literal[1]
    base_revision: int = Field(ge=0)
    entries: list[CheckpointEntry] = Field(max_length=8)
    mutation_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")

    @model_validator(mode="after")
    def _no_duplicates(self) -> WorkspacePut:
        canonical = [entry.model_dump_json(exclude_none=True) for entry in self.entries]
        if len(canonical) != len(set(canonical)):
            raise ValueError("workspace entries must be unique")
        return self


class WorkspaceGet(_Exact):
    schema_version: Literal[1] = 1
    revision: int
    entries: list[CheckpointEntry]


class WorkspaceSynced(_Exact):
    status: Literal["synced"] = "synced"
    revision: int
    event_id: str


class HtmlDocumentResponse(_Exact):
    schema_version: Literal[1] = 1
    resolver: Literal["hosted_document", "engagement_document"]
    document_id: str
    title: str
    view_format: Literal["html"] = "html"
    html: str


class DeepResearchSessionResponse(_Exact):
    schema_version: Literal[1] = 1
    session_id: str
    spawn_id: str
    investigation_id: str
    parent_asset_id: str
    status: Literal["reserved", "running", "complete", "failed"]
    research_tier: str
    view_format: Literal["html"] = "html"


def _engagement_store(request: Request, account_id: str):
    from .engagement_routes import get_account_resume_stores

    return get_account_resume_stores(request, account_id)[1]


def _resolve_manifest(request: Request, account_id: str, manifest_id: str):
    return read_collective_manifest(manifest_id, store=_engagement_store(request, account_id))


def _resolve_ancestry_interrogation(
    request: Request,
    account_id: str,
    entry: AncestryInterrogationEntry,
):
    from substrate.research_artifact.reasoning_ancestry_interrogation import (
        ReasoningAncestryInterrogationConflict,
    )
    from substrate.research_artifact.reasoning_ancestry_interrogation_resolution import (
        resolve_reasoning_ancestry_interrogation,
    )

    from .engagement_routes import get_account_resume_stores

    try:
        access = authority_from_request(request, entry.investigation_id)
        require_investigation_owner(access)
        authority = (
            operator_authority(entry.investigation_id)
            if account_id == "__operator__"
            and access.auth_method == "unauthenticated_local"
            else ArtifactAuthority(account_id, entry.investigation_id)
        )
        session_store, engagement_store = get_account_resume_stores(
            request, account_id
        )
        try:
            resolved = resolve_reasoning_ancestry_interrogation(
                authority=authority,
                receipt_id=entry.receipt_id,
                engagement_store=engagement_store,
                session_store=session_store,
            )
        except KeyError as exc:
            raise CollectiveManifestNotFound(entry.receipt_id) from exc
        if resolved.receipt.manifest_id != entry.manifest_id or (
            resolved.manifest.manifest_id != entry.manifest_id
        ):
            raise ReasoningAncestryInterrogationConflict(
                "workspace interrogation manifest conflicts"
            )
        return resolved.receipt
    except (
        InvestigationAccessDenied,
        InvestigationAuthenticationRequired,
    ) as exc:
        raise CollectiveManifestNotFound(entry.receipt_id) from exc
    except (
        FileNotFoundError,
        OSError,
        PermissionError,
        RuntimeError,
        TypeError,
        UnsafeArtifactState,
        ValueError,
    ) as exc:
        raise CollectiveManifestUnavailable(
            "ancestry interrogation unavailable"
        ) from exc


def _resolve_council(request: Request, account_id: str, plan_id: str) -> dict[str, object]:
    store = _engagement_store(request, account_id)
    try:
        plan = get_council_plan(plan_id, store=store)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise CollectiveManifestUnavailable("council plan unavailable") from exc
    if plan is None:
        raise CollectiveManifestNotFound(plan_id)
    members = [
        {
            "spawn_id": m.spawn_id,
            "role": m.role,
            "model_id": m.model_id,
            "projected_max_cents": m.projected_max_cents,
            "evidence_sha256": m.evidence_sha256,
        }
        for m in plan.members
    ]
    result = None
    result_id = owner_qualified_id(store.authority, "cresult", plan.plan_id, plan.input_sha256)
    try:
        row = store.get_document_strict(result_id)
    except RuntimeError as exc:
        raise CollectiveManifestUnavailable("council result unavailable") from exc
    if row is not None:
        required = {"result_id", "state", "spent_cents", "held_cents", "html"}
        if (
            row.get("kind") != "council_result"
            or not required <= set(row)
            or row["result_id"] != result_id
        ):
            raise CollectiveManifestUnavailable("council result corrupt")
        reviewable = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "engagement_authority_version",
                "owner_account_digest",
                "engagement_key_id",
                "display_document_id",
            }
        }
        result = {key: row[key] for key in required}
        result["result_sha256"] = council_result_sha256(reviewable)
    return {
        "schema_version": 1,
        "plan": {
            "plan_id": plan.plan_id,
            "collective_id": plan.collective_id,
            "shared_prompt": plan.shared_prompt,
            "members": members,
            "synthesizer_model_id": plan.synthesizer_model_id,
            "synthesizer_projected_max_cents": plan.synthesizer_projected_max_cents,
            "approved_ceiling_cents": plan.approved_ceiling_cents,
            "input_sha256": plan.input_sha256,
            "state": plan.state,
        },
        "result": result,
        "view_format": "html",
    }


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _account_id(request: Request) -> str:
    try:
        return authority_from_request(request, "workspace-resume-identity").authority.account_id
    except InvestigationAuthenticationRequired as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc


def _artifact_allowed(account_id: str, investigation_id: str, request: Request) -> bool:
    try:
        access = authority_from_request(request, investigation_id)
        require_investigation_owner(access)
        authority = (
            operator_authority(investigation_id)
            if account_id == "__operator__" and access.auth_method == "unauthenticated_local"
            else ArtifactAuthority(account_id, investigation_id)
        )
        read_canonical_artifact(authority)
    except (
        FileNotFoundError,
        UnsafeArtifactState,
        InvestigationAccessDenied,
        InvestigationAuthenticationRequired,
        RuntimeError,
        ValueError,
    ):
        return False
    return True


def _html_document_allowed(
    account_id: str, entry: HostedHtmlDocumentEntry, request: Request
) -> bool:
    try:
        resolve_html_document_reference(
            request,
            account_id=account_id,
            resolver=entry.resolver,
            document_id=entry.document_id,
        )
    except HtmlDocumentReferenceNotFound:
        return False
    return True


def _resolve_session(
    request: Request, account_id: str, session_id: str
) -> DeepResearchSessionProjection:
    try:
        from .engagement_routes import get_account_resume_stores

        session_store, engagement_store = get_account_resume_stores(request, account_id)
        return resolve_deep_research_session(
            session_id, session_store=session_store, engagement_store=engagement_store
        )
    except DeepResearchSessionNotFound:
        raise
    except DeepResearchSessionUnavailable:
        raise
    except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
        raise DeepResearchSessionUnavailable from exc


def _external(entries: tuple[WorkspaceResumeEntry, ...]) -> list[CheckpointEntry]:
    return [
        _ENTRY_ADAPTER.validate_python(entry.model_dump(mode="json", exclude_none=True))
        for entry in entries
    ]


@workspace_resume_router.get("/workspace-resume", response_model=WorkspaceGet)
async def get_workspace_resume(request: Request, response: Response) -> WorkspaceGet:
    _no_store(response)
    account_id = _account_id(request)
    try:
        checkpoint = read_workspace_checkpoint(account_workspace_authority(account_id))
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="workspace persistence unavailable") from exc
    filtered: list[WorkspaceResumeEntry] = []
    try:
        for entry in checkpoint.entries:
            if entry.kind == "research_artifact" and (
                entry.investigation_id is None
                or not _artifact_allowed(account_id, entry.investigation_id, request)
            ):
                continue
            if entry.kind == "hosted_html_document":
                if entry.resolver is None or entry.document_id is None:
                    continue
                if not _html_document_allowed(
                    account_id,
                    HostedHtmlDocumentEntry(
                        kind="hosted_html_document",
                        resolver=entry.resolver,
                        document_id=entry.document_id,
                    ),
                    request,
                ):
                    continue
            if entry.kind == "deep_research_session":
                if entry.session_id is None:
                    continue
                try:
                    _resolve_session(request, account_id, entry.session_id)
                except DeepResearchSessionNotFound:
                    continue
            if entry.kind == "collective_unit":
                if entry.manifest_id is None:
                    continue
                try:
                    _resolve_manifest(request, account_id, entry.manifest_id)
                except CollectiveManifestNotFound:
                    continue
            if entry.kind == "ancestry_interrogation":
                if (
                    entry.investigation_id is None
                    or entry.manifest_id is None
                    or entry.receipt_id is None
                ):
                    continue
                try:
                    _resolve_ancestry_interrogation(
                        request,
                        account_id,
                        AncestryInterrogationEntry(
                            kind="ancestry_interrogation",
                            investigation_id=entry.investigation_id,
                            manifest_id=entry.manifest_id,
                            receipt_id=entry.receipt_id,
                        ),
                    )
                except CollectiveManifestNotFound:
                    continue
            if entry.kind == "collective_council":
                if entry.plan_id is None:
                    continue
                try:
                    _resolve_council(request, account_id, entry.plan_id)
                except CollectiveManifestNotFound:
                    continue
            filtered.append(entry)
    except (
        HtmlDocumentReferenceUnavailable,
        DeepResearchSessionUnavailable,
        CollectiveManifestUnavailable,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail="workspace persistence unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc
    return WorkspaceGet(revision=checkpoint.revision, entries=_external(tuple(filtered)))


@workspace_resume_router.put("/workspace-resume", response_model=WorkspaceSynced)
async def put_workspace_resume(
    body: WorkspacePut, request: Request, response: Response
) -> WorkspaceSynced:
    _no_store(response)
    account_id = _account_id(request)
    for entry in body.entries:
        if isinstance(entry, ResearchArtifactEntry) and not _artifact_allowed(
            account_id, entry.investigation_id, request
        ):
            raise HTTPException(
                status_code=404,
                detail="workspace reference not found",
                headers={"Cache-Control": "no-store"},
            )
        if isinstance(entry, HostedHtmlDocumentEntry):
            try:
                allowed = _html_document_allowed(account_id, entry, request)
            except HtmlDocumentReferenceUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail="workspace persistence unavailable",
                    headers={"Cache-Control": "no-store"},
                ) from exc
            if not allowed:
                raise HTTPException(
                    status_code=404,
                    detail="workspace reference not found",
                    headers={"Cache-Control": "no-store"},
                )
        if isinstance(entry, DeepResearchSessionEntry):
            try:
                _resolve_session(request, account_id, entry.session_id)
            except DeepResearchSessionNotFound as exc:
                raise HTTPException(
                    status_code=404,
                    detail="workspace reference not found",
                    headers={"Cache-Control": "no-store"},
                ) from exc
            except DeepResearchSessionUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail="workspace persistence unavailable",
                    headers={"Cache-Control": "no-store"},
                ) from exc
        if isinstance(entry, CollectiveUnitEntry):
            try:
                _resolve_manifest(request, account_id, entry.manifest_id)
            except CollectiveManifestNotFound as exc:
                raise HTTPException(
                    status_code=404,
                    detail="workspace reference not found",
                    headers={"Cache-Control": "no-store"},
                ) from exc
            except CollectiveManifestUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail="workspace persistence unavailable",
                    headers={"Cache-Control": "no-store"},
                ) from exc
        if isinstance(entry, AncestryInterrogationEntry):
            try:
                _resolve_ancestry_interrogation(request, account_id, entry)
            except CollectiveManifestNotFound as exc:
                raise HTTPException(
                    status_code=404,
                    detail="workspace reference not found",
                    headers={"Cache-Control": "no-store"},
                ) from exc
            except CollectiveManifestUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail="workspace persistence unavailable",
                    headers={"Cache-Control": "no-store"},
                ) from exc
        if isinstance(entry, CollectiveCouncilEntry):
            try:
                _resolve_council(request, account_id, entry.plan_id)
            except CollectiveManifestNotFound as exc:
                raise HTTPException(
                    status_code=404,
                    detail="workspace reference not found",
                    headers={"Cache-Control": "no-store"},
                ) from exc
            except CollectiveManifestUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail="workspace persistence unavailable",
                    headers={"Cache-Control": "no-store"},
                ) from exc
    internal = tuple(
        WorkspaceResumeEntry.model_validate(entry.model_dump(mode="json")) for entry in body.entries
    )
    try:
        checkpoint = append_workspace_checkpoint(
            account_workspace_authority(account_id),
            base_revision=body.base_revision,
            entries=internal,
            mutation_key=body.mutation_key,
        )
    except (IdempotencyConflict, WorkspaceRevisionConflict) as exc:
        raise HTTPException(status_code=409, detail="workspace checkpoint conflict") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="workspace persistence unavailable") from exc
    if checkpoint.event_id is None:
        raise HTTPException(status_code=503, detail="workspace persistence unavailable")
    return WorkspaceSynced(revision=checkpoint.revision, event_id=checkpoint.event_id)


@workspace_resume_router.get("/collective-manifest-refs/{manifest_id}")
async def get_collective_manifest_reference(
    manifest_id: str, request: Request, response: Response
) -> dict[str, object]:
    _no_store(response)
    account_id = _account_id(request)
    try:
        return _resolve_manifest(request, account_id, manifest_id).receipt()
    except CollectiveManifestNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="collective manifest reference not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except CollectiveManifestUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="collective manifest reference unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc


@workspace_resume_router.get("/collective-council-refs/{plan_id}")
async def get_collective_council_reference(
    plan_id: str, request: Request, response: Response
) -> dict[str, object]:
    _no_store(response)
    account_id = _account_id(request)
    try:
        return _resolve_council(request, account_id, plan_id)
    except CollectiveManifestNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="collective council reference not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except CollectiveManifestUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="collective council reference unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc


@workspace_resume_router.get(
    "/html-document-refs/{resolver}/{document_id:path}",
    response_model=HtmlDocumentResponse,
)
async def get_html_document_reference(
    resolver: str, document_id: str, request: Request, response: Response
) -> HtmlDocumentResponse:
    _no_store(response)
    account_id = _account_id(request)
    try:
        hydrated = resolve_html_document_reference(
            request,
            account_id=account_id,
            resolver=resolver,
            document_id=document_id,
        )
    except HtmlDocumentReferenceNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="HTML document reference not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except HtmlDocumentReferenceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="HTML document reference unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc
    return HtmlDocumentResponse(
        resolver=hydrated.resolver,
        document_id=hydrated.document_id,
        title=hydrated.title,
        html=hydrated.html,
    )


@workspace_resume_router.get(
    "/deep-research-session-refs/{session_id:path}",
    response_model=DeepResearchSessionResponse,
)
async def get_deep_research_session_reference(
    session_id: str, request: Request, response: Response
) -> DeepResearchSessionResponse:
    _no_store(response)
    account_id = _account_id(request)
    try:
        projected = _resolve_session(request, account_id, session_id)
    except DeepResearchSessionNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="deep research session reference not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except DeepResearchSessionUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="deep research session reference unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc
    return DeepResearchSessionResponse(**projected.__dict__)
