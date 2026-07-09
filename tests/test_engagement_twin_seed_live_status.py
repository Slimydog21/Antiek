"""Residual (hs): twin seed live status readiness — offline-honest default."""

from __future__ import annotations

from interfaces.research.api import engagement_routes as er
from substrate.engagement_spine.twin import clear_twin_seed_live, configure_twin_seed_live


def setup_function() -> None:
    clear_twin_seed_live()


def teardown_function() -> None:
    clear_twin_seed_live()


def test_twin_seed_live_status_offline_default() -> None:
    payload = er.twin_seed_live_status_payload(environ={})
    assert payload["view_format"] == "html"
    assert payload["product_panel"] == "twin_seed_live_status"
    assert payload["offline_honest"] is True
    assert payload["injector_installed"] is False
    assert payload["live_env"] is False
    assert "offline-honest" in " ".join(payload["notes"]).lower()


def test_twin_seed_live_status_surfaces_installed_fn() -> None:
    configure_twin_seed_live(lambda _t, _b: [("insight", "x")])
    payload = er.twin_seed_live_status_payload(
        environ={"ANTIEK_TWIN_SEED_LIVE": "1"}
    )
    assert payload["offline_honest"] is False
    assert payload["injector_installed"] is True
    assert payload["live_env"] is True
