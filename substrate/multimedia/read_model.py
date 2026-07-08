"""Dry-run persistence/read-model seam for multimedia assets.

SPR-09 turns the substrate contracts into a small durable service that an API
can call. It is intentionally provider-free: create/approve/steer/harden all
work with deterministic planners, fake TTS, simulated Ken Burns rendering, and
JSON-backed records.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from substrate.contracts.multimedia import (
    AssetKind,
    MultimediaAssetContract,
    MultimediaStatus,
    RoutePolicy,
)
from substrate.multimedia.audio_assembly import assemble_audio_experience
from substrate.multimedia.hardening import MultimediaHardeningReport, evaluate_multimedia_asset
from substrate.multimedia.planner import (
    EvidenceChunk,
    MultimediaPlan,
    MultimediaPlanRequest,
    build_multimedia_plan,
)
from substrate.multimedia.steering import (
    SteeringIntent,
    SteeringTranscript,
    build_revision_asset,
    parse_steering_prompt,
    plan_revision,
)
from substrate.multimedia.tts import FakeTTSProvider
from substrate.multimedia.video import (
    assemble_video_documentary,
    build_video_scenes,
)

PlanMode = Literal["video", "audio", "hybrid"]
JobKind = Literal["render", "steering", "hardening", "provider_execution"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "partial"]


class _ReadModelBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CreateMultimediaDraftRequest(_ReadModelBase):
    topic: str = Field(min_length=1)
    target_minutes: int = Field(ge=15, le=45)
    mode: PlanMode = "hybrid"
    route_policy: RoutePolicy = "balanced"
    sources: tuple[str, ...] = Field(default_factory=tuple)
    must_cover: tuple[str, ...] = Field(default_factory=tuple)
    avoid: tuple[str, ...] = Field(default_factory=tuple)
    audience: str = "curious generalist"
    style: str | None = None


class SteeringRequest(_ReadModelBase):
    prompt: str = Field(min_length=1)
    raw_voice_transcript: str | None = None
    corrected_voice_transcript: str | None = None


class LiveProviderExecutionRequest(_ReadModelBase):
    """Operator request to transition a dry-run asset toward live spend.

    The gate checks budget, acknowledgement, and provider readiness BEFORE
    any queued state is recorded, and makes NO provider/network calls. A
    missing provider key records ``provider_unconfigured`` without echoing
    the secret value.
    """

    max_budget_usd: float = Field(gt=0, le=500)
    route_policy: RoutePolicy
    operator_acknowledged_spend: bool = False
    provider_families: tuple[str, ...] = Field(default=("krea",), min_length=1)
    dry_run_revision_id: str | None = None


class MultimediaJobRecord(_ReadModelBase):
    """Durable progress record for one multimedia operation.

    Job status is deliberately a SEPARATE vocabulary from asset status so
    future async workers can update job rows without changing the meaning
    of a published asset manifest. This sprint records only COMPLETED
    deterministic jobs; no background worker exists yet.
    """

    job_id: str
    asset_id: str
    revision_id: str
    sequence: int = Field(ge=1)
    kind: JobKind
    status: JobStatus
    progress_percent: int = Field(ge=0, le=100)
    message: str
    error_code: str | None = None
    retryable: bool | None = None


class MultimediaAssetSummary(_ReadModelBase):
    asset_id: str
    revision_id: str
    title: str
    kind: AssetKind
    status: str
    requested_duration_minutes: int
    route_policy: RoutePolicy
    estimated_cost_usd: float
    hardening_status: str | None = None
    latest_job_status: JobStatus | None = None
    latest_job_kind: JobKind | None = None


class MultimediaAssetRecord(_ReadModelBase):
    asset: MultimediaAssetContract
    plan: MultimediaPlan
    mode: PlanMode
    style: str | None = None
    hardening_report: MultimediaHardeningReport | None = None
    latest_steering_intent: SteeringIntent | None = None
    jobs: tuple[MultimediaJobRecord, ...] = Field(default_factory=tuple)

    def summary(self) -> MultimediaAssetSummary:
        latest_job = self.jobs[-1] if self.jobs else None
        return MultimediaAssetSummary(
            asset_id=self.asset.asset_id,
            revision_id=self.asset.revision_id,
            title=self.asset.title,
            kind=self.asset.kind,
            status=str(self.asset.status),
            requested_duration_minutes=self.asset.requested_duration_minutes,
            route_policy=self.asset.route_policy,
            estimated_cost_usd=round(sum(row.cost_usd for row in self.asset.manifest.cost_rows), 4),
            hardening_status=self.hardening_report.ship_status if self.hardening_report else None,
            latest_job_status=latest_job.status if latest_job else None,
            latest_job_kind=latest_job.kind if latest_job else None,
        )


class MultimediaAssetList(_ReadModelBase):
    assets: tuple[MultimediaAssetSummary, ...]
    count: int


class MultimediaJobList(_ReadModelBase):
    jobs: tuple[MultimediaJobRecord, ...]
    count: int


class MultimediaAssetStore:
    """JSON-backed asset record store.

    This is not a provider execution store and not a multi-user database. It is
    a deterministic local read model for the single-operator workstation and
    API tests. Files are written atomically so a process crash cannot leave a
    half-written JSON record.

    Single-writer assumption: every mutator does get -> model_copy -> save
    without a cross-request lock. The single-operator workstation has no
    realistic concurrent writers; a store-wide lock for async workers is
    deferred to the live-provider sprint (see SPR-11 handoff packet).
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        default_root = Path(tempfile.gettempdir()) / "antiek-multimedia-assets"
        if root is not None:
            self.root = Path(root)
        else:
            self.root = Path(os.environ.get("ANTIEK_MULTIMEDIA_STORE", str(default_root)))
        self.root.mkdir(parents=True, exist_ok=True)

    def create_draft(self, request: CreateMultimediaDraftRequest) -> MultimediaAssetRecord:
        asset_id = f"mm-{uuid.uuid4().hex[:12]}"
        revision_id = "rev-1"
        plan_request = MultimediaPlanRequest(
            topic=request.topic,
            target_minutes=request.target_minutes,
            mode=request.mode,
            route_policy=request.route_policy,
            sources=request.sources,
            must_cover=request.must_cover,
            avoid=request.avoid,
            audience=request.audience,
        )
        plan = build_multimedia_plan(plan_request, _evidence_from_request(request))
        kind: AssetKind = "audio_experience" if request.mode == "audio" else "documentary_video"
        asset = MultimediaAssetContract(
            asset_id=asset_id,
            kind=kind,
            title=_title(request.topic),
            user_prompt=request.topic,
            status=MultimediaStatus.PLANNED,
            route_policy=request.route_policy,
            requested_duration_minutes=request.target_minutes,
            revision_id=revision_id,
            manifest=plan.to_manifest(asset_id=asset_id, revision_id=revision_id),
        )
        record = MultimediaAssetRecord(asset=asset, plan=plan, mode=request.mode, style=request.style)
        self.save(record)
        return record

    def list_assets(self) -> MultimediaAssetList:
        records = sorted(
            (self.load(path.stem) for path in self.root.glob("*.json")),
            key=lambda record: record.asset.asset_id,
        )
        summaries = tuple(record.summary() for record in records)
        return MultimediaAssetList(assets=summaries, count=len(summaries))

    def get(self, asset_id: str) -> MultimediaAssetRecord:
        path = self._path(asset_id)
        if not path.exists():
            raise KeyError(asset_id)
        return self.load(asset_id)

    def approve_dry_run(self, asset_id: str) -> MultimediaAssetRecord:
        record = self.get(asset_id)
        asset = record.asset
        if record.mode == "audio":
            audio = assemble_audio_experience(record.plan, FakeTTSProvider(), asset_id=asset.asset_id, revision_id=asset.revision_id)
            manifest = audio.manifest
        else:
            audio = assemble_audio_experience(record.plan, FakeTTSProvider(), asset_id=asset.asset_id, revision_id=f"{asset.revision_id}-audio")
            video = assemble_video_documentary(record.plan, audio, asset_id=asset.asset_id, revision_id=asset.revision_id)
            manifest = video.manifest.model_copy(
                update={
                    # video.manifest already inherits audio's provider_calls +
                    # cost_rows (assemble_video_documentary seeds from
                    # audio.manifest), so we only add the audio *files* here —
                    # re-merging the rows would double-count TTS cost.
                    "files": video.manifest.files + audio.manifest.files,
                    "transcript_file_id": audio.manifest.transcript_file_id,
                }
            )
        approved = asset.model_copy(update={"status": MultimediaStatus.READY, "manifest": manifest})
        updated = self._with_job(
            record.model_copy(update={"asset": approved}),
            kind="render",
            status="succeeded",
            progress_percent=100,
            message="Dry-run render manifest assembled without live provider spend.",
        )
        self.save(updated)
        return updated

    def apply_steering(self, asset_id: str, request: SteeringRequest) -> MultimediaAssetRecord:
        record = self.get(asset_id)
        transcript = None
        if request.raw_voice_transcript:
            transcript = SteeringTranscript(
                transcript_id=f"voice-{uuid.uuid4().hex[:8]}",
                raw_text=request.raw_voice_transcript,
                corrected_text=request.corrected_voice_transcript,
            )
        intent = parse_steering_prompt(request.prompt, record.asset.manifest, transcript=transcript)
        revision = plan_revision(record.asset, intent)
        child = build_revision_asset(record.asset, revision)
        updated = self._with_job(
            record.model_copy(
                update={
                    "asset": child,
                    "latest_steering_intent": intent,
                    "hardening_report": None,
                }
            ),
            kind="steering",
            status="succeeded",
            progress_percent=100,
            message="Steering prompt planned as a child revision.",
        )
        self.save(updated)
        return updated

    def run_hardening(self, asset_id: str) -> MultimediaAssetRecord:
        record = self.get(asset_id)
        scenes: tuple[object, ...] = ()
        if record.mode != "audio":
            audio = assemble_audio_experience(record.plan, FakeTTSProvider(), asset_id=record.asset.asset_id, revision_id=f"{record.asset.revision_id}-audio")
            scenes = build_video_scenes(record.plan, audio)
        report = evaluate_multimedia_asset(record.asset, scenes=scenes)
        updated = self._with_job(
            record.model_copy(update={"hardening_report": report}),
            kind="hardening",
            status="succeeded",
            progress_percent=100,
            message=f"Hardening completed with ship status {report.ship_status}.",
        )
        self.save(updated)
        return updated

    def prepare_live_execution(
        self,
        asset_id: str,
        request: LiveProviderExecutionRequest,
    ) -> MultimediaAssetRecord:
        """Gate a dry-run asset toward live provider execution.

        Returns a ``provider_execution`` job row: ``queued`` only when budget
        + acknowledgement + provider readiness all pass, else ``failed`` with
        a clear non-secret error code. Makes NO provider/network calls —
        readiness is config-presence only. The gate ordering is deliberate:
        acknowledgement is checked before budget/readiness so an unack'd
        request never reaches a provider-ready state.
        """
        record = self.get(asset_id)
        if request.dry_run_revision_id and request.dry_run_revision_id != record.asset.revision_id:
            return self.record_job(
                asset_id,
                kind="provider_execution",
                status="failed",
                progress_percent=0,
                message="Requested dry-run revision does not match the current asset revision.",
                error_code="revision_mismatch",
                retryable=False,
            )
        if not request.operator_acknowledged_spend:
            return self.record_job(
                asset_id,
                kind="provider_execution",
                status="failed",
                progress_percent=0,
                message="Live provider execution requires explicit operator spend acknowledgement.",
                error_code="spend_not_acknowledged",
                retryable=False,
            )
        estimated = _estimated_live_budget_floor(record)
        if request.max_budget_usd < estimated:
            return self.record_job(
                asset_id,
                kind="provider_execution",
                status="failed",
                progress_percent=0,
                message=f"Live provider budget ${request.max_budget_usd:.2f} is below estimated floor ${estimated:.2f}.",
                error_code="budget_below_estimate",
                retryable=True,
            )
        missing = _missing_provider_families(request.provider_families)
        if missing:
            return self.record_job(
                asset_id,
                kind="provider_execution",
                status="failed",
                progress_percent=0,
                message=f"Provider families not configured: {', '.join(missing)}.",
                error_code="provider_unconfigured",
                retryable=False,
            )
        families = ", ".join(request.provider_families or ("none",))
        return self.record_job(
            asset_id,
            kind="provider_execution",
            status="queued",
            progress_percent=0,
            message=(
                f"Live execution queued for {families} with route {request.route_policy} "
                f"and max budget ${request.max_budget_usd:.2f}."
            ),
            retryable=True,
        )

    def record_job(
        self,
        asset_id: str,
        *,
        kind: JobKind,
        status: JobStatus,
        progress_percent: int,
        message: str,
        error_code: str | None = None,
        retryable: bool | None = None,
    ) -> MultimediaAssetRecord:
        """Append an arbitrary job row (failed/partial provider jobs, retries).

        Used before live workers exist so the failure contract is tested now;
        downgrade-to-cheapest stays a route-policy operation, never a magic
        mutation hidden inside render status.
        """
        record = self.get(asset_id)
        updated = self._with_job(
            record,
            kind=kind,
            status=status,
            progress_percent=progress_percent,
            message=message,
            error_code=error_code,
            retryable=retryable,
        )
        self.save(updated)
        return updated

    def list_jobs(self, asset_id: str) -> MultimediaJobList:
        record = self.get(asset_id)
        jobs = tuple(sorted(record.jobs, key=lambda job: job.sequence))
        return MultimediaJobList(jobs=jobs, count=len(jobs))

    def _with_job(
        self,
        record: MultimediaAssetRecord,
        *,
        kind: JobKind,
        status: JobStatus,
        progress_percent: int,
        message: str,
        error_code: str | None = None,
        retryable: bool | None = None,
    ) -> MultimediaAssetRecord:
        sequence = max((job.sequence for job in record.jobs), default=0) + 1
        job = MultimediaJobRecord(
            job_id=f"job-{record.asset.asset_id}-{sequence:04d}",
            asset_id=record.asset.asset_id,
            revision_id=record.asset.revision_id,
            sequence=sequence,
            kind=kind,
            status=status,
            progress_percent=progress_percent,
            message=message,
            error_code=error_code,
            retryable=retryable,
        )
        return record.model_copy(update={"jobs": record.jobs + (job,)})

    def save(self, record: MultimediaAssetRecord) -> None:
        path = self._path(record.asset.asset_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(record.model_dump_json(indent=2, exclude_computed_fields=True) + "\n")
        tmp.replace(path)

    def load(self, asset_id: str) -> MultimediaAssetRecord:
        return MultimediaAssetRecord.model_validate_json(self._path(asset_id).read_text())

    def _path(self, asset_id: str) -> Path:
        if "/" in asset_id or "\\" in asset_id:
            raise KeyError(asset_id)
        return self.root / f"{asset_id}.json"


def _evidence_from_request(request: CreateMultimediaDraftRequest) -> tuple[EvidenceChunk, ...]:
    rows: list[EvidenceChunk] = []
    for index, text in enumerate(request.sources or request.must_cover or (request.topic,)):
        rows.append(
            EvidenceChunk(
                chunk_id=f"mm-src-{index}",
                document_id=f"mm-doc-{index}",
                title=f"Multimedia source {index + 1}",
                section_path="operator brief",
                text=text,
            )
        )
    return tuple(rows)


def _title(topic: str) -> str:
    trimmed = " ".join(topic.split())
    return trimmed[:80] + ("..." if len(trimmed) > 80 else "")


def _estimated_live_budget_floor(record: MultimediaAssetRecord) -> float:
    """Conservative floor for live spend.

    The floor is the MAX of the persisted ledger total and a duration/mode
    estimate. Taking the max means a dust-positive ledger (a fraction of a
    cent) can never satisfy an arbitrarily tiny budget — the exact SPR-08
    low-cost-mask failure mode. A real priced ledger that exceeds the
    estimate still wins.
    """
    ledger_total = round(sum(row.cost_usd for row in record.asset.manifest.cost_rows), 4)
    mode_floor = 0.2 if record.mode == "audio" else 1.0
    duration_estimate = round(max(0.01, record.asset.requested_duration_minutes * mode_floor), 2)
    return max(ledger_total, duration_estimate)


_KNOWN_PROVIDER_FAMILIES = frozenset({"krea"})


def _missing_provider_families(provider_families: tuple[str, ...]) -> tuple[str, ...]:
    """Return provider families that are unconfigured.

    Fail-closed: an UNKNOWN family name (typo, not-yet-supported) is treated
    as unconfigured so the gate never queues live execution for a provider
    whose readiness was never checked. Checks env PRESENCE only — never
    reads or logs the secret value.
    """
    missing: list[str] = []
    for family in provider_families:
        normalized = family.strip().lower()
        if normalized not in _KNOWN_PROVIDER_FAMILIES:
            missing.append(family)
        elif normalized == "krea" and not os.environ.get("KREA_API_KEY"):
            missing.append("krea")
    return tuple(missing)


__all__ = [
    "CreateMultimediaDraftRequest",
    "LiveProviderExecutionRequest",
    "MultimediaAssetList",
    "MultimediaAssetRecord",
    "MultimediaAssetStore",
    "MultimediaAssetSummary",
    "MultimediaJobList",
    "MultimediaJobRecord",
    "SteeringRequest",
]
