"""Fixed HTTPS idempotent gateway adapter for paid chapter narration."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import IO

from .chapter_tts_production import (
    ChapterTTSSynthesisResult,
    PreparedChapterTTSRequest,
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_AUDIO_BYTES = 64 * 1024 * 1024
_MAX_RESPONSE_BYTES = 86 * 1024 * 1024
_MIME_TYPES = frozenset(
    {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/flac", "audio/ogg"}
)


class TTSSynthesisGatewayError(RuntimeError):
    """The gateway did not prove one completed exact synthesis."""


@dataclass(frozen=True)
class GatewayResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


GatewayPoster = Callable[[str, Mapping[str, str], bytes, float, int], GatewayResponse]


class TTSSynthesisGateway:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bearer_token: str,
        account_identity_digest: str,
        timeout_seconds: float = 60,
        poster: GatewayPoster | None = None,
    ) -> None:
        self._url = _https_url(endpoint_url)
        if (
            not isinstance(bearer_token, str)
            or not bearer_token
            or len(bearer_token) > 4096
            or any(character in bearer_token for character in "\r\n")
        ):
            raise ValueError("TTS gateway bearer token is invalid")
        if not isinstance(account_identity_digest, str) or not _DIGEST.fullmatch(
            account_identity_digest
        ):
            raise ValueError("TTS gateway account identity digest is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 1
            or timeout_seconds > 300
        ):
            raise ValueError("TTS gateway timeout must be between 1 and 300 seconds")
        self._token = bearer_token
        self._account_digest = account_identity_digest
        self._timeout = float(timeout_seconds)
        self._poster = poster or _post_https

    def __call__(self, request: PreparedChapterTTSRequest) -> ChapterTTSSynthesisResult:
        if not isinstance(request, PreparedChapterTTSRequest):
            raise TypeError("TTS gateway requires a prepared chapter request")
        body_digest = request.body_digest
        envelope = {
            "account_identity_digest": self._account_digest,
            "endpoint_capability": request.endpoint_capability,
            "model": request.model,
            "provider": request.provider,
            "request_body": json.loads(request.body_json),
            "request_body_digest": body_digest,
            "schema_version": "antiek.tts-gateway-request.v1",
        }
        body = json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"antiek-tts-{body_digest}",
        }
        try:
            response = self._poster(
                self._url, headers, body, self._timeout, _MAX_RESPONSE_BYTES
            )
        except Exception as exc:
            raise TTSSynthesisGatewayError("TTS gateway submission outcome is unknown") from exc
        if not isinstance(response, GatewayResponse):
            raise TTSSynthesisGatewayError("TTS gateway response is invalid")
        if response.status_code < 200 or response.status_code >= 300:
            raise TTSSynthesisGatewayError("TTS gateway did not complete synthesis")
        content_type = next(
            (
                value
                for key, value in response.headers.items()
                if key.lower() == "content-type"
            ),
            "",
        )
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise TTSSynthesisGatewayError("TTS gateway response is not JSON")
        if not isinstance(response.body, bytes) or len(response.body) > _MAX_RESPONSE_BYTES:
            raise TTSSynthesisGatewayError("TTS gateway response exceeds its byte ceiling")
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TTSSynthesisGatewayError("TTS gateway response is malformed") from exc
        required = {
            "audio_base64",
            "mime_type",
            "model",
            "provider",
            "provider_request_id",
            "request_body_digest",
            "schema_version",
            "status",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise TTSSynthesisGatewayError("TTS gateway response shape is invalid")
        if (
            value["schema_version"] != "antiek.tts-gateway-response.v1"
            or value["status"] != "completed"
            or value["request_body_digest"] != body_digest
            or value["provider"] != request.provider
            or value["model"] != request.model
            or not isinstance(value["provider_request_id"], str)
            or not _ID.fullmatch(value["provider_request_id"])
            or value["mime_type"] not in _MIME_TYPES
            or not isinstance(value["audio_base64"], str)
        ):
            raise TTSSynthesisGatewayError("TTS gateway response authority conflicts")
        try:
            audio = base64.b64decode(value["audio_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise TTSSynthesisGatewayError("TTS gateway audio is malformed") from exc
        if not audio or len(audio) > _MAX_AUDIO_BYTES:
            raise TTSSynthesisGatewayError("TTS gateway audio exceeds its byte ceiling")
        return ChapterTTSSynthesisResult(
            audio_bytes=audio,
            provider_request_id=value["provider_request_id"],
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def _post_https(
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout_seconds: float,
    response_byte_ceiling: int,
) -> GatewayResponse:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            response_headers = {str(key): str(value) for key, value in response.headers.items()}
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > response_byte_ceiling:
                raise TTSSynthesisGatewayError(
                    "TTS gateway response exceeds its byte ceiling"
                )
            payload = response.read(response_byte_ceiling + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        response_headers = {str(key): str(value) for key, value in exc.headers.items()}
        payload = exc.read(response_byte_ceiling + 1)
    if len(payload) > response_byte_ceiling:
        raise TTSSynthesisGatewayError("TTS gateway response exceeds its byte ceiling")
    return GatewayResponse(status, response_headers, payload)


def _https_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("TTS gateway URL is invalid")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port not in {None, 443}
    ):
        raise ValueError("TTS gateway URL must be a fixed HTTPS endpoint")
    return urllib.parse.urlunsplit(parsed)


__all__ = [
    "GatewayPoster",
    "GatewayResponse",
    "TTSSynthesisGateway",
    "TTSSynthesisGatewayError",
]
