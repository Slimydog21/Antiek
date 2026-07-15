from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.contracts.multimedia import GeneratedFile, ScriptLine
from substrate.multimedia.audio_assembly import ChapterAudio
from substrate.multimedia.local_narration_bridge import LocalNarrationInputs
from substrate.multimedia.local_source_card import (
    LocalSourceCardArtifact,
    LocalSourceCardRequest,
)
from substrate.multimedia.local_video_bridge import (
    LocalSourceCardInput,
    LocalVideoBridgeError,
    compile_local_video_inputs,
)
from substrate.multimedia.narration_production import (
    NarrationProductionArtifact,
    NarrationProductionManifest,
    NarrationSource,
)
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest
from substrate.multimedia.visual_selection import VerifiedVisualEvidence

EVIDENCE_KEY = b"local-video-evidence-authority-key"


def _authority():  # noqa: ANN202
    plan = MultimediaPlan(
        request=MultimediaPlanRequest(topic="Aircraft", target_minutes=15, route_policy="cheapest"),
        suggestions=(), chosen_arc_ids=(),
        chapters=(ChapterPlan(
            chapter_id="chapter-1", title="Flow", minutes=15,
            purpose="Explain flow", arc_id="flow", source_chunk_ids=("chunk-1",),
        ),),
        script_lines=(ScriptLine(
            line_id="chapter-1-line-0", sequence=0, text="Factories coordinate flow.",
            kind="factual", citations=(), unsourced_reason="fixture",
        ),),
        scenes=(), unsourced_line_ids=("chapter-1-line-0",),
    )
    chapter = ChapterAudio(
        chapter_id="chapter-1", title="Flow", sequence=0, audio_file_id="audio-1",
        duration_seconds=1.0, start_offset_seconds=0.0,
        script_line_ids=("chapter-1-line-0",), source_chunk_ids=("chunk-1",),
        paragraph_ids=("para-chapter-1-line-0",), recap_prompt="Recall flow.",
    )
    generated = GeneratedFile(
        file_id="audio-1", kind="audio", storage_uri="antiek-mm://asset-1/revision-1/audio.wav",
        sha256="1" * 64, mime="audio/wav", provider="local_executable_tts",
        duration_seconds=1.0,
    )
    inputs = LocalNarrationInputs(
        asset_id="asset-1", revision_id="revision-1", input_digest="2" * 64,
        chapters=(chapter,), generated_files=(generated,), chapter_paths={"audio-1": "/a.wav"},
        request_ids=("audio-1",), chapter_texts=("Factories coordinate flow.",),
    )
    narration = NarrationProductionArtifact(
        manifest=NarrationProductionManifest(
            asset_id="asset-1", revision_id="revision-1", output_path="/narration.wav",
            output_sha256="3" * 64, duration_seconds=1.0, sample_rate_hz=24_000,
            channels=1, sources=(NarrationSource(
                sequence=0, chapter_id="chapter-1", audio_file_id="audio-1",
                path="/chapter.wav", sha256="1" * 64, duration_seconds=1.0,
            ),),
        ),
        manifest_mac="4" * 64,
    )
    request = LocalSourceCardRequest(
        asset_id="asset-1", revision_id="revision-1", chapter_id="chapter-1",
        scene_id="scene-chapter-1", title="Flow", information_purpose="Explain flow",
        source_chunk_ids=("chunk-1",),
    )
    artifact = LocalSourceCardArtifact(
        card_id="card-1", asset_id="asset-1", revision_id="revision-1",
        chapter_id="chapter-1", scene_id="scene-chapter-1",
        source_chunk_ids=("chunk-1",), output_path="/card.png", output_sha256="5" * 64,
        input_digest="6" * 64, snapshot_digest="7" * 64,
        renderer_version="renderer", font_digest="8" * 64,
        width_px=1280, height_px=720, created_at="2026-07-13T00:00:00Z",
    )
    return plan, inputs, narration, request, artifact


class Resolver:
    def __init__(self, artifact: LocalSourceCardArtifact) -> None:
        self.artifact = artifact
        self.calls = 0

    def reopen(self, card_id, request, *, owner_id):  # noqa: ANN001, ANN201
        self.calls += 1
        if card_id != "card-1" or owner_id != "owner-1":
            raise RuntimeError("foreign")
        return self.artifact


def _evidence(selection, digest):  # noqa: ANN001, ANN202
    return VerifiedVisualEvidence.issue(
        scene_id=selection.scene_id, visual_label="diagram", content_sha256=digest,
        evidence_digest="9" * 64, authority_key=EVIDENCE_KEY,
    )


def test_compiles_deterministic_narration_timed_attested_diagram_inputs() -> None:
    plan, inputs, narration, request, artifact = _authority()
    resolver = Resolver(artifact)
    cards = (LocalSourceCardInput("card-1", request),)
    first = compile_local_video_inputs(
        plan, inputs, narration, cards, owner_id="owner-1",
        resolver=resolver, verify_evidence=_evidence,
    )
    second = compile_local_video_inputs(
        plan, inputs, narration, cards, owner_id="owner-1",
        resolver=resolver, verify_evidence=_evidence,
    )
    assert first == second and first.cost_usd == 0.0
    assert first.timeline[0].start_seconds == 0.0
    assert first.timeline[0].end_seconds == 1.0
    assert first.timeline[0].visual_label == "diagram"
    assert first.selections == (artifact.selection(),)
    assert resolver.calls == 2


@pytest.mark.parametrize("mutation", ["missing", "request", "artifact", "duration"])
def test_rejects_incomplete_or_cross_authority_drift(mutation: str) -> None:
    plan, inputs, narration, request, artifact = _authority()
    cards = (LocalSourceCardInput("card-1", request),)
    if mutation == "missing":
        cards = ()
    elif mutation == "request":
        cards = (LocalSourceCardInput("card-1", replace(request, title="drift")),)
    elif mutation == "artifact":
        artifact = replace(artifact, revision_id="revision-2")
    else:
        narration = narration.model_copy(
            update={"manifest": narration.manifest.model_copy(update={"duration_seconds": 2.0})}
        )
    with pytest.raises(LocalVideoBridgeError):
        compile_local_video_inputs(
            plan, inputs, narration, cards, owner_id="owner-1",
            resolver=Resolver(artifact), verify_evidence=_evidence,
        )


def test_rejects_forged_evidence_verdict() -> None:
    plan, inputs, narration, request, artifact = _authority()

    def forged(_selection, _digest):  # noqa: ANN001, ANN202
        return VerifiedVisualEvidence.issue(
            scene_id="other-scene", visual_label="diagram", content_sha256="5" * 64,
            evidence_digest="9" * 64, authority_key=EVIDENCE_KEY,
        )

    with pytest.raises(LocalVideoBridgeError, match="evidence conflicts"):
        compile_local_video_inputs(
            plan, inputs, narration, (LocalSourceCardInput("card-1", request),),
            owner_id="owner-1", resolver=Resolver(artifact), verify_evidence=forged,
        )
