"""One-shot Krea HTTP submission with a fixed production origin."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import httpx

KREA_API_ORIGIN = "https://api.krea.ai"
MAX_RESPONSE_BYTES = 64 * 1024
_ENDPOINTS = frozenset(
    {"/generate/image/google/imagen-3", "/generate/video/runway/gen-4.5"}
)
_STATUSES = frozenset(
    {
        "backlogged",
        "queued",
        "scheduled",
        "processing",
        "sampling",
        "intermediate-complete",
        "completed",
        "failed",
        "cancelled",
    }
)


class KreaClientError(RuntimeError):
    """A safe submission failure that never embeds response or credential data."""

    def __init__(self, kind: str, *, status_code: int | None = None) -> None:
        self.kind = kind
        self.status_code = status_code
        message = f"Krea submission failed: {kind}"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        super().__init__(message)


@dataclass(frozen=True)
class KreaSubmissionResponse:
    job_id: str
    status: str
    http_status: int


class KreaClient:
    """Submit exactly one reviewed request; this class contains no retry loop."""

    def __init__(self, api_token: str) -> None:
        self._origin = KREA_API_ORIGIN
        self._api_token = _token(api_token)

    def submit(self, *, endpoint: str, body: bytes) -> KreaSubmissionResponse:
        if endpoint not in _ENDPOINTS:
            raise ValueError("endpoint is not in the pinned Krea allowlist")
        if not isinstance(body, bytes) or not body or len(body) > 64 * 1024:
            raise ValueError("canonical request body must be bounded nonempty bytes")
        timeout = httpx.Timeout(connect=3.0, read=20.0, write=10.0, pool=3.0)
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client, client.stream(
                "POST",
                self._origin + endpoint,
                content=body,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.is_redirect:
                    raise KreaClientError("redirect_refused", status_code=response.status_code)
                if response.status_code != 200:
                    raise KreaClientError(
                        _http_error_kind(response.status_code),
                        status_code=response.status_code,
                    )
                length = response.headers.get("Content-Length")
                if length is not None:
                    try:
                        declared_length = int(length)
                    except ValueError:
                        raise KreaClientError("invalid_content_length") from None
                    if declared_length < 0 or declared_length > MAX_RESPONSE_BYTES:
                        raise KreaClientError("response_too_large")
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise KreaClientError("response_too_large")
        except KreaClientError:
            raise
        except httpx.RequestError:
            raise KreaClientError("transport_ambiguous") from None
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise KreaClientError("malformed_json") from None
        if not isinstance(value, dict):
            raise KreaClientError("malformed_response")
        job_id = value.get("job_id")
        status = value.get("status")
        if not isinstance(job_id, str) or not isinstance(status, str):
            raise KreaClientError("malformed_response")
        try:
            canonical_job_id = str(uuid.UUID(job_id))
        except ValueError:
            raise KreaClientError("invalid_job_id") from None
        if canonical_job_id != job_id or status not in _STATUSES:
            raise KreaClientError("invalid_job_response")
        return KreaSubmissionResponse(job_id=job_id, status=status, http_status=200)


def _token(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or ":" not in value
        or len(value) > 4096
        or any(character in value for character in "\r\n")
    ):
        raise ValueError("Krea API token must use the canonical id:secret form")
    return value


def _http_error_kind(status_code: int) -> str:
    return {
        400: "request_rejected",
        401: "authentication_rejected",
        402: "balance_insufficient",
        429: "rate_limited",
    }.get(status_code, "provider_unavailable" if status_code >= 500 else "http_error")


__all__ = [
    "KREA_API_ORIGIN",
    "MAX_RESPONSE_BYTES",
    "KreaClient",
    "KreaClientError",
    "KreaSubmissionResponse",
]
