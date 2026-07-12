"""Dry-run persistence/read-model seam for multimedia assets.

SPR-09 turns the substrate contracts into a small durable service that an API
can call. It is intentionally provider-free: create/approve/steer/harden all
work with deterministic planners, fake TTS, simulated Ken Burns rendering, and
JSON-backed records.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import stat
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
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
_DEFAULT_OWNER_ID = "__operator__"
_OWNER_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_RECORD_BYTES = 32 * 1024 * 1024
_MAX_ACCOUNT_ASSETS = 1_000


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


class MultimediaKnowledgeLink(_ReadModelBase):
    schema_version: Literal["antiek.multimedia-knowledge-link.v1"] = (
        "antiek.multimedia-knowledge-link.v1"
    )
    asset_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    revision_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    source_document_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    source_event_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    graph_node_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    twin_document_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    source_html_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    twin_html_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    insight_node_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=10_000)
    question_node_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=10_000)


class MultimediaProductionLink(_ReadModelBase):
    schema_version: Literal["antiek.multimedia-production-link.v1"] = (
        "antiek.multimedia-production-link.v1"
    )
    owner_identity_digest: str = Field(pattern=_OWNER_DIGEST.pattern)
    asset_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    revision_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_seconds: float = Field(gt=0)
    width_px: int = Field(ge=16, le=3840)
    height_px: int = Field(ge=16, le=2160)
    chapter_ids: tuple[str, ...] = Field(min_length=1, max_length=64)


class MultimediaAudioProductionLink(_ReadModelBase):
    schema_version: Literal["antiek.multimedia-audio-production-link.v1"] = (
        "antiek.multimedia-audio-production-link.v1"
    )
    owner_identity_digest: str = Field(pattern=_OWNER_DIGEST.pattern)
    asset_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    revision_id: str = Field(min_length=1, max_length=128, pattern=_ASSET_ID.pattern)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_seconds: float = Field(gt=0, le=45 * 60)
    chapter_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    retention_marker_count: int = Field(ge=1, le=10_000)
    learned_claim_count: int = Field(ge=1, le=10_000)


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
    knowledge_finalized: bool = False
    twin_document_id: str | None = None
    production_ready: bool = False


class MultimediaAssetRecord(_ReadModelBase):
    asset: MultimediaAssetContract
    plan: MultimediaPlan
    mode: PlanMode
    style: str | None = None
    hardening_report: MultimediaHardeningReport | None = None
    latest_steering_intent: SteeringIntent | None = None
    jobs: tuple[MultimediaJobRecord, ...] = Field(default_factory=tuple)
    knowledge_link: MultimediaKnowledgeLink | None = None
    knowledge_finalization_revision_id: str | None = None
    production_link: MultimediaProductionLink | None = None
    audio_production_link: MultimediaAudioProductionLink | None = None

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
            knowledge_finalized=self.knowledge_link is not None,
            twin_document_id=(
                self.knowledge_link.twin_document_id if self.knowledge_link else None
            ),
            production_ready=(
                self.production_link is not None or self.audio_production_link is not None
            ),
        )


class MultimediaAssetList(_ReadModelBase):
    assets: tuple[MultimediaAssetSummary, ...]
    count: int


class MultimediaJobList(_ReadModelBase):
    jobs: tuple[MultimediaJobRecord, ...]
    count: int


class _AccountAssetEnvelope(_ReadModelBase):
    schema_version: Literal["antiek.multimedia-account-asset.v1"]
    owner_identity_digest: str = Field(pattern=_OWNER_DIGEST.pattern)
    record: MultimediaAssetRecord


class MultimediaAssetStore:
    """JSON-backed asset record store.

    Account identity is represented on disk only by SHA-256. Every record is
    wrapped in an owner-bound envelope and all read/modify/write operations use
    one cross-thread/process lock. Root-level legacy JSON is never claimed by a
    caller; only ``migrate_legacy_assets`` can assign it to an explicit owner.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        default_root = Path(tempfile.gettempdir()) / "antiek-multimedia-assets"
        if root is not None:
            self.root = Path(root)
        else:
            self.root = Path(os.environ.get("ANTIEK_MULTIMEDIA_STORE", str(default_root)))
        if self.root.is_symlink():
            raise ValueError("multimedia asset root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self._accounts = self.root / "accounts"
        if self._accounts.is_symlink():
            raise ValueError("multimedia account root cannot be a symlink")
        self._accounts.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self._accounts, 0o700)
        self._thread_lock = threading.RLock()
        self._lock_path = self.root / ".store.lock"

    def create_draft(
        self,
        request: CreateMultimediaDraftRequest,
        *,
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
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
            owner_user_id=owner_digest,
            revision_id=revision_id,
            manifest=plan.to_manifest(asset_id=asset_id, revision_id=revision_id),
        )
        record = MultimediaAssetRecord(asset=asset, plan=plan, mode=request.mode, style=request.style)
        with self._locked(exclusive=True):
            if self._path(owner_digest, asset_id).exists():
                raise RuntimeError("multimedia asset identity collision")
            self._save_unlocked(record, owner_digest)
        return record

    def list_assets(self, *, owner_id: str = _DEFAULT_OWNER_ID) -> MultimediaAssetList:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=False):
            account = self._account_dir(owner_digest, create=False)
            paths = [] if account is None else sorted(account.glob("*.json"))
            if len(paths) > _MAX_ACCOUNT_ASSETS:
                raise ValueError("multimedia account asset count exceeds its bound")
            records = sorted(
                (self._load_unlocked(path.stem, owner_digest) for path in paths),
                key=lambda record: record.asset.asset_id,
            )
        summaries = tuple(record.summary() for record in records)
        return MultimediaAssetList(assets=summaries, count=len(summaries))

    def get(
        self, asset_id: str, *, owner_id: str = _DEFAULT_OWNER_ID
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=False):
            return self._load_unlocked(asset_id, owner_digest)

    def approve_dry_run(
        self, asset_id: str, *, owner_id: str = _DEFAULT_OWNER_ID
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            asset = record.asset
            if record.mode == "audio":
                audio = assemble_audio_experience(record.plan, FakeTTSProvider(), asset_id=asset.asset_id, revision_id=asset.revision_id)
                manifest = audio.manifest
            else:
                audio = assemble_audio_experience(record.plan, FakeTTSProvider(), asset_id=asset.asset_id, revision_id=f"{asset.revision_id}-audio")
                video = assemble_video_documentary(record.plan, audio, asset_id=asset.asset_id, revision_id=asset.revision_id)
                manifest = video.manifest.model_copy(
                    update={
                        # The video manifest already contains audio cost rows.
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
            self._save_unlocked(updated, owner_digest)
            return updated

    def apply_steering(
        self,
        asset_id: str,
        request: SteeringRequest,
        *,
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            if record.knowledge_finalization_revision_id is not None:
                raise ValueError("multimedia knowledge finalization is in progress")
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
                        "knowledge_link": None,
                        "production_link": None,
                        "audio_production_link": None,
                    }
                ),
                kind="steering",
                status="succeeded",
                progress_percent=100,
                message="Steering prompt planned as a child revision.",
            )
            self._save_unlocked(updated, owner_digest)
            return updated

    def run_hardening(
        self, asset_id: str, *, owner_id: str = _DEFAULT_OWNER_ID
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
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
            self._save_unlocked(updated, owner_digest)
            return updated

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
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        """Append an arbitrary job row (failed/partial provider jobs, retries).

        Used before live workers exist so the failure contract is tested now;
        downgrade-to-cheapest stays a route-policy operation, never a magic
        mutation hidden inside render status.
        """
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            return self._record_job_unlocked(
                record,
                owner_digest=owner_digest,
                kind=kind,
                status=status,
                progress_percent=progress_percent,
                message=message,
                error_code=error_code,
                retryable=retryable,
            )

    def attach_knowledge_link(
        self,
        asset_id: str,
        link: MultimediaKnowledgeLink,
        *,
        expected_revision_id: str,
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            if record.asset.revision_id != expected_revision_id:
                raise ValueError("multimedia knowledge revision is not current")
            if str(record.asset.status) != "ready":
                raise ValueError("multimedia knowledge finalization requires a ready asset")
            if (link.asset_id, link.revision_id) != (
                record.asset.asset_id,
                record.asset.revision_id,
            ):
                raise ValueError("multimedia knowledge link identity conflicts")
            if record.knowledge_link is not None:
                if record.knowledge_link != link:
                    raise ValueError("multimedia knowledge link conflicts")
                return record
            if record.knowledge_finalization_revision_id != expected_revision_id:
                raise ValueError("multimedia knowledge finalization reservation conflicts")
            updated = record.model_copy(
                update={
                    "knowledge_link": link,
                    "knowledge_finalization_revision_id": None,
                }
            )
            self._save_unlocked(updated, owner_digest)
            return updated

    def reserve_knowledge_finalization(
        self,
        asset_id: str,
        *,
        expected_revision_id: str,
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            if record.asset.revision_id != expected_revision_id:
                raise ValueError("multimedia knowledge revision is not current")
            if str(record.asset.status) != "ready":
                raise ValueError("multimedia knowledge finalization requires a ready asset")
            reserved = record.knowledge_finalization_revision_id
            if record.knowledge_link is not None:
                if record.knowledge_link.revision_id != expected_revision_id:
                    raise ValueError("multimedia knowledge link revision conflicts")
                return record
            if reserved is not None and reserved != expected_revision_id:
                raise ValueError("multimedia knowledge finalization reservation conflicts")
            if reserved == expected_revision_id:
                return record
            updated = record.model_copy(
                update={"knowledge_finalization_revision_id": expected_revision_id}
            )
            self._save_unlocked(updated, owner_digest)
            return updated

    def attach_production_link(
        self,
        asset_id: str,
        link: MultimediaProductionLink,
        *,
        expected_revision_id: str,
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            if record.asset.revision_id != expected_revision_id:
                raise ValueError("multimedia production revision is not current")
            if str(record.asset.status) != "ready":
                raise ValueError("multimedia production registration requires a ready asset")
            if record.mode == "audio" or str(record.asset.kind) == "audio_experience":
                raise ValueError("multimedia video production requires a video asset")
            if (
                link.owner_identity_digest != owner_digest
                or link.asset_id != record.asset.asset_id
                or link.revision_id != record.asset.revision_id
            ):
                raise ValueError("multimedia production link identity conflicts")
            if record.production_link is not None:
                if record.production_link != link:
                    raise ValueError("multimedia production link conflicts")
                return record
            updated = record.model_copy(update={"production_link": link})
            self._save_unlocked(updated, owner_digest)
            return updated

    def attach_audio_production_link(
        self,
        asset_id: str,
        link: MultimediaAudioProductionLink,
        *,
        expected_revision_id: str,
        owner_id: str = _DEFAULT_OWNER_ID,
    ) -> MultimediaAssetRecord:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            record = self._load_unlocked(asset_id, owner_digest)
            if record.asset.revision_id != expected_revision_id:
                raise ValueError("multimedia audio production revision is not current")
            if str(record.asset.status) != "ready":
                raise ValueError("multimedia audio registration requires a ready asset")
            if record.mode != "audio" or str(record.asset.kind) != "audio_experience":
                raise ValueError("multimedia audio production requires an audio asset")
            if (
                link.owner_identity_digest != owner_digest
                or link.asset_id != record.asset.asset_id
                or link.revision_id != record.asset.revision_id
            ):
                raise ValueError("multimedia audio production link identity conflicts")
            if record.audio_production_link is not None:
                if record.audio_production_link != link:
                    raise ValueError("multimedia audio production link conflicts")
                return record
            if record.production_link is not None:
                raise ValueError("multimedia audio production conflicts with video authority")
            updated = record.model_copy(update={"audio_production_link": link})
            self._save_unlocked(updated, owner_digest)
            return updated

    def _record_job_unlocked(
        self,
        record: MultimediaAssetRecord,
        *,
        owner_digest: str,
        kind: JobKind,
        status: JobStatus,
        progress_percent: int,
        message: str,
        error_code: str | None = None,
        retryable: bool | None = None,
    ) -> MultimediaAssetRecord:
        updated = self._with_job(
            record,
            kind=kind,
            status=status,
            progress_percent=progress_percent,
            message=message,
            error_code=error_code,
            retryable=retryable,
        )
        self._save_unlocked(updated, owner_digest)
        return updated

    def list_jobs(
        self, asset_id: str, *, owner_id: str = _DEFAULT_OWNER_ID
    ) -> MultimediaJobList:
        record = self.get(asset_id, owner_id=owner_id)
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

    def save(
        self, record: MultimediaAssetRecord, *, owner_id: str = _DEFAULT_OWNER_ID
    ) -> None:
        owner_digest = _owner_digest(owner_id)
        with self._locked(exclusive=True):
            self._save_unlocked(record, owner_digest)

    def load(
        self, asset_id: str, *, owner_id: str = _DEFAULT_OWNER_ID
    ) -> MultimediaAssetRecord:
        return self.get(asset_id, owner_id=owner_id)

    def migrate_legacy_assets(self, *, owner_id: str) -> int:
        """Assign root-level v0 records only to an explicitly configured owner."""
        owner_digest = _owner_digest(owner_id)
        migrated = 0
        with self._locked(exclusive=True):
            legacy_paths = sorted(self.root.glob("*.json"))
            if len(legacy_paths) > _MAX_ACCOUNT_ASSETS:
                raise ValueError("legacy multimedia asset count exceeds its bound")
            for legacy in legacy_paths:
                record = self._read_legacy_unlocked(legacy)
                if record.asset.asset_id != legacy.stem:
                    raise ValueError("legacy multimedia asset identity conflicts")
                record = _bind_record_owner(record, owner_digest)
                destination = self._path(owner_digest, record.asset.asset_id)
                if destination.exists():
                    existing = self._load_unlocked(record.asset.asset_id, owner_digest)
                    if existing != record:
                        raise ValueError("legacy multimedia asset migration conflicts")
                else:
                    self._save_unlocked(record, owner_digest)
                legacy.unlink()
                _fsync_directory(self.root)
                migrated += 1
        return migrated

    def _save_unlocked(self, record: MultimediaAssetRecord, owner_digest: str) -> None:
        if record.asset.owner_user_id != owner_digest:
            raise ValueError("multimedia asset owner conflicts")
        _validate_production_link(record, owner_digest)
        path = self._path(owner_digest, record.asset.asset_id)
        account = self._account_dir(owner_digest, create=True)
        assert account is not None
        if path.is_symlink():
            raise ValueError("multimedia asset path cannot be a symlink")
        if path.exists():
            _require_private_regular(path)
        envelope = _AccountAssetEnvelope(
            schema_version="antiek.multimedia-account-asset.v1",
            owner_identity_digest=owner_digest,
            record=record,
        )
        payload = (
            envelope.model_dump_json(indent=2, exclude_computed_fields=True).encode("utf-8")
            + b"\n"
        )
        if len(payload) > _MAX_RECORD_BYTES:
            raise ValueError("multimedia asset record exceeds its byte bound")
        temporary = account / f".{record.asset.asset_id}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
            _fsync_directory(account)
        finally:
            os.close(descriptor)
            with suppress(FileNotFoundError):
                temporary.unlink()

    def _load_unlocked(self, asset_id: str, owner_digest: str) -> MultimediaAssetRecord:
        path = self._path(owner_digest, asset_id)
        if not path.exists():
            raise KeyError(asset_id)
        raw = _read_bounded_private(path)
        try:
            envelope = _AccountAssetEnvelope.model_validate_json(raw)
        except Exception:
            raise ValueError("multimedia asset envelope is invalid") from None
        if (
            envelope.owner_identity_digest != owner_digest
            or envelope.record.asset.asset_id != asset_id
        ):
            raise ValueError("multimedia asset envelope identity conflicts")
        if envelope.record.asset.owner_user_id == "__operator__":
            return _bind_record_owner(envelope.record, owner_digest)
        if envelope.record.asset.owner_user_id != owner_digest:
            raise ValueError("multimedia asset envelope owner conflicts")
        _validate_production_link(envelope.record, owner_digest)
        return envelope.record

    def _read_legacy_unlocked(self, path: Path) -> MultimediaAssetRecord:
        raw = _read_bounded_legacy(path)
        try:
            return MultimediaAssetRecord.model_validate_json(raw)
        except Exception:
            raise ValueError("legacy multimedia asset record is invalid") from None

    def _path(self, owner_digest: str, asset_id: str) -> Path:
        if not _OWNER_DIGEST.fullmatch(owner_digest) or not _ASSET_ID.fullmatch(asset_id):
            raise KeyError(asset_id)
        return self._accounts / owner_digest / f"{asset_id}.json"

    def _account_dir(self, owner_digest: str, *, create: bool) -> Path | None:
        if not _OWNER_DIGEST.fullmatch(owner_digest):
            raise ValueError("multimedia owner identity is invalid")
        path = self._accounts / owner_digest
        if path.is_symlink():
            raise ValueError("multimedia account path cannot be a symlink")
        if not path.exists():
            if not create:
                return None
            path.mkdir(mode=0o700)
            _fsync_directory(self._accounts)
        if not path.is_dir():
            raise ValueError("multimedia account path is invalid")
        os.chmod(path, 0o700)
        return path

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        with self._thread_lock:
            descriptor = os.open(
                self._lock_path,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                os.chmod(self._lock_path, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)


def _owner_digest(owner_id: str) -> str:
    if not isinstance(owner_id, str):
        raise ValueError("multimedia owner identity is invalid")
    encoded = owner_id.strip().encode("utf-8")
    if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError("multimedia owner identity is invalid")
    return hashlib.sha256(encoded).hexdigest()


def _validate_production_link(record: MultimediaAssetRecord, owner_digest: str) -> None:
    link = record.production_link
    if link is not None and (
        link.owner_identity_digest != owner_digest
        or link.asset_id != record.asset.asset_id
        or link.revision_id != record.asset.revision_id
    ):
        raise ValueError("multimedia production link identity conflicts")
    audio_link = record.audio_production_link
    if audio_link is not None and (
        audio_link.owner_identity_digest != owner_digest
        or audio_link.asset_id != record.asset.asset_id
        or audio_link.revision_id != record.asset.revision_id
        or record.mode != "audio"
        or str(record.asset.kind) != "audio_experience"
        or link is not None
    ):
        raise ValueError("multimedia audio production link identity conflicts")


def _bind_record_owner(
    record: MultimediaAssetRecord, owner_digest: str
) -> MultimediaAssetRecord:
    return record.model_copy(
        update={"asset": record.asset.model_copy(update={"owner_user_id": owner_digest})}
    )


def _require_private_regular(path: Path) -> os.stat_result:
    if path.is_symlink():
        raise ValueError("multimedia asset path cannot be a symlink")
    metadata = path.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("multimedia asset path is unsafe")
    return metadata


def _read_bounded_private(path: Path) -> bytes:
    metadata = _require_private_regular(path)
    if not 0 < metadata.st_size <= _MAX_RECORD_BYTES:
        raise ValueError("multimedia asset record is invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise ValueError("multimedia asset changed during read")
        chunks: list[bytes] = []
        remaining = _MAX_RECORD_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw or len(raw) > _MAX_RECORD_BYTES or os.read(descriptor, 1):
            raise ValueError("multimedia asset record is invalid")
        return raw
    finally:
        os.close(descriptor)


def _read_bounded_legacy(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("legacy multimedia asset path is unsafe")
    metadata = path.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 0 < metadata.st_size <= _MAX_RECORD_BYTES
    ):
        raise ValueError("legacy multimedia asset path is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise ValueError("legacy multimedia asset changed during read")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != metadata.st_size or os.read(descriptor, 1):
            raise ValueError("legacy multimedia asset changed during read")
        return raw
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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


__all__ = [
    "CreateMultimediaDraftRequest",
    "MultimediaAssetList",
    "MultimediaAssetRecord",
    "MultimediaAssetStore",
    "MultimediaAssetSummary",
    "MultimediaJobList",
    "MultimediaJobRecord",
    "SteeringRequest",
]
