"""Residual (hq): hydrate live status readiness report — offline-honest default."""

from __future__ import annotations

from interfaces.research.api import engagement_routes as er


def setup_function() -> None:
    er.hydrate_arxiv_fetch_by_id = None
    er.hydrate_substack_fetch_post = None
    er.hydrate_fetch_publication = None


def teardown_function() -> None:
    er.hydrate_arxiv_fetch_by_id = None
    er.hydrate_substack_fetch_post = None
    er.hydrate_fetch_publication = None


def test_hydrate_live_status_offline_honest_default() -> None:
    payload = er.hydrate_live_status_payload(environ={})
    assert payload["view_format"] == "html"
    assert payload["product_panel"] == "hydrate_live_status"
    assert payload["offline_honest"] is True
    assert payload["any_live_injector"] is False
    assert payload["arxiv"]["env_enabled"] is False
    assert payload["arxiv"]["injector_installed"] is False
    assert payload["substack"]["injector_installed"] is False
    assert "offline-honest" in " ".join(payload["notes"]).lower()
    assert "offline_honest=true" in (payload.get("html") or "")


def test_hydrate_live_status_surfaces_arxiv_injector() -> None:
    er.hydrate_arxiv_fetch_by_id = lambda _aid: {"title": "x"}
    payload = er.hydrate_live_status_payload(
        environ={"ANTIEK_HYDRATE_LIVE_ARXIV": "1"}
    )
    assert payload["offline_honest"] is False
    assert payload["any_live_injector"] is True
    assert payload["arxiv"]["env_enabled"] is True
    assert payload["arxiv"]["injector_installed"] is True


def test_hydrate_live_status_env_without_injector_notes_gap() -> None:
    payload = er.hydrate_live_status_payload(
        environ={"ANTIEK_HYDRATE_LIVE_SUBSTACK": "1"}
    )
    assert payload["offline_honest"] is True  # no injector installed
    assert payload["substack"]["env_enabled"] is True
    assert payload["substack"]["injector_installed"] is False
    assert any("factory" in n.lower() or "not installed" in n.lower() for n in payload["notes"])
