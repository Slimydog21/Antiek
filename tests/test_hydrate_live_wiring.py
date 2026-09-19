"""Env-gated live hydrate wiring (residual bk)."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine.hydrate_live_wiring import (  # noqa: E402
    ANTIEK_HYDRATE_LIVE_ARXIV_ENV,
    ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV,
    configure_engagement_hydrate_injectors,
    env_flag,
    live_fetch_publication_from_env,
)


def test_env_flag_truthy():
    assert env_flag("X", environ={"X": "1"}) is True
    assert env_flag("X", environ={"X": "TRUE"}) is True
    assert env_flag("X", environ={"X": "0"}) is False
    assert env_flag("X", environ={}) is False


def test_configure_defaults_offline():
    eng = SimpleNamespace(
        hydrate_arxiv_fetch_by_id="sentinel",
        hydrate_substack_fetch_post="sentinel",
    )
    report = configure_engagement_hydrate_injectors(eng, environ={})
    assert report["arxiv_live"] is False
    assert report["substack_live"] is False
    assert eng.hydrate_arxiv_fetch_by_id is None
    assert eng.hydrate_substack_fetch_post is None
    assert any("offline" in n.lower() for n in report["notes"])


def test_configure_arxiv_flag_without_injector_stays_zero_request_offline():
    eng = SimpleNamespace(
        hydrate_arxiv_fetch_by_id=None,
        hydrate_substack_fetch_post=None,
    )
    report = configure_engagement_hydrate_injectors(
        eng, environ={ANTIEK_HYDRATE_LIVE_ARXIV_ENV: "1"}
    )
    assert report["arxiv_live"] is False
    assert eng.hydrate_arxiv_fetch_by_id is None
    assert any("no arxiv injector" in n.lower() for n in report["notes"])


def test_configure_arxiv_requires_env_and_installed_injector():
    calls: list[str] = []

    def injected(arxiv_id: str):
        calls.append(arxiv_id)

    eng = SimpleNamespace(
        hydrate_arxiv_fetch_by_id=None,
        hydrate_arxiv_fetch_body=None,
        hydrate_substack_fetch_post=None,
    )
    off = configure_engagement_hydrate_injectors(
        eng, environ={}, arxiv_fetch_body=injected
    )
    assert off["arxiv_live"] is False
    assert eng.hydrate_arxiv_fetch_body is None
    assert calls == []
    on = configure_engagement_hydrate_injectors(
        eng,
        environ={ANTIEK_HYDRATE_LIVE_ARXIV_ENV: "1"},
        arxiv_fetch_body=injected,
    )
    assert on["arxiv_live"] is True
    assert eng.hydrate_arxiv_fetch_body is injected
    assert calls == []


def test_configure_substack_requires_factory():
    eng = SimpleNamespace(
        hydrate_arxiv_fetch_by_id=None,
        hydrate_substack_fetch_post=None,
    )
    report = configure_engagement_hydrate_injectors(
        eng, environ={ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV: "1"}
    )
    assert report["substack_live"] is False
    assert eng.hydrate_substack_fetch_post is None
    assert any("factory" in n.lower() for n in report["notes"])

    def fake_fetch(url: str):
        return {"title": "t", "body_markdown": "b", "post_url": url}

    report2 = configure_engagement_hydrate_injectors(
        eng,
        environ={ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV: "yes"},
        substack_fetch_post=fake_fetch,
    )
    assert report2["substack_live"] is True
    assert eng.hydrate_substack_fetch_post is fake_fetch


def test_live_fetch_publication_from_env_none_by_default():
    assert live_fetch_publication_from_env(environ={}) is None
