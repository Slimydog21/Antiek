from __future__ import annotations

import platform
import subprocess
import wave
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from substrate.contracts.multimedia import ScriptLine
from substrate.multimedia.chapter_tts_production import prepare_chapter_tts_request
from substrate.multimedia.local_tts import (
    LocalTTSAdapter,
    LocalTTSConfig,
    LocalTTSError,
    LocalTTSOutcomeUnknown,
)
from substrate.multimedia.planner import ChapterPlan, MultimediaPlan, MultimediaPlanRequest

NOW = datetime(2026, 7, 13, tzinfo=UTC)
KEY = b"local-tts-test-signing-key-material"


def _request(text: str = "Antiek explains how aircraft factories coordinate assembly."):
    plan = MultimediaPlan(
        request=MultimediaPlanRequest(
            topic="Aircraft factories",
            target_minutes=15,
            route_policy="cheapest",
        ),
        suggestions=(),
        chosen_arc_ids=(),
        chapters=(
            ChapterPlan(
                chapter_id="chapter-1",
                title="Factory coordination",
                minutes=15,
                purpose="Explain the production system",
                arc_id="mechanism",
                source_chunk_ids=("chunk-1",),
            ),
        ),
        script_lines=(
            ScriptLine(
                line_id="chapter-1-line-0",
                sequence=0,
                text=text,
                kind="narration",
            ),
        ),
        scenes=(),
        unsourced_line_ids=(),
    )
    return prepare_chapter_tts_request(
        plan,
        asset_id="asset-1",
        revision_id="revision-1",
        provider="local_executable_tts",
        model="macos-say-v1",
        voice="narrator",
        chapter_id="chapter-1",
        sample_rate_hz=24_000,
        channels=1,
    )


def _adapter(tmp_path: Path) -> LocalTTSAdapter:
    output = tmp_path / "audio"
    output.mkdir(mode=0o700)
    return LocalTTSAdapter(
        config=LocalTTSConfig(
            synthesizer_path="/usr/bin/say",
            ffprobe_path="/opt/homebrew/bin/ffprobe",
            output_dir=str(output),
            voice="Samantha",
        ),
        db_path=str(tmp_path / "local.duckdb"),
        signing_key=KEY,
    )


@pytest.mark.skipif(
    platform.system() != "Darwin"
    or not Path("/usr/bin/say").exists()
    or not Path("/opt/homebrew/bin/ffprobe").exists(),
    reason="requires configured macOS local speech executables",
)
def test_real_say_produces_private_playable_wav_and_exactly_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    first = adapter.synthesize(_request(), now=NOW)
    real_run = subprocess.run

    def no_second_synthesis(command, **kwargs):  # noqa: ANN001
        if command[0] == "/usr/bin/say":
            raise AssertionError("exact replay must not invoke local synthesis")
        return real_run(command, **kwargs)

    monkeypatch.setattr("substrate.multimedia.local_tts.subprocess.run", no_second_synthesis)
    replay = adapter.synthesize(_request(), now=NOW)
    reopened = adapter.reopen(_request())
    assert replay == first and reopened == first
    path = Path(first.output_path)
    assert path.read_bytes()[:4] == b"RIFF" and path.read_bytes()[8:12] == b"WAVE"
    assert first.duration_seconds > 0 and first.sample_rate_hz == 24_000
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(
    platform.system() != "Darwin"
    or not Path("/usr/bin/say").exists()
    or not Path("/opt/homebrew/bin/ffprobe").exists(),
    reason="requires configured macOS local speech executables",
)
def test_text_is_file_input_not_shell_and_tamper_fails_replay(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    adapter = _adapter(tmp_path)
    artifact = adapter.synthesize(
        _request(f"Aircraft text $(touch {marker}) ; touch {marker}"), now=NOW
    )
    assert not marker.exists()
    Path(artifact.output_path).write_bytes(b"RIFF\x00\x00\x00\x00WAVEtampered")
    with pytest.raises(LocalTTSError):
        adapter.synthesize(
            _request(f"Aircraft text $(touch {marker}) ; touch {marker}"), now=NOW
        )


@pytest.mark.skipif(
    platform.system() != "Darwin"
    or not Path("/usr/bin/say").exists()
    or not Path("/opt/homebrew/bin/ffprobe").exists(),
    reason="requires configured macOS local speech executables",
)
def test_timeout_with_valid_pending_output_requires_explicit_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    real_run = subprocess.run

    def interrupted(command, **kwargs):  # noqa: ANN001
        pending = Path(command[command.index("-o") + 1])
        with wave.open(str(pending), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24_000)
            output.writeframes(b"\x00\x00" * 24_000)
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr("substrate.multimedia.local_tts.subprocess.run", interrupted)
    with pytest.raises(LocalTTSOutcomeUnknown):
        adapter.synthesize(_request(), now=NOW)
    monkeypatch.setattr("substrate.multimedia.local_tts.subprocess.run", real_run)
    recovered = adapter.recover(_request())
    assert recovered.duration_seconds == 1.0
    assert Path(recovered.output_path).is_file()


@pytest.mark.skipif(
    platform.system() != "Darwin"
    or not Path("/usr/bin/say").exists()
    or not Path("/opt/homebrew/bin/ffprobe").exists(),
    reason="requires configured macOS local speech executables",
)
def test_database_mac_and_executable_configuration_fail_closed(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    artifact = adapter.synthesize(_request(), now=NOW)
    with duckdb.connect(str(tmp_path / "local.duckdb")) as connection:
        connection.execute(
            "UPDATE multimedia_local_tts_artifacts SET duration_seconds=999"
        )
    with pytest.raises(LocalTTSError, match="integrity"):
        adapter.synthesize(_request(), now=NOW)
    assert Path(artifact.output_path).exists()

    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="private"):
        LocalTTSAdapter(
            config=LocalTTSConfig(
                synthesizer_path="/usr/bin/say",
                ffprobe_path="/opt/homebrew/bin/ffprobe",
                output_dir=str(public),
            ),
            db_path=str(tmp_path / "other.duckdb"),
            signing_key=KEY,
        )


def test_fake_or_paid_request_cannot_enter_local_production(tmp_path: Path) -> None:
    if platform.system() != "Darwin" or not Path("/opt/homebrew/bin/ffprobe").exists():
        pytest.skip("requires configured local adapter")
    adapter = _adapter(tmp_path)
    wrong = prepare_chapter_tts_request(
        MultimediaPlan(
            request=MultimediaPlanRequest(topic="x", target_minutes=15, route_policy="balanced"),
            suggestions=(), chosen_arc_ids=(),
            chapters=(ChapterPlan(chapter_id="chapter-1", title="x", minutes=15, purpose="x", arc_id="x"),),
            script_lines=(ScriptLine(line_id="chapter-1-line-0", sequence=0, text="spoken", kind="narration"),),
            scenes=(), unsourced_line_ids=(),
        ),
        asset_id="asset-1", revision_id="revision-1", provider="openai",
        model="gpt-4o-mini-tts", chapter_id="chapter-1",
    )
    with pytest.raises(ValueError, match="invalid"):
        adapter.synthesize(wrong, now=NOW)
