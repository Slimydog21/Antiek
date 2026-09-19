"""Contract tests — Anti-Ek honesty API shapes (#3213–#3219).

Encodes product rules: no fake cents, no invented Synquery/G2 flips,
structured capacity exhausted, HTML projection disposition honesty.
"""

from __future__ import annotations

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


def test_html_inline_artifact_paths_registered_on_app():
    """Route inventory — View HTML paths exist (contract vs OpenAPI drift)."""
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[]
    )
    paths = {getattr(r, "path", None) for r in app.routes}
    for template in HTML_INLINE_ARTIFACT_PATHS:
        assert template in paths, f"missing honesty route {template}"
    assert HTML_PROJECTION_HEADER == "X-Antiek-Html-Projection"
    # Smoke: OpenAPI lists artifact.html operations (no silent drift)
    schema = app.openapi()
    paths_oas = schema.get("paths") or {}
    for template in HTML_INLINE_ARTIFACT_PATHS:
        assert template in paths_oas, f"OpenAPI missing {template}"
