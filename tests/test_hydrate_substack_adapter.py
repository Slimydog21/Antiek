"""Substack hydrate adapter — post body into HTML asset (residual bj)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine import (  # noqa: E402
    InMemoryEngagementStore,
    hydrate_with_publication_adapters,
    substack_post_fetch_publication,
)
from substrate.engagement_spine.source_refs import parse_source_reference  # noqa: E402


@dataclass
class _FakePost:
    title: str = "Deep research needs recursive twin notes"
    body_markdown: str = (
        "Authors argue that LLMs are perfect note-takers for twin substrates."
    )
    body_html: str = ""
    post_url: str = "https://research.substack.com/p/attention"
    author: str = "Researcher"
    truncated: bool = False


def test_substack_adapter_lands_body():
    store = InMemoryEngagementStore()

    def fetch_post(url: str):
        assert "substack" in url
        return _FakePost()

    asset = hydrate_with_publication_adapters(
        "https://research.substack.com/p/attention",
        store=store,
        substack_fetch_post=fetch_post,
        include_html=True,
    )
    assert asset.fetched is True
    assert "recursive twin" in asset.title or "Deep research" in asset.title
    assert "note-takers" in asset.body_text
    assert "Researcher" in asset.body_text
    assert asset.view_format == "html"
    assert asset.html
    assert "application/pdf" not in asset.html.lower()


def test_substack_adapter_refuses_silent_network():
    fetch = substack_post_fetch_publication(fetch_post=None)
    ref = parse_source_reference("https://research.substack.com/p/attention")
    try:
        fetch(ref)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "silent" in str(exc).lower() or "injected" in str(exc).lower()


def test_api_hydrate_with_injected_substack_fetch():
    reset_engagement_stores()
    eng_mod.hydrate_fetch_publication = None
    eng_mod.hydrate_arxiv_fetch_by_id = None
    eng_mod.hydrate_substack_fetch_post = lambda url: _FakePost(post_url=url)

    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)
    try:
        r1 = client.post(
            "/engagement/hydrate-ref",
            json={
                "reference": "https://research.substack.com/p/attention",
                "include_html": True,
            },
        )
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["fetched"] is True
        assert "note-takers" in b1["body_text"]
        assert b1["view_format"] == "html"
        r2 = client.post(
            "/engagement/hydrate-ref",
            json={
                "reference": "https://research.substack.com/p/attention",
                "include_html": True,
            },
        )
        assert r2.status_code == 200
        assert r2.json()["asset_id"] == b1["asset_id"]
    finally:
        eng_mod.hydrate_substack_fetch_post = None
