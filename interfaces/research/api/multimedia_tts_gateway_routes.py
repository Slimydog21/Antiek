"""Authenticated HTTP server and production transport for chapter TTS."""

from __future__ import annotations

import base64
import os
import secrets
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints

from substrate.multimedia.tts_gateway_server import (
    ProviderSpeechResult,
    TTSGatewayConflict,
    TTSGatewayOutcomeUnknown,
    TTSGatewayServerRuntime,
    synthesize_gateway_request,
)

_PREFIX = "ANTIEK_MULTIMEDIA_TTS_GATEWAY_"
_FIELDS = (
    "DB_PATH", "OUTPUT_DIR", "INTEGRITY_KEY_HEX", "BEARER_TOKEN",
    "ACCOUNT_IDENTITY_DIGEST", "OPENAI_API_KEY", "MODEL", "LOGICAL_VOICE",
    "PROVIDER_VOICE", "TIMEOUT_SECONDS",
)
_MAX_PROVIDER_BYTES = 64 * 1024 * 1024


BoundedId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]


class ChapterTTSRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: BoundedId
    channels: Literal[1, 2]
    chapter_id: BoundedId
    endpoint_capability: Literal["text-to-speech"]
    model: str = Field(min_length=1, max_length=128)
    paragraph_ids: list[BoundedId] = Field(min_length=1, max_length=4096)
    provider: Literal["openai"]
    revision_id: BoundedId
    route_policy: Literal["cheapest", "balanced", "highest_quality"]
    sample_rate_hz: int = Field(ge=8000, le=48000, strict=True)
    schema_version: Literal["antiek.chapter-tts-request.v1"]
    script_line_ids: list[BoundedId] = Field(min_length=1, max_length=4096)
    source_chunk_ids: list[BoundedId] = Field(min_length=1, max_length=4096)
    speed: Annotated[StrictInt | StrictFloat, Field(ge=0.25, le=4)]
    text: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=512)
    voice: str = Field(min_length=1, max_length=128)


class TTSGatewayRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["antiek.tts-gateway-request.v1"]
    account_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    endpoint_capability: Literal["text-to-speech"]
    model: str = Field(min_length=1, max_length=128)
    provider: Literal["openai"]
    request_body: ChapterTTSRequestBody
    request_body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class TTSGatewayResponseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "antiek.tts-gateway-response.v1"
    status: str = "completed"
    request_body_digest: str
    provider: str
    model: str
    provider_request_id: str
    mime_type: str
    audio_base64: str


def get_multimedia_tts_gateway_runtime() -> TTSGatewayServerRuntime:
    raise HTTPException(status_code=503, detail="multimedia TTS gateway is unavailable")


multimedia_tts_gateway_router = APIRouter(tags=["multimedia-tts-gateway"])


@multimedia_tts_gateway_router.post(
    "/tts-gateway/synthesize", response_model=TTSGatewayResponseBody
)
def synthesize_multimedia_tts(
    body: TTSGatewayRequestBody,
    authorization: str = Header(default=""),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    runtime: TTSGatewayServerRuntime = Depends(get_multimedia_tts_gateway_runtime),
) -> TTSGatewayResponseBody:
    scheme, separator, credential = authorization.partition(" ")
    if (
        separator != " " or scheme.lower() != "bearer" or not credential
        or not secrets.compare_digest(credential, runtime.bearer_token)
    ):
        raise HTTPException(status_code=401, detail="TTS gateway authentication failed")
    try:
        result = synthesize_gateway_request(
            body.model_dump(mode="python"), idempotency_key=idempotency_key, runtime=runtime
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="TTS gateway request is invalid") from exc
    except TTSGatewayConflict as exc:
        raise HTTPException(status_code=409, detail="TTS gateway authority conflicts") from exc
    except TTSGatewayOutcomeUnknown as exc:
        raise HTTPException(status_code=503, detail="TTS gateway outcome is unknown") from exc
    return TTSGatewayResponseBody(
        request_body_digest=result.request_body_digest,
        provider=result.provider,
        model=result.model,
        provider_request_id=result.provider_request_id,
        mime_type=result.mime_type,
        audio_base64=base64.b64encode(result.audio_bytes).decode("ascii"),
    )


def multimedia_tts_gateway_runtime_from_environment(
    environ: Mapping[str, str] | None = None,
    *, transport: httpx.BaseTransport | None = None,
) -> TTSGatewayServerRuntime | None:
    values = os.environ if environ is None else environ
    fields = {name: values.get(f"{_PREFIX}{name}", "").strip() for name in _FIELDS}
    if not any(fields.values()):
        return None
    if any(not value for value in fields.values()):
        raise RuntimeError("multimedia TTS gateway configuration is incomplete")
    try:
        key = bytes.fromhex(fields["INTEGRITY_KEY_HEX"])
        timeout = float(fields["TIMEOUT_SECONDS"])
    except ValueError:
        raise RuntimeError("multimedia TTS gateway configuration is invalid") from None
    account = fields["ACCOUNT_IDENTITY_DIGEST"]
    if (
        len(key) < 32 or len(account) != 64
        or any(character not in "0123456789abcdef" for character in account)
        or not 1 <= timeout <= 300
        or fields["MODEL"] not in {
            "gpt-4o-mini-tts", "gpt-4o-mini-tts-2025-12-15", "tts-1", "tts-1-hd"
        }
        or len(fields["BEARER_TOKEN"]) > 4096
        or any(character in fields["BEARER_TOKEN"] for character in "\r\n")
        or any(character in fields["OPENAI_API_KEY"] for character in "\r\n")
        or not 1 <= len(fields["LOGICAL_VOICE"]) <= 128
        or fields["PROVIDER_VOICE"] not in {
            "alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova",
            "sage", "shimmer", "verse", "marin", "cedar",
        }
        or secrets.compare_digest(fields["BEARER_TOKEN"], fields["OPENAI_API_KEY"])
    ):
        raise RuntimeError("multimedia TTS gateway configuration is invalid")
    _private_directory(fields["OUTPUT_DIR"])
    _private_parent(fields["DB_PATH"])

    def synthesize(
        request_body: Mapping[str, object], client_request_id: str, provider_voice: str
    ) -> ProviderSpeechResult:
        payload = {
            "input": request_body["text"], "model": request_body["model"],
            "response_format": "mp3", "speed": request_body["speed"],
            "voice": provider_voice,
        }
        headers = {
            "Authorization": f"Bearer {fields['OPENAI_API_KEY']}",
            "Content-Type": "application/json", "X-Client-Request-Id": client_request_id,
        }
        with httpx.Client(
            base_url="https://api.openai.com/v1", follow_redirects=False,
            trust_env=False, timeout=timeout, transport=transport,
        ) as client, client.stream(
            "POST", "/audio/speech", headers=headers, json=payload, timeout=timeout,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError("TTS provider refused synthesis")
            provider_request_id = response.headers.get("x-request-id", "")
            mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > _MAX_PROVIDER_BYTES:
                        raise RuntimeError("TTS provider response exceeds byte ceiling")
                except ValueError:
                    raise RuntimeError("TTS provider response length is invalid") from None
            audio = bytearray()
            for chunk in response.iter_bytes():
                audio.extend(chunk)
                if len(audio) > _MAX_PROVIDER_BYTES:
                    raise RuntimeError("TTS provider response exceeds byte ceiling")
        return ProviderSpeechResult(bytes(audio), mime_type, provider_request_id)

    return TTSGatewayServerRuntime(
        db_path=fields["DB_PATH"], output_dir=fields["OUTPUT_DIR"], integrity_key=key,
        bearer_token=fields["BEARER_TOKEN"], account_identity_digest=account,
        provider="openai", model=fields["MODEL"], logical_voice=fields["LOGICAL_VOICE"],
        provider_voice=fields["PROVIDER_VOICE"], synthesize=synthesize,
    )


def _private_directory(value: str) -> None:
    path = Path(value)
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError("multimedia TTS gateway private directory is invalid") from None
    if (
        not path.is_absolute() or path.is_symlink() or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("multimedia TTS gateway private directory is invalid")


def _private_parent(value: str) -> None:
    path = Path(value)
    if not path.is_absolute() or (path.exists() and path.is_symlink()):
        raise RuntimeError("multimedia TTS gateway database path is invalid")
    _private_directory(str(path.parent))


__all__ = [
    "TTSGatewayRequestBody", "TTSGatewayResponseBody", "get_multimedia_tts_gateway_runtime",
    "multimedia_tts_gateway_router", "multimedia_tts_gateway_runtime_from_environment",
]
