"""Bounded in-memory normalization for a later independently admitted ASR send."""

from __future__ import annotations

import hashlib
import math
import os
import re
import selectors
import stat
import struct
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import IO, Literal, Protocol

MAX_INPUT_BYTES = 25 * 1024 * 1024
SAMPLE_RATE_HZ = 16_000
MAX_SAMPLES = 600 * SAMPLE_RATE_HZ
MAX_PCM_BYTES = MAX_SAMPLES * 2
MAX_STDERR_BYTES = 65_536
TOTAL_SECONDS = 30.0
CLEANUP_SECONDS = 5.0
_CHUNK_BYTES = 65_536
_SLOT = threading.BoundedSemaphore(1)


@dataclass(frozen=True, slots=True)
class DecoderConfig:
    executable: Path
    executable_sha256: str
    allow_local_darwin: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.executable, Path)
            or not self.executable.is_absolute()
            or re.fullmatch(r"[0-9a-f]{64}", self.executable_sha256) is None
            or type(self.allow_local_darwin) is not bool
        ):
            raise ValueError("trusted_decoder_configuration_required")


@dataclass(frozen=True, slots=True)
class DecodeFacts:
    input_bytes_written: int
    pcm_bytes_read: int
    stderr_bytes_read: int
    stderr_sha256: str
    stdout_eof: bool
    stderr_eof: bool
    exit_code: int | None
    terminated: bool
    killed: bool
    reaped: bool
    handles_closed: bool
    cleanup_complete: bool
    elapsed_seconds: float
    limit_policy: str


@dataclass(frozen=True, slots=True)
class NormalizedAudio:
    wav: bytes = field(repr=False)
    source_sha256: str
    source_bytes: int
    wav_sha256: str
    pcm_sha256: str
    pcm_bytes: int
    sample_count: int
    facts: DecodeFacts

    def __post_init__(self) -> None:
        if (
            type(self.wav) is not bytes
            or type(self.sample_count) is not int
            or not 1 <= self.sample_count <= MAX_SAMPLES
            or type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_INPUT_BYTES
            or re.fullmatch(r"[0-9a-f]{64}", self.source_sha256) is None
            or type(self.pcm_bytes) is not int
            or self.pcm_bytes != self.sample_count * 2
            or len(self.wav) != self.pcm_bytes + 44
            or self.wav[:44] != _wav_header(self.pcm_bytes)
            or hashlib.sha256(self.wav).hexdigest() != self.wav_sha256
            or hashlib.sha256(self.wav[44:]).hexdigest() != self.pcm_sha256
            or not self.facts.cleanup_complete
            or not self.facts.stdout_eof
            or not self.facts.stderr_eof
            or self.facts.exit_code != 0
            or self.facts.input_bytes_written != self.source_bytes
            or self.facts.pcm_bytes_read != self.pcm_bytes
        ):
            raise ValueError("invalid_normalized_audio_binding")

    @property
    def duration_seconds(self) -> Fraction:
        return Fraction(self.sample_count, SAMPLE_RATE_HZ)


class AudioNormalizationError(RuntimeError):
    def __init__(self, code: str, facts: DecodeFacts | None = None):
        self.code = code
        self.facts = facts
        super().__init__(code)


class _Digest(Protocol):
    def update(self, data: bytes) -> None: ...

    def hexdigest(self) -> str: ...


@dataclass(slots=True)
class _ChildCustody:
    child: subprocess.Popen[bytes] = field(repr=False)
    streams: tuple[IO[bytes] | None, ...] = field(repr=False)
    fault: Literal["retirement_exception", "reap_unconfirmed", "streams_unclosed"] | None = None


_OWNED_CHILD: _ChildCustody | None = None


@dataclass(slots=True)
class _Progress:
    written: int = 0
    output: bytearray = field(default_factory=bytearray, repr=False)
    stderr_bytes: int = 0
    stderr_digest: _Digest = field(default_factory=hashlib.sha256, repr=False)
    stdout_eof: bool = False
    stderr_eof: bool = False


def _check_deadline(deadline: float, cancelled: threading.Event | None) -> None:
    if cancelled is not None and cancelled.is_set():
        raise AudioNormalizationError("cancelled")
    if time.monotonic() >= deadline:
        raise AudioNormalizationError("deadline_exceeded")


def _check_wave_container(audio: bytes) -> None:
    # FFmpeg can successfully decode a truncated RIFF data chunk. Enforce its
    # declared structure independently; duration still comes only from PCM.
    if audio[:4] != b"RIFF":
        return
    if len(audio) < 12 or audio[8:12] != b"WAVE":
        raise AudioNormalizationError("invalid_audio")
    if struct.unpack_from("<I", audio, 4)[0] + 8 != len(audio):
        raise AudioNormalizationError("invalid_audio")
    offset = 12
    data_chunks = 0
    format_code = bits = 0
    data: memoryview | None = None
    while offset < len(audio):
        if len(audio) - offset < 8:
            raise AudioNormalizationError("invalid_audio")
        size = struct.unpack_from("<I", audio, offset + 4)[0]
        if offset + 8 + size + (size & 1) > len(audio):
            raise AudioNormalizationError("invalid_audio")
        name = audio[offset : offset + 4]
        if name == b"fmt " and size >= 16:
            format_code = struct.unpack_from("<H", audio, offset + 8)[0]
            bits = struct.unpack_from("<H", audio, offset + 22)[0]
            if format_code == 65534 and size >= 40:
                format_code = struct.unpack_from("<H", audio, offset + 32)[0]
        if name == b"data":
            data_chunks += 1
            data = memoryview(audio)[offset + 8 : offset + 8 + size]
        offset += 8 + size + (size & 1)
        if offset > len(audio):
            raise AudioNormalizationError("invalid_audio")
    if data_chunks != 1:
        raise AudioNormalizationError("invalid_audio")
    if format_code == 3:
        if bits not in (32, 64) or data is None or len(data) % (bits // 8):
            raise AudioNormalizationError("invalid_audio")
        for (value,) in struct.iter_unpack("<f" if bits == 32 else "<d", data):
            if not math.isfinite(value):
                raise AudioNormalizationError("invalid_audio")


def _verify_executable(
    config: DecoderConfig, deadline: float, cancelled: threading.Event | None
) -> None:
    fd = os.open(config.executable, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111:
            raise AudioNormalizationError("decoder_unavailable")
        digest = hashlib.sha256()
        while block := os.read(fd, _CHUNK_BYTES):
            _check_deadline(deadline, cancelled)
            digest.update(block)
        after = os.fstat(fd)
        if digest.hexdigest() != config.executable_sha256 or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise AudioNormalizationError("decoder_unavailable")
    finally:
        os.close(fd)


def _pump(
    child: subprocess.Popen[bytes],
    audio: bytes,
    progress: _Progress,
    deadline: float,
    cancelled: threading.Event | None,
) -> None:
    streams = (child.stdin, child.stdout, child.stderr)
    if any(stream is None for stream in streams):
        raise AudioNormalizationError("decoder_unavailable")
    with selectors.DefaultSelector() as selector:
        for stream, name, event in zip(
            streams,
            ("stdin", "stdout", "stderr"),
            (selectors.EVENT_WRITE, selectors.EVENT_READ, selectors.EVENT_READ),
            strict=True,
        ):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event, name)
        source = memoryview(audio)
        while selector.get_map():
            _check_deadline(deadline, cancelled)
            for key, _events in selector.select(min(0.05, max(0.0, deadline - time.monotonic()))):
                name = key.data
                fd = key.fd
                if name == "stdin":
                    try:
                        count = os.write(
                            fd, source[progress.written : progress.written + _CHUNK_BYTES]
                        )
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        raise AudioNormalizationError("decoder_failed") from None
                    progress.written += count
                    if progress.written == len(audio):
                        selector.unregister(key.fileobj)
                        assert child.stdin is not None
                        child.stdin.close()
                    continue
                remaining = (
                    MAX_PCM_BYTES - len(progress.output)
                    if name == "stdout"
                    else MAX_STDERR_BYTES - progress.stderr_bytes
                )
                try:
                    block = os.read(fd, min(_CHUNK_BYTES, remaining + 1))
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(key.fileobj)
                    if name == "stdout":
                        progress.stdout_eof = True
                    else:
                        progress.stderr_eof = True
                    continue
                if len(block) > remaining:
                    raise AudioNormalizationError(
                        "duration_exceeded" if name == "stdout" else "decoder_diagnostics_exceeded"
                    )
                if name == "stdout":
                    progress.output.extend(block)
                else:
                    progress.stderr_bytes += len(block)
                    progress.stderr_digest.update(block)
        _check_deadline(deadline, cancelled)
        try:
            child.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise AudioNormalizationError("deadline_exceeded") from None


def _retire(
    child: subprocess.Popen[bytes], streams: tuple[IO[bytes] | None, ...], total_deadline: float
) -> tuple[bool, bool, bool, bool]:
    cleanup_deadline = min(total_deadline, time.monotonic() + CLEANUP_SECONDS)
    terminated = killed = False
    for stream in streams:
        if stream is not None and not stream.closed:
            with suppress(OSError):
                stream.close()
    if child.poll() is None:
        try:
            child.terminate()
            terminated = True
        except OSError:
            pass
        # A signaling error must not skip direct wait/reap.
        with suppress(subprocess.TimeoutExpired):
            child.wait(timeout=max(0.0, min(1.0, cleanup_deadline - time.monotonic())))
    if child.poll() is None:
        try:
            child.kill()
            killed = True
        except OSError:
            pass
    reaped = False
    try:
        child.wait(timeout=max(0.0, cleanup_deadline - time.monotonic()))
        reaped = True
    except subprocess.TimeoutExpired:
        pass
    return (
        terminated,
        killed,
        reaped,
        all(stream is None or stream.closed for stream in streams),
    )


def _wav_header(count: int) -> bytes:
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        count + 36,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        SAMPLE_RATE_HZ,
        SAMPLE_RATE_HZ * 2,
        2,
        16,
        b"data",
        count,
    )


def _wav(pcm: bytearray) -> bytes:
    return _wav_header(len(pcm)) + pcm


def normalize_audio(
    audio: bytes,
    *,
    config: DecoderConfig,
    deadline: float,
    cancelled: threading.Event | None = None,
) -> NormalizedAudio:
    """Decode the first audio stream completely, without mixing other streams.

    Configuration and monotonic deadline belong to the trusted server caller.
    This producer does not admit a payer, provider send, tariff or route.
    """
    global _OWNED_CHILD
    started = time.monotonic()
    if type(audio) is not bytes or not audio:
        raise AudioNormalizationError("empty_or_invalid_audio")
    if len(audio) > MAX_INPUT_BYTES:
        raise AudioNormalizationError("input_too_large")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise AudioNormalizationError("invalid_deadline")
    total_deadline = min(float(deadline), started + TOTAL_SECONDS)
    decode_deadline = total_deadline - CLEANUP_SECONDS
    _check_deadline(decode_deadline, cancelled)
    source_digest = hashlib.sha256(audio).hexdigest()
    _check_wave_container(audio)
    local = sys.platform == "darwin" and config.allow_local_darwin
    if sys.platform != "linux" and not local:
        raise AudioNormalizationError("required_limits_unavailable")
    while not _SLOT.acquire(timeout=max(0.0, min(0.05, decode_deadline - time.monotonic()))):
        _check_deadline(decode_deadline, cancelled)
    child: subprocess.Popen[bytes] | None = None
    release_slot = True
    progress = _Progress()
    failure: AudioNormalizationError | None = None
    facts: DecodeFacts | None = None
    try:
        _check_deadline(decode_deadline, cancelled)
        _verify_executable(config, decode_deadline, cancelled)
        _check_deadline(decode_deadline, cancelled)
        worker = Path(__file__).with_name("_audio_decode_worker.py")
        child = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                str(worker),
                str(config.executable),
                config.executable_sha256,
                "local-darwin" if local else "linux",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            cwd=worker.parent,
        )
        release_slot = False
        custody = _ChildCustody(child, (child.stdin, child.stdout, child.stderr))
        _OWNED_CHILD = custody
        streams = custody.streams
        try:
            _pump(child, audio, progress, decode_deadline, cancelled)
            if child.returncode != 0 or progress.stderr_bytes:
                raise AudioNormalizationError("decoder_failed")
            if (
                progress.written != len(audio)
                or not progress.stdout_eof
                or not progress.stderr_eof
                or not progress.output
                or len(progress.output) % 2
            ):
                raise AudioNormalizationError("invalid_decoded_audio")
        except AudioNormalizationError as exc:
            failure = exc
        finally:
            try:
                terminated, killed, reaped, closed = _retire(child, streams, total_deadline)
            except BaseException:
                custody.fault = "retirement_exception"
                raise
            release_slot = reaped and closed
            if release_slot:
                _OWNED_CHILD = None
            else:
                custody.fault = "reap_unconfirmed" if not reaped else "streams_unclosed"
            complete = reaped and closed and time.monotonic() <= total_deadline
            facts = DecodeFacts(
                progress.written,
                len(progress.output),
                progress.stderr_bytes,
                progress.stderr_digest.hexdigest(),
                progress.stdout_eof,
                progress.stderr_eof,
                child.returncode,
                terminated,
                killed,
                reaped,
                closed,
                complete,
                time.monotonic() - started,
                "darwin_local_cpu_only_linux_memory_unproved"
                if local
                else "linux_cpu_and_address_space",
            )
        if failure is not None:
            raise AudioNormalizationError(failure.code, facts)
        if not facts.cleanup_complete:
            raise AudioNormalizationError("cleanup_incomplete", facts)
        _check_deadline(total_deadline, cancelled)
        wav = _wav(progress.output)
        _check_deadline(total_deadline, cancelled)
        result = NormalizedAudio(
            wav,
            source_digest,
            len(audio),
            hashlib.sha256(wav).hexdigest(),
            hashlib.sha256(progress.output).hexdigest(),
            len(progress.output),
            len(progress.output) // 2,
            facts,
        )
        _check_deadline(total_deadline, cancelled)
        return result
    except AudioNormalizationError as exc:
        if exc.facts is None and facts is not None:
            raise AudioNormalizationError(exc.code, facts) from None
        raise
    except OSError:
        raise AudioNormalizationError("decoder_unavailable", facts) from None
    finally:
        # Unknown reap or stream closure retains exact handles and the slot.
        # A later caller times out honestly instead of starting a second child.
        if child is None or release_slot:
            _SLOT.release()
