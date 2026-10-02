"""Contract tests — Anti-Ek honesty API shapes (#3213–#3219).

Encodes product rules: no fake cents, no invented Synquery/G2 flips,
structured capacity exhausted, HTML projection disposition honesty.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from substrate.ad_inventory.rank0_honesty import website_ads_honesty
from substrate.compute_capacity.acu_meter import (
    CapacityGateResult,
    capacity_exhausted_payload,
)
from substrate.compute_capacity.store import CapacityEvaluation, ComputeCapacity
from substrate.contracts.anti_ek_honesty import (
    CAPACITY_EXHAUSTED_CODE,
    HTML_INLINE_ARTIFACT_PATHS,
    HTML_PROJECTION_HEADER,
    HonestyContractError,
    assert_ads_honesty_shape,
    assert_capacity_exhausted_shape,
    assert_g2_synquery_honesty_shape,
    assert_html_projection_header,
    html_projection_response_headers,
)
from substrate.speak.g2_synquery_honesty import g2_synquery_honesty


def test_ads_honesty_envelope_matches_contract():
    h = website_ads_honesty()
    assert_ads_honesty_shape(h)
    bad = dict(h)
    bad["revenue_usd_cents_until_pricing"] = 99
    with pytest.raises(HonestyContractError, match="no fake cents"):
        assert_ads_honesty_shape(bad)


def test_g2_synquery_honesty_envelope_matches_contract(monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    monkeypatch.delenv("ANTIEK_SYNQUERY_ENABLED", raising=False)
    h = g2_synquery_honesty()
    assert_g2_synquery_honesty_shape(h)
    assert h["paid_today"] is False
    assert h["g2_counsel_gated"] is True
    assert h["synquery_gated"] is True


def test_capacity_exhausted_payload_matches_contract():
    cap = ComputeCapacity(
        owner_user_id="o",
        tier="custom",
        monthly_compute_units=5,
        used_compute_units=5,
        used_status="known",
        enforcement="hard",
        updated_at=None,
        is_default=False,
    )
    ev = CapacityEvaluation(
        allowed=False,
        soft_over=True,
        would_hard_block=True,
        enforcement="hard",
        used_status="known",
        note="hard_block",
    )
    gate = CapacityGateResult(
        verdict="hard_refuse",
        capacity=cap,
        evaluation=ev,
        warning=None,
        detail=CAPACITY_EXHAUSTED_CODE,
    )
    payload = capacity_exhausted_payload(gate)
    assert_capacity_exhausted_shape(payload)
    bad = dict(payload)
    bad["retryable"] = True
    with pytest.raises(HonestyContractError, match="not retryable"):
        assert_capacity_exhausted_shape(bad)


def test_html_projection_header_contract():
    assert_html_projection_header(
        "script-free; disposition=inline", disposition="inline"
    )
    assert_html_projection_header(
        "script-free; disposition=attachment", disposition="attachment"
    )
    with pytest.raises(HonestyContractError):
        assert_html_projection_header("unsafe", disposition="inline")


def _collect_route_paths(routes: Iterable[Any]) -> set[str]:
    """Walk FastAPI APIRoute + ``_IncludedRouter.original_router`` (no OAS)."""
    out: set[str] = set()
    for r in routes:
        p = getattr(r, "path", None)
        if isinstance(p, str) and p:
            out.add(p)
        orig = getattr(r, "original_router", None)
        if orig is not None:
            out |= _collect_route_paths(getattr(orig, "routes", []) or [])
        subs = getattr(r, "routes", None)
        if subs:
            out |= _collect_route_paths(subs)
    return out


def test_html_inline_artifact_paths_registered_on_app():
    """Route inventory — View HTML paths exist (contract vs route drift)."""
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[]
    )
    paths = _collect_route_paths(app.routes)
    for template in HTML_INLINE_ARTIFACT_PATHS:
        assert template in paths, f"missing honesty route {template}"
    assert HTML_PROJECTION_HEADER == "X-Antiek-Html-Projection"


def test_html_projection_response_headers_helper():
    h = html_projection_response_headers(
        filename="research-inv-1.html", disposition="inline"
    )
    assert h["X-Antiek-Html-Projection"] == "script-free; disposition=inline"
    assert 'inline; filename="research-inv-1.html"' in h["Content-Disposition"]
    with pytest.raises(HonestyContractError):
        html_projection_response_headers(filename="../x.html", disposition="inline")


# ── paid_today must not outlive its evidence ────────────────────────────────


def _live_disbursement(monkeypatch):
    """Flip the gate the way an operator would, without touching real state."""
    from substrate.speak import g2_synquery_honesty as mod

    class _Allowed:
        allowed = True

    # Both gates move together — the module notes "same operator flip post
    # G2+G3". Flipping only disbursement leaves g2_counsel_gated True, and the
    # contract then (correctly) demands paid_today be False.
    monkeypatch.setattr(mod._gs, "disbursement_allowed", lambda: _Allowed())
    monkeypatch.setattr(mod._gs, "public_publishing_allowed", lambda: _Allowed())
    return mod


def test_paid_today_is_false_only_while_disbursement_is_gated():
    from substrate.speak.g2_synquery_honesty import g2_synquery_honesty

    h = g2_synquery_honesty()
    assert h["disbursement"] == "gated_G2_G3_accrue_escrow_only"
    assert h["paid_today"] is False, (
        "while gated, no money can move — False is provable here"
    )


def test_paid_today_becomes_unknown_once_disbursement_goes_live(monkeypatch):
    """The bug: a bare False survived the operator flipping the gate.

    This envelope is deliberately DB-free, so once disbursement is live it
    cannot see whether anything was paid — that lives in
    substrate/payouts/ledger.py. Emitting False there tells a contributor
    they were not paid when they may have been.
    """
    mod = _live_disbursement(monkeypatch)

    h = mod.g2_synquery_honesty()

    assert h["disbursement"] == "live", "fixture must actually flip the gate"
    assert h["paid_today"] is None, (
        "paid_today stayed False after disbursement went live — a claim this "
        "DB-free envelope has no standing to make"
    )


def test_contract_rejects_a_payload_claiming_a_payment_it_cannot_see():
    """True is not an available value: the envelope cannot observe the ledger."""
    from substrate.contracts.anti_ek_honesty import (
        HonestyContractError,
        assert_g2_synquery_honesty_shape,
    )
    from substrate.speak.g2_synquery_honesty import g2_synquery_honesty

    payload = dict(g2_synquery_honesty())
    payload["g2_counsel_gated"] = False
    payload["paid_today"] = True

    with pytest.raises(HonestyContractError, match="cannot be True"):
        assert_g2_synquery_honesty_shape(payload)


def test_contract_still_rejects_paid_today_not_false_while_gated():
    """The original invariant, now reachable because the value is derived."""
    from substrate.contracts.anti_ek_honesty import (
        HonestyContractError,
        assert_g2_synquery_honesty_shape,
    )
    from substrate.speak.g2_synquery_honesty import g2_synquery_honesty

    payload = dict(g2_synquery_honesty())
    assert payload["g2_counsel_gated"] is True, "fixture assumes the gated default"
    payload["paid_today"] = None  # unknown is wrong while gated: it IS knowable

    with pytest.raises(HonestyContractError, match="must be False while G2"):
        assert_g2_synquery_honesty_shape(payload)
