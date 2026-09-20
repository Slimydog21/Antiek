"""Anti-Ek honesty API contracts — tip-honest field shapes (no fake money).

Frozen required keys for envelopes shipped #3213–#3219. Callers validate
live payloads against these sets; they never invent CPM, Synquery partnership,
G2 counsel flips, or ``production_default_mount``.

Cite: docs/specs/anti-ek-honesty-api-contracts-2026-09-19.md
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# --- Ads (#3213) ---
ADS_HONESTY_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "surface",
        "serving_model",
        "max_sdk_on_web",
        "fill_ladder",
        "price_status_default",
        "revenue_usd_cents_until_pricing",
        "settlement_open",
        "paid_fill_gated",
        "paid_fill_requires",
        "paid_fill_default",
        "applovin_alignment",
        "money_model",
        "paid_fill_decision_ref",
    }
)

# --- Speak G2 / Synquery (#3214) ---
G2_SYNQUERY_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "surface",
        "g2_counsel_gated",
        "synquery_gated",
        "synquery_partnership",
        "money_model",
        "paid_today",
        "disbursement_allowed",
        "public_publishing_allowed",
        "g2_requires",
        "synquery_requires",
        "decision_refs",
    }
)

# --- BYOT hard refuse (#3216) ---
CAPACITY_EXHAUSTED_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "code",
        "message",
        "used_compute_units",
        "monthly_compute_units",
        "enforcement",
        "used_status",
        "retryable",
    }
)
CAPACITY_EXHAUSTED_CODE = "compute_capacity_exhausted"

# --- HTML projection honesty (#3219) ---
HTML_PROJECTION_HEADER = "X-Antiek-Html-Projection"
HTML_INLINE_ARTIFACT_PATHS: tuple[str, ...] = (
    "/api/syntheses/{synthesis_id}/artifact.html",
    "/api/deliverables/{deliverable_id}/artifact.html",
    "/api/notebooks/{notebook_id}/artifact.html",
    "/research/{investigation_id}/artifact.html",
)


class HonestyContractError(ValueError):
    """Payload missing required honesty keys or violating invariants."""


def _missing(payload: Mapping[str, Any], required: frozenset[str]) -> list[str]:
    return sorted(k for k in required if k not in payload)


def assert_ads_honesty_shape(payload: Mapping[str, Any]) -> None:
    miss = _missing(payload, ADS_HONESTY_REQUIRED_KEYS)
    if miss:
        raise HonestyContractError(f"ads honesty missing keys: {miss}")
    if payload.get("paid_fill_gated") is not True:
        raise HonestyContractError("paid_fill_gated must be True (scaffold gated)")
    if payload.get("max_sdk_on_web") is not False:
        raise HonestyContractError("max_sdk_on_web must be False (no MAX on web)")
    if payload.get("revenue_usd_cents_until_pricing") != 0:
        raise HonestyContractError("no fake cents until pricing")
    if payload.get("paid_fill_default") != "unpriced_zero":
        raise HonestyContractError("paid_fill_default must be unpriced_zero")
    if payload.get("settlement_open") is not False:
        raise HonestyContractError("settlement_open must default False")


def assert_g2_synquery_honesty_shape(payload: Mapping[str, Any]) -> None:
    miss = _missing(payload, G2_SYNQUERY_REQUIRED_KEYS)
    if miss:
        raise HonestyContractError(f"g2/synquery honesty missing keys: {miss}")
    if payload.get("money_model") != "accrue_escrow_now_disburse_after_legal_review":
        raise HonestyContractError("money_model must be accrue-escrow (not paid today)")
    # When gated, paid_today must be false — never invent cash. This check
    # was unsatisfiable while the producer hardcoded False; it is meaningful
    # now that the value is derived from disbursement state.
    if payload.get("g2_counsel_gated") and payload.get("paid_today") is not False:
        raise HonestyContractError("paid_today must be False while G2 counsel gated")
    # And never claim a payment this envelope cannot see. It is DB-free, so
    # True is a value it has no standing to emit: False when provably gated,
    # None when it cannot know. A True here means someone wired a claim to a
    # source that is not the payouts ledger.
    if payload.get("paid_today") is True:
        raise HonestyContractError(
            "paid_today cannot be True in a DB-free honesty envelope — it "
            "cannot observe the payouts ledger; emit None for unknown"
        )
    if payload.get("synquery_gated") and payload.get("synquery_partnership") == "live":
        raise HonestyContractError("synquery_partnership cannot be live while gated")


def assert_capacity_exhausted_shape(payload: Mapping[str, Any]) -> None:
    miss = _missing(payload, CAPACITY_EXHAUSTED_REQUIRED_KEYS)
    if miss:
        raise HonestyContractError(f"capacity_exhausted missing keys: {miss}")
    if payload.get("code") != CAPACITY_EXHAUSTED_CODE:
        raise HonestyContractError(
            f"code must be {CAPACITY_EXHAUSTED_CODE!r}, got {payload.get('code')!r}"
        )
    if payload.get("retryable") is not False:
        raise HonestyContractError("capacity exhausted is not retryable without top-up")


def assert_html_projection_header(value: str, *, disposition: str) -> None:
    """``script-free; disposition=inline|attachment`` — no invented trust bits."""
    expected = f"script-free; disposition={disposition}"
    if value != expected:
        raise HonestyContractError(
            f"HTML projection header must be {expected!r}, got {value!r}"
        )


def html_projection_response_headers(
    *,
    filename: str,
    disposition: str,
) -> dict[str, str]:
    """Shared HTTP headers for View HTML / export — tip-honest Specs contract.

    All four artifact surfaces (research / synthesis / deliverable / notebook)
    must emit ``X-Antiek-Html-Projection`` with this form. Do not invent a
    second projection header name.
    """
    if disposition not in {"inline", "attachment"}:
        raise HonestyContractError(
            f"disposition must be inline|attachment, got {disposition!r}"
        )
    if not filename or "/" in filename or chr(92) in filename:
        raise HonestyContractError(f"unsafe Content-Disposition filename: {filename!r}")
    value = f"script-free; disposition={disposition}"
    assert_html_projection_header(value, disposition=disposition)
    return {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        HTML_PROJECTION_HEADER: value,
    }


__all__ = [
    "ADS_HONESTY_REQUIRED_KEYS",
    "CAPACITY_EXHAUSTED_CODE",
    "CAPACITY_EXHAUSTED_REQUIRED_KEYS",
    "G2_SYNQUERY_REQUIRED_KEYS",
    "HTML_INLINE_ARTIFACT_PATHS",
    "HTML_PROJECTION_HEADER",
    "HonestyContractError",
    "assert_ads_honesty_shape",
    "assert_capacity_exhausted_shape",
    "assert_g2_synquery_honesty_shape",
    "assert_html_projection_header",
    "html_projection_response_headers",
]
