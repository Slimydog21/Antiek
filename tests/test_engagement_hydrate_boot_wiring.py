"""Residual (hr): app boot wires env-gated hydrate injectors (offline default)."""

from __future__ import annotations

from interfaces.research.api import engagement_routes as eng
from substrate.engagement_spine.hydrate_live_wiring import (
    configure_engagement_hydrate_injectors,
)


def setup_function() -> None:
    configure_engagement_hydrate_injectors(eng, environ={})


def teardown_function() -> None:
    configure_engagement_hydrate_injectors(eng, environ={})


def test_boot_wiring_default_leaves_offline() -> None:
    report = configure_engagement_hydrate_injectors(eng, environ={})
    assert report["arxiv_live"] is False
    assert report["substack_live"] is False
    assert eng.hydrate_arxiv_fetch_by_id is None
    assert eng.hydrate_substack_fetch_post is None
    payload = eng.hydrate_live_status_payload(environ={})
    assert payload["offline_honest"] is True


def test_boot_wiring_arxiv_env_without_injector_remains_offline() -> None:
    report = configure_engagement_hydrate_injectors(
        eng, environ={"ANTIEK_HYDRATE_LIVE_ARXIV": "1"}
    )
    assert report["arxiv_live"] is False
    assert eng.hydrate_arxiv_fetch_by_id is None
    assert eng.hydrate_arxiv_fetch_body is None
    payload = eng.hydrate_live_status_payload(
        environ={"ANTIEK_HYDRATE_LIVE_ARXIV": "1"}
    )
    assert payload["offline_honest"] is True
    assert payload["arxiv"]["injector_installed"] is False
