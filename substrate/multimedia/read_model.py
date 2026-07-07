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
from substrate.multimedia.audio import assemble_audio_experience
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
from substrate.multimedia.video import (
    assemble_video_documentary,
    build_video_scenes,
)

PlanMode = Literal["video", "audio", "hybrid"]


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


class MultimediaAssetRecord(_ReadModelBase):
    asset: MultimediaAssetContract
    plan: MultimediaPlan
    mode: PlanMode
    style: str | None = None
    hardening_report: MultimediaHardeningReport | None = None
    latest_steering_intent: SteeringIntent | None = None

    def summary(self) -> MultimediaAssetSummary:
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
        )


class MultimediaAssetList(_ReadModelBase):
    assets: tuple[MultimediaAssetSummary, ...]
    count: int


class MultimediaAssetStore:
    """JSON-backed asset record store.

    This is not a provider execution store and not a multi-user database. It is
    a deterministic local read model for the single-operator workstation and
    API tests. Files are written atomically so a process crash cannot leave a
    half-written JSON record.
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
            audio = assemble_audio_experience(record.plan, asset_id=asset.asset_id, revision_id=asset.revision_id)
            manifest = audio.manifest
        else:
            audio = assemble_audio_experience(record.plan, asset_id=asset.asset_id, revision_id=f"{asset.revision_id}-audio")
            video = assemble_video_documentary(record.plan, audio, asset_id=asset.asset_id, revision_id=asset.revision_id)
            manifest = video.manifest.model_copy(
                update={
                    "files": video.manifest.files + audio.manifest.files,
                    "provider_calls": video.manifest.provider_calls + audio.manifest.provider_calls,
                    "cost_rows": video.manifest.cost_rows + audio.manifest.cost_rows,
                    "transcript_file_id": audio.manifest.transcript_file_id,
                }
            )
        approved = asset.model_copy(update={"status": MultimediaStatus.READY, "manifest": manifest})
        updated = record.model_copy(update={"asset": approved})
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
        updated = record.model_copy(
            update={
                "asset": child,
                "latest_steering_intent": intent,
                "hardening_report": None,
            }
        )
        self.save(updated)
        return updated

    def run_hardening(self, asset_id: str) -> MultimediaAssetRecord:
        record = self.get(asset_id)
        scenes: tuple[object, ...] = ()
        if record.mode != "audio":
            audio = assemble_audio_experience(record.plan, asset_id=record.asset.asset_id, revision_id=f"{record.asset.revision_id}-audio")
            scenes = build_video_scenes(record.plan, audio)
        report = evaluate_multimedia_asset(record.asset, scenes=scenes)
        updated = record.model_copy(update={"hardening_report": report})
        self.save(updated)
        return updated

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


__all__ = [
    "CreateMultimediaDraftRequest",
    "MultimediaAssetList",
    "MultimediaAssetRecord",
    "MultimediaAssetStore",
    "MultimediaAssetSummary",
    "SteeringRequest",
]
