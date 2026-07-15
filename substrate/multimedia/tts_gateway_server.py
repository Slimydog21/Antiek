"""Durable paid-call authority behind the multimedia TTS gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from runtime.db_lock import FlockWriteCoordinator

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_AUDIO_BYTES = 64 * 1024 * 1024
_REQUEST_KEYS = {
    "asset_id", "channels", "chapter_id", "endpoint_capability", "model",
    "paragraph_ids", "provider", "revision_id", "route_policy", "sample_rate_hz",
    "schema_version", "script_line_ids", "source_chunk_ids", "speed", "text", "title",
    "voice",
}
_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_tts_gateway_submissions (
 idempotency_key TEXT PRIMARY KEY, account_identity_digest TEXT NOT NULL,
 request_body_digest TEXT NOT NULL, request_body_json TEXT NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
 client_request_id TEXT NOT NULL, provider_request_id TEXT,
 mime_type TEXT, audio_path TEXT, audio_sha256 TEXT, row_mac TEXT NOT NULL)
"""


class TTSGatewayServerError(RuntimeError):
    """The request cannot produce a proven completed synthesis."""


class TTSGatewayConflict(TTSGatewayServerError):
    """An idempotency authority conflicts with durable state."""


class TTSGatewayOutcomeUnknown(TTSGatewayServerError):
    """A paid submission may have reached the provider."""


@dataclass(frozen=True)
class ProviderSpeechResult:
    audio_bytes: bytes
    mime_type: str
    provider_request_id: str


@dataclass(frozen=True, repr=False)
class TTSGatewayServerRuntime:
    db_path: str
    output_dir: str
    integrity_key: bytes
    bearer_token: str
    account_identity_digest: str
    provider: str
    model: str
    logical_voice: str
    provider_voice: str
    synthesize: Callable[[Mapping[str, object], str, str], ProviderSpeechResult]


@dataclass(frozen=True)
class TTSGatewayCompleted:
    audio_bytes: bytes
    mime_type: str
    provider_request_id: str
    provider: str
    model: str
    request_body_digest: str


def synthesize_gateway_request(
    envelope: Mapping[str, object], *, idempotency_key: str, runtime: TTSGatewayServerRuntime
) -> TTSGatewayCompleted:
    _private_database(runtime.db_path)
    account, digest, body_json, body = _validate_request(
        envelope, idempotency_key=idempotency_key, runtime=runtime
    )
    client_request_id = _client_request_id(digest)
    values: list[object] = [
        idempotency_key, account, digest, body_json, runtime.provider, runtime.model,
        "sending", client_request_id, None, None, None, None,
    ]
    coordinator = FlockWriteCoordinator(runtime.db_path)
    with coordinator.acquire_write_context("multimedia_tts_gateway_claim") as connection:
        os.chmod(runtime.db_path, 0o600)
        _private_database(runtime.db_path)
        connection.execute(_DDL)
        row = connection.execute(
            "SELECT * FROM multimedia_tts_gateway_submissions WHERE idempotency_key=?",
            [idempotency_key],
        ).fetchone()
        if row is not None:
            return _replay(row, values[:6], runtime)
        connection.execute(
            "INSERT INTO multimedia_tts_gateway_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [*values, _row_mac(values, runtime.integrity_key)],
        )
    try:
        result = runtime.synthesize(body, client_request_id, runtime.provider_voice)
        _validate_provider_result(result)
        path, audio_digest = _seal_audio(
            result.audio_bytes, digest=digest, output_dir=runtime.output_dir
        )
        completed_values = [
            *values[:6], "completed", client_request_id, result.provider_request_id,
            result.mime_type, path, audio_digest,
        ]
        with coordinator.acquire_write_context("multimedia_tts_gateway_complete") as connection:
            updated = connection.execute(
                "UPDATE multimedia_tts_gateway_submissions SET status=?, provider_request_id=?, "
                "mime_type=?, audio_path=?, audio_sha256=?, row_mac=? "
                "WHERE idempotency_key=? AND status='sending' RETURNING 1",
                [
                    "completed", result.provider_request_id, result.mime_type, path, audio_digest,
                    _row_mac(completed_values, runtime.integrity_key), idempotency_key,
                ],
            ).fetchone()
            if updated is None:
                raise TTSGatewayOutcomeUnknown("TTS gateway completion state conflicts")
        return TTSGatewayCompleted(
            result.audio_bytes, result.mime_type, result.provider_request_id,
            runtime.provider, runtime.model, digest,
        )
    except Exception as exc:
        try:
            _mark_unknown(idempotency_key, runtime)
        except Exception as persistence_exc:
            raise TTSGatewayOutcomeUnknown(
                "TTS gateway outcome and durable state are unknown"
            ) from persistence_exc
        raise TTSGatewayOutcomeUnknown("TTS gateway provider outcome is unknown") from exc


def _validate_request(
    envelope: Mapping[str, object],
    *,
    idempotency_key: str,
    runtime: TTSGatewayServerRuntime,
) -> tuple[str, str, str, Mapping[str, object]]:
    required = {
        "account_identity_digest", "endpoint_capability", "model", "provider",
        "request_body", "request_body_digest", "schema_version",
    }
    if not isinstance(envelope, Mapping) or set(envelope) != required:
        raise ValueError("TTS gateway request shape is invalid")
    account = envelope["account_identity_digest"]
    digest = envelope["request_body_digest"]
    body = envelope["request_body"]
    if (
        envelope["schema_version"] != "antiek.tts-gateway-request.v1"
        or not isinstance(account, str) or account != runtime.account_identity_digest
        or not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
        or idempotency_key != f"antiek-tts-{digest}"
        or envelope["provider"] != runtime.provider
        or envelope["model"] != runtime.model
        or envelope["endpoint_capability"] != "text-to-speech"
        or not isinstance(body, Mapping) or set(body) != _REQUEST_KEYS
    ):
        raise ValueError("TTS gateway request authority is invalid")
    body_json = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if hashlib.sha256(body_json.encode("ascii")).hexdigest() != digest:
        raise ValueError("TTS gateway request digest is invalid")
    text = body.get("text")
    speed = body.get("speed")
    if (
        body.get("schema_version") != "antiek.chapter-tts-request.v1"
        or body.get("provider") != runtime.provider or body.get("model") != runtime.model
        or body.get("endpoint_capability") != "text-to-speech"
        or body.get("voice") != runtime.logical_voice
        or not isinstance(text, str) or not text.strip() or len(text) > 4096
        or isinstance(speed, bool) or not isinstance(speed, (int, float))
        or not 0.25 <= float(speed) <= 4
    ):
        raise ValueError("TTS gateway provider request is invalid")
    return account, digest, body_json, body


def _replay(
    row: tuple[object, ...],
    authority: Sequence[object],
    runtime: TTSGatewayServerRuntime,
) -> TTSGatewayCompleted:
    if (
        len(row) != 13
        or not isinstance(row[12], str)
        or not hmac.compare_digest(row[12], _row_mac(row[:12], runtime.integrity_key))
    ):
        raise TTSGatewayConflict("TTS gateway durable state integrity failed")
    if list(row[:6]) != authority:
        raise TTSGatewayConflict("TTS gateway idempotency replay conflicts")
    if row[6] != "completed":
        raise TTSGatewayOutcomeUnknown("TTS gateway submission outcome is unknown")
    audio = _read_audio(row[10], row[11], runtime.output_dir)
    completed_fields = row[9], row[8], row[4], row[5], row[2]
    if not all(isinstance(value, str) for value in completed_fields):
        raise TTSGatewayConflict("TTS gateway completed state is invalid")
    mime_type, provider_request_id, provider, model, digest = completed_fields
    assert isinstance(mime_type, str)
    assert isinstance(provider_request_id, str)
    assert isinstance(provider, str)
    assert isinstance(model, str)
    assert isinstance(digest, str)
    return TTSGatewayCompleted(audio, mime_type, provider_request_id, provider, model, digest)


def _validate_provider_result(result: object) -> None:
    if (
        not isinstance(result, ProviderSpeechResult)
        or not isinstance(result.audio_bytes, bytes) or not 0 < len(result.audio_bytes) <= _MAX_AUDIO_BYTES
        or result.mime_type not in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/flac", "audio/ogg"}
        or not isinstance(result.provider_request_id, str) or not _ID.fullmatch(result.provider_request_id)
    ):
        raise TTSGatewayOutcomeUnknown("TTS provider response is invalid")


def _seal_audio(audio: bytes, *, digest: str, output_dir: str) -> tuple[str, str]:
    root = _private_root(output_dir)
    final = root / f"{digest}.audio"
    temporary = root / f".{digest}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(audio)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, final)
    return str(final), hashlib.sha256(audio).hexdigest()


def _read_audio(path_value: object, expected_digest: object, output_dir: str) -> bytes:
    if not isinstance(path_value, str) or not isinstance(expected_digest, str):
        raise TTSGatewayConflict("TTS gateway completed artifact is invalid")
    root = _private_root(output_dir)
    path = Path(path_value)
    try:
        metadata = path.lstat()
        if path.parent.resolve(strict=True) != root or path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise OSError
        audio = path.read_bytes()
    except OSError:
        raise TTSGatewayConflict("TTS gateway completed artifact is unavailable") from None
    if not audio or len(audio) > _MAX_AUDIO_BYTES or hashlib.sha256(audio).hexdigest() != expected_digest:
        raise TTSGatewayConflict("TTS gateway completed artifact integrity failed")
    return audio


def _mark_unknown(key: str, runtime: TTSGatewayServerRuntime) -> None:
    coordinator = FlockWriteCoordinator(runtime.db_path)
    with coordinator.acquire_write_context("multimedia_tts_gateway_unknown") as connection:
        row = connection.execute(
            "SELECT * FROM multimedia_tts_gateway_submissions WHERE idempotency_key=?", [key]
        ).fetchone()
        if row is None or row[6] != "sending":
            return
        if not hmac.compare_digest(
            row[12], _row_mac(list(row[:12]), runtime.integrity_key)
        ):
            raise TTSGatewayConflict("TTS gateway durable state integrity failed")
        values = [*row[:6], "unknown", *row[7:12]]
        connection.execute(
            "UPDATE multimedia_tts_gateway_submissions SET status='unknown', row_mac=? WHERE idempotency_key=?",
            [_row_mac(values, runtime.integrity_key), key],
        )


def _client_request_id(digest: str) -> str:
    return f"antiek-{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _row_mac(values: Sequence[object], key: bytes) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _private_database(value: str) -> None:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise TTSGatewayConflict("TTS gateway database path is invalid")
    if not path.exists():
        try:
            parent = path.parent.lstat()
        except OSError:
            raise TTSGatewayConflict("TTS gateway database path is invalid") from None
        if (
            path.parent.is_symlink() or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise TTSGatewayConflict("TTS gateway database path is invalid")
        return
    try:
        metadata = path.lstat()
    except OSError:
        raise TTSGatewayConflict("TTS gateway database path is invalid") from None
    if (
        path.is_symlink() or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise TTSGatewayConflict("TTS gateway database path is invalid")


def _private_root(value: str) -> Path:
    path = Path(value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        raise TTSGatewayConflict("TTS gateway output directory is invalid") from None
    if (
        not path.is_absolute() or path.is_symlink() or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise TTSGatewayConflict("TTS gateway output directory is invalid")
    return resolved


__all__ = [
    "ProviderSpeechResult", "TTSGatewayCompleted", "TTSGatewayConflict",
    "TTSGatewayOutcomeUnknown", "TTSGatewayServerRuntime", "synthesize_gateway_request",
]
