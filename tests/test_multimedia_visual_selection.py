from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from substrate.multimedia.video import TimelineEntry
from substrate.multimedia.visual_selection import (
    ReviewedVisualSelection,
    VerifiedVisualEvidence,
    VisualSelectionError,
    VisualSelectionPacket,
)
from substrate.multimedia.visual_selection import (
    compile_visual_selection_packet as _compile_visual_selection_packet,
)

KEY = b"visual-selection-integrity-key-32b"
AUTHORITY_KEY = b"visual-evidence-authority-key-32b"


def _verifier(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
    if selection.rights_review_id == "fictional":
        raise VisualSelectionError("rights authority rejected selection")
    refs = "|".join(
        value
        for value in (
            selection.execution_receipt_id,
            selection.artifact_receipt_id,
            selection.source_locator_digest,
            selection.rights_review_id,
        )
        if value
    )
    return VerifiedVisualEvidence.issue(
        scene_id=selection.scene_id,
        visual_label=selection.visual_label,
        content_sha256=digest,
        evidence_digest=hashlib.sha256(refs.encode()).hexdigest(),
        authority_key=AUTHORITY_KEY,
    )


def compile_visual_selection_packet(**kwargs):
    kwargs.setdefault("verify_evidence", _verifier)
    kwargs.setdefault("evidence_authority_key", AUTHORITY_KEY)
    return _compile_visual_selection_packet(**kwargs)


def _timeline() -> tuple[TimelineEntry, ...]:
    return (
        TimelineEntry(
            scene_id="scene-a",
            chapter_id="a",
            start_seconds=0,
            end_seconds=1,
            motion="hold",
            visual_label="generated",
            caption="A",
            source_chunk_ids=("c1",),
        ),
        TimelineEntry(
            scene_id="scene-b",
            chapter_id="b",
            start_seconds=1,
            end_seconds=2,
            motion="pan_left",
            visual_label="sourced",
            caption="B",
            source_chunk_ids=("c2",),
        ),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selections(a: Path, b: Path) -> tuple[ReviewedVisualSelection, ...]:
    return (
        ReviewedVisualSelection(
            scene_id="scene-a",
            path=str(a),
            expected_sha256=_sha(a),
            visual_label="generated",
            source_chunk_ids=("c1",),
            execution_receipt_id="exec-1",
            artifact_receipt_id="artifact-1",
        ),
        ReviewedVisualSelection(
            scene_id="scene-b",
            path=str(b),
            expected_sha256=_sha(b),
            visual_label="sourced",
            source_chunk_ids=("c2",),
            source_locator_digest="1" * 64,
            rights_basis="licensed",
            rights_review_id="rights-1",
        ),
    )


@pytest.fixture
def media(tmp_path: Path) -> tuple[Path, Path, Path]:
    a, b, out = tmp_path / "a.ppm", tmp_path / "b.ppm", tmp_path / "out"
    a.write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
    b.write_bytes(b"P6\n1 1\n255\n\xff\xff\xff")
    out.mkdir(mode=0o700)
    return a, b, out


def test_compiles_private_sealed_renderer_packet_and_reopens(media) -> None:
    a, b, out = media
    packet = compile_visual_selection_packet(
        asset_id="planes",
        revision_id="r1",
        timeline=_timeline(),
        selections=_selections(a, b),
        output_dir=str(out),
        integrity_key=KEY,
    )
    assert packet.consume_renderer_inputs(
        KEY, lambda rows: tuple(row.scene_id for row in rows)
    ) == (
        "scene-a",
        "scene-b",
    )
    assert all(Path(row.path).parent.stat().st_mode & 0o077 == 0 for row in packet.visuals)
    assert all(Path(row.path) not in {a, b} for row in packet.visuals)
    assert VisualSelectionPacket.reopen(packet.to_json(), KEY) == packet


@pytest.mark.parametrize(
    "change,match",
    [
        ({"visual_label": "archival"}, "sourced visuals require"),
        ({"source_chunk_ids": ("wrong",)}, "source chunks drifted"),
        ({"scene_id": "scene-x"}, "scene order"),
    ],
)
def test_timeline_is_the_label_source_and_order_authority(media, change, match) -> None:
    a, b, out = media
    rows = list(_selections(a, b))
    rows[0] = rows[0].model_copy(update=change)
    with pytest.raises(ValueError, match=match):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=tuple(rows),
            output_dir=str(out),
            integrity_key=KEY,
        )


def test_label_specific_evidence_fails_closed(media) -> None:
    a, _, _ = media
    base = dict(scene_id="scene-a", path=str(a), expected_sha256=_sha(a), source_chunk_ids=("c1",))
    with pytest.raises(ValidationError, match="execution and artifact"):
        ReviewedVisualSelection(**base, visual_label="generated", execution_receipt_id="exec-1")
    with pytest.raises(ValidationError, match="locator, rights basis"):
        ReviewedVisualSelection(**base, visual_label="archival", source_locator_digest="1" * 64)
    with pytest.raises(ValidationError, match="Diagrams|diagrams"):
        ReviewedVisualSelection(**{**base, "source_chunk_ids": ()}, visual_label="diagram")
    with pytest.raises(ValidationError, match="omitted"):
        ReviewedVisualSelection(**base, visual_label="omitted")


def test_digest_symlink_existing_destination_and_public_root_refused(media) -> None:
    a, b, out = media
    rows = list(_selections(a, b))
    rows[0] = rows[0].model_copy(update={"expected_sha256": "0" * 64})
    with pytest.raises(VisualSelectionError, match="digest"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=tuple(rows),
            output_dir=str(out),
            integrity_key=KEY,
        )
    assert not (out / "planes-r1-visuals").exists()
    link = a.parent / "link.ppm"
    link.symlink_to(a)
    rows = list(_selections(a, b))
    rows[0] = rows[0].model_copy(update={"path": str(link)})
    with pytest.raises(VisualSelectionError, match="unavailable"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=tuple(rows),
            output_dir=str(out),
            integrity_key=KEY,
        )
    out.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=_selections(a, b),
            output_dir=str(out),
            integrity_key=KEY,
        )


def test_packet_tamper_file_drift_and_second_publish_refused(media) -> None:
    a, b, out = media
    packet = compile_visual_selection_packet(
        asset_id="planes",
        revision_id="r1",
        timeline=_timeline(),
        selections=_selections(a, b),
        output_dir=str(out),
        integrity_key=KEY,
    )
    assert (
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=_selections(a, b),
            output_dir=str(out),
            integrity_key=KEY,
        )
        == packet
    )
    body = json.loads(packet.to_json())
    body["visuals"][0]["evidence_digest"] = "0" * 64
    with pytest.raises(VisualSelectionError, match="packet digest"):
        VisualSelectionPacket.reopen(json.dumps(body), KEY)
    path = Path(packet.visuals[0].path)
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(VisualSelectionError, match="file digest"):
        VisualSelectionPacket.reopen(packet.to_json(), KEY)
    with pytest.raises(VisualSelectionError, match="file digest"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=_selections(a, b),
            output_dir=str(out),
            integrity_key=KEY,
        )


def test_models_reject_unknown_fields_and_short_integrity_key(media) -> None:
    a, b, out = media
    with pytest.raises(ValidationError, match="Extra inputs"):
        ReviewedVisualSelection(
            **_selections(a, b)[0].model_dump(), secret_url="https://example.test"
        )
    with pytest.raises(ValueError, match="too short"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=_selections(a, b),
            output_dir=str(out),
            integrity_key=b"short",
        )


def test_bypassed_or_rejected_evidence_and_forged_packet_fail_closed(media) -> None:
    a, b, out = media
    rows = list(_selections(a, b))
    rows[0] = rows[0].model_copy(update={"execution_receipt_id": None, "artifact_receipt_id": None})
    with pytest.raises(ValidationError, match="execution and artifact"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=tuple(rows),
            output_dir=str(out),
            integrity_key=KEY,
        )
    rows = list(_selections(a, b))
    rows[1] = rows[1].model_copy(update={"rights_review_id": "fictional"})
    with pytest.raises(VisualSelectionError, match="authority rejected"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=tuple(rows),
            output_dir=str(out),
            integrity_key=KEY,
        )
    packet = compile_visual_selection_packet(
        asset_id="planes",
        revision_id="r1",
        timeline=_timeline(),
        selections=_selections(a, b),
        output_dir=str(out),
        integrity_key=KEY,
    )
    forged = packet.model_copy(update={"packet_digest": "0" * 64})
    with pytest.raises(VisualSelectionError, match="packet digest"):
        forged.consume_renderer_inputs(KEY, lambda rows: rows)


def test_abandoned_staging_directory_does_not_wedge_revision(media) -> None:
    a, b, out = media
    stale = out / ".visual-selection-stale"
    stale.mkdir(mode=0o700)
    (stale / "partial").write_bytes(b"partial")
    packet = compile_visual_selection_packet(
        asset_id="planes",
        revision_id="r1",
        timeline=_timeline(),
        selections=_selections(a, b),
        output_dir=str(out),
        integrity_key=KEY,
    )
    assert packet.consume_renderer_inputs(KEY, lambda rows: rows)


def test_unsigned_or_wrong_authority_verdict_is_rejected(media) -> None:
    a, b, out = media

    def forged(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
        return VerifiedVisualEvidence(
            scene_id=selection.scene_id,
            visual_label=selection.visual_label,
            content_sha256=digest,
            evidence_digest="0" * 64,
            authority_mac="0" * 64,
        )

    with pytest.raises(VisualSelectionError, match="authority verdict"):
        compile_visual_selection_packet(
            asset_id="planes",
            revision_id="r1",
            timeline=_timeline(),
            selections=_selections(a, b),
            output_dir=str(out),
            integrity_key=KEY,
            verify_evidence=forged,
        )


def test_published_stills_are_read_only_until_same_uid_explicitly_reauthorizes(media) -> None:
    a, b, out = media
    packet = compile_visual_selection_packet(
        asset_id="planes",
        revision_id="r1",
        timeline=_timeline(),
        selections=_selections(a, b),
        output_dir=str(out),
        integrity_key=KEY,
    )
    path = Path(packet.visuals[0].path)
    assert path.stat().st_mode & 0o222 == 0
