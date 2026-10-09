"""Private decoder-boundary controls; no app, credential or provider imports."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import math
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

_PATH = Path(__file__).resolve().parents[1] / "acquisition/voice/audio_bound.py"
_SPEC = importlib.util.spec_from_file_location("_isolated_audio_bound", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
bound = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bound
_SPEC.loader.exec_module(bound)


def wav_bytes(samples: int = 160, rate: int = 16000, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x01\x00" * samples * channels)
    return buffer.getvalue()


def tool(tmp_path: Path, body: str) -> Any:
    path = tmp_path / "owned-decoder-control"
    path.write_text(f"#!{sys.executable} -S\nimport os, sys, time\n" + body)
    path.chmod(0o555)
    return bound.DecoderConfig(
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        allow_local_darwin=sys.platform == "darwin",
    )


def run(config: Any, audio: bytes | None = None, **options: Any) -> Any:
    return bound.normalize_audio(
        wav_bytes() if audio is None else audio,
        config=config,
        deadline=time.monotonic() + 10,
        **options,
    )


def output_tool(tmp_path: Path, count: int, tail: str = "") -> Any:
    return tool(
        tmp_path,
        f"while os.read(0,65536): pass\nremaining={count}\n"
        "while remaining:\n n=min(remaining,65536)\n os.write(1,b'\\x01'*n)\n remaining-=n\n"
        + tail,
    )


def test_useful_canonical_wav_and_frozen_bindings(tmp_path: Path) -> None:
    source = wav_bytes(320)
    result = run(output_tool(tmp_path, 640), source)
    assert result.sample_count == 320 and result.duration_seconds == Fraction(320, 16000)
    assert len(result.wav) == 684 and result.pcm_bytes == 640
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    assert result.wav_sha256 == hashlib.sha256(result.wav).hexdigest()
    assert result.pcm_sha256 == hashlib.sha256(result.wav[44:]).hexdigest()
    with wave.open(io.BytesIO(result.wav)) as reader:
        assert (
            reader.getnchannels(),
            reader.getsampwidth(),
            reader.getframerate(),
            reader.getnframes(),
        ) == (1, 2, 16000, 320)
    assert result.facts.input_bytes_written == len(source)
    assert result.facts.stdout_eof and result.facts.stderr_eof and result.facts.exit_code == 0
    assert result.facts.reaped and result.facts.handles_closed and result.facts.cleanup_complete
    assert "wav=" not in repr(result) and source.hex() not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.sample_count = 5
    with pytest.raises(ValueError):
        replace(result, sample_count=math.nan)
    with pytest.raises(ValueError):
        replace(result, wav_sha256="0" * 64)


@pytest.mark.parametrize("samples", [bound.MAX_SAMPLES - 1, bound.MAX_SAMPLES])
def test_inclusive_duration_boundary(tmp_path: Path, samples: int) -> None:
    result = run(output_tool(tmp_path, samples * 2))
    assert result.sample_count == samples and len(result.wav) == samples * 2 + 44
    assert result.duration_seconds <= 600


def test_over_duration_refuses_without_shorter_success(tmp_path: Path) -> None:
    with pytest.raises(bound.AudioNormalizationError, match="duration_exceeded") as error:
        run(output_tool(tmp_path, bound.MAX_PCM_BYTES + 2))
    assert error.value.facts.pcm_bytes_read <= bound.MAX_PCM_BYTES
    assert error.value.facts.reaped and error.value.facts.handles_closed


@pytest.mark.parametrize("audio", [b"", bytearray(b"x"), None])
def test_empty_or_mutable_input_refuses_without_child(audio: Any, tmp_path: Path) -> None:
    config = output_tool(tmp_path, 4)
    with pytest.raises(bound.AudioNormalizationError, match="empty_or_invalid_audio"):
        bound.normalize_audio(audio, config=config, deadline=time.monotonic() + 10)


def test_input_byte_cap_is_inclusive(tmp_path: Path) -> None:
    config = output_tool(tmp_path, 2)
    for count in (bound.MAX_INPUT_BYTES - 1, bound.MAX_INPUT_BYTES):
        result = run(config, b"x" * count)
        assert result.source_bytes == count and result.facts.input_bytes_written == count
    with pytest.raises(bound.AudioNormalizationError, match="input_too_large"):
        run(config, b"x" * (bound.MAX_INPUT_BYTES + 1))


@pytest.mark.parametrize("change", ["short", "extra", "forged-size"])
def test_wave_truncation_or_forged_container_rejected(tmp_path: Path, change: str) -> None:
    source = wav_bytes()
    if change == "short":
        source = source[:-2]
    elif change == "extra":
        source += b"junk"
    else:
        source = source[:4] + struct.pack("<I", 8) + source[8:]
    with pytest.raises(bound.AudioNormalizationError, match="invalid_audio"):
        run(output_tool(tmp_path, 2), source)


@pytest.mark.parametrize("number", [math.nan, math.inf, -math.inf])
def test_nonfinite_float_wave_is_not_normalized_to_false_silence(
    tmp_path: Path, number: float
) -> None:
    data = struct.pack("<f", number)
    source = (
        struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            40,
            b"WAVE",
            b"fmt ",
            16,
            3,
            1,
            16000,
            64000,
            4,
            32,
            b"data",
            4,
        )
        + data
    )
    with pytest.raises(bound.AudioNormalizationError, match="invalid_audio"):
        run(output_tool(tmp_path, 2), source)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_empty_and_misaligned_decoded_samples_refused(tmp_path: Path, count: int) -> None:
    with pytest.raises(bound.AudioNormalizationError, match="invalid_decoded_audio") as error:
        run(output_tool(tmp_path, count))
    assert error.value.facts.reaped


def test_stderr_exhaustion_is_bounded_and_private(tmp_path: Path) -> None:
    config = tool(
        tmp_path,
        "while os.read(0,65536): pass\nos.write(2,b'private-diagnostic'*5000)\ntime.sleep(10)\n",
    )
    with pytest.raises(
        bound.AudioNormalizationError, match="decoder_diagnostics_exceeded"
    ) as error:
        run(config)
    assert error.value.facts.stderr_bytes_read <= 65536 and error.value.facts.reaped
    assert "private-diagnostic" not in str(error.value)
    assert "private-diagnostic" not in repr(error.value.facts)


def test_nonzero_exit_and_diagnostics_refuse(tmp_path: Path) -> None:
    config = output_tool(tmp_path, 4, "os.write(2,b'decode failure')\nsys.exit(1)\n")
    with pytest.raises(bound.AudioNormalizationError, match="decoder_failed") as error:
        run(config)
    assert error.value.facts.exit_code == 1 and error.value.facts.reaped


def test_zero_exit_with_error_diagnostics_refuses(tmp_path: Path) -> None:
    with pytest.raises(bound.AudioNormalizationError, match="decoder_failed"):
        run(output_tool(tmp_path, 4, "os.write(2,b'premature end')\n"))


def test_caller_deadline_reserves_cleanup_and_reaps_hung_child(tmp_path: Path) -> None:
    config = tool(tmp_path, "while os.read(0,65536): pass\ntime.sleep(20)\n")
    started = time.monotonic()
    with pytest.raises(bound.AudioNormalizationError, match="deadline_exceeded") as error:
        bound.normalize_audio(wav_bytes(), config=config, deadline=started + 5.4)
    assert time.monotonic() - started < 5.4
    assert error.value.facts.reaped and error.value.facts.terminated
    assert error.value.facts.handles_closed and error.value.facts.cleanup_complete


def test_cancellation_reaps_actual_owned_child(tmp_path: Path) -> None:
    flag = threading.Event()
    config = tool(tmp_path, "while os.read(0,65536): pass\ntime.sleep(20)\n")
    timer = threading.Timer(0.2, flag.set)
    timer.start()
    try:
        with pytest.raises(bound.AudioNormalizationError, match="cancelled") as error:
            run(config, cancelled=flag)
        assert error.value.facts.reaped and error.value.facts.handles_closed
    finally:
        timer.cancel()
        timer.join()


def test_signaling_failure_does_not_skip_direct_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tool(tmp_path, "while os.read(0,65536): pass\ntime.sleep(.8)\n")

    def fail_signal(_self: Any) -> None:
        raise OSError("controlled-signal-failure")

    monkeypatch.setattr(bound.subprocess.Popen, "terminate", fail_signal)
    with pytest.raises(bound.AudioNormalizationError, match="deadline_exceeded") as error:
        bound.normalize_audio(wav_bytes(), config=config, deadline=time.monotonic() + 5.2)
    assert error.value.facts.reaped and error.value.facts.exit_code == 0


def test_queue_wait_uses_the_same_caller_deadline(tmp_path: Path) -> None:
    config = output_tool(tmp_path, 4)
    assert bound._SLOT.acquire(timeout=1)
    started = time.monotonic()
    try:
        with pytest.raises(bound.AudioNormalizationError, match="deadline_exceeded"):
            bound.normalize_audio(wav_bytes(), config=config, deadline=started + 5.1)
        assert time.monotonic() - started < 0.5
    finally:
        bound._SLOT.release()


def test_two_concurrent_calls_are_serialized(tmp_path: Path) -> None:
    marker = tmp_path / "decoder-live-metadata-only"
    body = f"fd=os.open({str(marker)!r},os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)\n"
    body += (
        "while os.read(0,65536): pass\ntime.sleep(.2)\nos.write(1,b'\\x01\\x00')\nos.close(fd)\n"
    )
    body += f"os.unlink({str(marker)!r})\n"
    config = tool(tmp_path, body)
    results: list[Any] = []

    def invoke() -> None:
        results.append(run(config))

    threads = [threading.Thread(target=invoke) for _ in range(2)]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == 2 and all(not thread.is_alive() for thread in threads)
    assert time.monotonic() - started >= 0.4
    assert all(result.facts.reaped for result in results)
    assert not marker.exists()


def test_term_ignoring_child_is_killed_and_reaped(tmp_path: Path) -> None:
    config = tool(
        tmp_path,
        "import signal\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nwhile os.read(0,65536): pass\ntime.sleep(20)\n",
    )
    with pytest.raises(bound.AudioNormalizationError, match="deadline_exceeded") as error:
        bound.normalize_audio(wav_bytes(), config=config, deadline=time.monotonic() + 5.3)
    assert error.value.facts.terminated and error.value.facts.killed and error.value.facts.reaped


def test_actual_returned_pipe_handles_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = bound.subprocess.Popen
    captured: list[Any] = []

    def capture(*args: Any, **kwargs: Any) -> Any:
        child = original(*args, **kwargs)
        captured.append(child)
        return child

    monkeypatch.setattr(bound.subprocess, "Popen", capture)
    result = run(output_tool(tmp_path, 4))
    assert result.facts.cleanup_complete and len(captured) == 1
    child = captured[0]
    assert all(stream.closed for stream in (child.stdin, child.stdout, child.stderr))
    assert child.returncode == 0


@pytest.mark.parametrize("deadline", [math.nan, math.inf, -math.inf, True])
def test_invalid_or_expired_deadline_never_starts(tmp_path: Path, deadline: Any) -> None:
    with pytest.raises(bound.AudioNormalizationError, match="invalid_deadline"):
        bound.normalize_audio(wav_bytes(), config=output_tool(tmp_path, 2), deadline=deadline)


def test_expired_cleanup_budget_never_starts(tmp_path: Path) -> None:
    with pytest.raises(bound.AudioNormalizationError, match="deadline_exceeded"):
        bound.normalize_audio(
            wav_bytes(), config=output_tool(tmp_path, 2), deadline=time.monotonic() + 4
        )


def test_executable_identity_and_production_limit_refusal(tmp_path: Path) -> None:
    config = output_tool(tmp_path, 2)
    with pytest.raises(bound.AudioNormalizationError, match="decoder_unavailable"):
        run(replace(config, executable_sha256="0" * 64))
    if sys.platform == "darwin":
        with pytest.raises(bound.AudioNormalizationError, match="required_limits_unavailable"):
            run(replace(config, allow_local_darwin=False))


def test_fixed_pipe_only_single_stream_command_and_replacement_env(tmp_path: Path) -> None:
    body = "assert sys.argv[sys.argv.index('-protocol_whitelist')+1]=='pipe'\n"
    body += "assert sys.argv[sys.argv.index('-map')+1]=='0:a:0'\nassert '-t' not in sys.argv and '-to' not in sys.argv\n"
    body += "assert set(os.environ) <= {'PATH','LANG','LC_ALL','TZ','LC_CTYPE'}\n"
    body += "assert '-vn' in sys.argv and '-sn' in sys.argv and '-dn' in sys.argv\n"
    body += "import resource\nassert resource.getrlimit(resource.RLIMIT_CPU)==(20,20)\n"
    body += "if sys.platform=='linux': assert resource.getrlimit(resource.RLIMIT_AS)==(536870912,536870912)\n"
    body += "while os.read(0,65536): pass\nos.write(1,b'\\x01\\x00')\n"
    if sys.platform == "darwin":
        body = "os.environ.pop('__CF_USER_TEXT_ENCODING', None)\n" + body
    result = run(tool(tmp_path, body))
    assert result.sample_count == 1


def native_config() -> Any:
    configured = os.environ.get("ANTIEK_AUDIO_BOUND_TEST_FFMPEG")
    executable = Path(configured or shutil.which("ffmpeg") or "/missing-ffmpeg").resolve(
        strict=True
    )
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    if sys.platform == "darwin":
        assert str(executable) == "/opt/homebrew/Cellar/ffmpeg/9.0.1/bin/ffmpeg"
        assert digest == "11012f10d9d2eff4df94d760eec5964980880ced20bd4cdbd9f82ec399867e9d"
    return bound.DecoderConfig(executable, digest, allow_local_darwin=sys.platform == "darwin")


def test_native_wav_normalization_and_digest_parity() -> None:
    source = wav_bytes(4800, 48000, 2)
    result = run(native_config(), source)
    assert result.sample_count == 1600 and result.duration_seconds == Fraction(1, 10)
    assert result.wav[44:] == b"\x01\x00" * 1600
    assert result.facts.cleanup_complete and result.facts.stdout_eof and result.facts.stderr_eof
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    if sys.platform == "darwin":
        assert "linux_memory_unproved" in result.facts.limit_policy
    else:
        assert result.facts.limit_policy == "linux_cpu_and_address_space"


def native_webm(copies: int = 1, video_only: bool = False) -> bytes:
    config = native_config()
    if video_only:
        inputs = ["-f", "lavfi", "-i", "color=size=16x16:rate=1:duration=1"]
        outputs = ["-frames:v", "1", "-c:v", "libvpx", "-an"]
        source = b"fixture-input-not-consumed"
    else:
        inputs = ["-protocol_whitelist", "pipe", "-i", "pipe:0"]
        outputs = [value for _ in range(copies) for value in ("-map", "0:a:0")] + [
            "-c:a",
            "libopus",
        ]
        source = wav_bytes(3200)
    argv = [
        str(config.executable),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-threads",
        "1",
        *inputs,
        *outputs,
        "-threads",
        "1",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-f",
        "webm",
        "pipe:1",
    ]
    child = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "TZ": "UTC"},
    )
    progress = bound._Progress()
    deadline = time.monotonic() + 10
    try:
        bound._pump(child, source, progress, deadline, None)
        assert child.returncode == 0 and not progress.stderr_bytes and len(progress.output) <= 65536
        return bytes(progress.output)
    finally:
        retired = bound._retire(child, (child.stdin, child.stdout, child.stderr), deadline + 5)
        assert retired[2] and retired[3]


def test_native_webm_decodes_real_generated_fixture() -> None:
    source = native_webm()
    result = run(native_config(), source)
    assert 0 < result.sample_count <= 4000 and result.duration_seconds <= 1 / 4
    assert result.facts.cleanup_complete and result.source_bytes == len(source)


def test_native_multiple_streams_selects_first_without_mixing() -> None:
    single = run(native_config(), native_webm())
    multiple = run(native_config(), native_webm(copies=2))
    assert single.sample_count == multiple.sample_count and single.pcm_sha256 == multiple.pcm_sha256


def test_native_video_only_and_truncated_webm_refused() -> None:
    config = native_config()
    for source in (native_webm(video_only=True), native_webm()[:-20]):
        with pytest.raises(bound.AudioNormalizationError):
            run(config, source)


def test_native_invalid_noaudio_or_network_playlist_refused() -> None:
    config = native_config()
    for source in (b"invalid-audio", b"#EXTM3U\nhttps://127.0.0.1:1/audio\n", wav_bytes(0)):
        with pytest.raises(bound.AudioNormalizationError):
            run(config, source)


def test_custody_published_before_pump_and_cleared_after_actual_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_pump = bound._pump
    observed: list[Any] = []

    def observe(child: Any, *args: Any) -> None:
        custody = bound._OWNED_CHILD
        assert custody is not None and custody.child is child
        assert custody.streams == (child.stdin, child.stdout, child.stderr)
        assert custody.fault is None
        assert set(custody.__slots__) == {"child", "streams", "fault"}
        observed.append(custody)
        original_pump(child, *args)

    monkeypatch.setattr(bound, "_pump", observe)
    result = run(output_tool(tmp_path, 4))
    assert result.facts.cleanup_complete and len(observed) == 1
    assert bound._OWNED_CHILD is None
    assert observed[0].child.returncode == 0
    assert all(stream.closed for stream in observed[0].streams)
    assert bound._SLOT.acquire(blocking=False)
    bound._SLOT.release()


@pytest.mark.parametrize("uncertainty", ["unreaped", "unclosed", "exception"])
def test_synthetic_retirement_uncertainty_retains_exact_handles_and_blocks_new_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uncertainty: str
) -> None:
    # Injected uncertainty is a custody control, not a native cleanup failure.
    original_popen = bound.subprocess.Popen
    original_retire = bound._retire
    captured: list[Any] = []
    test_deadline = time.monotonic() + 12
    config = tool(tmp_path, "time.sleep(20)\n")

    def capture(*args: Any, **kwargs: Any) -> Any:
        child = original_popen(*args, **kwargs)
        captured.append(child)
        return child

    def refuse_pump(child: Any, *args: Any) -> None:
        custody = bound._OWNED_CHILD
        assert custody is not None and custody.child is child
        assert custody.streams == (child.stdin, child.stdout, child.stderr)
        raise bound.AudioNormalizationError("cancelled")

    def uncertain_retire(child: Any, streams: Any, deadline: float) -> Any:
        assert child is captured[0] and bound._OWNED_CHILD.child is child
        if uncertainty == "exception":
            raise OSError("synthetic retirement uncertainty")
        if uncertainty == "unclosed":
            child.kill()
            child.wait(timeout=max(0.0, min(2.0, test_deadline - time.monotonic())))
            assert any(not stream.closed for stream in streams)
            return False, True, True, False
        return False, False, False, False

    monkeypatch.setattr(bound.subprocess, "Popen", capture)
    monkeypatch.setattr(bound, "_pump", refuse_pump)
    monkeypatch.setattr(bound, "_retire", uncertain_retire)
    try:
        expected = "decoder_unavailable" if uncertainty == "exception" else "cancelled"
        with pytest.raises(bound.AudioNormalizationError, match=expected):
            run(config)
        assert len(captured) == 1
        custody = bound._OWNED_CHILD
        assert custody is not None and custody.child is captured[0]
        assert custody.streams == (captured[0].stdin, captured[0].stdout, captured[0].stderr)
        expected_fault = {
            "exception": "retirement_exception",
            "unclosed": "streams_unclosed",
            "unreaped": "reap_unconfirmed",
        }[uncertainty]
        assert custody.fault == expected_fault
        assert set(custody.__slots__) == {"child", "streams", "fault"}
        assert not bound._SLOT.acquire(blocking=False)
        with pytest.raises(bound.AudioNormalizationError, match="deadline_exceeded"):
            bound.normalize_audio(wav_bytes(), config=config, deadline=time.monotonic() + 5.1)
        assert len(captured) == 1 and bound._OWNED_CHILD is custody
    finally:
        # Test-only recovery: direct native retirement before releasing test state.
        # Production has no observer, retry or automatic recovery of uncertainty.
        if captured:
            child = captured[0]
            streams = (child.stdin, child.stdout, child.stderr)
            _, _, reaped, closed = original_retire(child, streams, test_deadline)
            assert reaped and closed and time.monotonic() <= test_deadline
            assert child.wait(timeout=0) is not None
            if bound._OWNED_CHILD is not None:
                assert bound._OWNED_CHILD.child is child
                bound.__dict__["_OWNED_CHILD"] = None
                bound._SLOT.release()


def test_retirement_requires_returned_direct_wait_not_cached_returncode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real child is reaped first; only the later wait observation is synthetic.
    child = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", "pass"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    streams = (child.stdin, child.stdout, child.stderr)
    deadline = time.monotonic() + 5
    try:
        assert child.wait(timeout=4) == 0

        def uncertain_wait(timeout: float) -> int:
            raise subprocess.TimeoutExpired(child.args, timeout)

        with monkeypatch.context() as wait_patch:
            wait_patch.setattr(child, "wait", uncertain_wait)
            _, _, reaped, closed = bound._retire(child, streams, deadline)
            assert child.returncode == 0 and not reaped and closed
    finally:
        assert child.wait(timeout=max(0.0, deadline - time.monotonic())) == 0
        for stream in streams:
            assert stream is not None
            stream.close()
