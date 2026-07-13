from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from PIL import Image

from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.local_production_coordinator import LocalProductionOutcomeUnknown
from substrate.multimedia.local_source_card import (
    LocalSourceCardArtifact,
    LocalSourceCardRequest,
)
from substrate.multimedia.local_tts import (
    LocalTTSArtifact,
    LocalTTSError,
    LocalTTSOutcomeUnknown,
)
from substrate.multimedia.local_workstation import (
    LocalWorkstationError,
    LocalWorkstationRuntime,
)
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest
from substrate.multimedia.visual_selection import VerifiedVisualEvidence

NOW = datetime(2026, 7, 13, tzinfo=UTC)
SIGNING_KEY = b"local-workstation-signing-key-32bytes"
OPERATOR_KEY = bytes(range(32))
EVIDENCE_KEY = b"local-workstation-evidence-key-32bytes"


def _plan() -> MultimediaPlan:
    return MultimediaPlan(
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


class Store:
    def __init__(self) -> None:
        self.record = SimpleNamespace(
            asset=SimpleNamespace(
                asset_id="asset-1", revision_id="revision-1", status="ready",
                route_policy="cheapest", kind="documentary_video",
                owner_user_id="a" * 64,
            ),
            plan=_plan(), mode="hybrid",
        )

    def get(self, asset_id: str, *, owner_id: str):  # noqa: ANN201
        if asset_id != "asset-1" or owner_id != "owner-1":
            raise KeyError(asset_id)
        return self.record


class TTS:
    def __init__(self) -> None:
        self.rows: dict[str, LocalTTSArtifact] = {}
        self.unknown_once = False
        self.synthesis_calls = 0
        self.recovery_fails = False

    def _artifact(self, request) -> LocalTTSArtifact:  # noqa: ANN001
        return LocalTTSArtifact(
            request_id="mmlocaltts_" + hashlib.sha256(request.body_json.encode()).hexdigest(),
            request_body_digest=request.body_digest, config_digest="c" * 64,
            output_path="/private/chapter.wav", output_sha256="1" * 64,
            duration_seconds=1.0, sample_rate_hz=24_000, channels=1,
            synthesizer_digest="2" * 64, probe_digest="3" * 64,
            created_at="2026-07-13T00:00:00Z",
        )

    def synthesize(self, request, *, now):  # noqa: ANN001, ANN201
        self.synthesis_calls += 1
        if self.unknown_once:
            self.unknown_once = False
            self.rows[request.body_digest] = self._artifact(request)
            raise LocalTTSOutcomeUnknown("unknown")
        return self.rows.setdefault(request.body_digest, self._artifact(request))

    def recover(self, request):  # noqa: ANN001, ANN201
        if self.recovery_fails:
            raise LocalTTSError("pending output unavailable")
        return self.rows[request.body_digest]

    def reopen(self, request):  # noqa: ANN001, ANN201
        try:
            return self.rows[request.body_digest]
        except KeyError:
            raise LocalTTSError("unavailable") from None


class Cards:
    def __init__(self, root: Path) -> None:
        self.rows: dict[str, LocalSourceCardArtifact] = {}
        self.attested: set[str] = set()
        self.root = root

    def create(self, request: LocalSourceCardRequest, *, owner_id: str, now: datetime):  # noqa: ANN201
        card_id = "card-" + request.chapter_id
        output_path = self.root / f"{card_id}.png"
        Image.new("RGB", (1280, 720), "white").save(output_path, format="PNG")
        output_path.chmod(0o600)
        artifact = LocalSourceCardArtifact(
            card_id=card_id, asset_id=request.asset_id, revision_id=request.revision_id,
            chapter_id=request.chapter_id, scene_id=request.scene_id,
            source_chunk_ids=request.source_chunk_ids, output_path=str(output_path),
            output_sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(), input_digest="5" * 64,
            snapshot_digest="6" * 64, renderer_version="renderer",
            font_digest="7" * 64, width_px=1280, height_px=720,
            created_at="2026-07-13T00:00:00Z",
        )
        self.rows[card_id] = artifact
        return artifact

    def reopen(self, card_id, request, *, owner_id):  # noqa: ANN001, ANN201
        artifact = self.rows[card_id]
        if artifact.scene_id != request.scene_id or owner_id != "owner-1":
            raise RuntimeError("foreign")
        return artifact

    def attest(self, card_id, request, **kwargs):  # noqa: ANN001, ANN003, ANN201
        self.reopen(card_id, request, owner_id=kwargs["owner_id"])
        self.attested.add(card_id)
        return SimpleNamespace(attestation_id="attestation-1")


class Video:
    def __init__(self) -> None:
        self.unknown_once = False
        self.register_calls = 0

    def register(self, request, *, now):  # noqa: ANN001, ANN201
        self.register_calls += 1
        if self.unknown_once:
            self.unknown_once = False
            raise LocalProductionOutcomeUnknown("unknown")
        return SimpleNamespace(registered=True)

    def recover(self, request, *, now):  # noqa: ANN001, ANN201
        return SimpleNamespace(registered=False)


@pytest.fixture
def runtime(tmp_path: Path):  # noqa: ANN201
    tts, cards, video, store = TTS(), Cards(tmp_path), Video(), Store()

    def verify(selection, digest):  # noqa: ANN001, ANN202
        if "card-chapter-1" not in cards.attested:
            raise RuntimeError("attestation unavailable")
        return VerifiedVisualEvidence.issue(
            scene_id=selection.scene_id, visual_label="diagram", content_sha256=digest,
            evidence_digest="8" * 64, authority_key=EVIDENCE_KEY,
        )

    result = LocalWorkstationRuntime(
        db_path=str(tmp_path / "local.duckdb"), signing_key=SIGNING_KEY,
        operator_signing_key=OPERATOR_KEY, store=store, tts=tts, cards=cards,
        video=video, verify_evidence=verify, clock=lambda: NOW,
    )
    return result, tts, cards, video, store, tmp_path


def test_prepare_requires_explicit_attestation_then_registers_and_replays(runtime) -> None:
    service, tts, _cards, video, _store, _tmp = runtime
    prepared = service.prepare("asset-1", "revision-1", owner_id="owner-1")
    assert service.prepare("asset-1", "revision-1", owner_id="owner-1") == prepared
    assert tts.synthesis_calls == 1
    assert prepared.status == "review_required" and prepared.cost_usd == 0.0
    assert prepared.chapters[0].narration_ready and prepared.chapters[0].card_ready
    assert prepared.chapters[0].attested is False
    preview = service.preview_card(
        "asset-1", "revision-1", prepared.set_id, prepared.chapters[0].card_id or "",
        owner_id="owner-1",
    )
    assert preview[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(LocalWorkstationError, match="explicit review"):
        service.produce("asset-1", "revision-1", prepared.set_id, owner_id="owner-1")
    reviewed = service.attest(
        "asset-1", "revision-1", prepared.set_id, prepared.chapters[0].card_id or "",
        owner_id="owner-1",
    )
    assert reviewed.status == "ready_to_produce" and reviewed.chapters[0].attested
    complete = service.produce(
        "asset-1", "revision-1", reviewed.set_id, owner_id="owner-1"
    )
    assert complete.status == "registered" and complete.playback_ready
    assert service.inspect(
        "asset-1", "revision-1", complete.set_id, owner_id="owner-1"
    ) == complete
    assert video.register_calls == 1


def test_preparation_unknown_requires_explicit_recovery(runtime) -> None:
    service, tts, _cards, _video, _store, _tmp = runtime
    tts.unknown_once = True
    pending = service.prepare("asset-1", "revision-1", owner_id="owner-1")
    assert pending.status == "preparation_unknown" and pending.recoverable
    assert service.prepare("asset-1", "revision-1", owner_id="owner-1") == pending
    assert tts.synthesis_calls == 1
    recovered = service.recover(
        "asset-1", "revision-1", pending.set_id, owner_id="owner-1"
    )
    assert recovered.status == "review_required" and not recovered.recoverable


def test_failed_preparation_recovery_remains_honestly_recoverable(runtime) -> None:
    service, tts, _cards, _video, _store, _tmp = runtime
    tts.unknown_once = True
    pending = service.prepare("asset-1", "revision-1", owner_id="owner-1")
    tts.unknown_once = True
    tts.recovery_fails = True
    unresolved = service.recover(
        "asset-1", "revision-1", pending.set_id, owner_id="owner-1"
    )
    assert unresolved.status == "preparation_unknown" and unresolved.recoverable


def test_production_unknown_requires_recovery(runtime) -> None:
    service, _tts, _cards, video, _store, _tmp = runtime
    prepared = service.prepare("asset-1", "revision-1", owner_id="owner-1")
    reviewed = service.attest(
        "asset-1", "revision-1", prepared.set_id, prepared.chapters[0].card_id or "",
        owner_id="owner-1",
    )
    video.unknown_once = True
    pending = service.produce(
        "asset-1", "revision-1", reviewed.set_id, owner_id="owner-1"
    )
    assert pending.status == "production_unknown" and pending.recoverable
    complete = service.recover(
        "asset-1", "revision-1", pending.set_id, owner_id="owner-1"
    )
    assert complete.status == "registered"


def test_foreign_stale_and_database_tamper_fail_closed(runtime) -> None:
    service, _tts, _cards, _video, store, tmp_path = runtime
    prepared = service.prepare("asset-1", "revision-1", owner_id="owner-1")
    with pytest.raises(LocalWorkstationError, match="unavailable"):
        service.inspect("asset-1", "revision-1", prepared.set_id, owner_id="owner-2")
    store.record.asset.revision_id = "revision-2"
    with pytest.raises(LocalWorkstationError, match="current ready"):
        service.inspect("asset-1", "revision-1", prepared.set_id, owner_id="owner-1")
    store.record.asset.revision_id = "revision-1"
    with duckdb.connect(str(tmp_path / "local.duckdb")) as connection:
        connection.execute(
            "UPDATE multimedia_local_prepared_sets SET status='registered'"
        )
    with pytest.raises(LocalWorkstationError, match="integrity"):
        service.inspect("asset-1", "revision-1", prepared.set_id, owner_id="owner-1")
