"""Pure signed-quote authority for authenticated interactive research.

This module performs no I/O, reads no environment variables, and grants no
provider authority by itself. API wiring must inject a dedicated key and must
persist only ``quote_id``/``payload_sha256`` after accepting a quote.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from typing import Any

from .router import DispatchConfig, TierConfig, pricing_authority

_DOMAIN = b"antiek.research-quote.v1\x00"
_SCHEMA_VERSION = 2
_MAX_TTL_MS = 15 * 60 * 1000


class ResearchQuoteInvalid(ValueError):
    """The quote is malformed, untrusted, stale, or context-mismatched."""


@dataclass(frozen=True)
class ResearchRouteQuote:
    role: str
    fallback_index: int
    logical_tier_name: str
    provider: str
    model: str
    route_tier_name: str
    max_output_tokens: int
    temperature: float
    context_budget_tokens: int
    pricing_fingerprint: str
    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: float
    currency: str
    billing_unit: str
    source_url: str
    verified_at: str
    expires_at: str


@dataclass(frozen=True)
class ResearchRouteManifest:
    routes: tuple[ResearchRouteQuote, ...]
    fingerprint: str


@dataclass(frozen=True)
class ResearchQuoteReceipt:
    quote_id: str
    payload_sha256: str
    account_id: str
    prompt_sha256: str
    research_tier: str
    route_manifest_fingerprint: str
    approved_run_ceiling_usd: str
    issued_at_ms: int
    expires_at_ms: int
    nonce: str
    selected_driver_role: str | None = None
    selected_driver_provider: str | None = None
    selected_driver_model: str | None = None
    selected_driver_pricing_fingerprint: str | None = None


def _selected_driver_payload(
    *,
    manifest: ResearchRouteManifest,
    role: str | None,
    provider: str | None,
    model: str | None,
    pricing_fingerprint: str | None,
) -> dict[str, str] | None:
    values = (role, provider, model, pricing_fingerprint)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ResearchQuoteInvalid("exact research driver identity is incomplete")
    exact = {
        "role": _bounded_text(role or "", "selected_driver_role", maximum=128),
        "provider": _bounded_text(
            provider or "", "selected_driver_provider", maximum=256
        ),
        "model": _bounded_text(model or "", "selected_driver_model"),
        "pricing_fingerprint": _bounded_text(
            pricing_fingerprint or "",
            "selected_driver_pricing_fingerprint",
            maximum=64,
        ),
    }
    matches = [
        row
        for row in manifest.routes
        if row.role == exact["role"]
        and row.provider == exact["provider"]
        and row.model == exact["model"]
        and row.pricing_fingerprint == exact["pricing_fingerprint"]
    ]
    if len(matches) != 1:
        raise ResearchQuoteInvalid(
            "exact research driver is not a unique canonical manifest route"
        )
    return exact


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not value or len(value) > 32_768:
        raise ResearchQuoteInvalid("research quote token is malformed")
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise ResearchQuoteInvalid("research quote token is malformed") from exc


def _bounded_text(value: str, name: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > maximum:
        raise ResearchQuoteInvalid(f"{name} is invalid")
    return value


def _ceiling_text(value: float) -> str:
    if (
        type(value) not in (int, float)
        or not math.isfinite(float(value))
        or not 0.01 <= float(value) <= 100.0
    ):
        raise ResearchQuoteInvalid("approved run ceiling is invalid")
    return f"{float(value):.2f}"


def build_research_route_manifest(config: DispatchConfig) -> ResearchRouteManifest:
    """Resolve every role's ordered primary/fallback route with exact pricing."""
    rows: list[ResearchRouteQuote] = []
    for role in sorted(config.role_tiers):
        tier_name = config.role_tiers[role]
        current: TierConfig | None = config.tiers.get(tier_name)
        if current is None:
            raise ResearchQuoteInvalid(f"role {role!r} references an unknown tier")
        seen: set[int] = set()
        fallback_index = 0
        while current is not None:
            identity = id(current)
            if identity in seen:
                raise ResearchQuoteInvalid("route fallback cycle detected")
            seen.add(identity)
            valid, reason, fingerprint = pricing_authority(
                provider=current.provider,
                model=current.model,
                pricing=current.pricing,
            )
            if not valid or current.provider is None or current.model is None:
                raise ResearchQuoteInvalid(
                    f"route pricing authority unavailable: {reason}"
                )
            if type(current.max_tokens) is not int or current.max_tokens <= 0:
                raise ResearchQuoteInvalid("route output-token maximum is invalid")
            rows.append(
                ResearchRouteQuote(
                    role=role,
                    fallback_index=fallback_index,
                    logical_tier_name=tier_name,
                    provider=current.provider,
                    model=current.model,
                    route_tier_name=current.name,
                    max_output_tokens=current.max_tokens,
                    temperature=current.temperature,
                    context_budget_tokens=current.context_budget_tokens,
                    pricing_fingerprint=fingerprint,
                    input_per_mtok=current.pricing.input_per_mtok,
                    output_per_mtok=current.pricing.output_per_mtok,
                    cached_input_per_mtok=current.pricing.cached_input_per_mtok,
                    currency=current.pricing.currency,
                    billing_unit=current.pricing.billing_unit,
                    source_url=current.pricing.source_url,
                    verified_at=current.pricing.verified_at,
                    expires_at=current.pricing.expires_at,
                )
            )
            current = current.fallback
            fallback_index += 1
    body = [row.__dict__ for row in rows]
    return ResearchRouteManifest(
        routes=tuple(rows),
        fingerprint=_sha256(b"antiek.research-route-manifest.v1\x00" + _canonical(body)),
    )


def issue_research_quote(
    *,
    account_id: str,
    prompt: str,
    research_tier: str,
    manifest: ResearchRouteManifest,
    approved_run_ceiling_usd: float,
    issued_at_ms: int,
    expires_at_ms: int,
    nonce: str,
    key_id: str,
    signing_key: bytes,
    selected_driver_role: str | None = None,
    selected_driver_provider: str | None = None,
    selected_driver_model: str | None = None,
    selected_driver_pricing_fingerprint: str | None = None,
) -> tuple[str, ResearchQuoteReceipt]:
    account = _bounded_text(account_id, "account_id")
    tier = _bounded_text(research_tier, "research_tier", maximum=64)
    nonce_value = _bounded_text(nonce, "nonce", maximum=256)
    kid = _bounded_text(key_id, "key_id", maximum=128)
    if type(signing_key) is not bytes or len(signing_key) < 32:
        raise ResearchQuoteInvalid("a 256-bit research quote signing key is required")
    if type(issued_at_ms) is not int or type(expires_at_ms) is not int:
        raise ResearchQuoteInvalid("research quote timestamps are invalid")
    if not issued_at_ms < expires_at_ms <= issued_at_ms + _MAX_TTL_MS:
        raise ResearchQuoteInvalid("research quote lifetime is invalid")
    if not manifest.routes or len(manifest.fingerprint) != 64:
        raise ResearchQuoteInvalid("research route manifest is invalid")
    selected_driver = _selected_driver_payload(
        manifest=manifest,
        role=selected_driver_role,
        provider=selected_driver_provider,
        model=selected_driver_model,
        pricing_fingerprint=selected_driver_pricing_fingerprint,
    )
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "account_id": account,
        "prompt_sha256": _sha256(prompt.encode("utf-8")),
        "research_tier": tier,
        "route_manifest_fingerprint": manifest.fingerprint,
        "approved_run_ceiling_usd": _ceiling_text(approved_run_ceiling_usd),
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
        "nonce": nonce_value,
        "key_id": kid,
        "selected_driver": selected_driver,
    }
    payload_bytes = _canonical(payload)
    signature = hmac.digest(signing_key, _DOMAIN + payload_bytes, "sha256")
    token = f"rq1.{_b64encode(payload_bytes)}.{_b64encode(signature)}"
    payload_sha256 = _sha256(payload_bytes)
    receipt = ResearchQuoteReceipt(
        quote_id=_sha256(b"antiek.research-quote-id.v1\x00" + payload_bytes),
        payload_sha256=payload_sha256,
        account_id=account,
        prompt_sha256=payload["prompt_sha256"],
        research_tier=tier,
        route_manifest_fingerprint=manifest.fingerprint,
        approved_run_ceiling_usd=payload["approved_run_ceiling_usd"],
        issued_at_ms=issued_at_ms,
        expires_at_ms=expires_at_ms,
        nonce=nonce_value,
        selected_driver_role=(selected_driver or {}).get("role"),
        selected_driver_provider=(selected_driver or {}).get("provider"),
        selected_driver_model=(selected_driver or {}).get("model"),
        selected_driver_pricing_fingerprint=(selected_driver or {}).get(
            "pricing_fingerprint"
        ),
    )
    return token, receipt


def verify_research_quote(
    token: str,
    *,
    account_id: str,
    prompt: str,
    research_tier: str,
    manifest: ResearchRouteManifest,
    approved_run_ceiling_usd: float,
    now_ms: int,
    verification_keys: dict[str, bytes],
    selected_driver_role: str | None = None,
    selected_driver_provider: str | None = None,
    selected_driver_model: str | None = None,
    selected_driver_pricing_fingerprint: str | None = None,
    allow_expired: bool = False,
) -> ResearchQuoteReceipt:
    try:
        prefix, payload_text, signature_text = token.split(".")
    except (AttributeError, ValueError) as exc:
        raise ResearchQuoteInvalid("research quote token is malformed") from exc
    if prefix != "rq1" or type(now_ms) is not int:
        raise ResearchQuoteInvalid("research quote token is malformed")
    payload_bytes = _b64decode(payload_text)
    signature = _b64decode(signature_text)
    try:
        payload = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchQuoteInvalid("research quote token is malformed") from exc
    if type(payload) is not dict or _canonical(payload) != payload_bytes:
        raise ResearchQuoteInvalid("research quote payload is not canonical")
    version = payload.get("schema_version")
    expected_keys = {
        "schema_version", "account_id", "prompt_sha256", "research_tier",
        "route_manifest_fingerprint", "approved_run_ceiling_usd", "issued_at_ms",
        "expires_at_ms", "nonce", "key_id",
    }
    if version == 2:
        expected_keys.add("selected_driver")
    if set(payload) != expected_keys or version not in {1, 2}:
        raise ResearchQuoteInvalid("research quote payload schema is invalid")
    key = verification_keys.get(payload.get("key_id"))
    if type(key) is not bytes or len(key) < 32:
        raise ResearchQuoteInvalid("research quote signing key is unavailable")
    expected_signature = hmac.digest(key, _DOMAIN + payload_bytes, "sha256")
    if not hmac.compare_digest(signature, expected_signature):
        raise ResearchQuoteInvalid("research quote signature is invalid")
    expected = {
        "account_id": _bounded_text(account_id, "account_id"),
        "prompt_sha256": _sha256(prompt.encode("utf-8")),
        "research_tier": _bounded_text(research_tier, "research_tier", maximum=64),
        "route_manifest_fingerprint": manifest.fingerprint,
        "approved_run_ceiling_usd": _ceiling_text(approved_run_ceiling_usd),
    }
    expected_driver = _selected_driver_payload(
        manifest=manifest,
        role=selected_driver_role,
        provider=selected_driver_provider,
        model=selected_driver_model,
        pricing_fingerprint=selected_driver_pricing_fingerprint,
    )
    actual_driver = payload.get("selected_driver") if version == 2 else None
    if actual_driver != expected_driver:
        raise ResearchQuoteInvalid("research quote selected_driver does not match")
    for field, value in expected.items():
        actual = payload.get(field)
        if type(actual) is not str or not hmac.compare_digest(actual, value):
            raise ResearchQuoteInvalid(f"research quote {field} does not match")
    issued = payload.get("issued_at_ms")
    expires = payload.get("expires_at_ms")
    if type(issued) is not int or type(expires) is not int or not issued < expires:
        raise ResearchQuoteInvalid("research quote timestamps are invalid")
    if now_ms < issued or (now_ms >= expires and not allow_expired):
        raise ResearchQuoteInvalid("research quote is not currently valid")
    nonce = _bounded_text(payload.get("nonce"), "nonce", maximum=256)
    return ResearchQuoteReceipt(
        quote_id=_sha256(b"antiek.research-quote-id.v1\x00" + payload_bytes),
        payload_sha256=_sha256(payload_bytes),
        account_id=expected["account_id"],
        prompt_sha256=expected["prompt_sha256"],
        research_tier=expected["research_tier"],
        route_manifest_fingerprint=expected["route_manifest_fingerprint"],
        approved_run_ceiling_usd=expected["approved_run_ceiling_usd"],
        issued_at_ms=issued,
        expires_at_ms=expires,
        nonce=nonce,
        selected_driver_role=(expected_driver or {}).get("role"),
        selected_driver_provider=(expected_driver or {}).get("provider"),
        selected_driver_model=(expected_driver or {}).get("model"),
        selected_driver_pricing_fingerprint=(expected_driver or {}).get(
            "pricing_fingerprint"
        ),
    )
