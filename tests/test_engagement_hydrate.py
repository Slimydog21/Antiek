"""Hydrate arxiv/substack refs into HTML-first assets (residual aq)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from substrate.engagement_spine import (  # noqa: E402
    InMemoryEngagementStore,
    asset_id_for_ref,
    hydrate_reference,
    parse_source_reference,
)


@pytest.fixture
def client():
    reset_engagement_stores()
    eng_mod.hydrate_fetch_publication = None
    app = FastAPI()
    register_engagement_routes(app)
    yield TestClient(app)
    eng_mod.hydrate_fetch_publication = None


def test_hydrate_offline_identity_only():
    store = InMemoryEngagementStore()
    asset = hydrate_reference(
        "https://arxiv.org/abs/1706.03762",
        store=store,
        include_html=True,
    )
    assert asset.view_format == "html"
    assert asset.fetched is False
    assert asset.asset_id.startswith("pub_arxiv_")
    assert asset.html
    assert "application/pdf" not in asset.html.lower()
    assert "HTML" in asset.html or "html" in asset.html.lower()
    assert "1706.03762" in asset.body_text or "1706.03762" in asset.title
    doc = store.get_document(asset.asset_id)
    assert doc is not None
    assert doc["view_format"] == "html"


def test_hydrate_with_injector_lands_body():
    store = InMemoryEngagementStore()

    def fetch(ref):
        return {
            "title": "Attention Is All You Need",
            "abstract": "We propose the Transformer, a model architecture based solely on attention.",
            "canonical_url": "https://arxiv.org/abs/1706.03762",
        }

    asset = hydrate_reference(
        "arxiv:1706.03762",
        store=store,
        fetch_publication=fetch,
        include_html=True,
    )
    assert asset.fetched is True
    assert "Attention Is All You Need" in asset.title
    assert "Transformer" in asset.body_text
    assert asset.html
    assert "Attention" in asset.html


def test_asset_id_stable():
    r1 = parse_source_reference("https://arxiv.org/abs/1706.03762")
    r2 = parse_source_reference("arxiv:1706.03762")
    # same kind+identity preferred; at least same kind arxiv
    assert r1.kind == "arxiv"
    assert asset_id_for_ref(r1) == asset_id_for_ref(
        parse_source_reference(r1.raw)
    )


def test_api_hydrate_double_run_stable(client):
    r1 = client.post(
        "/engagement/hydrate-ref",
        json={"reference": "https://arxiv.org/abs/1706.03762", "include_html": True},
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["view_format"] == "html"
    assert b1["fetched"] is False
    assert b1["html"]
    r2 = client.post(
        "/engagement/hydrate-ref",
        json={"reference": "https://arxiv.org/abs/1706.03762", "include_html": True},
    )
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["asset_id"] == b1["asset_id"]
    assert b2["view_format"] == "html"


def test_api_hydrate_with_injected_fetcher(client):
    def fetch(ref):
        return {
            "title": "Injected Substack Post",
            "body_text": "Deep research needs recursive twin notes.",
        }

    eng_mod.hydrate_fetch_publication = fetch
    r = client.post(
        "/engagement/hydrate-ref",
        json={
            "reference": "https://research.substack.com/p/attention",
            "include_html": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fetched"] is True
    assert "Injected Substack" in body["title"]
    assert "recursive twin" in body["body_text"]
    assert body["view_format"] == "html"
    assert "application/pdf" not in (body.get("html") or "").lower()
