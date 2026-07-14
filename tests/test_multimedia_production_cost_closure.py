"""MSR-02 production-byte cost authority closure."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from integrations.krea.client import KreaClient
from runtime.db_lock import connect_read, connect_write
from substrate.multimedia.educational_video_production import (
    EducationalVideoProductionArtifact,
)
from substrate.multimedia.educational_video_receipt import issue, receipt_file_path
from substrate.multimedia.execution_authorization import (
    issue_async_execution_authorization,
)
from substrate.multimedia.ken_burns_renderer import (
    KenBurnsRenderArtifact,
    KenBurnsRenderManifest,
    RenderedCaption,
    RenderedInput,
)
from substrate.multimedia.krea_reconcile import observe_provider_job
from substrate.multimedia.narration_production import (
    NarrationChapterBinding,
    NarrationProductionArtifact,
    NarrationProductionManifest,
    NarrationSource,
)
from substrate.multimedia.narration_run import narration_child_revision
from substrate.multimedia.production_cost_closure import (
    ProductionByteConstituentV1,
    build_production_byte_cost_closure,
    verify_production_byte_projection,
)
from substrate.multimedia.provider_execution import (
    ProviderExecutionRecord,
    begin_reserved_provider_submission,
    bind_provider_job,
    provider_execution_record_from_row,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaProductionLink,
)
from substrate.multimedia.reviewed_visual_registry import (
    ReviewedVisualRegistry,
    ReviewedVisualRegistryError,
)
from substrate.multimedia.ship_cost_snapshot import (
    MultimediaShipCostEvidenceConflict,
    MultimediaShipCostEvidenceUnavailable,
)
from substrate.multimedia.verified_playback import VerifiedPlaybackRuntime
from substrate.multimedia.visual_selection import (
    PacketVisual,
    ReviewedVisualSelection,
    VisualSelectionPacket,
)

_RECEIPT_KEY = b"receipt-key-production-closure-0001"
_NARRATION_KEY = b"narration-key-production-closure-01"
_VISUAL_KEY = b"visual-key-production-closure-00001"
_RENDER_KEY = b"render-key-production-closure-00001"
_SIGNING_KEY = b"provider-key-production-closure-0001"
_SNAPSHOT_KEY = b"snapshot-key-production-closure-0001"
_REGISTRY_KEY = b"registry-key-production-closure-0001"
_NOW = datetime(2026, 7, 14, 6, 0, tzinfo=UTC)
_OWNER = "alice"


class _CompletedKrea(KreaClient):
    def __init__(self, job_id: str) -> None:
        super().__init__("account:secret")
        self._job_id = job_id

    def _request(self, method: str, path: str) -> bytes:
        return json.dumps(
            {
                "job_id": self._job_id,
                "status": "completed",
                "created_at": "2026-07-14T06:00:00Z",
                "completed_at": "2026-07-14T06:00:02Z",
                "result": {"urls": ["https://cdn.example/result.png"]},
            }
        ).encode()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wav(path: Path, sample: int) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(sample.to_bytes(2, "little", signed=True) * 8_000)
    path.chmod(0o600)


def _png(path: Path, suffix: int) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([suffix]) * 64)
    path.chmod(0o600)


def _artifact_mac(model: object, key: bytes, *, field: str) -> str:
    value = getattr(model, field)
    payload = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _owner_digest(owner_id: str = _OWNER) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


class Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.db_path = tmp_path / "accounting.duckdb"
        self.asset_store = MultimediaAssetStore(tmp_path / "assets")
        draft = self.asset_store.create_draft(
            CreateMultimediaDraftRequest(topic="Aircraft", target_minutes=15, mode="video"),
            owner_id=_OWNER,
        )
        record = self.asset_store.approve_dry_run(draft.asset.asset_id, owner_id=_OWNER)
        self.asset_id = record.asset.asset_id
        self.revision_id = record.asset.revision_id
        self.chapter_ids = ("chapter-0", "chapter-1")
        self.labels = ("generated", "sourced")
        self.receipt = self._receipt()
        self.receipt_digest = hashlib.sha256(self.receipt.to_json().encode()).hexdigest()
        render = self.receipt.render.manifest
        narration = self.receipt.narration.manifest
        self.link = MultimediaProductionLink(
            owner_identity_digest=_owner_digest(),
            asset_id=self.asset_id,
            revision_id=self.revision_id,
            receipt_sha256=self.receipt_digest,
            video_sha256=render.output_sha256,
            audio_sha256=narration.output_sha256,
            duration_seconds=render.duration_seconds,
            width_px=render.width_px,
            height_px=render.height_px,
            chapter_ids=render.chapter_ids,
        )
        self.asset_store.attach_production_link(
            self.asset_id,
            self.link,
            expected_revision_id=self.revision_id,
            owner_id=_OWNER,
        )
        self.playback = VerifiedPlaybackRuntime(
            str(tmp_path / "receipts"),
            _RECEIPT_KEY,
            _NARRATION_KEY,
            _VISUAL_KEY,
            _RENDER_KEY,
        )

    def _receipt(self) -> object:
        sources: list[NarrationSource] = []
        bindings: list[NarrationChapterBinding] = []
        visuals: list[PacketVisual] = []
        rendered_inputs: list[RenderedInput] = []
        for sequence, (chapter_id, label) in enumerate(
            zip(self.chapter_ids, self.labels, strict=True)
        ):
            audio = self.root / f"source-{sequence}.wav"
            still = self.root / f"still-{sequence}.png"
            _wav(audio, 100 + sequence)
            _png(still, 10 + sequence)
            sources.append(
                NarrationSource(
                    sequence=sequence,
                    chapter_id=chapter_id,
                    audio_file_id=f"audio-{sequence}",
                    path=str(audio),
                    sha256=_digest(audio),
                    duration_seconds=1.0,
                )
            )
            bindings.append(
                NarrationChapterBinding(
                    chapter_id=chapter_id,
                    script_line_ids=(f"{chapter_id}-line-0",),
                    source_chunk_ids=(f"chunk-{sequence}",),
                    paragraph_ids=(f"paragraph-{sequence}",),
                )
            )
            packet = PacketVisual(
                scene_id=f"scene-{sequence}",
                path=str(still),
                sha256=_digest(still),
                visual_label=label,
                source_chunk_ids=(f"chunk-{sequence}",),
                evidence_digest=hashlib.sha256(f"evidence-{sequence}".encode()).hexdigest(),
            )
            visuals.append(packet)
            rendered_inputs.append(
                RenderedInput(
                    scene_id=packet.scene_id,
                    path=packet.path,
                    sha256=packet.sha256,
                    visual_label=packet.visual_label,
                    source_chunk_ids=packet.source_chunk_ids,
                )
            )
        aggregate = self.root / "narration.wav"
        _wav(aggregate, 200)
        narration_manifest = NarrationProductionManifest(
            asset_id=self.asset_id,
            revision_id=self.revision_id,
            output_path=str(aggregate),
            output_sha256=_digest(aggregate),
            duration_seconds=2.0,
            sample_rate_hz=8_000,
            channels=1,
            sources=tuple(sources),
            chapter_bindings=tuple(bindings),
        )
        narration = NarrationProductionArtifact(
            manifest=narration_manifest,
            manifest_mac=_artifact_mac(
                type("Holder", (), {"manifest": narration_manifest})(),
                _NARRATION_KEY,
                field="manifest",
            ),
        )
        timeline_digest = hashlib.sha256(b"timeline").hexdigest()
        visual_unsigned = {
            "schema_version": "antiek.documentary-visual-packet.v1",
            "asset_id": self.asset_id,
            "revision_id": self.revision_id,
            "timeline_sha256": timeline_digest,
            "visuals": [row.model_dump(mode="json") for row in visuals],
        }
        visual = VisualSelectionPacket(
            **visual_unsigned,
            packet_digest=hmac.new(
                _VISUAL_KEY,
                json.dumps(visual_unsigned, sort_keys=True, separators=(",", ":")).encode(),
                hashlib.sha256,
            ).hexdigest(),
        )
        video = self.root / "documentary.mp4"
        captions = self.root / "captions.vtt"
        video.write_bytes(b"video" + os.urandom(64))
        captions.write_text("WEBVTT\n")
        video.chmod(0o600)
        captions.chmod(0o600)
        render_manifest = KenBurnsRenderManifest(
            asset_id=self.asset_id,
            revision_id=self.revision_id,
            output_path=str(video),
            output_sha256=_digest(video),
            captions_path=str(captions),
            captions_sha256=_digest(captions),
            narration_path=str(aggregate),
            narration_sha256=_digest(aggregate),
            timeline_sha256=timeline_digest,
            width_px=1280,
            height_px=720,
            fps=30,
            duration_seconds=2.0,
            video_codec="h264",
            audio_codec="aac",
            subtitle_codec="mov_text",
            scene_ids=("scene-0", "scene-1"),
            chapter_ids=self.chapter_ids,
            motions=("hold", "hold"),
            visual_labels=self.labels,
            inputs=tuple(rendered_inputs),
            captions=tuple(
                RenderedCaption(
                    cue_id=f"cue-{sequence:04d}",
                    scene_id=f"scene-{sequence}",
                    chapter_id=chapter_id,
                    start_seconds=float(sequence),
                    end_seconds=float(sequence + 1),
                    text=f"Caption {sequence}",
                    source_chunk_ids=(f"chunk-{sequence}",),
                )
                for sequence, chapter_id in enumerate(self.chapter_ids)
            ),
        )
        render = KenBurnsRenderArtifact(
            manifest=render_manifest,
            manifest_sha256=_artifact_mac(
                type("Holder", (), {"manifest": render_manifest})(),
                _RENDER_KEY,
                field="manifest",
            ),
        )
        documentary = type(
            "Documentary", (), {"visual_packet": visual, "render_artifact": render}
        )()
        artifact = EducationalVideoProductionArtifact(narration, documentary)
        receipt_root = self.root / "receipts"
        receipt_root.mkdir(mode=0o700)
        return issue(
            artifact=artifact,
            receipt_key=_RECEIPT_KEY,
            narration_key=_NARRATION_KEY,
            visual_key=_VISUAL_KEY,
            render_key=_RENDER_KEY,
            output_dir=str(receipt_root),
        )

    def settle(
        self,
        *,
        revision_id: str,
        capability: str,
        suffix: str,
        complete: bool = True,
    ) -> str:
        authorization = issue_async_execution_authorization(
            signing_key=_SIGNING_KEY,
            request_id=f"request-{suffix}",
            operator_id=_OWNER,
            asset_id=self.asset_id,
            revision_id=revision_id,
            provider="krea",
            route_policy="balanced",
            model="model",
            endpoint_capability=capability,
            catalog_version="v1",
            catalog_digest=hashlib.sha256(b"catalog").hexdigest(),
            quote_id=f"quote-{suffix}",
            quote_expires_at=_NOW + timedelta(minutes=5),
            recovery_authority_id="recovery",
            recovery_verification_key_digest=hashlib.sha256(b"recovery").hexdigest(),
            approved_ceiling_microdollars=250_001,
            request_body_digest=hashlib.sha256(suffix.encode()).hexdigest(),
            issued_at=_NOW,
            expires_at=_NOW + timedelta(minutes=10),
        )
        execution, _ = begin_reserved_provider_submission(
            db_path=str(self.db_path),
            authorization=authorization,
            signing_key=_SIGNING_KEY,
            now=_NOW,
        )
        if complete:
            job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, suffix))
            bind_provider_job(
                db_path=str(self.db_path),
                execution_id=execution.execution_id,
                provider_job_id=job_id,
                signing_key=_SIGNING_KEY,
                now=_NOW + timedelta(seconds=1),
            )
            observe_provider_job(
                db_path=str(self.db_path),
                execution_id=execution.execution_id,
                client=_CompletedKrea(job_id),
                signing_key=_SIGNING_KEY,
                observed_at=_NOW + timedelta(seconds=2),
            )
        return execution.execution_id

    def narration_executions(self) -> tuple[str, ...]:
        return tuple(
            self.settle(
                revision_id=narration_child_revision(self.revision_id, chapter_id, sequence),
                capability="text-to-speech",
                suffix=f"tts-{sequence}",
            )
            for sequence, chapter_id in enumerate(self.chapter_ids)
        )

    def registry(
        self, visual_execution_id: str, *, first_scene: str = "scene-0"
    ) -> ReviewedVisualRegistry:
        registry = ReviewedVisualRegistry(
            db_path=str(self.root / "reviewed.duckdb"), integrity_key=_REGISTRY_KEY
        )
        generated, sourced = self.receipt.visual.visuals
        selections = (
            ReviewedVisualSelection(
                scene_id=first_scene,
                path=generated.path,
                expected_sha256=generated.sha256,
                visual_label="generated",
                source_chunk_ids=generated.source_chunk_ids,
                execution_receipt_id=visual_execution_id,
                artifact_receipt_id="artifact-0",
            ),
            ReviewedVisualSelection(
                scene_id=sourced.scene_id,
                path=sourced.path,
                expected_sha256=sourced.sha256,
                visual_label="sourced",
                source_chunk_ids=sourced.source_chunk_ids,
                source_locator_digest=hashlib.sha256(b"locator").hexdigest(),
                rights_basis="licensed",
                rights_review_id="rights-1",
            ),
        )
        registry.register(
            owner_identity_digest=_owner_digest(),
            asset_id=self.asset_id,
            revision_id=self.revision_id,
            request_id="review-1",
            candidate_ids=("candidate-0", "candidate-1"),
            selections=selections,
            now=_NOW,
        )
        return registry

    def record(self, execution_id: str) -> ProviderExecutionRecord:
        with connect_read(str(self.db_path)) as connection:
            row = connection.execute(
                "SELECT * FROM multimedia_provider_executions WHERE execution_id=?",
                [execution_id],
            ).fetchone()
        assert row is not None
        return provider_execution_record_from_row(tuple(row), signing_key=_SIGNING_KEY)

    def seal_run(
        self,
        execution_ids: tuple[str, ...],
        *,
        status: str = "sealed",
        artifact_json: str | None = None,
        set_digest: str | None = None,
    ) -> str:
        records = tuple(self.record(execution_id) for execution_id in execution_ids)
        set_rows = [
            [
                sequence,
                chapter_id,
                record.revision_id,
                record.request_body_digest,
                record.authorization_id,
                record.approved_ceiling_microdollars,
            ]
            for sequence, (chapter_id, record) in enumerate(
                zip(self.chapter_ids, records, strict=True)
            )
        ]
        digest = (
            set_digest
            or hashlib.sha256(json.dumps(set_rows, separators=(",", ":")).encode()).hexdigest()
        )
        run_id = (
            "mmnrun_"
            + hashlib.sha256(
                json.dumps(
                    [self.asset_id, self.revision_id, digest],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        bindings = json.dumps(
            [
                [
                    row.chapter_id,
                    list(row.script_line_ids),
                    list(row.source_chunk_ids),
                    list(row.paragraph_ids),
                ]
                for row in self.receipt.narration.manifest.chapter_bindings
            ],
            separators=(",", ":"),
        )
        values: list[object] = [
            run_id,
            self.asset_id,
            self.revision_id,
            digest,
            bindings,
            status,
            artifact_json or self.receipt.narration.to_json(),
        ]
        run_mac = hmac.new(
            _SIGNING_KEY,
            json.dumps(values, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        with connect_write(str(self.db_path), purpose="test.seal_narration") as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS multimedia_narration_runs ("
                "run_id TEXT PRIMARY KEY,asset_id TEXT NOT NULL,revision_id TEXT NOT NULL,"
                "authorization_set_digest TEXT NOT NULL,chapter_bindings_json TEXT NOT NULL,"
                "status TEXT NOT NULL,artifact_json TEXT,run_mac TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO multimedia_narration_runs VALUES (?,?,?,?,?,?,?,?)",
                [*values, run_mac],
            )
        return run_id

    def build(self, registry: ReviewedVisualRegistry, *, now: datetime | None = None) -> object:
        return build_production_byte_cost_closure(
            asset_id=self.asset_id,
            owner_id=_OWNER,
            db_path=str(self.db_path),
            store=self.asset_store,
            playback=self.playback,
            registry=registry,
            signing_key=_SIGNING_KEY,
            snapshot_key=_SNAPSHOT_KEY,
            narration_key=_NARRATION_KEY,
            now=now or _NOW + timedelta(seconds=3),
        )


def _ready(fixture: Fixture) -> tuple[ReviewedVisualRegistry, tuple[str, ...]]:
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    narration = fixture.narration_executions()
    fixture.seal_run(narration)
    return fixture.registry(visual), narration


def test_builds_mixed_visual_and_narration_closure(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    registry, narration_ids = _ready(fixture)
    closure = fixture.build(registry)
    projection = closure.production_byte_projection
    assert projection.basis == "production_byte_contributing_settled_provider_executions"
    assert projection.charged_cents == 78
    assert closure.narration_execution_ids == narration_ids
    assert {(row.role, row.scene_id, row.chapter_id) for row in projection.constituents} == {
        ("visual", "scene-0", None),
        ("narration", None, "chapter-0"),
        ("narration", None, "chapter-1"),
    }
    assert {
        row.execution_revision for row in projection.constituents if row.role == "narration"
    } == set(
        narration_child_revision(fixture.revision_id, chapter_id, sequence)
        for sequence, chapter_id in enumerate(fixture.chapter_ids)
    )
    verify_production_byte_projection(
        projection,
        snapshot_key=_SNAPSHOT_KEY,
        owner_id=_OWNER,
        asset_id=fixture.asset_id,
        revision_id=fixture.revision_id,
    )


def test_missing_production_link_is_unavailable(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    record = fixture.asset_store.get(fixture.asset_id, owner_id=_OWNER)
    fixture.asset_store._save_unlocked(  # type: ignore[attr-defined]
        record.model_copy(update={"production_link": None}), _owner_digest()
    )
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "empty.duckdb"), integrity_key=_REGISTRY_KEY
    )
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        fixture.build(registry)


def test_stale_link_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    from substrate.multimedia.read_model import _AccountAssetEnvelope

    path = fixture.asset_store._path(_owner_digest(), fixture.asset_id)
    envelope = _AccountAssetEnvelope.model_validate_json(path.read_bytes())
    bad = envelope.record.model_copy(
        update={"production_link": fixture.link.model_copy(update={"video_sha256": "f" * 64})}
    )
    path.write_text(
        _AccountAssetEnvelope(
            schema_version="antiek.multimedia-account-asset.v1",
            owner_identity_digest=_owner_digest(),
            record=bad,
        ).model_dump_json()
    )
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(
            ReviewedVisualRegistry(
                db_path=str(tmp_path / "empty.duckdb"), integrity_key=_REGISTRY_KEY
            )
        )


def test_changed_receipt_bytes_are_unavailable(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    receipt_path = Path(
        receipt_file_path(
            str(tmp_path / "receipts"), fixture.asset_id, fixture.revision_id
        )
    )
    receipt_path.write_text("{}")
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        fixture.build(
            ReviewedVisualRegistry(
                db_path=str(tmp_path / "empty.duckdb"), integrity_key=_REGISTRY_KEY
            )
        )


def test_visual_scene_mismatch_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(fixture.registry(visual, first_scene="scene-wrong"))


def test_reviewed_visual_identity_conflict_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path)
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "reviewed.duckdb"), integrity_key=_REGISTRY_KEY
    )

    def conflict(**_: str) -> object:
        raise ReviewedVisualRegistryError("stored reviewed visual identity conflicts")

    monkeypatch.setattr(registry, "get_existing", conflict)
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(registry)


def test_missing_sealed_run_is_unavailable(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    fixture.narration_executions()
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        fixture.build(fixture.registry(visual))


def test_missing_registry_does_not_create_database(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    missing = tmp_path / "missing-reviewed.duckdb"
    registry = ReviewedVisualRegistry(
        db_path=str(missing), integrity_key=_REGISTRY_KEY
    )
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        fixture.build(registry)
    assert not missing.exists()


def test_multiple_matching_runs_are_unavailable(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    narration = fixture.narration_executions()
    fixture.seal_run(narration)
    fixture.seal_run(narration, set_digest="a" * 64)
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        fixture.build(fixture.registry(visual))


def test_corrupt_run_mac_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    narration = fixture.narration_executions()
    run_id = fixture.seal_run(narration)
    with connect_write(str(fixture.db_path), purpose="test.corrupt_run") as connection:
        connection.execute(
            "UPDATE multimedia_narration_runs SET run_mac=? WHERE run_id=?",
            ["0" * 64, run_id],
        )
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(fixture.registry(visual))


def test_narration_authorization_set_mismatch_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    narration = fixture.narration_executions()
    fixture.seal_run(narration, set_digest="b" * 64)
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(fixture.registry(visual))


def test_multiple_child_executions_are_unavailable(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    narration = fixture.narration_executions()
    fixture.seal_run(narration)
    fixture.settle(
        revision_id=narration_child_revision(fixture.revision_id, fixture.chapter_ids[0], 0),
        capability="text-to-speech",
        suffix="duplicate-child",
    )
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        fixture.build(fixture.registry(visual))


def test_unsettled_selected_visual_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(
        revision_id=fixture.revision_id,
        capability="image",
        suffix="unsettled",
        complete=False,
    )
    narration = fixture.narration_executions()
    fixture.seal_run(narration)
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(fixture.registry(visual))


def test_unsettled_narration_child_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(revision_id=fixture.revision_id, capability="image", suffix="visual")
    narration = (
        fixture.settle(
            revision_id=narration_child_revision(
                fixture.revision_id, fixture.chapter_ids[0], 0
            ),
            capability="text-to-speech",
            suffix="tts-unsettled",
            complete=False,
        ),
        fixture.settle(
            revision_id=narration_child_revision(
                fixture.revision_id, fixture.chapter_ids[1], 1
            ),
            capability="text-to-speech",
            suffix="tts-settled",
        ),
    )
    fixture.seal_run(narration)
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(fixture.registry(visual))


def test_visual_capability_mismatch_is_conflict(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    visual = fixture.settle(
        revision_id=fixture.revision_id,
        capability="text-to-speech",
        suffix="visual-wrong-capability",
    )
    narration = fixture.narration_executions()
    fixture.seal_run(narration)
    with pytest.raises(MultimediaShipCostEvidenceConflict):
        fixture.build(fixture.registry(visual))


def test_projection_tamper_and_duplicate_fail_verification(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    registry, _ = _ready(fixture)
    projection = fixture.build(registry).production_byte_projection
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        verify_production_byte_projection(
            projection.model_copy(update={"charged_cents": 1}),
            snapshot_key=_SNAPSHOT_KEY,
            owner_id=_OWNER,
            asset_id=fixture.asset_id,
            revision_id=fixture.revision_id,
        )
    duplicate = projection.model_copy(update={"constituents": (projection.constituents[0],) * 2})
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        verify_production_byte_projection(
            duplicate,
            snapshot_key=_SNAPSHOT_KEY,
            owner_id=_OWNER,
            asset_id=fixture.asset_id,
            revision_id=fixture.revision_id,
        )


@pytest.mark.parametrize(
    ("owner_id", "asset_id", "revision_id"),
    [
        ("other-owner", None, None),
        (None, "other-asset", None),
        (None, None, "other-revision"),
    ],
)
def test_projection_verification_rejects_wrong_identity(
    tmp_path: Path,
    owner_id: str | None,
    asset_id: str | None,
    revision_id: str | None,
) -> None:
    fixture = Fixture(tmp_path)
    registry, _ = _ready(fixture)
    projection = fixture.build(registry).production_byte_projection
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        verify_production_byte_projection(
            projection,
            snapshot_key=_SNAPSHOT_KEY,
            owner_id=owner_id or _OWNER,
            asset_id=asset_id or fixture.asset_id,
            revision_id=revision_id or fixture.revision_id,
        )


def test_projection_verification_rejects_wrong_key(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    registry, _ = _ready(fixture)
    projection = fixture.build(registry).production_byte_projection
    with pytest.raises(MultimediaShipCostEvidenceUnavailable):
        verify_production_byte_projection(
            projection,
            snapshot_key=b"wrong-snapshot-key-production-0001",
            owner_id=_OWNER,
            asset_id=fixture.asset_id,
            revision_id=fixture.revision_id,
        )


def test_projection_role_identity_is_structural() -> None:
    with pytest.raises(ValueError):
        ProductionByteConstituentV1(
            role="visual",
            chapter_id="chapter-0",
            execution_revision="revision",
            execution_id="execution",
            authorization_id="authorization",
            provider="provider",
            model="model",
            capability="image",
            charged_cents=1,
            settled_at="2026-07-14T06:00:02Z",
        )


@pytest.mark.parametrize("snapshot_key", [_SIGNING_KEY, _NARRATION_KEY])
def test_projection_key_must_be_independent(
    tmp_path: Path, snapshot_key: bytes
) -> None:
    fixture = Fixture(tmp_path)
    with pytest.raises(ValueError, match="independent"):
        build_production_byte_cost_closure(
            asset_id=fixture.asset_id,
            owner_id=_OWNER,
            db_path=str(fixture.db_path),
            store=fixture.asset_store,
            playback=fixture.playback,
            registry=ReviewedVisualRegistry(
                db_path=str(tmp_path / "empty.duckdb"), integrity_key=_REGISTRY_KEY
            ),
            signing_key=_SIGNING_KEY,
            snapshot_key=snapshot_key,
            narration_key=_NARRATION_KEY,
            now=_NOW,
        )
