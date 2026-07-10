"""API tests for marketplace host-into-account product surface."""

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

from interfaces.research.api.marketplace_host_routes import (  # noqa: E402
    register_marketplace_host_routes,
    reset_marketplace_host_store,
)


@pytest.fixture
def client():
    reset_marketplace_host_store()
    app = FastAPI()
    register_marketplace_host_routes(app)
    return TestClient(app)


def test_catalog_and_host_pd(client):
    cat = client.get("/marketplace/catalog")
    assert cat.status_code == 200
    assert cat.json()["count"] >= 1
    assert cat.json()["view_format"] == "html"

    r = client.post(
        "/marketplace/host",
        json={"owner_id": "user-api", "book_id": "pd-pride"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document_id"].startswith("hdoc_")
    assert body["view_format"] == "html"
    assert body["already_hosted"] is False
    assert body["html"]
    doc_id = body["document_id"]

    r2 = client.post(
        "/marketplace/host",
        json={"owner_id": "user-api", "book_id": "pd-pride"},
    )
    assert r2.json()["document_id"] == doc_id
    assert r2.json()["already_hosted"] is True

    lib = client.get("/marketplace/library/user-api")
    assert lib.status_code == 200
    assert lib.json()["count"] >= 1
    assert any(d["document_id"] == doc_id for d in lib.json()["documents"])
    # Residual (abu): library documents stamp is_free for free inventory honesty.
    pride = next(d for d in lib.json()["documents"] if d["document_id"] == doc_id)
    assert pride.get("license_class") == "public_domain"
    assert pride.get("is_free") is True

    html = client.get(f"/marketplace/documents/{doc_id}/html")
    assert html.status_code == 200
    hbody = html.json()
    assert hbody["view_format"] == "html"
    assert hbody["html"]
    # Residual (dp): rehydrate metadata for library open path.
    assert hbody.get("title")
    assert hbody.get("source") == "marketplace_host.project_hosted_book_html"
    assert hbody.get("document_id") == doc_id


def test_purchased_without_receipt_400(client):
    raw = base64.b64encode(b"%PDF-1.4 stub").decode("ascii")
    r = client.post(
        "/marketplace/host",
        json={
            "owner_id": "user-api",
            "book_id": "buy-modern",
            "content_b64": raw,
        },
    )
    assert r.status_code == 400
    assert "receipt" in r.json()["detail"].lower()


def test_purchase_and_host(client):
    raw = base64.b64encode(b"%PDF-1.4 stub purchase").decode("ascii")
    r = client.post(
        "/marketplace/purchase-and-host",
        json={
            "owner_id": "user-buy",
            "book_id": "buy-modern",
            "opaque_reference": "ORDER-99",
            "content_b64": raw,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["receipt_id"].startswith("rcpt_")
    assert body["license_class"] == "purchased"
    assert body["view_format"] == "html"
    # Residual (abw): purchased library row is never free inventory.
    lib = client.get("/marketplace/library/user-buy")
    assert lib.status_code == 200
    docs = lib.json()["documents"]
    assert docs
    bought = next(d for d in docs if d.get("document_id") == body["document_id"])
    assert bought.get("license_class") == "purchased"
    assert bought.get("is_free") is False
