"""Bind attested local source cards to a narration-timed documentary timeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .local_narration_bridge import LocalNarrationInputs
from .local_source_card import LocalSourceCardArtifact, LocalSourceCardRequest
from .narration_production import NarrationProductionArtifact
from .planner import MultimediaPlan
from .video import MotionPreset, TimelineEntry
from .visual_selection import (
    EvidenceVerifier,
    ReviewedVisualSelection,
    VerifiedVisualEvidence,
)

_MOTIONS: tuple[MotionPreset, ...] = (
    "slow_zoom_in", "pan_left", "slow_zoom_out", "pan_right", "hold", "map_callout"
)


class LocalVideoBridgeError(RuntimeError):
    """Local visual evidence did not match the narration-timed plan."""


class LocalSourceCardResolver(Protocol):
    def reopen(
        self, card_id: str, request: LocalSourceCardRequest, *, owner_id: str
    ) -> LocalSourceCardArtifact: ...


@dataclass(frozen=True)
class LocalSourceCardInput:
    card_id: str
    request: LocalSourceCardRequest


@dataclass(frozen=True)
class LocalVideoInputs:
    asset_id: str
    revision_id: str
    input_digest: str
    timeline: tuple[TimelineEntry, ...]
    selections: tuple[ReviewedVisualSelection, ...]
    evidence: tuple[VerifiedVisualEvidence, ...]
    card_ids: tuple[str, ...]
    cost_usd: float = 0.0


def compile_local_video_inputs(
    plan: MultimediaPlan,
    narration_inputs: LocalNarrationInputs,
    narration: NarrationProductionArtifact,
    cards: tuple[LocalSourceCardInput, ...],
    *,
    owner_id: str,
    resolver: LocalSourceCardResolver,
    verify_evidence: EvidenceVerifier,
) -> LocalVideoInputs:
    """Reopen graph cards and explicit attestations in narration chapter order."""
    if not owner_id or plan.request.route_policy != "cheapest":
        raise ValueError("local video requires an owner-bound cheapest plan")
    manifest = narration.manifest
    if (
        manifest.asset_id != narration_inputs.asset_id
        or manifest.revision_id != narration_inputs.revision_id
        or len(cards) != len(narration_inputs.chapters)
        or tuple(row.chapter_id for row in manifest.sources)
        != tuple(row.chapter_id for row in narration_inputs.chapters)
    ):
        raise LocalVideoBridgeError("local video narration authority conflicts")
    chapters = {chapter.chapter_id: chapter for chapter in plan.chapters}
    timeline: list[TimelineEntry] = []
    selections: list[ReviewedVisualSelection] = []
    evidence: list[VerifiedVisualEvidence] = []
    artifacts: list[LocalSourceCardArtifact] = []
    cursor = 0.0
    for index, (audio, source, card) in enumerate(
        zip(narration_inputs.chapters, manifest.sources, cards, strict=True)
    ):
        chapter = chapters.get(audio.chapter_id)
        if chapter is None:
            raise LocalVideoBridgeError("local video chapter is unavailable")
        expected = LocalSourceCardRequest(
            asset_id=narration_inputs.asset_id,
            revision_id=narration_inputs.revision_id,
            chapter_id=audio.chapter_id,
            scene_id=f"scene-{audio.chapter_id}",
            title=chapter.title,
            information_purpose=chapter.purpose,
            source_chunk_ids=audio.source_chunk_ids,
        )
        if card.request != expected:
            raise LocalVideoBridgeError("local source-card request drifted from plan")
        try:
            artifact = resolver.reopen(card.card_id, expected, owner_id=owner_id)
        except Exception as exc:
            raise LocalVideoBridgeError("local source-card artifact is unavailable") from exc
        selection = artifact.selection()
        if (
            artifact.card_id != card.card_id
            or artifact.asset_id != expected.asset_id
            or artifact.revision_id != expected.revision_id
            or artifact.chapter_id != expected.chapter_id
            or artifact.scene_id != expected.scene_id
            or artifact.source_chunk_ids != expected.source_chunk_ids
        ):
            raise LocalVideoBridgeError("local source-card artifact conflicts with plan")
        try:
            verdict = verify_evidence(selection, artifact.output_sha256)
        except Exception as exc:
            raise LocalVideoBridgeError("local source-card evidence is unavailable") from exc
        if (
            verdict.scene_id != selection.scene_id
            or verdict.visual_label != "diagram"
            or verdict.content_sha256 != selection.expected_sha256
        ):
            raise LocalVideoBridgeError("local source-card evidence conflicts")
        end = round(cursor + source.duration_seconds, 3)
        timeline.append(
            TimelineEntry(
                scene_id=expected.scene_id,
                chapter_id=expected.chapter_id,
                start_seconds=cursor,
                end_seconds=end,
                motion=_MOTIONS[index % len(_MOTIONS)],
                visual_label="diagram",
                caption=narration_inputs.chapter_texts[index],
                source_chunk_ids=expected.source_chunk_ids,
            )
        )
        selections.append(selection)
        evidence.append(verdict)
        artifacts.append(artifact)
        cursor = end
    if cursor != manifest.duration_seconds:
        raise LocalVideoBridgeError("local video timeline duration conflicts with narration")
    authority = {
        "cards": [artifact.__dict__ for artifact in artifacts],
        "cost_usd": 0.0,
        "evidence": [row.model_dump(mode="json") for row in evidence],
        "narration_input_digest": narration_inputs.input_digest,
        "narration_manifest_mac": narration.manifest_mac,
        "schema_version": "antiek.local-video-inputs.v1",
        "timeline": [row.model_dump(mode="json") for row in timeline],
    }
    digest = hashlib.sha256(
        json.dumps(authority, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return LocalVideoInputs(
        asset_id=narration_inputs.asset_id,
        revision_id=narration_inputs.revision_id,
        input_digest=digest,
        timeline=tuple(timeline),
        selections=tuple(selections),
        evidence=tuple(evidence),
        card_ids=tuple(artifact.card_id for artifact in artifacts),
    )


__all__ = [
    "LocalSourceCardInput",
    "LocalSourceCardResolver",
    "LocalVideoBridgeError",
    "LocalVideoInputs",
    "compile_local_video_inputs",
]
