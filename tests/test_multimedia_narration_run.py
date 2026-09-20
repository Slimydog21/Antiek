from __future__ import annotations

import hashlib
import io
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import substrate.multimedia.narration_run as narration_run_module
from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import (
    ChapterTTSProductionError,
    ChapterTTSSynthesisResult,
    PreparedChapterTTSRequest,
    produce_chapter_narration,
)
from substrate.multimedia.execution_authorization import (
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
)
from substrate.multimedia.narration_production import NarrationProductionArtifact
from substrate.multimedia.narration_run import (
    AuthorizedNarrationRun,
    NarrationRunError,
    authorize_narration_run,
    get_narration_run,
    prepare_narration_run,
    produce_narration_run,
)
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest

KEY = b"narration-run-signing-key-32-bytes!"
INTEGRITY_KEY = b"narration-run-integrity-key-32bytes"
NOW = datetime(2026, 7, 11, 18, 0, tzinfo=UTC)
CATALOG = hashlib.sha256(b"tts-catalog").hexdigest()
RECOVERY = hashlib.sha256(b"recovery-key").hexdigest()


def _plan() -> MultimediaPlan:
    chapters = tuple(
        ChapterPlan(
            chapter_id=f"chapter-{index}",
            title=f"Chapter {index}",
            minutes=5,
            purpose="Explain evidence",
            arc_id=f"arc-{index}",
            source_chunk_ids=(f"chunk-{index}",),
        )
        for index in range(3)
    )
    lines = tuple(
        ScriptLine(
            line_id=f"chapter-{index}-line-0",
            sequence=index,
            text=f"Narration for chapter {index}.",
            kind="narration",
        )
        for index in range(3)
    )
    return MultimediaPlan(
        request=MultimediaPlanRequest(topic="Aircraft", target_minutes=15),
        suggestions=(),
        chosen_arc_ids=(),
        chapters=chapters,
        script_lines=lines,
        scenes=(),
        unsourced_line_ids=(),
    )


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes((100).to_bytes(2, "little", signed=True) * 8_000)
    return output.getvalue()


def _authority(
    request: PreparedChapterTTSRequest, sequence: int
) -> MultimediaExecutionAuthorizationV2:
    return issue_async_execution_authorization(
        signing_key=KEY,
        request_id=f"tts-approval-{sequence}",
        operator_id="operator-1",
        asset_id=request.asset_id,
        revision_id=request.revision_id,
        provider=request.provider,
        route_policy=request.route_policy,
        model=request.model,
        endpoint_capability=request.endpoint_capability,
        catalog_version="catalog-1",
        catalog_digest=CATALOG,
        quote_id=f"quote-{sequence}",
        quote_expires_at=NOW + timedelta(hours=1),
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest=RECOVERY,
        approved_ceiling_microdollars=20_000,
        request_body_digest=request.body_digest,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _prepared() -> tuple[
    AuthorizedNarrationRun, dict[str, MultimediaExecutionAuthorizationV2]
]:
    routes = {f"chapter-{index}": ("openai", "gpt-4o-mini-tts") for index in range(3)}
    requests = prepare_narration_run(
        _plan(),
        asset_id="asset-747",
        revision_id="revision-parent",
        routes=routes,
        sample_rate_hz=8_000,
    )
    authorizations = {
        request.chapter_id: _authority(request, index)
        for index, request in enumerate(requests.chapters)
    }
    return authorize_narration_run(requests, authorizations), authorizations


def test_three_chapter_run_executes_once_and_replays(tmp_path: Path) -> None:
    prepared, authorizations = _prepared()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    calls: list[str] = []

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(request.chapter_id)
        return ChapterTTSSynthesisResult(_wav(), f"provider-{request.chapter_id}")

    values = {
        "plan": _plan(),
        "prepared": prepared,
        "authorizations": authorizations,
        "operator_id": "operator-1",
        "signing_key": KEY,
        "integrity_key": INTEGRITY_KEY,
        "db_path": str(tmp_path / "run.duckdb"),
        "output_dir": str(output),
        "now": NOW,
        "synthesize": synthesize,
    }
    first = produce_narration_run(**values)
    second = produce_narration_run(**values)
    expired_values = {**values, "now": NOW + timedelta(hours=2)}
    expired_replay = produce_narration_run(**expired_values)
    assert first == second
    assert expired_replay == first
    assert calls == ["chapter-0", "chapter-1", "chapter-2"]
    assert first.manifest.duration_seconds == 3.0
    assert tuple(row.chapter_id for row in first.manifest.sources) == (
        "chapter-0",
        "chapter-1",
        "chapter-2",
    )
    assert tuple(
        (row.chapter_id, row.script_line_ids, row.source_chunk_ids)
        for row in first.manifest.chapter_bindings
    ) == tuple(
        (row.chapter_id, row.script_line_ids, row.source_chunk_ids)
        for row in prepared.chapters
    )
    receipt = get_narration_run(
        db_path=str(values["db_path"]), run_id=prepared.run_id, signing_key=KEY
    )
    assert receipt.status == "sealed"


def test_authorization_set_substitution_fails_before_provider(tmp_path: Path) -> None:
    prepared, authorizations = _prepared()
    changed = dict(authorizations)
    changed.pop("chapter-2")
    with pytest.raises(ValueError, match="exactly cover|conflicts"):
        authorize_narration_run(
            prepare_narration_run(
                _plan(),
                asset_id="asset-747",
                revision_id="revision-parent",
                routes={
                    f"chapter-{index}": ("openai", "gpt-4o-mini-tts")
                    for index in range(3)
                },
                sample_rate_hz=8_000,
            ),
            changed,
        )


def test_parent_identifiers_cannot_escape_aggregate_root() -> None:
    with pytest.raises(ValueError, match="revision_id"):
        prepare_narration_run(
            _plan(),
            asset_id="asset-747",
            revision_id="../escape",
            routes={
                f"chapter-{index}": ("openai", "gpt-4o-mini-tts")
                for index in range(3)
            },
            sample_rate_hz=8_000,
        )


def test_run_receipt_mac_tamper_fails_closed(tmp_path: Path) -> None:
    prepared, authorizations = _prepared()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    db_path = str(tmp_path / "run.duckdb")
    produce_narration_run(
        plan=_plan(),
        prepared=prepared,
        authorizations=authorizations,
        operator_id="operator-1",
        signing_key=KEY,
        integrity_key=INTEGRITY_KEY,
        db_path=db_path,
        output_dir=str(output),
        now=NOW,
        synthesize=lambda request: ChapterTTSSynthesisResult(
            _wav(), f"provider-{request.chapter_id}"
        ),
    )
    from runtime.db_lock import FlockWriteCoordinator

    with FlockWriteCoordinator(db_path).acquire_write_context("test.run_tamper") as ctx:
        ctx.execute(
            "UPDATE multimedia_narration_runs SET authorization_set_digest = ? "
            "WHERE run_id = ?",
            ["0" * 64, prepared.run_id],
        )
    with pytest.raises(NarrationRunError, match="MAC"):
        get_narration_run(db_path=db_path, run_id=prepared.run_id, signing_key=KEY)


def test_crash_between_chapters_resumes_only_missing_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, authorizations = _prepared()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    db_path = str(tmp_path / "run.duckdb")
    calls: list[str] = []
    original = produce_chapter_narration
    chapter_invocations = 0

    def interrupted(**kwargs: object) -> NarrationProductionArtifact:
        nonlocal chapter_invocations
        chapter_invocations += 1
        if chapter_invocations == 2:
            raise RuntimeError("process interrupted between chapters")
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(narration_run_module, "produce_chapter_narration", interrupted)

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(request.chapter_id)
        return ChapterTTSSynthesisResult(_wav(), f"provider-{request.chapter_id}")

    values = dict(
        plan=_plan(), prepared=prepared, authorizations=authorizations,
        operator_id="operator-1", signing_key=KEY, integrity_key=INTEGRITY_KEY,
        db_path=db_path, output_dir=str(output), now=NOW, synthesize=synthesize,
    )
    with pytest.raises(RuntimeError, match="interrupted"):
        produce_narration_run(**values)
    monkeypatch.setattr(narration_run_module, "produce_chapter_narration", original)
    artifact = produce_narration_run(**values)
    assert artifact.manifest.duration_seconds == 3.0
    assert calls == ["chapter-0", "chapter-1", "chapter-2"]


def test_concurrent_parent_callers_do_not_duplicate_children(tmp_path: Path) -> None:
    prepared, authorizations = _prepared()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    calls: list[str] = []

    def synthesize(request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        calls.append(request.chapter_id)
        return ChapterTTSSynthesisResult(_wav(), f"provider-{request.chapter_id}")

    values = dict(
        plan=_plan(), prepared=prepared, authorizations=authorizations,
        operator_id="operator-1", signing_key=KEY, integrity_key=INTEGRITY_KEY,
        db_path=str(tmp_path / "run.duckdb"), output_dir=str(output), now=NOW,
        synthesize=synthesize,
    )

    def run() -> object:
        try:
            return produce_narration_run(**values)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = tuple(pool.map(lambda _: run(), range(10)))
    final = produce_narration_run(**values)
    assert final.manifest.duration_seconds == 3.0
    assert sorted(calls) == ["chapter-0", "chapter-1", "chapter-2"]
    assert any(not isinstance(result, Exception) for result in results)
    errors = tuple(result for result in results if isinstance(result, Exception))
    assert all(
        isinstance(error, (ChapterTTSProductionError, NarrationRunError))
        and ("in flight" in str(error) or "retry is forbidden" in str(error))
        for error in errors
    ), [repr(error) for error in errors]
