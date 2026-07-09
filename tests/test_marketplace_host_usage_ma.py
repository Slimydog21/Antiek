"""Residual (ma): marketplace host → Antiek-bench book_qa usage feed."""

from __future__ import annotations

import base64
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    get_bench_usage_store,
    reset_bench_usage_store,
)
from interfaces.research.api.marketplace_host_routes import (  # noqa: E402
    register_marketplace_host_routes,
    reset_marketplace_host_store,
)
from substrate.antiek_bench import list_usage_events  # noqa: E402


@pytest.fixture
def client():
    reset_marketplace_host_store()
    reset_bench_usage_store()
    app = FastAPI()
    register_marketplace_host_routes(app)
    return TestClient(app)


def test_host_records_book_qa_usage_event(client) -> None:
    r = client.post(
        "/marketplace/host",
        json={"owner_id": "researcher", "book_id": "pd-elements", "seed_twins": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["view_format"] == "html"
    assert body.get("usage_event") is not None
    ev = body["usage_event"]
    assert ev["task_class"] == "book_qa"
    assert ev["outcome"] == "worked"
    assert ev["source"] == "marketplace_host"
    assert "pd-elements" in ev["prompt_hint"]
    assert "mathematics" in ev["prompt_hint"] or "Euclid" in ev["prompt_hint"]

    store = get_bench_usage_store(create_if_missing=False)
    assert store is not None
    events = list_usage_events(store=store)
    assert any(
        e.get("source") == "marketplace_host" and e.get("task_class") == "book_qa"
        for e in events
    )


def test_purchase_host_records_book_qa_usage(client) -> None:
    content = base64.b64encode(b"<html><body>Modern</body></html>").decode("ascii")
    r = client.post(
        "/marketplace/purchase-and-host",
        json={
            "owner_id": "buyer",
            "book_id": "buy-modern",
            "opaque_reference": "order-ma-1",
            "content_b64": content,
            "seed_twins": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("usage_event", {}).get("task_class") == "book_qa"
    assert body["usage_event"]["source"] == "marketplace_host"
    assert "buy-modern" in body["usage_event"]["prompt_hint"]
