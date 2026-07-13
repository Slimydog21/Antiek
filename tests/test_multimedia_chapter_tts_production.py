from __future__ import annotations

import hashlib
import io
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import substrate.multimedia.chapter_tts_production as chapter_tts_module
from runtime.db_lock import FlockWriteCoordinator
from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import (
    ChapterTTSSynthesisResult,
    PreparedChapterTTSRequest,
    get_chapter_tts_attempt,
    prepare_chapter_tts_request,
    produce_chapter_narration,
    verify_chapter_tts_authorization,
)
from substrate.multimedia.execution_authorization import (
    ExecutionAuthorizationIntegrityError,
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
)
from substrate.multimedia.planner import (
    ChapterPlan,
    MultimediaPlan,
    MultimediaPlanRequest,
)
from substrate.multimedia.provider_execution import ProviderExecutionIntegrityError

KEY = b"chapter-tts-authority-key-32-bytes-long"
NOW = datetime(2026, 7, 11, tzinfo=UTC)
CATALOG_DIGEST = "a" * 64
RECOVERY_DIGEST = "b" * 64


def _plan(*, chapters: int = 1) -> MultimediaPlan:
    chapter_rows = tuple(
        ChapterPlan(
            chapter_id=f"chapter-{index}",
            title=f"Chapter {index}",
            minutes=15 / chapters,
            purpose="Explain grounded evidence",
            arc_id=f"arc-{index}",
            source_chunk_ids=(f"chunk-{index}",),
        )
        for index in range(chapters)
    )
    lines = tuple(
        ScriptLine(
            line_id=f"chapter-{index}-line-0",
            sequence=index,
            text=f"Grounded chapter {index} explains the evidence.",
            kind="narration",
        )
        for index in range(chapters)
    )
    return MultimediaPlan(
        request=MultimediaPlanRequest(topic="Aircraft", target_minutes=15),
        suggestions=(),
        chosen_arc_ids=(),
        chapters=chapter_rows,
        script_lines=lines,
        scenes=(),
        unsourced_line_ids=(),
    )


def _prepared() -> PreparedChapterTTSRequest:
    return prepare_chapter_tts_request(
        _plan(),
        asset_id="asset-747",
        revision_id="revision-1",
        provider="openai",
        model="gpt-4o-mini-tts",
        voice="alloy",
    )


def _authorization(digest: str) -> MultimediaExecutionAuthorizationV2:
    return issue_async_execution_authorization(
        signing_key=KEY,
        request_id="request-1",
        operator_id="operator-1",
        asset_id="asset-747",
        revision_id="revision-1",
        provider="openai",
        route_policy="balanced",
        model="gpt-4o-mini-tts",
        endpoint_capability="text-to-speech",
        catalog_version="catalog-1",
        catalog_digest=CATALOG_DIGEST,
        quote_id="quote-1",
        quote_expires_at=NOW + timedelta(hours=1),
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest=RECOVERY_DIGEST,
        approved_ceiling_microdollars=50_000,
        request_body_digest=digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def test_request_is_canonical_grounded_and_deterministic() -> None:
    first = _prepared()
    second = _prepared()
    assert first.body_json == second.body_json
    assert first.body_digest == second.body_digest
    assert first.text == "Grounded chapter 0 explains the evidence."
    assert first.script_line_ids == ("chapter-0-line-0",)
    assert first.paragraph_ids == ("para-chapter-0-line-0",)
    assert first.source_chunk_ids == ("chunk-0",)
    assert "\\n" not in first.body_json


def test_authorization_is_bound_to_exact_prepared_body() -> None:
    prepared = _prepared()
    verify_chapter_tts_authorization(
        _authorization(prepared.body_digest),
        prepared,
        signing_key=KEY,
        operator_id="operator-1",
        catalog_version="catalog-1",
        catalog_digest=CATALOG_DIGEST,
        quote_id="quote-1",
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest=RECOVERY_DIGEST,
        approved_ceiling_microdollars=50_000,
        now=NOW,
    )


def test_body_or_execution_binding_mismatch_fails_closed() -> None:
    prepared = _prepared()
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="request_body_digest"):
        verify_chapter_tts_authorization(
            _authorization("0" * 64),
            prepared,
            signing_key=KEY,
            operator_id="operator-1",
            catalog_version="catalog-1",
            catalog_digest=CATALOG_DIGEST,
            quote_id="quote-1",
            recovery_authority_id="recovery-1",
            recovery_verification_key_digest=RECOVERY_DIGEST,
            approved_ceiling_microdollars=50_000,
            now=NOW,
        )


def test_multi_chapter_and_invalid_media_shape_rejected_before_execution() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        prepare_chapter_tts_request(
            _plan(chapters=2),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
        )
    with pytest.raises(ValueError, match="audio shape"):
        prepare_chapter_tts_request(
            _plan(),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
            sample_rate_hz=1,
        )


def test_parent_can_explicitly_prepare_one_chapter_from_multi_plan() -> None:
    prepared = prepare_chapter_tts_request(
        _plan(chapters=2),
        asset_id="asset",
        revision_id="revision.chapter-1",
        provider="openai",
        model="tts",
        chapter_id="chapter-1",
    )
    assert prepared.chapter_id == "chapter-1"
    assert prepared.text == "Grounded chapter 1 explains the evidence."
    with pytest.raises(ValueError, match="chapter_id"):
        prepare_chapter_tts_request(
            _plan(chapters=2),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
            chapter_id="missing",
        )


def test_identifiers_and_speed_cannot_escape_canonical_request() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        prepare_chapter_tts_request(
            _plan(),
            asset_id="../escape",
            revision_id="revision",
            provider="openai",
            model="tts",
        )
    with pytest.raises(ValueError, match="speed"):
        prepare_chapter_tts_request(
            _plan(),
            asset_id="asset",
            revision_id="revision",
            provider="openai",
            model="tts",
            speed=float("nan"),
        )


def _wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes((100).to_bytes(2, "little", signed=True) * 8_000)
    return output.getvalue()


def _produce_args(tmp_path: Path) -> tuple[dict[str, object], PreparedChapterTTSRequest]:
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    prepared = _prepared()
    values: dict[str, object] = {
        "plan": _plan(),
        "prepared": prepared,
        "authorization": _authorization(prepared.body_digest),
        "signing_key": KEY,
        "integrity_key": b"chapter-tts-narration-integrity-key",
        "operator_id": "operator-1",
        "catalog_version": "catalog-1",
        "catalog_digest": CATALOG_DIGEST,
        "quote_id": "quote-1",
        "recovery_authority_id": "recovery-1",
        "recovery_verification_key_digest": RECOVERY_DIGEST,
        "approved_ceiling_microdollars": 50_000,
        "db_path": str(tmp_path / "tts.duckdb"),
        "output_dir": str(output),
        "now": NOW,
    }
    return values, prepared


def test_paid_send_materializes_truthful_audio_and_replays_once(tmp_path: Path) -> None:
    values, _ = _produce_args(tmp_path)
    calls: list[int] = []

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        return ChapterTTSSynthesisResult(_wav_bytes(), "provider-request-1")

    first = produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
    second = produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
    assert first == second
    assert calls == [1]
    assert first.manifest.asset_id == "asset-747"
    assert first.manifest.duration_seconds == 1.0
    assert Path(first.manifest.output_path).is_file()


def test_callback_failure_is_quarantined_and_never_retried(tmp_path: Path) -> None:
    values, prepared = _produce_args(tmp_path)
    calls: list[int] = []

    def fail(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        raise TimeoutError("ambiguous provider timeout")

    with pytest.raises(TimeoutError):
        produce_chapter_narration(**values, synthesize=fail)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="in flight|unknown|consumed"):
        produce_chapter_narration(**values, synthesize=fail)  # type: ignore[arg-type]
    assert calls == [1]
    authorization = _authorization(prepared.body_digest)
    execution_id = "mmexec_" + hashlib.sha256(
        f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
    ).hexdigest()
    attempt = get_chapter_tts_attempt(
        db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
    )
    assert attempt.status == "outcome_unknown"


def test_attempt_mac_tamper_fails_closed(tmp_path: Path) -> None:
    values, prepared = _produce_args(tmp_path)
    produce_chapter_narration(
        **values,  # type: ignore[arg-type]
        synthesize=lambda request: ChapterTTSSynthesisResult(
            _wav_bytes(), "provider-request-mac"
        ),
    )
    authorization = _authorization(prepared.body_digest)
    execution_id = "mmexec_" + hashlib.sha256(
        f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
    ).hexdigest()
    coordinator = FlockWriteCoordinator(str(values["db_path"]))
    with coordinator.acquire_write_context("test.tamper") as connection:
        connection.execute(
            "UPDATE multimedia_chapter_tts_attempts SET raw_sha256 = ? WHERE execution_id = ?",
            ["0" * 64, execution_id],
        )
    with pytest.raises(ProviderExecutionIntegrityError, match="MAC"):
        get_chapter_tts_attempt(
            db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
        )


def test_persisted_raw_tamper_breaks_received_resume(tmp_path: Path) -> None:
    values, prepared = _produce_args(tmp_path)
    authorization = _authorization(prepared.body_digest)
    calls: list[int] = []

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        return ChapterTTSSynthesisResult(_wav_bytes(), "provider-request-raw")

    artifact = produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
    execution_id = "mmexec_" + hashlib.sha256(
        f"{authorization.authorization_id}:{authorization.request_body_digest}".encode()
    ).hexdigest()
    attempt = get_chapter_tts_attempt(
        db_path=str(values["db_path"]), execution_id=execution_id, signing_key=KEY
    )
    assert attempt.raw_path is not None
    Path(attempt.raw_path).write_bytes(b"tampered")
    Path(attempt.raw_path).chmod(0o600)
    Path(artifact.manifest.output_path).write_bytes(b"tampered")
    Path(artifact.manifest.output_path).chmod(0o600)
    with pytest.raises(Exception, match="digest"):
        produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
    assert calls == [1]


def test_invalid_provider_bytes_after_send_are_never_retried(tmp_path: Path) -> None:
    values, _ = _produce_args(tmp_path)
    calls: list[int] = []

    def invalid(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        return ChapterTTSSynthesisResult(b"", "provider-request-empty")

    with pytest.raises(ValueError, match="empty"):
        produce_chapter_narration(**values, synthesize=invalid)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="retry is forbidden"):
        produce_chapter_narration(**values, synthesize=invalid)  # type: ignore[arg-type]
    assert calls == [1]


def test_twenty_concurrent_callers_invoke_provider_once(tmp_path: Path) -> None:
    values, _ = _produce_args(tmp_path)
    calls: list[int] = []
    lock = threading.Lock()

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        with lock:
            calls.append(1)
        return ChapterTTSSynthesisResult(_wav_bytes(), "provider-request-race")

    def run() -> object:
        try:
            return produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = tuple(pool.map(lambda _: run(), range(20)))
    assert calls == [1]
    assert any(not isinstance(result, Exception) for result in results)
    assert all(
        not isinstance(result, Exception)
        or "in flight" in str(result)
        or "retry is forbidden" in str(result)
        for result in results
    ), [repr(result) for result in results if isinstance(result, Exception)]


def test_competing_sealer_after_receive_is_reported_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values, _ = _produce_args(tmp_path)
    calls: list[int] = []
    record_observation = chapter_tts_module.record_provider_observation

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        return ChapterTTSSynthesisResult(_wav_bytes(), "provider-request-seal-race")

    def record_and_claim(**kwargs: object) -> None:
        record_observation(**kwargs)  # type: ignore[arg-type]
        lease = chapter_tts_module._claim_seal(  # noqa: SLF001
            str(values["db_path"]),
            str(kwargs["execution_id"]),
            KEY,
            acquired_at=NOW,
        )
        assert lease is not None

    monkeypatch.setattr(chapter_tts_module, "record_provider_observation", record_and_claim)

    with pytest.raises(Exception, match="seal is already in flight"):
        produce_chapter_narration(**values, synthesize=synthesize)  # type: ignore[arg-type]
    assert calls == [1]


def test_competing_sealer_completion_after_receive_reopens_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values, prepared = _produce_args(tmp_path)
    calls: list[int] = []
    record_observation = chapter_tts_module.record_provider_observation

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(1)
        return ChapterTTSSynthesisResult(_wav_bytes(), "provider-request-sealed-race")

    def record_and_seal(**kwargs: object) -> None:
        record_observation(**kwargs)  # type: ignore[arg-type]
        attempt = get_chapter_tts_attempt(
            db_path=str(values["db_path"]),
            execution_id=str(kwargs["execution_id"]),
            signing_key=KEY,
        )
        chapter_tts_module._seal_received(  # noqa: SLF001
            attempt=attempt,
            prepared=prepared,
            signing_key=KEY,
            integrity_key=values["integrity_key"],  # type: ignore[arg-type]
            db_path=str(values["db_path"]),
            output_dir=str(values["output_dir"]),
            ffmpeg_path=chapter_tts_module.DEFAULT_FFMPEG_PATH,
            ffprobe_path=chapter_tts_module.DEFAULT_FFPROBE_PATH,
            timeout_seconds=300,
            now=NOW,
        )

    monkeypatch.setattr(chapter_tts_module, "record_provider_observation", record_and_seal)

    artifact = produce_chapter_narration(  # type: ignore[arg-type]
        **values, synthesize=synthesize
    )
    assert calls == [1]
    assert Path(artifact.manifest.output_path).is_file()
