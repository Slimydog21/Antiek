"""Authenticated provider-account recovery for job-less TTS submissions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from .provider_execution import ProviderExecutionRecord, ProviderExecutionStatus
from .tts_reconciliation import sign_provider_recovery_evidence

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_AUDIO_BYTES = 64 * 1024 * 1024
_MAX_RESPONSE_BYTES = 86 * 1024 * 1024


class ProviderRecoveryError(RuntimeError):
    """Provider-account evidence is absent, ambiguous, or untrustworthy."""


@dataclass(frozen=True)
class ProviderRecoveryLookup:
    execution_id: str
    authorization_id: str
    operator_identity_digest: str
    asset_id: str
    revision_id: str
    provider: str
    request_body_digest: str

    def to_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RecoveredProviderAudio:
    provider_request_id: str
    audio_bytes: bytes
    evidence_source: str
    external_signature: str
    recorded_at: datetime


class RecoveryTransport(Protocol):
    def __call__(self, lookup: ProviderRecoveryLookup) -> bytes:
        """Return one bounded JSON provider-account lookup response."""


class HttpProviderRecoveryTransport:
    """POST an exact idempotency lookup to a fixed authenticated HTTPS gateway."""

    def __init__(
        self,
        *,
        endpoint: str,
        bearer_token: str,
        allowed_host: str,
        timeout_seconds: float = 15.0,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self._endpoint = _endpoint(endpoint, allowed_host)
        token = bearer_token.strip()
        if not token or len(token) > 4096 or "\n" in token or "\r" in token:
            raise ValueError("provider recovery token is invalid")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("provider recovery timeout is invalid")
        self._token = token
        self._timeout = timeout_seconds
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=self._timeout, follow_redirects=False)
        )

    def __call__(self, lookup: ProviderRecoveryLookup) -> bytes:
        try:
            with (
                self._client_factory() as client,
                client.stream(
                    "POST",
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=lookup.to_dict(),
                ) as response,
            ):
                    if response.status_code == 404:
                        raise ProviderRecoveryError("provider recovery evidence is unavailable")
                    if response.status_code != 200:
                        raise ProviderRecoveryError("provider recovery gateway rejected the lookup")
                    declared = response.headers.get("content-length")
                    if declared is not None and (not declared.isdigit() or int(declared) > _MAX_RESPONSE_BYTES):
                        raise ProviderRecoveryError("provider recovery response is too large")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > _MAX_RESPONSE_BYTES:
                            raise ProviderRecoveryError("provider recovery response is too large")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except ProviderRecoveryError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise ProviderRecoveryError("provider recovery gateway is unavailable") from exc


class ProviderAccountRecoveryAdapter:
    """Normalize one authenticated provider-account match into signed Antiek evidence."""

    def __init__(
        self,
        *,
        transport: RecoveryTransport,
        antiek_owner_identity_digest: str,
        account_identity_digest: str,
        evidence_key: bytes,
    ) -> None:
        if not _DIGEST.fullmatch(antiek_owner_identity_digest):
            raise ValueError("Antiek recovery owner identity digest is invalid")
        if not _DIGEST.fullmatch(account_identity_digest):
            raise ValueError("provider account identity digest is invalid")
        if not isinstance(evidence_key, bytes) or len(evidence_key) < 32:
            raise ValueError("provider recovery evidence key is invalid")
        self._transport = transport
        self._antiek_owner_digest = antiek_owner_identity_digest
        self._account_digest = account_identity_digest
        self._evidence_key = evidence_key

    def resolve(
        self, execution: ProviderExecutionRecord, *, verified_at: datetime
    ) -> RecoveredProviderAudio:
        if (
            execution.status is not ProviderExecutionStatus.OUTCOME_UNKNOWN
            or execution.provider_job_id is not None
        ):
            raise ProviderRecoveryError("execution is not eligible for provider recovery")
        operator_digest = hashlib.sha256(execution.operator_id.strip().encode("utf-8")).hexdigest()
        if operator_digest != self._antiek_owner_digest:
            raise ProviderRecoveryError("execution is unavailable for provider recovery")
        lookup = ProviderRecoveryLookup(
            execution_id=execution.execution_id,
            authorization_id=execution.authorization_id,
            operator_identity_digest=operator_digest,
            asset_id=execution.asset_id,
            revision_id=execution.revision_id,
            provider=execution.provider,
            request_body_digest=execution.request_body_digest,
        )
        payload = _decode_json(self._transport(lookup))
        if set(payload) != {"schema_version", "matches"} or payload["schema_version"] != "antiek.provider-recovery-response.v1":
            raise ProviderRecoveryError("provider recovery response schema is invalid")
        matches = payload["matches"]
        if not isinstance(matches, list) or len(matches) != 1 or not isinstance(matches[0], dict):
            raise ProviderRecoveryError("provider recovery result is absent or ambiguous")
        match = matches[0]
        required = {
            "execution_id", "authorization_id", "operator_identity_digest", "asset_id", "revision_id",
            "provider", "request_body_digest", "account_identity_digest", "provider_request_id",
            "evidence_source", "audio_base64", "audio_sha256", "recorded_at",
        }
        if set(match) != required:
            raise ProviderRecoveryError("provider recovery match schema is invalid")
        for field, expected in lookup.to_dict().items():
            if match[field] != expected:
                raise ProviderRecoveryError("provider recovery identity conflicts")
        if match["account_identity_digest"] != self._account_digest:
            raise ProviderRecoveryError("provider recovery account conflicts")
        provider_request_id = _identifier(match["provider_request_id"])
        evidence_source = _identifier(match["evidence_source"])
        audio = _audio(match["audio_base64"])
        if match["audio_sha256"] != hashlib.sha256(audio).hexdigest():
            raise ProviderRecoveryError("provider recovery audio digest conflicts")
        recorded_at = _timestamp(match["recorded_at"])
        checked_at = _aware_utc(verified_at)
        if recorded_at > checked_at:
            raise ProviderRecoveryError("provider recovery evidence is from the future")
        execution_updated = _timestamp(execution.updated_at)
        if recorded_at < execution_updated:
            raise ProviderRecoveryError("provider recovery evidence predates unknown execution")
        return RecoveredProviderAudio(
            provider_request_id=provider_request_id,
            audio_bytes=audio,
            evidence_source=evidence_source,
            external_signature=sign_provider_recovery_evidence(
                evidence_key=self._evidence_key,
                execution_id=execution.execution_id,
                provider_request_id=provider_request_id,
                evidence_source=evidence_source,
                audio_bytes=audio,
                recorded_at=recorded_at,
            ),
            recorded_at=recorded_at,
        )


def _decode_json(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_RESPONSE_BYTES:
        raise ProviderRecoveryError("provider recovery response is invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ProviderRecoveryError):
        raise ProviderRecoveryError("provider recovery response is invalid") from None
    if not isinstance(value, dict):
        raise ProviderRecoveryError("provider recovery response is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProviderRecoveryError("provider recovery response has duplicate fields")
        result[key] = value
    return result


def _audio(value: object) -> bytes:
    if not isinstance(value, str) or not value or len(value) > ((_MAX_AUDIO_BYTES + 2) // 3) * 4:
        raise ProviderRecoveryError("provider recovery audio is invalid")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ProviderRecoveryError("provider recovery audio is invalid") from None
    if not 0 < len(decoded) <= _MAX_AUDIO_BYTES:
        raise ProviderRecoveryError("provider recovery audio is invalid")
    return decoded


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ProviderRecoveryError("provider recovery identifier is invalid")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProviderRecoveryError("provider recovery timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProviderRecoveryError("provider recovery timestamp is invalid") from None
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProviderRecoveryError("provider recovery timestamp is invalid")
    return value.astimezone(UTC)


def _endpoint(value: str, allowed_host: str) -> str:
    host = allowed_host.strip().lower().rstrip(".")
    parts = urlsplit(value.strip())
    candidate = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or not host
        or candidate != host
        or "." not in candidate
        or candidate == "localhost"
        or candidate.endswith((".localhost", ".local", ".internal"))
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or not parts.path.startswith("/")
        or parts.path == "/"
        or parts.port not in (None, 443)
    ):
        raise ValueError("provider recovery endpoint is invalid")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("provider recovery endpoint is invalid")
    return value.strip()


__all__ = [
    "HttpProviderRecoveryTransport",
    "ProviderAccountRecoveryAdapter",
    "ProviderRecoveryError",
    "ProviderRecoveryLookup",
    "RecoveredProviderAudio",
    "RecoveryTransport",
]
