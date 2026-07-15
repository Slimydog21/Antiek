"""Tests for the educational video receipt authority."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import stat
import threading
import wave
from pathlib import Path

import pytest

import substrate.multimedia.educational_video_receipt as receipt_module
from substrate.multimedia.educational_video_production import (
    EducationalVideoProductionArtifact,
)
from substrate.multimedia.educational_video_receipt import (
    EducationalVideoReceipt,
    EducationalVideoReceiptError,
    issue,
)
from substrate.multimedia.ken_burns_renderer import (
    KenBurnsRenderArtifact,
    KenBurnsRenderError,
    KenBurnsRenderManifest,
    RenderedCaption,
    RenderedInput,
)
from substrate.multimedia.narration_production import (
    NarrationProductionArtifact,
    NarrationProductionError,
    NarrationProductionManifest,
    NarrationSource,
)
from substrate.multimedia.visual_selection import (
    PacketVisual,
    VisualSelectionError,
    VisualSelectionPacket,
)
from tests import test_multimedia_educational_video_production as production_tests

_RECEIPT_KEY = b"educational-video-receipt-key-32b!"
_NARRATION_KEY = b"narration-integrity-key-32-bytes!!"
_VISUAL_KEY = b"visual-selection-integrity-key-32!"
_RENDER_KEY = b"ken-burns-render-integrity-key-32!"


def _wav(path: Path, duration: float, sample: int = 100) -> None:
    rate = 8_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(sample.to_bytes(2, "little", signed=True) * round(rate * duration))
    path.chmod(0o600)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _narration_mac(manifest: NarrationProductionManifest, key: bytes) -> str:
    payload = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _render_mac(manifest: KenBurnsRenderManifest, key: bytes) -> str:
    payload = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _visual_digest(packet_data: dict, key: bytes) -> str:
    payload = json.dumps(packet_data, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _resign(data: dict[str, object]) -> str:
    payload = json.dumps(
        {key: value for key, value in data.items() if key != "receipt_mac"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(_RECEIPT_KEY, payload, hashlib.sha256).hexdigest()


def _receipt_path(root: Path, asset_id: str, revision_id: str) -> Path:
    identity = json.dumps([asset_id, revision_id], separators=(",", ":")).encode("ascii")
    return root / ("mmvideo_" + hashlib.sha256(identity).hexdigest()) / "receipt.json"


def _make_png(path: Path) -> None:
    """Write a minimal valid 1x1 white PNG."""
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"  # signature
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"  # IHDR
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"  # IDAT
        b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
    )
    path.chmod(0o600)


@pytest.fixture
def artifacts(tmp_path: Path):
    """Create valid artifacts for testing."""
    # Narration
    output = tmp_path / "narration"
    output.mkdir(mode=0o700)
    wav_path = tmp_path / "source.wav"
    _wav(wav_path, 1.0, 100)
    shutil.copy2(wav_path, output / "narration.wav")
    (output / "narration.wav").chmod(0o600)
    output_sha = _sha(output / "narration.wav")

    sources = (
        NarrationSource(
            sequence=0,
            chapter_id="chapter-0",
            audio_file_id="audio-0",
            path=str(wav_path),
            sha256=_sha(wav_path),
            duration_seconds=1.0,
        ),
    )
    narration_manifest = NarrationProductionManifest(
        asset_id="asset-0",
        revision_id="rev-0",
        output_path=str(output / "narration.wav"),
        output_sha256=output_sha,
        duration_seconds=1.0,
        sample_rate_hz=8_000,
        channels=1,
        sources=sources,
    )
    narration = NarrationProductionArtifact(
        manifest=narration_manifest,
        manifest_mac=_narration_mac(narration_manifest, _NARRATION_KEY),
    )

    # Visual packet
    still = tmp_path / "still.png"
    _make_png(still)
    visuals = (
        PacketVisual(
            scene_id="scene-0",
            path=str(still),
            sha256=_sha(still),
            visual_label="generated",
            source_chunk_ids=("chunk-0",),
            evidence_digest="a" * 64,
        ),
    )
    timeline_sha = hashlib.sha256(b"timeline-placeholder").hexdigest()
    visual_data = {
        "schema_version": "antiek.documentary-visual-packet.v1",
        "asset_id": "asset-0",
        "revision_id": "rev-0",
        "timeline_sha256": timeline_sha,
        "visuals": [v.model_dump(mode="json") for v in visuals],
    }
    visual = VisualSelectionPacket(
        asset_id="asset-0",
        revision_id="rev-0",
        timeline_sha256=timeline_sha,
        visuals=visuals,
        packet_digest=_visual_digest(visual_data, _VISUAL_KEY),
    )

    # Render artifact
    doc_path = tmp_path / "documentary.mp4"
    doc_path.write_bytes(b"fake-video-content")
    doc_path.chmod(0o600)
    cap_path = tmp_path / "captions.vtt"
    cap_path.write_bytes(b"WEBVTT\n\n")
    cap_path.chmod(0o600)
    narr_path = output / "narration.wav"

    captions = (
        RenderedCaption(
            cue_id="cue-0000",
            scene_id="scene-0",
            chapter_id="chapter-0",
            start_seconds=0.0,
            end_seconds=1.0,
            text="Test caption",
            source_chunk_ids=("chunk-0",),
        ),
    )
    inputs = (
        RenderedInput(
            scene_id="scene-0",
            path=str(still),
            sha256=_sha(still),
            visual_label="generated",
            source_chunk_ids=("chunk-0",),
        ),
    )
    render_manifest = KenBurnsRenderManifest(
        asset_id="asset-0",
        revision_id="rev-0",
        output_path=str(doc_path),
        output_sha256=_sha(doc_path),
        captions_path=str(cap_path),
        captions_sha256=_sha(cap_path),
        narration_path=str(narr_path),
        narration_sha256=output_sha,
        timeline_sha256=timeline_sha,
        width_px=1280,
        height_px=720,
        fps=30,
        duration_seconds=1.0,
        video_codec="h264",
        audio_codec="aac",
        subtitle_codec="mov_text",
        scene_ids=("scene-0",),
        chapter_ids=("chapter-0",),
        motions=("hold",),
        visual_labels=("generated",),
        inputs=inputs,
        captions=captions,
    )
    render = KenBurnsRenderArtifact(
        manifest=render_manifest,
        manifest_sha256=_render_mac(render_manifest, _RENDER_KEY),
    )

    # Compose
    documentary = type("DocumentaryProductionArtifact", (), {
        "visual_packet": visual,
        "render_artifact": render,
    })()
    production = EducationalVideoProductionArtifact(
        narration=narration,
        documentary=documentary,
    )
    return production, narration, visual, render


def test_issue_and_reopen_happy_path(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    assert receipt.schema_version == "antiek.educational-video-receipt.v1"
    assert receipt.asset_id == "asset-0"
    assert receipt.revision_id == "rev-0"
    reopened = EducationalVideoReceipt.reopen(
        receipt.to_json(), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
    )
    assert reopened == receipt


def test_reopen_from_file(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    receipt_path = _receipt_path(output, receipt.asset_id, receipt.revision_id)
    reopened = EducationalVideoReceipt.reopen_from_file(
        str(receipt_path), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
    )
    assert reopened == receipt


def test_real_production_can_be_persisted_and_reopened(tmp_path: Path) -> None:
    state = production_tests.state.__wrapped__(tmp_path)
    production = production_tests._produce(state)
    output = tmp_path / "receipts"
    output.mkdir(mode=0o700)

    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=production_tests.NARRATION_KEY,
        visual_key=production_tests.VISUAL_KEY,
        render_key=production_tests.RENDER_KEY,
        output_dir=str(output),
    )
    path = _receipt_path(output, "asset", "revision")
    reopened = EducationalVideoReceipt.reopen_from_file(
        str(path),
        _RECEIPT_KEY,
        production_tests.NARRATION_KEY,
        production_tests.VISUAL_KEY,
        production_tests.RENDER_KEY,
    )

    assert reopened == receipt
    assert Path(reopened.render.manifest.output_path).is_file()


def test_wrong_receipt_key(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    wrong_key = b"wrong-receipt-key-32-bytes!!!!!!"
    with pytest.raises(EducationalVideoReceiptError, match="MAC"):
        EducationalVideoReceipt.reopen(receipt.to_json(), wrong_key, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY)


def test_wrong_narration_key(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    wrong_key = b"wrong-narration-key-32-bytes!!!!"
    with pytest.raises((EducationalVideoReceiptError, NarrationProductionError)):
        EducationalVideoReceipt.reopen(receipt.to_json(), _RECEIPT_KEY, wrong_key, _VISUAL_KEY, _RENDER_KEY)


def test_wrong_visual_key(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    wrong_key = b"wrong-visual-key-32-bytes!!!!!!!"
    with pytest.raises((EducationalVideoReceiptError, VisualSelectionError)):
        EducationalVideoReceipt.reopen(receipt.to_json(), _RECEIPT_KEY, _NARRATION_KEY, wrong_key, _RENDER_KEY)


def test_wrong_render_key(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    wrong_key = b"wrong-render-key-32-bytes!!!!!!!"
    with pytest.raises((EducationalVideoReceiptError, KenBurnsRenderError)):
        EducationalVideoReceipt.reopen(receipt.to_json(), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, wrong_key)


def test_receipt_mac_tamper(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    tampered = receipt.model_copy(update={"receipt_mac": "f" * 64})
    with pytest.raises(EducationalVideoReceiptError, match="MAC"):
        EducationalVideoReceipt.reopen(tampered.to_json(), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY)


def test_asset_id_tamper(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    # Tamper the asset_id in the receipt JSON and recompute MAC
    data = json.loads(receipt.to_json())
    data["asset_id"] = "tampered"
    data["receipt_mac"] = _resign(data)
    tampered_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    # The MAC check passes (we recomputed it), but the cross-binding check fails
    with pytest.raises(EducationalVideoReceiptError):
        EducationalVideoReceipt.reopen(tampered_json, _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY)


def test_unbounded_receipt_identity_is_rejected_before_bundle_lookup(
    tmp_path: Path, artifacts
) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    data = json.loads(receipt.to_json())
    data["asset_id"] = "not/ascii-bounded"
    data["receipt_mac"] = _resign(data)
    with pytest.raises(EducationalVideoReceiptError, match="payload"):
        EducationalVideoReceipt.reopen(
            json.dumps(data), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
        )


def test_symlink_output_dir_fails(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlinks"):
        issue(
            artifact=production,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(link),
        )


def test_public_output_dir_fails(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="private"):
        issue(
            artifact=production,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(output),
        )


def test_reopen_from_symlink_file_fails(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    receipt_path = _receipt_path(output, receipt.asset_id, receipt.revision_id)
    link = tmp_path / "link.json"
    link.symlink_to(receipt_path)
    with pytest.raises(EducationalVideoReceiptError, match="symlink"):
        EducationalVideoReceipt.reopen_from_file(
            str(link), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
        )


def test_reopen_rejects_public_bundle_and_hardlinked_file(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    path = _receipt_path(output, receipt.asset_id, receipt.revision_id)
    bundle = path.parent
    bundle.chmod(0o755)
    with pytest.raises(EducationalVideoReceiptError, match="bundle"):
        EducationalVideoReceipt.reopen_from_file(
            str(path), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
        )
    bundle.chmod(0o700)
    hardlink = tmp_path / "receipt-hardlink.json"
    hardlink.hardlink_to(path)
    with pytest.raises(EducationalVideoReceiptError, match="private"):
        EducationalVideoReceipt.reopen_from_file(
            str(path), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
        )


def test_replay_returns_same_receipt(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt1 = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    receipt2 = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    assert receipt1 == receipt2


def test_conflicting_content_fails(tmp_path: Path, artifacts) -> None:
    production, _, visual, render = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    changed_manifest = render.manifest.model_copy(update={"video_codec": "h265"})
    changed_render = KenBurnsRenderArtifact(
        manifest=changed_manifest,
        manifest_sha256=_render_mac(changed_manifest, _RENDER_KEY),
    )
    changed_documentary = type(
        "DocumentaryProductionArtifact",
        (),
        {"visual_packet": visual, "render_artifact": changed_render},
    )()
    changed_production = EducationalVideoProductionArtifact(
        narration=production.narration,
        documentary=changed_documentary,
    )
    issue(
        artifact=changed_production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    with pytest.raises(FileExistsError, match="destination conflicts"):
        issue(
            artifact=production,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(output),
        )
    assert list(output.iterdir()) == [
        _receipt_path(output, "asset-0", "rev-0").parent
    ]


def test_partial_failure_cleanup(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    bad_key = b"bad"
    with pytest.raises((ValueError, EducationalVideoReceiptError)):
        issue(
            artifact=production,
            receipt_key=bad_key,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(output),
        )
    contents = list(output.iterdir())
    assert len(contents) == 0, f"Partial files remain: {contents}"


def test_staged_validation_failure_leaves_no_receipt(
    tmp_path: Path, artifacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)

    def fail_reopen(*_args, **_kwargs):
        raise EducationalVideoReceiptError("injected staged failure")

    monkeypatch.setattr(EducationalVideoReceipt, "reopen", fail_reopen)
    with pytest.raises(EducationalVideoReceiptError, match="injected"):
        issue(
            artifact=production,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(output),
        )
    assert list(output.iterdir()) == []


def test_boundary_drift_fails_before_publication(tmp_path: Path, artifacts) -> None:
    production, narration, _, _ = artifacts
    source = narration.manifest.sources[0].model_copy(update={"duration_seconds": 0.5})
    manifest = narration.manifest.model_copy(
        update={"duration_seconds": 0.5, "sources": (source,)}
    )
    drifted_narration = NarrationProductionArtifact(
        manifest=manifest,
        manifest_mac=_narration_mac(manifest, _NARRATION_KEY),
    )
    drifted = EducationalVideoProductionArtifact(
        narration=drifted_narration,
        documentary=production.documentary,
    )
    output = tmp_path / "output"
    output.mkdir(mode=0o700)

    with pytest.raises(EducationalVideoReceiptError, match="boundary|duration"):
        issue(
            artifact=drifted,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(output),
        )
    assert list(output.iterdir()) == []


def test_render_media_tamper_fails_persisted_reopen(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    Path(receipt.render.manifest.output_path).write_bytes(b"tampered")
    path = _receipt_path(output, receipt.asset_id, receipt.revision_id)
    with pytest.raises(KenBurnsRenderError, match="digest"):
        EducationalVideoReceipt.reopen_from_file(
            str(path), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
        )


def test_reopen_rejects_bundle_detached_after_verified_read(
    tmp_path: Path, artifacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    path = _receipt_path(output, receipt.asset_id, receipt.revision_id)
    detached = tmp_path / "detached"
    original = receipt_module._read_private_file

    def detach_after_read(value: str):
        result = original(value)
        path.parent.rename(detached)
        path.parent.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(receipt_module, "_read_private_file", detach_after_read)
    with pytest.raises(EducationalVideoReceiptError, match="changed"):
        EducationalVideoReceipt.reopen_from_file(
            str(path), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY
        )


def test_to_json_roundtrip(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    json_str = receipt.to_json()
    data = json.loads(json_str)
    assert data["schema_version"] == "antiek.educational-video-receipt.v1"
    assert data["asset_id"] == "asset-0"
    assert "narration" in data
    assert "visual" in data
    assert "render" in data
    assert "receipt_mac" in data


def test_receipt_file_permissions(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    receipt_path = _receipt_path(output, receipt.asset_id, receipt.revision_id)
    info = receipt_path.stat()
    assert stat.S_IMODE(info.st_mode) == 0o600


def test_concurrent_identical_issuance(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    results: list[EducationalVideoReceipt | Exception] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        try:
            barrier.wait()
            receipt = issue(
                artifact=production,
                receipt_key=_RECEIPT_KEY,
                narration_key=_NARRATION_KEY,
                visual_key=_VISUAL_KEY,
                render_key=_RENDER_KEY,
                output_dir=str(output),
            )
            results.append(receipt)
        except Exception as e:
            results.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    successes = [r for r in results if isinstance(r, EducationalVideoReceipt)]
    assert len(successes) == 4, results
    for s in successes[1:]:
        assert s == successes[0]
    assert list(output.iterdir()) == [
        _receipt_path(output, "asset-0", "rev-0").parent
    ]


def test_short_key_rejected(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    short_key = b"short"
    with pytest.raises(ValueError, match="32 bytes"):
        issue(
            artifact=production,
            receipt_key=short_key,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(output),
        )


def test_receipt_carries_nested_payloads(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    assert receipt.narration.manifest.schema_version == "antiek.narration-production.v1"
    assert receipt.visual.schema_version == "antiek.documentary-visual-packet.v1"
    assert receipt.render.manifest.schema_version == "antiek.ken-burns-render.v1"
    assert "manifest" in receipt.narration.model_dump()
    assert "manifest" in receipt.render.model_dump()
    assert "visuals" in receipt.visual.model_dump()


def test_cross_binding_timeline_digest(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    assert receipt.visual.timeline_sha256 == receipt.render.manifest.timeline_sha256


def test_cross_binding_narration_path(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    assert receipt.render.manifest.narration_path == receipt.narration.manifest.output_path
    assert receipt.render.manifest.narration_sha256 == receipt.narration.manifest.output_sha256


def test_cross_binding_visual_rows(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    visual_rows = tuple(
        (row.scene_id, row.path, row.sha256, row.visual_label, row.source_chunk_ids)
        for row in receipt.visual.visuals
    )
    render_rows = tuple(
        (row.scene_id, row.path, row.sha256, row.visual_label, row.source_chunk_ids)
        for row in receipt.render.manifest.inputs
    )
    assert visual_rows == render_rows


def test_cross_binding_chapter_ids(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    narration_chapters = tuple(row.chapter_id for row in receipt.narration.manifest.sources)
    render_chapters = tuple(row.chapter_id for row in receipt.render.manifest.captions)
    assert narration_chapters == render_chapters


def test_cross_binding_duration(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    assert abs(
        receipt.narration.manifest.duration_seconds - receipt.render.manifest.duration_seconds
    ) < 0.001


def test_nested_model_copy_tamper(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    tampered_manifest = receipt.narration.manifest.model_copy(update={"duration_seconds": 999.0})
    tampered_narration = receipt.narration.model_copy(update={"manifest": tampered_manifest})
    tampered = receipt.model_copy(update={"narration": tampered_narration, "receipt_mac": "0" * 64})
    data = tampered.model_dump(mode="json")
    tampered = tampered.model_copy(update={"receipt_mac": _resign(data)})
    with pytest.raises((EducationalVideoReceiptError, ValueError)):
        EducationalVideoReceipt.reopen(tampered.to_json(), _RECEIPT_KEY, _NARRATION_KEY, _VISUAL_KEY, _RENDER_KEY)


def test_receipt_deterministic_path(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    expected = _receipt_path(output.resolve(), receipt.asset_id, receipt.revision_id)
    assert expected.exists()


def test_no_media_bytes_duplicated(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    receipt_json = receipt.to_json()
    assert b"fake-video-content" not in receipt_json.encode()
    assert b"PNG" not in receipt_json.encode()


def test_missing_output_directory_is_rejected(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    with pytest.raises(ValueError, match="already exist"):
        issue(
            artifact=production,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(tmp_path / "missing"),
        )


def test_output_dir_is_resolved(tmp_path: Path, artifacts) -> None:
    production, _, _, _ = artifacts
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    receipt = issue(
        artifact=production,
        receipt_key=_RECEIPT_KEY,
        narration_key=_NARRATION_KEY,
        visual_key=_VISUAL_KEY,
        render_key=_RENDER_KEY,
        output_dir=str(output),
    )
    receipt_path = _receipt_path(output.resolve(), receipt.asset_id, receipt.revision_id)
    assert receipt_path.exists()
    info = receipt_path.stat()
    assert stat.S_ISREG(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o600
    assert info.st_nlink == 1
