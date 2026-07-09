"""arXiv hydrate adapter — metadata abstract into HTML asset (residual bi)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

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
    arxiv_metadata_fetch_publication,
    hydrate_with_arxiv_adapter,
)


@dataclass
class _FakePaper:
    arxiv_id: str = "1706.03762"
    title: str = "Attention Is All You Need"
    abstract: str = (
        "We propose the Transformer, a model architecture based solely on "
        "attention mechanisms."
    )
    abs_url: str = "https://arxiv.org/abs/1706.03762"
    authors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.authors is None:
            self.authors = ["Vaswani", "Shazeer"]


def test_arxiv_adapter_lands_abstract():
    store = InMemoryEngagementStore()

    def fetch_by_id(arxiv_id: str):
        assert "1706.03762" in arxiv_id
        return _FakePaper()

    asset = hydrate_with_arxiv_adapter(
        "https://arxiv.org/abs/1706.03762",
        store=store,
        fetch_by_id=fetch_by_id,
        include_html=True,
    )
    assert asset.fetched is True
    assert "Attention Is All You Need" in asset.title
    assert "Transformer" in asset.body_text
    assert "Vaswani" in asset.body_text
    assert asset.view_format == "html"
    assert asset.html
    assert "application/pdf" not in asset.html.lower()
    assert "Attention" in asset.html or "Transformer" in asset.html


def test_arxiv_adapter_without_injector_identity_only_for_non_wired_path():
    """hydrate_with_arxiv_adapter without fetch_by_id stays identity-only."""
    store = InMemoryEngagementStore()
    asset = hydrate_with_arxiv_adapter(
        "https://arxiv.org/abs/1706.03762",
        store=store,
        fetch_by_id=None,
        include_html=True,
    )
    assert asset.fetched is False
    assert asset.view_format == "html"


def test_api_hydrate_with_injected_arxiv_fetch():
    reset_engagement_stores()
    eng_mod.hydrate_fetch_publication = None
    eng_mod.hydrate_arxiv_fetch_by_id = lambda arxiv_id: _FakePaper(arxiv_id=arxiv_id)

    app = FastAPI()
    register_engagement_routes(app)
    client = TestClient(app)
    try:
        r1 = client.post(
            "/engagement/hydrate-ref",
            json={
                "reference": "arxiv:1706.03762",
                "include_html": True,
            },
        )
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["fetched"] is True
        assert "Attention Is All You Need" in b1["title"]
        assert b1["view_format"] == "html"
        assert b1["html"]
        r2 = client.post(
            "/engagement/hydrate-ref",
            json={"reference": "arxiv:1706.03762", "include_html": True},
        )
        assert r2.status_code == 200
        assert r2.json()["asset_id"] == b1["asset_id"]
        assert r2.json()["fetched"] is True
    finally:
        eng_mod.hydrate_arxiv_fetch_by_id = None
        eng_mod.hydrate_fetch_publication = None


def test_adapter_builder_refuses_silent_network():
    fetch = arxiv_metadata_fetch_publication(fetch_by_id=None)
    from substrate.engagement_spine.source_refs import parse_source_reference

    ref = parse_source_reference("arxiv:1706.03762")
    try:
        fetch(ref)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "silent" in str(exc).lower() or "injected" in str(exc).lower()
