"""Reviewed Krea capability subset pinned to one official OpenAPI digest."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

OPENAPI_SOURCE_URL = "https://api.krea.ai/openapi.json"
OPENAPI_SUBSET_SHA256 = "ac30291d0e814be871c732f14eb045e801f13358497fdd08489054f8df2e8a19"
CATALOG_VERSION = "2026-07-11.ac30291d"
_RUNWAY_ASPECT_RATIOS = frozenset(
    {"1280:720", "720:1280", "1104:832", "832:1104", "960:960", "1584:672", "672:1584"}
)
_CATALOG: dict[str, dict[str, Any]] = {
    "imagen-3": {
        "endpoint": "/generate/image/google/imagen-3",
        "endpoint_capability": "text-to-image",
        "openapi_subset_sha256": OPENAPI_SUBSET_SHA256,
        "pricing_provenance": "operator-signed microdollar quote; successful Krea jobs charged",
        "schema": {"prompt": "nonempty", "width": [512, 8192], "height": [512, 8192]},
    },
    "runway-gen-4.5": {
        "endpoint": "/generate/video/runway/gen-4.5",
        "endpoint_capability": "text-to-video",
        "openapi_subset_sha256": OPENAPI_SUBSET_SHA256,
        "pricing_provenance": "operator-signed microdollar quote; successful Krea jobs charged",
        "schema": {"prompt": "nonempty", "duration": [2, 10], "aspect_ratio": sorted(_RUNWAY_ASPECT_RATIOS)},
    },
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


CATALOG_DIGEST = hashlib.sha256(
    _canonical({"version": CATALOG_VERSION, "capabilities": _CATALOG})
).hexdigest()


@dataclass(frozen=True)
class Imagen3Request:
    prompt: str
    width: int = 1024
    height: int = 1024
    seed: int = 1337


@dataclass(frozen=True)
class RunwayGen45Request:
    prompt: str
    duration: int = 5
    aspect_ratio: str = "1280:720"
    seed: int | None = None


@dataclass(frozen=True)
class PreparedKreaRequest:
    model: str
    endpoint_capability: str
    endpoint: str
    body: bytes
    body_digest: str
    catalog_version: str
    catalog_digest: str


@dataclass(frozen=True)
class KreaQuote:
    version: int
    quote_id: str
    model: str
    endpoint_capability: str
    catalog_version: str
    catalog_digest: str
    request_body_digest: str
    ceiling_microdollars: int
    pricing_source: str
    issued_at: str
    expires_at: str
    signature: str


def prepare_request(request: Imagen3Request | RunwayGen45Request) -> PreparedKreaRequest:
    """Validate the reviewed subset and produce exact canonical provider bytes."""
    if isinstance(request, Imagen3Request):
        _prompt(request.prompt)
        _bounded_integer("width", request.width, 512, 8192)
        _bounded_integer("height", request.height, 512, 8192)
        _integer("seed", request.seed)
        model = "imagen-3"
        body_value: dict[str, object] = {
            "height": request.height,
            "prompt": request.prompt,
            "seed": request.seed,
            "width": request.width,
        }
    elif isinstance(request, RunwayGen45Request):
        _prompt(request.prompt)
        _bounded_integer("duration", request.duration, 2, 10)
        if request.aspect_ratio not in _RUNWAY_ASPECT_RATIOS:
            raise ValueError("aspect_ratio is not supported by the pinned Runway catalog")
        if request.seed is not None:
            _integer("seed", request.seed)
        model = "runway-gen-4.5"
        body_value = {
            "aspect_ratio": request.aspect_ratio,
            "duration": request.duration,
            "prompt": request.prompt,
        }
        if request.seed is not None:
            body_value["seed"] = request.seed
    else:
        raise TypeError("request is not a pinned Krea capability")
    entry = _CATALOG[model]
    body = _canonical(body_value)
    return PreparedKreaRequest(
        model=model,
        endpoint_capability=str(entry["endpoint_capability"]),
        endpoint=str(entry["endpoint"]),
        body=body,
        body_digest=hashlib.sha256(body).hexdigest(),
        catalog_version=CATALOG_VERSION,
        catalog_digest=CATALOG_DIGEST,
    )


def extract_reviewed_openapi_paths(document: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the reviewed request and response contract from a fresh OpenAPI document."""
    paths = document.get("paths")
    if not isinstance(paths, Mapping):
        raise ValueError("OpenAPI document has no paths object")
    extracted: dict[str, Any] = {}
    for endpoint in sorted(entry["endpoint"] for entry in _CATALOG.values()):
        try:
            post = paths[endpoint]["post"]
            request_schema = post["requestBody"]["content"]["application/json"]["schema"]
            response_schema = post["responses"]["200"]["content"]["application/json"]["schema"]
            properties = response_schema["properties"]
            statuses = properties["status"]["enum"]
            job_format = properties["job_id"]["format"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"OpenAPI endpoint {endpoint} has an unexpected shape") from exc
        extracted[endpoint] = {
            "request_schema": request_schema,
            "response": {"job_id": job_format, "status": statuses},
        }
    return extracted


def issue_quote(
    *,
    signing_key: bytes,
    prepared: PreparedKreaRequest,
    ceiling_microdollars: int,
    issued_at: datetime,
    expires_at: datetime,
) -> KreaQuote:
    """Issue one independently verifiable quote for exact provider bytes."""
    _key(signing_key)
    if (
        isinstance(ceiling_microdollars, bool)
        or not isinstance(ceiling_microdollars, int)
        or ceiling_microdollars <= 0
    ):
        raise ValueError("ceiling_microdollars must be a positive integer")
    issued = _timestamp(issued_at)
    expires = _timestamp(expires_at)
    if _parse_timestamp(expires) <= _parse_timestamp(issued):
        raise ValueError("quote expiry must follow issuance")
    fields: dict[str, object] = {
        "version": 1,
        "model": prepared.model,
        "endpoint_capability": prepared.endpoint_capability,
        "catalog_version": prepared.catalog_version,
        "catalog_digest": prepared.catalog_digest,
        "request_body_digest": prepared.body_digest,
        "ceiling_microdollars": ceiling_microdollars,
        "pricing_source": "operator-approved Krea API quote",
        "issued_at": issued,
        "expires_at": expires,
    }
    quote_id = "kreaquote_" + hashlib.sha256(_canonical(fields)).hexdigest()
    signed = {**fields, "quote_id": quote_id}
    return KreaQuote(
        version=1,
        quote_id=quote_id,
        model=prepared.model,
        endpoint_capability=prepared.endpoint_capability,
        catalog_version=prepared.catalog_version,
        catalog_digest=prepared.catalog_digest,
        request_body_digest=prepared.body_digest,
        ceiling_microdollars=ceiling_microdollars,
        pricing_source="operator-approved Krea API quote",
        issued_at=issued,
        expires_at=expires,
        signature=hmac.new(signing_key, _canonical(signed), hashlib.sha256).hexdigest(),
    )


def verify_quote(
    quote: KreaQuote,
    *,
    signing_key: bytes,
    prepared: PreparedKreaRequest,
    expected_quote_id: str,
    expected_expires_at: str,
    expected_ceiling_microdollars: int,
    now: datetime,
) -> None:
    _key(signing_key)
    fields: dict[str, object] = {
        "version": quote.version,
        "model": quote.model,
        "endpoint_capability": quote.endpoint_capability,
        "catalog_version": quote.catalog_version,
        "catalog_digest": quote.catalog_digest,
        "request_body_digest": quote.request_body_digest,
        "ceiling_microdollars": quote.ceiling_microdollars,
        "pricing_source": quote.pricing_source,
        "issued_at": quote.issued_at,
        "expires_at": quote.expires_at,
    }
    expected_id = "kreaquote_" + hashlib.sha256(_canonical(fields)).hexdigest()
    signed = {**fields, "quote_id": quote.quote_id}
    expected_signature = hmac.new(signing_key, _canonical(signed), hashlib.sha256).hexdigest()
    if quote.quote_id != expected_id or not hmac.compare_digest(
        quote.signature, expected_signature
    ):
        raise ValueError("Krea quote signature or identity is invalid")
    bindings = (
        (quote.quote_id, expected_quote_id),
        (quote.model, prepared.model),
        (quote.endpoint_capability, prepared.endpoint_capability),
        (quote.catalog_version, prepared.catalog_version),
        (quote.catalog_digest, prepared.catalog_digest),
        (quote.request_body_digest, prepared.body_digest),
        (quote.expires_at, expected_expires_at),
        (quote.ceiling_microdollars, expected_ceiling_microdollars),
    )
    if any(actual != expected for actual, expected in bindings):
        raise ValueError("Krea quote does not match signed execution authority")
    checked_at = _aware(now)
    if checked_at < _parse_timestamp(quote.issued_at) or checked_at >= _parse_timestamp(
        quote.expires_at
    ):
        raise ValueError("Krea quote is not active")


def _prompt(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("prompt must be a nonempty canonical string")
    return value


def _integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _bounded_integer(name: str, value: object, minimum: int, maximum: int) -> int:
    number = _integer(name, value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} is outside the pinned capability range")
    return number


def _key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("quote signing key must contain at least 32 bytes")
    return value


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if _timestamp(parsed) != value:
        raise ValueError("timestamp must be canonical UTC")
    return parsed


__all__ = [
    "CATALOG_DIGEST",
    "CATALOG_VERSION",
    "OPENAPI_SOURCE_URL",
    "OPENAPI_SUBSET_SHA256",
    "Imagen3Request",
    "KreaQuote",
    "PreparedKreaRequest",
    "RunwayGen45Request",
    "issue_quote",
    "extract_reviewed_openapi_paths",
    "prepare_request",
    "verify_quote",
]
