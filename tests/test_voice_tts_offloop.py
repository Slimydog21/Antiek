"""LB-12 — the reader's voice routes keep the event loop free, bound the
transcribe body, and keep no audio on disk.

The API runs one uvicorn worker, so a synchronous provider call inside an
``async def`` handler parks the event loop and stalls every other request for
as long as Whisper or TTS takes (up to the 120 s / 60 s client timeouts).
These tests drive the real app (``create_app``) over ASGI with the provider
stubbed, and watch ``GET /health`` while the provider is in flight:

* a concurrent ``/health`` must complete within 200 ms while a 2 s provider
  call is running, for ``POST /voice/transcribe`` and ``POST /speech/tts``;
* a transcribe body over 25 MiB answers 413 ``too_large`` before any provider
  is called, and the route stops reading the body once it passes the cap;
* no audio byte survives under the test's storage roots (DuckDB, events,
  artifacts, ``ANTIEK_HOME``, the temp dir) after a transcription, whether it
  succeeded, the provider failed, or the body was refused.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from interfaces.research.api.app import create_app
from substrate.graph import ensure_initialized

_PROVIDER_SLEEP_S = 2.0
_HEALTH_BUDGET_S = 0.2
_MAX_TRANSCRIBE_BYTES = 25 * 1024 * 1024
_MIB = 1024 * 1024


@pytest.fixture
def api_env(monkeypatch, tmp_path):
    # Substrate-free route fixture (the tests/test_reading_state_routes.py
    # shape): ambient operator credentials must not turn it into a 401 suite.
    for variable in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(variable, raising=False)
    # Every storage root lives under tmp_path (the conftest already points
    # ANTIEK_HOME at tmp_path/home), so a scan of tmp_path covers them all.
    db = tmp_path / "db" / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    tmp = tmp_path / "tmp"
    for directory in (db.parent, events, arts, tmp):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    ensure_initialized(str(db))
    return {"root": tmp_path, "arts": arts, "tmp": tmp}


class _ProviderProbe:
    """Records whether and when the stubbed provider ran. ``sleep_s`` uses a
    blocking ``time.sleep`` on purpose: that is what a synchronous httpx call
    to Whisper or TTS does to whichever thread runs it."""

    def __init__(self, sleep_s: float = 0.0) -> None:
        self.sleep_s = sleep_s
        self.calls = 0
        self.audio_lengths: list[int] = []
        self.started_at: float | None = None
        self.ended_at: float | None = None

    def run(self) -> None:
        self.calls += 1
        self.started_at = time.monotonic()
        if self.sleep_s:
            time.sleep(self.sleep_s)
        self.ended_at = time.monotonic()


def _stub_whisper(monkeypatch, probe: _ProviderProbe) -> None:
    from acquisition.voice import client as voice_client

    class _StubWhisper:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def transcribe(self, audio_bytes, *, filename, language=None):
            probe.audio_lengths.append(len(audio_bytes))
            probe.run()
            return voice_client.Transcript(
                text="stub transcript", language="en", duration_seconds=1.5, model="stub"
            )

    # transcribe_audio() builds WhisperTranscriber() from its module global at
    # call time, so replacing the global stubs the provider on the route path.
    monkeypatch.setattr(voice_client, "WhisperTranscriber", _StubWhisper)


def _stub_tts(monkeypatch, probe: _ProviderProbe) -> None:
    from substrate.dispatch.providers.openai_tts import OpenAITTSProvider

    def _synthesize(self, text, *, model=None, voice=None, poster=None):
        probe.run()
        return b"ID3-stub-mp3"

    monkeypatch.setattr(OpenAITTSProvider, "synthesize", _synthesize)


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _health_while(client: httpx.AsyncClient, request) -> tuple[httpx.Response, list]:
    """Run ``request`` and keep ``GET /health`` in flight until it finishes.
    Returns the request's response and one (sent, done, status) per probe."""
    warm = await client.get("/health")
    assert warm.status_code == 200
    task = asyncio.create_task(request)
    beats: list[tuple[float, float, int]] = []
    while not task.done():
        sent = time.monotonic()
        response = await client.get("/health")
        beats.append((sent, time.monotonic(), response.status_code))
        await asyncio.sleep(0.02)
    return await task, beats


def _assert_health_stayed_responsive(probe: _ProviderProbe, beats: list) -> None:
    assert probe.calls == 1
    assert probe.started_at is not None and probe.ended_at is not None
    assert all(status == 200 for _, _, status in beats)
    # A /health that was SENT and ANSWERED while the provider was sleeping.
    # When the provider blocks the loop no coroutine can even send one inside
    # that window, so this is the load-bearing concurrency assertion, and it
    # does not depend on how fast the host is.
    inside = [
        done - sent
        for sent, done, _ in beats
        if sent >= probe.started_at and done <= probe.ended_at
    ]
    assert inside, "no /health completed while the provider call was in flight"
    # The acceptance: a concurrent /health completes within 200 ms. It is
    # asserted on the fastest in-window probe, not the slowest, because one
    # probe that loses the CPU to other processes on a loaded host (seen at
    # 0.2-0.85 s with load average ~37 on 12 cores) says nothing about the
    # event loop; a blocked loop makes every probe wait out the provider.
    fastest = min(inside)
    assert fastest < _HEALTH_BUDGET_S, (
        f"fastest in-window /health took {fastest:.3f}s (budget {_HEALTH_BUDGET_S}s); "
        f"in-window latencies: {[round(x, 3) for x in inside]}"
    )
    # No probe waited out the provider call: a parked loop holds the probe in
    # flight for the whole 2 s sleep.
    overlapping = [
        done - sent
        for sent, done, _ in beats
        if done >= probe.started_at and sent <= probe.ended_at
    ]
    slowest = max(overlapping)
    assert slowest < _PROVIDER_SLEEP_S, (
        f"/health took {slowest:.3f}s while the provider ran: parked behind the provider"
    )


# ── off the event loop ──────────────────────────────────────────────


async def test_health_answers_while_transcribe_provider_runs(api_env, monkeypatch):
    probe = _ProviderProbe(sleep_s=_PROVIDER_SLEEP_S)
    _stub_whisper(monkeypatch, probe)
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response, beats = await _health_while(
            client,
            client.post(
                "/voice/transcribe",
                content=b"\x1aE\xdf\xa3fake-webm",
                headers={"content-type": "audio/webm"},
            ),
        )
    assert response.status_code == 200
    assert response.json() == {
        "transcript": "stub transcript",
        "language": "en",
        "duration_seconds": 1.5,
    }
    _assert_health_stayed_responsive(probe, beats)


async def test_health_answers_while_tts_provider_runs(api_env, monkeypatch):
    probe = _ProviderProbe(sleep_s=_PROVIDER_SLEEP_S)
    _stub_tts(monkeypatch, probe)
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response, beats = await _health_while(
            client, client.post("/speech/tts", json={"text": "hello", "voice": "nova"})
        )
    assert response.status_code == 200
    assert response.content == b"ID3-stub-mp3"
    assert response.headers["content-type"] == "audio/mpeg"
    _assert_health_stayed_responsive(probe, beats)


async def test_tts_error_mapping_survives_the_thread_hop(api_env, monkeypatch):
    """RuntimeError (no key) is still 503 and ValueError still 400 when the
    provider raises from the worker thread."""
    from substrate.dispatch.providers.openai_tts import OpenAITTSProvider

    def _no_key(self, text, *, model=None, voice=None, poster=None):
        raise RuntimeError("OPENAI_API_KEY missing")

    def _bad_input(self, text, *, model=None, voice=None, poster=None):
        raise ValueError("cannot synthesize empty text")

    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        monkeypatch.setattr(OpenAITTSProvider, "synthesize", _no_key)
        unavailable = await client.post("/speech/tts", json={"text": "hi"})
        monkeypatch.setattr(OpenAITTSProvider, "synthesize", _bad_input)
        bad = await client.post("/speech/tts", json={"text": "hi"})
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "tts_unavailable: OPENAI_API_KEY missing"}
    assert bad.status_code == 400
    assert bad.json() == {"detail": "cannot synthesize empty text"}


# ── the 25 MiB transcribe bound ─────────────────────────────────────


async def test_transcribe_over_cap_is_413_before_provider(api_env, monkeypatch):
    probe = _ProviderProbe()
    _stub_whisper(monkeypatch, probe)
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response = await client.post(
            "/voice/transcribe",
            content=b"\0" * (_MAX_TRANSCRIBE_BYTES + 1),
            headers={"content-type": "audio/webm"},
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "too_large"}
    assert probe.calls == 0


@pytest.mark.parametrize(
    "declared",
    [None, "10", b"\xb2"],
    ids=["chunked", "lying_small_length", "unparseable_length"],
)
async def test_transcribe_chunked_over_cap_stops_reading_and_is_413(
    api_env, monkeypatch, declared
):
    """No usable Content-Length (a chunked upload, a header that under-states
    the body, or one that does not parse): the stream bound is the authority,
    and the route stops pulling the body once it passes 25 MiB instead of
    buffering the whole upload first."""
    probe = _ProviderProbe()
    _stub_whisper(monkeypatch, probe)
    pulled = 0

    async def _body() -> AsyncIterator[bytes]:
        nonlocal pulled
        for _ in range(64):  # 64 MiB offered
            pulled += 1
            yield b"\0" * _MIB

    headers: dict[str, str | bytes] = {"content-type": "audio/webm"}
    if declared is not None:
        headers["content-length"] = declared
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response = await client.post("/voice/transcribe", content=_body(), headers=headers)
    assert response.status_code == 413
    assert response.json() == {"detail": "too_large"}
    assert probe.calls == 0
    # 25 chunks reach the cap exactly; the 26th crosses it.
    assert pulled <= 26, f"route pulled {pulled} MiB past a 25 MiB cap"


async def test_transcribe_declared_over_cap_is_refused_before_reading(api_env, monkeypatch):
    """A Content-Length over the cap is refused without pulling one body chunk."""
    probe = _ProviderProbe()
    _stub_whisper(monkeypatch, probe)
    pulled = 0
    offered = 64

    async def _body() -> AsyncIterator[bytes]:
        nonlocal pulled
        for _ in range(offered):
            pulled += 1
            yield b"\0" * _MIB

    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response = await client.post(
            "/voice/transcribe",
            content=_body(),
            headers={"content-type": "audio/webm", "content-length": str(offered * _MIB)},
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "too_large"}
    assert probe.calls == 0
    assert pulled == 0


async def test_transcribe_exactly_at_cap_reaches_provider(api_env, monkeypatch):
    probe = _ProviderProbe()
    _stub_whisper(monkeypatch, probe)
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response = await client.post(
            "/voice/transcribe",
            content=b"\0" * _MAX_TRANSCRIBE_BYTES,
            headers={"content-type": "audio/webm"},
        )
    assert response.status_code == 200
    assert probe.calls == 1
    assert probe.audio_lengths == [_MAX_TRANSCRIBE_BYTES]


async def test_transcribe_unparseable_content_length_is_not_a_500(api_env, monkeypatch):
    """``"²".isdigit()`` is True but ``int("²")`` raises. A header the route
    cannot parse is ignored (the streamed count decides), never a crash."""
    probe = _ProviderProbe()
    _stub_whisper(monkeypatch, probe)
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response = await client.post(
            "/voice/transcribe",
            content=b"\x1aE\xdf\xa3fake-webm",
            headers={"content-type": "audio/webm", "content-length": b"\xb2"},
        )
    assert response.status_code == 200
    assert probe.calls == 1


async def test_transcribe_empty_body_is_still_400(api_env, monkeypatch):
    probe = _ProviderProbe()
    _stub_whisper(monkeypatch, probe)
    app = create_app(register_wrestling=False)
    async with _client(app) as client:
        response = await client.post("/voice/transcribe", content=b"")
    assert response.status_code == 400
    assert response.json() == {"detail": "empty_audio"}
    assert probe.calls == 0


# ── no audio kept ───────────────────────────────────────────────────


def _files_holding(root: Path, marker: bytes) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and marker in p.read_bytes()]


@pytest.mark.parametrize("outcome", ["ok", "provider_error", "too_large"])
async def test_transcribe_keeps_no_audio_on_disk(api_env, monkeypatch, outcome):
    """Drives the REAL WhisperTranscriber (multipart encode and all) against
    an in-process mock of the OpenAI endpoint, then scans every storage root
    for the audio's marker bytes."""
    marker = b"LB12-AUDIO-" + os.urandom(12).hex().encode()
    if outcome == "too_large":
        audio = marker * (_MAX_TRANSCRIBE_BYTES // len(marker) + 1)
        assert len(audio) > _MAX_TRANSCRIBE_BYTES
    else:
        audio = b"\x1aE\xdf\xa3" + marker * 64
    upstream: list[bool] = []

    def _openai(request: httpx.Request) -> httpx.Response:
        upstream.append(marker in request.read())
        if outcome == "ok":
            return httpx.Response(200, json={"text": "hello", "language": "en", "duration": 1.0})
        return httpx.Response(500, json={"error": "upstream failure"})

    from acquisition.voice import client as voice_client

    real_client = httpx.Client

    def _mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_openai)
        return real_client(*args, **kwargs)

    app = create_app(register_wrestling=False)
    # Set after create_app so no dispatch provider registers against the key;
    # WhisperTranscriber reads it per request.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-lb12-not-real")
    monkeypatch.setattr(voice_client.httpx, "Client", _mock_client)
    async with _client(app) as client:
        response = await client.post(
            "/voice/transcribe", content=audio, headers={"content-type": "audio/webm"}
        )

    if outcome == "ok":
        assert response.status_code == 200
        assert response.json()["transcript"] == "hello"
        assert upstream == [True]  # the provider really received the audio
    elif outcome == "provider_error":
        assert response.status_code == 503
        assert response.json()["detail"].startswith("transcription_unavailable:")
        assert upstream == [True]
    else:
        assert response.status_code == 413
        assert upstream == []
    assert tempfile.gettempdir() == str(api_env["tmp"])
    assert _files_holding(api_env["root"], marker) == []
