"""One-shot Krea HTTP submission with a fixed production origin."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

KREA_API_ORIGIN = "https://api.krea.ai"
MAX_RESPONSE_BYTES = 64 * 1024
_ENDPOINTS = frozenset({"/generate/image/google/imagen-3", "/generate/video/runway/gen-4.5"})
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


@dataclass(frozen=True)
class KreaJobObservation:
    job_id: str
    status: str
    results: tuple[str, ...]
    raw_digest: str
    account_identity_digest: str


class KreaClient:
    """Submit exactly one reviewed request; this class contains no retry loop."""

    def __init__(self, api_token: str) -> None:
        self._origin = KREA_API_ORIGIN
        self._api_token = _token(api_token)
        token_id = self._api_token.split(":", 1)[0]
        self.account_identity_digest = hashlib.sha256(token_id.encode()).hexdigest()

    def poll(self, job_id: str) -> KreaJobObservation:
        """Perform one bounded fixed-origin GET. No retry and no redirect."""
        canonical = _job_id(job_id)
        payload = self._request("GET", f"/jobs/{canonical}")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise KreaClientError("malformed_json") from None
        if not isinstance(value, dict):
            raise KreaClientError("malformed_response")
        if set(value) - {"job_id", "status", "created_at", "completed_at", "result", "error"}:
            raise KreaClientError("malformed_response")
        if "created_at" not in value:
            raise KreaClientError("malformed_response")
        returned_id, status = value.get("job_id"), value.get("status")
        if returned_id != canonical or not isinstance(status, str) or status not in _STATUSES:
            raise KreaClientError("invalid_job_response")
        _canonical_timestamp(value["created_at"], field="created_at")
        completed_at = value.get("completed_at")
        if completed_at is not None:
            _canonical_timestamp(completed_at, field="completed_at")
        _validate_error(value.get("error"))
        results = _result_urls(value.get("result"))
        return KreaJobObservation(
            canonical,
            status,
            tuple(results),
            hashlib.sha256(payload).hexdigest(),
            self.account_identity_digest,
        )

    def _request(self, method: str, path: str) -> bytes:
        timeout = httpx.Timeout(connect=3.0, read=20.0, write=10.0, pool=3.0)
        try:
            with (
                httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client,
                client.stream(
                    method,
                    self._origin + path,
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Accept": "application/json",
                    },
                ) as response,
            ):
                if response.is_redirect:
                    raise KreaClientError("redirect_refused", status_code=response.status_code)
                if response.status_code != 200:
                    raise KreaClientError(
                        _http_error_kind(response.status_code), status_code=response.status_code
                    )
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        length = int(declared)
                    except ValueError:
                        raise KreaClientError("invalid_content_length") from None
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise KreaClientError("response_too_large")
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise KreaClientError("response_too_large")
                return bytes(payload)
        except KreaClientError:
            raise
        except httpx.RequestError:
            raise KreaClientError("transport_ambiguous") from None

    def submit(self, *, endpoint: str, body: bytes) -> KreaSubmissionResponse:
        if endpoint not in _ENDPOINTS:
            raise ValueError("endpoint is not in the pinned Krea allowlist")
        if not isinstance(body, bytes) or not body or len(body) > 64 * 1024:
            raise ValueError("canonical request body must be bounded nonempty bytes")
        timeout = httpx.Timeout(connect=3.0, read=20.0, write=10.0, pool=3.0)
        try:
            with (
                httpx.Client(
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST",
                    self._origin + endpoint,
                    content=body,
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Content-Type": "application/json",
                    },
                ) as response,
            ):
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
    token_id, secret = value.split(":", 1)
    if not token_id or not secret:
        raise ValueError("Krea API token must use the canonical id:secret form")
    return value


def _job_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("job_id must be a canonical UUID")
    try:
        canonical = str(uuid.UUID(value))
    except ValueError:
        raise ValueError("job_id must be a canonical UUID") from None
    if canonical != value:
        raise ValueError("job_id must be a canonical UUID")
    return canonical


def _result_urls(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or set(value) - {"urls", "style_id"}:
        raise KreaClientError("invalid_results")
    raw = value.get("urls")
    style_id = value.get("style_id")
    if style_id is not None and (
        not isinstance(style_id, str) or not style_id or len(style_id) > 4096
    ):
        raise KreaClientError("invalid_results")
    if raw is None:
        return ()
    urls: list[object]
    if isinstance(raw, list):
        urls = []
        for item in raw:
            if isinstance(item, str):
                urls.append(item)
            elif (
                isinstance(item, dict)
                and set(item) == {"type", "url"}
                and item.get("type") in {"model", "preview"}
            ):
                urls.append(item.get("url"))
            else:
                raise KreaClientError("invalid_results")
    elif isinstance(raw, dict) and all(isinstance(key, str) for key in raw):
        urls = [raw[key] for key in sorted(raw)]
    else:
        raise KreaClientError("invalid_results")
    if len(urls) > 8 or any(not _valid_uri(url) for url in urls):
        raise KreaClientError("invalid_results")
    return tuple(urls)  # type: ignore[arg-type]


def _valid_uri(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 4096:
        return False
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(parsed.scheme and (parsed.netloc or parsed.path))


def _canonical_timestamp(value: object, *, field: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ) is None:
        raise KreaClientError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise KreaClientError(f"invalid_{field}") from None
    if parsed.tzinfo != UTC:
        raise KreaClientError(f"invalid_{field}")


def _validate_error(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - {"code", "message"} or "code" not in value:
        raise KreaClientError("invalid_error")
    code, message = value["code"], value.get("message")
    if not isinstance(code, str) or not code or len(code) > 256:
        raise KreaClientError("invalid_error")
    if message is not None and (not isinstance(message, str) or len(message) > 4096):
        raise KreaClientError("invalid_error")


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
    "KreaJobObservation",
    "KreaSubmissionResponse",
]
