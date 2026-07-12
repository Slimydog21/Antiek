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

from interfaces.research.api import marketplace_host_routes as routes  # noqa: E402
from interfaces.research.api.marketplace_host_routes import (  # noqa: E402
    register_marketplace_host_routes,
    reset_marketplace_host_store,
)
from substrate.marketplace_host import InMemoryHostStore  # noqa: E402


@pytest.fixture
def client():
    reset_marketplace_host_store()
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = request.headers.get("x-test-user", "user-api")
        return await call_next(request)

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
    # Residual (acb): library free_count aggregate matches free inventory.
    assert lib.json().get("free_count") == 1

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


def test_all_base64_marketplace_models_have_the_same_encoded_length_ceiling():
    host_schema = routes.HostBody.model_json_schema()["properties"]["content_b64"]
    purchase_schema = routes.PurchaseHostBody.model_json_schema()["properties"][
        "content_b64"
    ]
    assert host_schema["anyOf"][0]["maxLength"] == routes.MAX_BASE64_SOURCE_CHARS
    assert purchase_schema["maxLength"] == routes.MAX_BASE64_SOURCE_CHARS


def test_public_domain_catalog_refuses_caller_supplied_bytes(client):
    injected = base64.b64encode(
        " ".join(f"unrelated-private-word-{i}" for i in range(80)).encode()
    ).decode()
    response = client.post(
        "/marketplace/host",
        json={
            "owner_id": "user-api",
            "book_id": "pd-pride",
            "content_b64": injected,
        },
    )
    assert response.status_code == 400
    assert "cannot inherit" in response.json()["detail"]


def test_purchase_and_host(client):
    raw = base64.b64encode(b"%PDF-1.4 stub purchase").decode("ascii")
    headers = {"x-test-user": "user-buy"}
    r = client.post(
        "/marketplace/purchase-and-host",
        json={
            "owner_id": "user-buy",
            "book_id": "buy-modern",
            "opaque_reference": "ORDER-99",
            "content_b64": raw,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["receipt_id"].startswith("rcpt_")
    assert body["license_class"] == "purchased"
    assert body["view_format"] == "html"
    assert body["state"] == "non_viewable"
    assert body["html"] == ""
    assert body["non_viewable_reason"] == "extraction_failed"
    assert body["document_loaded_event_id"] is None
    assert body.get("twins") is None
    assert body.get("usage_event") is None
    # Residual (abw): purchased library row is never free inventory.
    lib = client.get("/marketplace/library/user-buy", headers=headers)
    assert lib.status_code == 200
    docs = lib.json()["documents"]
    assert docs
    bought = next(d for d in docs if d.get("document_id") == body["document_id"])
    assert bought.get("license_class") == "purchased"
    assert bought.get("is_free") is False


def test_purchase_file_multipart_preserves_declared_text_format(client, monkeypatch):
    monkeypatch.setattr(
        "interfaces.research.api.hosted_document_routes._emit_document_loaded",
        lambda *args: "evt-purchased-file",
    )
    content = " ".join(f"licensed-markdown-word-{i}" for i in range(60)).encode()
    response = client.post(
        "/marketplace/purchase-and-host-file",
        data={
            "owner_id": "buyer",
            "book_id": "buy-modern",
            "opaque_reference": "ORDER-MULTIPART-1",
            "source_format": "md",
            "note": "Bought from publisher",
        },
        files={"content": ("modern.md", content, "text/markdown")},
        headers={"x-test-user": "buyer"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ready"
    assert body["source_format"] == "md"
    assert body["document_loaded_event_id"] == "evt-purchased-file"
    assert "licensed-markdown-word-59" in body["html"]


def test_purchase_file_rejects_oversize_before_recording_receipt(client, monkeypatch):
    monkeypatch.setattr(routes, "MAX_SOURCE_BYTES", 10)
    response = client.post(
        "/marketplace/purchase-and-host-file",
        data={
            "owner_id": "buyer",
            "book_id": "buy-modern",
            "opaque_reference": "ORDER-TOO-LARGE",
            "source_format": "pdf",
        },
        files={"content": ("large.pdf", b"x" * 11, "application/pdf")},
        headers={"x-test-user": "buyer"},
    )
    assert response.status_code == 413
    assert routes.get_marketplace_host_store().list_membership("buyer") == []


def test_owner_scope_is_server_bound_and_document_reads_are_isolated(client):
    forged = client.post(
        "/marketplace/host",
        json={"owner_id": "victim", "book_id": "pd-pride"},
    )
    assert forged.status_code == 403

    hosted = client.post(
        "/marketplace/host",
        json={"owner_id": "user-api", "book_id": "pd-pride"},
    )
    assert hosted.status_code == 200
    document_id = hosted.json()["document_id"]

    assert client.get("/marketplace/library/victim").status_code == 403
    victim_library = client.get("/marketplace/library/victim", headers={"x-test-user": "victim"})
    assert victim_library.status_code == 200
    assert victim_library.json()["count"] == 0
    assert (
        client.get(
            f"/marketplace/documents/{document_id}/html",
            headers={"x-test-user": "victim"},
        ).status_code
        == 403
    )


def test_owner_routes_fail_closed_without_identity_but_catalog_remains_public():
    reset_marketplace_host_store()
    app = FastAPI()
    register_marketplace_host_routes(app)
    client = TestClient(app)

    assert client.get("/marketplace/catalog").status_code == 200
    denied = client.post(
        "/marketplace/host",
        json={"owner_id": "operator", "book_id": "pd-pride"},
    )
    assert denied.status_code == 503


def test_operator_alias_membership_migrates_without_hiding_existing_books():
    store = InMemoryHostStore()
    store.put_document(
        "legacy-doc",
        {
            "document_id": "legacy-doc",
            "owner_id": "operator",
            "title": "Legacy book",
            "license_class": "public_domain",
            "view_format": "html",
        },
    )
    store.put_membership("operator", "legacy-doc")
    reset_marketplace_host_store(store)
    app = FastAPI()

    @app.middleware("http")
    async def operator_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "__operator__"
        return await call_next(request)

    register_marketplace_host_routes(app)
    client = TestClient(app)

    response = client.get("/marketplace/library/operator")
    assert response.status_code == 200
    assert response.json()["owner_id"] == "__operator__"
    assert response.json()["documents"][0]["document_id"] == "legacy-doc"
    assert store.list_membership("__operator__") == ["legacy-doc"]
