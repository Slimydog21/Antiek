"""Depth-tier presets for decision-tree + cost projection hints (residual at)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.settings_budget import (  # noqa: E402
    register_settings_budget_routes,
)
from substrate.model_registration import (  # noqa: E402
    apply_depth_tier,
    clear_active_depth_tier,
    clear_decision_tree_selection,
    depth_tiers_settings_payload,
    get_active_depth_tier,
    list_depth_tiers,
)


@pytest.fixture(autouse=True)
def _reset_depth():
    clear_active_depth_tier()
    clear_decision_tree_selection()
    yield
    clear_active_depth_tier()
    clear_decision_tree_selection()


def test_list_three_presets():
    presets = list_depth_tiers()
    assert [p.depth_tier for p in presets] == ["flash", "pro", "wrestle"]
    flash = presets[0]
    assert flash.dispatch_tier == "flash"
    assert flash.task_class == "distill"
    wrestle = presets[2]
    assert wrestle.task_class == "wrestle"
    assert wrestle.default_expected_output_tokens > flash.default_expected_output_tokens


def test_apply_depth_tier_sets_active_and_hints():
    out = apply_depth_tier("wrestle")
    assert out["depth_tier"] == "wrestle"
    assert get_active_depth_tier() == "wrestle"
    hints = out["projection_hints"]
    assert hints["tier"] == "pro"
    assert hints["task_class"] == "wrestle"
    assert hints["expected_output_tokens"] == 4000
    assert out["view_format"] == "html"


def test_apply_with_driver_install():
    out = apply_depth_tier(
        "flash",
        model_id="glm-5.2",
        provider_id="zai",
        install_driver=True,
    )
    assert out["depth_tier"] == "flash"
    install = out["decision_tree_install"]
    assert install is not None
    assert install["model_id"] == "glm-5.2"
    assert install["installed"] is True


def test_settings_payload_html():
    apply_depth_tier("pro")
    payload = depth_tiers_settings_payload(include_html=True)
    assert payload["active_depth_tier"] == "pro"
    assert len(payload["presets"]) == 3
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    assert "pro" in payload["html"].lower() or "Pro" in payload["html"]


def test_api_depth_tier_double_run():
    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)
    r1 = client.post(
        "/settings/depth-tier",
        json={"depth_tier": "flash", "include_html": True},
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["active_depth_tier"] == "flash"
    assert b1["projection_hints"]["task_class"] == "distill"
    assert b1["view_format"] == "html"
    assert b1["html"]
    r2 = client.get("/settings/depth-tier?include_html=true")
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["active_depth_tier"] == "flash"
    assert b2["projection_hints"]["expected_output_tokens"] == b1[
        "projection_hints"
    ]["expected_output_tokens"]
    bad = client.post("/settings/depth-tier", json={"depth_tier": "turbo"})
    assert bad.status_code == 400
