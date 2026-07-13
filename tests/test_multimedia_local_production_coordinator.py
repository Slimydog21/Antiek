from __future__ import annotations

import hashlib
import platform
import wave
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from PIL import Image, ImageDraw

import substrate.multimedia.local_production_coordinator as coordinator_module
from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import prepare_chapter_tts_request
from substrate.multimedia.local_production_coordinator import (
    LocalNarrationRunRequest,
    LocalProductionCoordinator,
    LocalProductionCoordinatorError,
    LocalProductionOutcomeUnknown,
    LocalVideoProductionCoordinator,
    LocalVideoRunRequest,
)
from substrate.multimedia.local_source_card import (
    LocalSourceCardArtifact,
    LocalSourceCardRequest,
)
from substrate.multimedia.local_tts import LocalTTSArtifact
from substrate.multimedia.local_video_bridge import LocalSourceCardInput
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest
from substrate.multimedia.visual_selection import VerifiedVisualEvidence

NOW = datetime(2026, 7, 13, tzinfo=UTC)
FFMPEG = Path("/opt/homebrew/bin/ffmpeg")
FFPROBE = Path("/opt/homebrew/bin/ffprobe")
pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin" or not FFMPEG.exists() or not FFPROBE.exists(),
    reason="requires configured local FFmpeg executables",
)


def _plan() -> MultimediaPlan:
    return MultimediaPlan(
        request=MultimediaPlanRequest(
            topic="Aircraft production", target_minutes=15, route_policy="cheapest"
        ),
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


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24_000)
        output.writeframes(b"\x00\x00" * 24_000)
    path.chmod(0o600)


class Store:
    def __init__(self, plan: MultimediaPlan) -> None:
        self.record = SimpleNamespace(
            asset=SimpleNamespace(
                asset_id="asset-1", revision_id="revision-1", status="ready",
                route_policy="cheapest", kind="documentary_video",
                owner_user_id="a" * 64,
            ),
            plan=plan,
            mode="hybrid",
            production_link=None,
        )

    def get(self, asset_id: str, *, owner_id: str):  # noqa: ANN201
        if asset_id != "asset-1" or owner_id != "owner-1":
            raise KeyError(asset_id)
        return self.record

    def attach_production_link(
        self, asset_id, link, *, expected_revision_id, owner_id  # noqa: ANN001
    ):  # noqa: ANN201
        if (
            asset_id != self.record.asset.asset_id
            or expected_revision_id != self.record.asset.revision_id
            or owner_id != "owner-1"
        ):
            raise ValueError("production identity conflicts")
        if self.record.production_link is not None and self.record.production_link != link:
            raise ValueError("production link conflicts")
        self.record.production_link = link
        return self.record


class Resolver:
    def __init__(self, request, path: Path) -> None:  # noqa: ANN001
        self.request = request
        self.path = path
        self.calls = 0

    def reopen(self, request):  # noqa: ANN001, ANN201
        self.calls += 1
        if request != self.request:
            raise RuntimeError("request drift")
        return LocalTTSArtifact(
            request_id="mmlocaltts_" + "1" * 64,
            request_body_digest=request.body_digest,
            config_digest="c" * 64,
            output_path=str(self.path),
            output_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
            duration_seconds=1.0,
            sample_rate_hz=24_000,
            channels=1,
            synthesizer_digest="s" * 64,
            probe_digest="p" * 64,
            created_at="2026-07-13T00:00:00Z",
        )


@pytest.fixture
def runtime(tmp_path: Path):  # noqa: ANN201
    plan = _plan()
    request = prepare_chapter_tts_request(
        plan, asset_id="asset-1", revision_id="revision-1",
        provider="local_executable_tts", model="macos-say-v1",
        voice="narrator", chapter_id="chapter-1",
    )
    source = tmp_path / "chapter.wav"
    _wav(source)
    output = tmp_path / "narration"
    output.mkdir(mode=0o700)
    store = Store(plan)
    resolver = Resolver(request, source)
    coordinator = LocalProductionCoordinator(
        db_path=str(tmp_path / "runs.duckdb"),
        signing_key=b"coordinator-signing-key-material-32",
        narration_integrity_key=b"narration-integrity-key-material-32",
        narration_output_dir=str(output),
        store=store,  # type: ignore[arg-type]
        tts_resolver=resolver,
    )
    run_request = LocalNarrationRunRequest(
        owner_id="owner-1", asset_id="asset-1", expected_revision_id="revision-1",
        chapter_requests=(request,),
    )
    return coordinator, run_request, store, resolver, tmp_path


def test_produces_private_canonical_narration_and_exactly_replays(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, request, _store, _resolver, _tmp = runtime
    first = coordinator.produce_narration(request, now=NOW)

    def no_second_production(**_kwargs):  # noqa: ANN003, ANN202
        raise AssertionError("exact replay must not invoke FFmpeg")

    monkeypatch.setattr(coordinator_module, "produce_narration_track", no_second_production)
    replay = coordinator.produce_narration(request, now=NOW)
    assert replay == first and replay.cost_usd == 0.0
    assert replay.narration.manifest.duration_seconds == 1.0
    assert Path(replay.narration.manifest.output_path).stat().st_mode & 0o777 == 0o600


def test_post_render_crash_requires_explicit_adoption(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, request, _store, _resolver, _tmp = runtime
    real_complete = LocalProductionCoordinator._complete

    def interrupted(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("crash after output publication")

    monkeypatch.setattr(LocalProductionCoordinator, "_complete", interrupted)
    with pytest.raises(LocalProductionOutcomeUnknown):
        coordinator.produce_narration(request, now=NOW)
    with pytest.raises(LocalProductionOutcomeUnknown):
        coordinator.produce_narration(request, now=NOW)
    monkeypatch.setattr(LocalProductionCoordinator, "_complete", real_complete)
    recovered = coordinator.recover_narration(request, now=NOW)
    assert recovered.narration.manifest.duration_seconds == 1.0


def test_missing_recovery_output_remains_unknown(runtime) -> None:
    coordinator, request, _store, _resolver, tmp_path = runtime
    inputs, owner_digest = coordinator._inputs(request)  # noqa: SLF001
    run_id = coordinator_module._run_id(  # noqa: SLF001
        owner_digest, inputs.input_digest, coordinator._config_digest  # noqa: SLF001
    )
    timestamp = NOW.isoformat().replace("+00:00", "Z")
    path = tmp_path / "narration" / "asset-1-revision-1-narration" / "narration.json"
    values = [
        run_id, owner_digest, "asset-1", "revision-1", inputs.input_digest,
        coordinator._config_digest, "producing", str(path), "", timestamp, timestamp,  # noqa: SLF001
    ]
    with duckdb.connect(str(tmp_path / "runs.duckdb")) as connection:
        connection.execute(coordinator_module._DDL)  # noqa: SLF001
        connection.execute(
            "INSERT INTO multimedia_local_production_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [*values, coordinator_module._mac(values, coordinator._key)],  # noqa: SLF001
        )
    with pytest.raises(LocalProductionOutcomeUnknown, match="unavailable"):
        coordinator.recover_narration(request, now=NOW)


def test_stale_revision_and_database_tamper_fail_closed(runtime) -> None:
    coordinator, request, store, _resolver, tmp_path = runtime
    artifact = coordinator.produce_narration(request, now=NOW)
    store.record.asset.revision_id = "revision-2"
    with pytest.raises(LocalProductionCoordinatorError, match="current ready"):
        coordinator.produce_narration(request, now=NOW)
    store.record.asset.revision_id = "revision-1"
    with duckdb.connect(str(tmp_path / "runs.duckdb")) as connection:
        connection.execute(
            "UPDATE multimedia_local_production_runs SET narration_manifest_sha256=?",
            ["0" * 64],
        )
    with pytest.raises(LocalProductionCoordinatorError, match="integrity"):
        coordinator.produce_narration(request, now=NOW)
    assert Path(artifact.narration.manifest.output_path).exists()


class CardResolver:
    def __init__(self, artifact: LocalSourceCardArtifact) -> None:
        self.artifact = artifact

    def reopen(self, card_id, request, *, owner_id):  # noqa: ANN001, ANN201
        if card_id != self.artifact.card_id or owner_id != "owner-1":
            raise RuntimeError("card unavailable")
        return self.artifact


def _video_runtime(runtime):  # noqa: ANN201
    narration, narration_request, store, _resolver, tmp_path = runtime
    card_path = tmp_path / "card.png"
    card_image = Image.new("RGB", (1280, 720), "white")
    card_draw = ImageDraw.Draw(card_image)
    card_draw.rectangle((0, 0, 1280, 96), fill="#18232f")
    card_draw.rectangle((0, 0, 18, 720), fill="#f2c94c")
    card_draw.text((56, 34), "ANTIEK LOCAL SOURCE CARD", fill="white")
    card_draw.text((96, 250), "AIRCRAFT FACTORY FLOW", fill="#18232f")
    card_draw.text((96, 320), "Factories coordinate work through staged flow.", fill="#35495e")
    card_image.save(card_path, format="PNG")
    card_path.chmod(0o600)
    card_request = LocalSourceCardRequest(
        asset_id="asset-1", revision_id="revision-1", chapter_id="chapter-1",
        scene_id="scene-chapter-1", title="Flow", information_purpose="Explain flow",
        source_chunk_ids=("chunk-1",),
    )
    card = LocalSourceCardArtifact(
        card_id="card-1", asset_id="asset-1", revision_id="revision-1",
        chapter_id="chapter-1", scene_id="scene-chapter-1",
        source_chunk_ids=("chunk-1",), output_path=str(card_path),
        output_sha256=hashlib.sha256(card_path.read_bytes()).hexdigest(),
        input_digest="6" * 64, snapshot_digest="7" * 64,
        renderer_version="renderer", font_digest="8" * 64,
        width_px=1280, height_px=720, created_at="2026-07-13T00:00:00Z",
    )
    evidence_key = b"video-evidence-authority-key-32bytes"

    def verify(selection, digest):  # noqa: ANN001, ANN202
        return VerifiedVisualEvidence.issue(
            scene_id=selection.scene_id, visual_label="diagram", content_sha256=digest,
            evidence_digest="9" * 64, authority_key=evidence_key,
        )

    roots = []
    for name in ("visuals", "renders", "receipts"):
        root = tmp_path / name
        root.mkdir(mode=0o700)
        roots.append(root)
    video = LocalVideoProductionCoordinator(
        narration_coordinator=narration,
        source_card_resolver=CardResolver(card),
        verify_evidence=verify,
        visual_output_dir=str(roots[0]), render_output_dir=str(roots[1]),
        receipt_output_dir=str(roots[2]),
        visual_integrity_key=b"video-visual-integrity-key-32bytes",
        evidence_authority_key=evidence_key,
        render_integrity_key=b"video-render-integrity-key-32bytes",
        receipt_integrity_key=b"video-receipt-integrity-key-32bytes",
    )
    request = LocalVideoRunRequest(
        narration=narration_request,
        source_cards=(LocalSourceCardInput("card-1", card_request),),
    )
    return video, request, store, tmp_path


def test_renders_receipts_and_exactly_replays_local_video(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, request, _store, _tmp = _video_runtime(runtime)
    first = video.produce(request, now=NOW)
    assert first.cost_usd == 0.0
    assert Path(first.receipt.render.manifest.output_path).read_bytes()[4:8] == b"ftyp"
    assert Path(first.receipt.render.manifest.captions_path).read_text().startswith("WEBVTT")

    def no_second_render(**_kwargs):  # noqa: ANN003, ANN202
        raise AssertionError("exact replay must not render")

    monkeypatch.setattr(coordinator_module, "produce_educational_video", no_second_render)
    assert video.produce(request, now=NOW) == first


def test_render_publication_crash_is_adopted_only_by_recovery(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, request, _store, _tmp = _video_runtime(runtime)
    real_complete = LocalVideoProductionCoordinator._complete_render

    def interrupted(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("crash after render publication")

    monkeypatch.setattr(LocalVideoProductionCoordinator, "_complete_render", interrupted)
    with pytest.raises(LocalProductionOutcomeUnknown):
        video.produce(request, now=NOW)
    with pytest.raises(LocalProductionOutcomeUnknown, match="render outcome"):
        video.produce(request, now=NOW)
    monkeypatch.setattr(LocalVideoProductionCoordinator, "_complete_render", real_complete)
    recovered = video.recover(request, now=NOW)
    assert Path(recovered.receipt.render.manifest.output_path).is_file()


def test_receipt_publication_crash_remains_unknown_until_recovery(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, request, _store, _tmp = _video_runtime(runtime)
    real_issue = coordinator_module.issue_educational_video_receipt

    def interrupted(**kwargs):  # noqa: ANN003, ANN202
        real_issue(**kwargs)
        raise RuntimeError("crash after receipt publication")

    monkeypatch.setattr(coordinator_module, "issue_educational_video_receipt", interrupted)
    with pytest.raises(LocalProductionOutcomeUnknown, match="receipt output"):
        video.produce(request, now=NOW)
    with pytest.raises(LocalProductionOutcomeUnknown, match="receipt outcome"):
        video.produce(request, now=NOW)
    monkeypatch.setattr(coordinator_module, "issue_educational_video_receipt", real_issue)
    recovered = video.recover(request, now=NOW)
    assert recovered.receipt.asset_id == "asset-1"


def test_video_row_tamper_fails_closed(runtime) -> None:
    video, request, _store, tmp_path = _video_runtime(runtime)
    video.produce(request, now=NOW)
    with duckdb.connect(str(tmp_path / "runs.duckdb")) as connection:
        connection.execute(
            "UPDATE multimedia_local_video_runs SET receipt_sha256=?", ["0" * 64]
        )
    with pytest.raises(LocalProductionCoordinatorError, match="integrity"):
        video.produce(request, now=NOW)


def test_rendered_media_tamper_fails_receipt_replay(runtime) -> None:
    video, request, _store, _tmp = _video_runtime(runtime)
    artifact = video.produce(request, now=NOW)
    Path(artifact.receipt.render.manifest.output_path).write_bytes(b"tampered")
    Path(artifact.receipt.render.manifest.output_path).chmod(0o600)
    with pytest.raises(RuntimeError, match="digest"):
        video.produce(request, now=NOW)


def test_verified_playback_registers_exact_current_revision_and_replays(runtime) -> None:
    video, request, store, _tmp = _video_runtime(runtime)
    first = video.register(request, now=NOW)
    assert first.registered is True
    assert store.record.production_link is not None
    assert store.record.production_link.receipt_sha256 == hashlib.sha256(
        first.receipt.to_json().encode()
    ).hexdigest()
    assert video.register(request, now=NOW) == first


def test_database_failure_is_not_misreported_as_missing(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinator, _request, _store, _resolver, tmp_path = runtime
    Path(tmp_path / "runs.duckdb").touch(mode=0o600)

    def unavailable(_path):  # noqa: ANN001, ANN202
        raise OSError("disk failure")

    monkeypatch.setattr(coordinator_module, "connect_read", unavailable)
    with pytest.raises(LocalProductionCoordinatorError, match="database"):
        coordinator._load("missing")  # noqa: SLF001
