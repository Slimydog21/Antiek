from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import pytest

import substrate.multimedia.documentary_production as production
from substrate.multimedia.documentary_production import (
    DocumentaryProductionError,
    produce_ken_burns_documentary,
)
from substrate.multimedia.ken_burns_renderer import (
    KenBurnsRenderArtifact,
    KenBurnsRenderError,
)
from substrate.multimedia.video import TimelineEntry
from substrate.multimedia.visual_selection import (
    ReviewedVisualSelection,
    VerifiedVisualEvidence,
    VisualSelectionError,
)

VISUAL_KEY = b"visual-packet-integrity-key-32b!"
EVIDENCE_KEY = b"visual-evidence-authority-key-32"
RENDER_KEY = b"render-artifact-integrity-key-32"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
    return VerifiedVisualEvidence.issue(
        scene_id=selection.scene_id,
        visual_label=selection.visual_label,
        content_sha256=digest,
        evidence_digest="a" * 64,
        authority_key=EVIDENCE_KEY,
    )


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("documentary-production")
    visual_root, render_root = root / "visuals", root / "renders"
    visual_root.mkdir(mode=0o700)
    render_root.mkdir(mode=0o700)
    still = root / "lift.ppm"
    still.write_bytes(b"P6\n16 16\n255\n" + bytes([40, 100, 180]) * 256)
    still.chmod(0o600)
    narration = root / "narration.wav"
    with wave.open(str(narration), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 8_000)
    narration.chmod(0o600)
    timeline = (
        TimelineEntry(
            scene_id="scene-1",
            chapter_id="chapter-1",
            start_seconds=0,
            end_seconds=1,
            motion="slow_zoom_in",
            visual_label="diagram",
            caption="Lift follows from pressure differences.",
            source_chunk_ids=("chunk-lift",),
        ),
    )
    selection = ReviewedVisualSelection(
        scene_id="scene-1",
        path=str(still),
        expected_sha256=_sha(still),
        visual_label="diagram",
        source_chunk_ids=("chunk-lift",),
    )
    result = produce_ken_burns_documentary(
        asset_id="asset-1",
        revision_id="revision-1",
        timeline=timeline,
        selections=(selection,),
        narration_path=str(narration),
        visual_output_dir=str(visual_root),
        render_output_dir=str(render_root),
        visual_integrity_key=VISUAL_KEY,
        evidence_authority_key=EVIDENCE_KEY,
        render_integrity_key=RENDER_KEY,
        verify_evidence=_evidence,
        width_px=320,
        height_px=240,
        fps=10,
    )
    return root, narration, timeline, selection, result


def test_production_reaches_real_renderer_with_exact_binding(rendered) -> None:
    _, _, timeline, _, result = rendered
    manifest = result.render_artifact.manifest
    assert manifest.asset_id == result.visual_packet.asset_id == "asset-1"
    assert manifest.timeline_sha256 == result.visual_packet.timeline_sha256
    assert manifest.scene_ids == tuple(row.scene_id for row in timeline)
    assert manifest.inputs[0].sha256 == result.visual_packet.visuals[0].sha256
    assert Path(manifest.output_path).is_file()


@pytest.mark.parametrize(
    ("field", "value"),
    (("asset_id", "asset-other"), ("revision_id", "revision-other"), ("timeline_sha256", "b" * 64)),
)
def test_cross_artifact_identity_substitution_fails(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    substituted = result.render_artifact.manifest.model_copy(update={field: value})
    sealed = KenBurnsRenderArtifact.seal(substituted, RENDER_KEY)
    monkeypatch.setattr(production, "render_ken_burns_documentary", lambda **_: sealed)
    with pytest.raises(DocumentaryProductionError, match="identity"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
            width_px=320,
            height_px=240,
            fps=10,
        )


def test_forged_renderer_artifact_fails_before_cross_binding(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    forged = result.render_artifact.model_copy(update={"manifest_sha256": "0" * 64})
    monkeypatch.setattr(production, "render_ken_burns_documentary", lambda **_: forged)
    with pytest.raises(KenBurnsRenderError, match="digest"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
        )


def test_cross_artifact_source_authority_substitution_fails(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    manifest = result.render_artifact.manifest
    changed_chunks = ("chunk-substituted",)
    substituted = manifest.model_copy(
        update={
            "inputs": (
                manifest.inputs[0].model_copy(update={"source_chunk_ids": changed_chunks}),
            ),
            "captions": (
                manifest.captions[0].model_copy(update={"source_chunk_ids": changed_chunks}),
            ),
        }
    )
    sealed = KenBurnsRenderArtifact.seal(substituted, RENDER_KEY)
    monkeypatch.setattr(production, "render_ken_burns_documentary", lambda **_: sealed)
    with pytest.raises(DocumentaryProductionError, match="timeline content|inputs"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
            width_px=320,
            height_px=240,
            fps=10,
        )


def test_forged_evidence_never_reaches_renderer(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    called = False

    def renderer(**_):
        nonlocal called
        called = True
        return result.render_artifact

    def forged(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
        return _evidence(selection, digest).model_copy(update={"authority_mac": "0" * 64})

    monkeypatch.setattr(production, "render_ken_burns_documentary", renderer)
    with pytest.raises(VisualSelectionError, match="authority"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(tmp_path / "unused"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=forged,
        )
    assert called is False


@pytest.mark.parametrize("changed", ("narration", "dimensions"))
def test_prior_artifact_cannot_replace_changed_render_request(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    requested_narration = narration
    width_px, height_px = 320, 240
    if changed == "narration":
        requested_narration = tmp_path / "different.wav"
        requested_narration.write_bytes(narration.read_bytes() + b"different")
    else:
        width_px = 640
    monkeypatch.setattr(
        production, "render_ken_burns_documentary", lambda **_: result.render_artifact
    )
    with pytest.raises(DocumentaryProductionError, match="request"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(requested_narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
            width_px=width_px,
            height_px=height_px,
            fps=10,
        )


def test_prior_artifact_cannot_replace_new_visual_packet_destination(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    monkeypatch.setattr(
        production, "render_ken_burns_documentary", lambda **_: result.render_artifact
    )
    with pytest.raises(DocumentaryProductionError, match="inputs"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
            width_px=320,
            height_px=240,
            fps=10,
        )


def test_signed_caption_substitution_cannot_hide_behind_timeline_digest(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    manifest = result.render_artifact.manifest
    changed = manifest.model_copy(
        update={
            "captions": (
                manifest.captions[0].model_copy(update={"text": "Substituted claim."}),
            )
        }
    )
    sealed = KenBurnsRenderArtifact.seal(changed, RENDER_KEY)
    monkeypatch.setattr(production, "render_ken_burns_documentary", lambda **_: sealed)
    with pytest.raises(DocumentaryProductionError, match="timeline content"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
            width_px=320,
            height_px=240,
            fps=10,
        )


def test_signed_motion_substitution_cannot_hide_behind_timeline_digest(
    rendered, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, narration, timeline, selection, result = rendered
    visual_root = tmp_path / "visuals"
    visual_root.mkdir(mode=0o700)
    changed = result.render_artifact.manifest.model_copy(update={"motions": ("hold",)})
    sealed = KenBurnsRenderArtifact.seal(changed, RENDER_KEY)
    monkeypatch.setattr(production, "render_ken_burns_documentary", lambda **_: sealed)
    with pytest.raises(DocumentaryProductionError, match="timeline content"):
        produce_ken_burns_documentary(
            asset_id="asset-1",
            revision_id="revision-1",
            timeline=timeline,
            selections=(selection,),
            narration_path=str(narration),
            visual_output_dir=str(visual_root),
            render_output_dir=str(root / "renders"),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
            width_px=320,
            height_px=240,
            fps=10,
        )
