from __future__ import annotations

import base64
import sqlite3

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import hosted_document_routes
from interfaces.research.api.app import create_app
from interfaces.research.api.hosted_document_routes import register_hosted_document_routes
from interfaces.research.api.marketplace_host_routes import register_marketplace_host_routes
from substrate.marketplace_host import SQLiteHostStore


def _app(store: SQLiteHostStore) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = request.headers.get("x-test-user", "owner-a")
        return await call_next(request)

    register_marketplace_host_routes(app, store=store)
    register_hosted_document_routes(app)
    return app


def _purchased_body() -> dict[str, object]:
    words = " ".join(f"purchased-book-word-{index}" for index in range(80))
    raw = f"<html><body><p>{words}</p></body></html>".encode()
    return {
        "owner_id": "owner-a",
        "book_id": "buy-modern",
        "opaque_reference": "merchant-order-durable-1",
        "content_b64": base64.b64encode(raw).decode(),
        "source_format": "html",
        "seed_twins": False,
    }


def test_sqlite_store_round_trips_defensive_json_and_membership(tmp_path) -> None:
    path = tmp_path / "marketplace.sqlite3"
    first = SQLiteHostStore(path)
    doc = {"document_id": "doc-1", "owner_id": "owner-a", "nested": {"value": 1}}
    receipt = {"receipt_id": "receipt-1", "owner_id": "owner-a"}
    first.put_document("doc-1", doc)
    first.put_membership("owner-a", "doc-1")
    first.put_membership("owner-a", "doc-1")
    first.put_receipt("receipt-1", receipt)

    second = SQLiteHostStore(path)
    loaded = second.get_document("doc-1")
    assert loaded == doc
    assert loaded is not doc
    loaded["nested"] = {"value": 2}
    assert second.get_document("doc-1") == doc
    assert second.list_membership("owner-a") == ["doc-1"]
    assert second.get_receipt("receipt-1") == receipt
    assert path.stat().st_mode & 0o777 == 0o600

    with pytest.raises(ValueError, match="immutable receipt evidence"):
        second.put_receipt(
            "receipt-1", {"receipt_id": "receipt-1", "owner_id": "owner-b"}
        )


def test_sqlite_store_rejects_corrupt_persisted_payload(tmp_path) -> None:
    store = SQLiteHostStore(tmp_path / "marketplace.sqlite3")
    with sqlite3.connect(store.path) as con:
        con.execute(
            "INSERT INTO hosted_documents(document_id, payload_json) VALUES (?, ?)",
            ("doc-corrupt", "not-json"),
        )

    with pytest.raises(RuntimeError, match="not valid JSON"):
        store.get_document("doc-corrupt")


def test_sqlite_store_rejects_unknown_schema_version(tmp_path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA user_version=2")

    with pytest.raises(RuntimeError, match="unsupported marketplace host schema"):
        SQLiteHostStore(path)


def test_hosted_library_and_receipt_survive_fresh_app_and_store(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "marketplace.sqlite3"
    monkeypatch.setattr(
        hosted_document_routes,
        "_emit_document_loaded",
        lambda *args: "evt-durable-host",
    )
    first = TestClient(_app(SQLiteHostStore(path)))
    public_domain = first.post(
        "/marketplace/host",
        headers={"x-test-user": "owner-a"},
        json={"owner_id": "owner-a", "book_id": "pd-pride", "seed_twins": False},
    )
    purchased = first.post(
        "/marketplace/purchase-and-host",
        headers={"x-test-user": "owner-a"},
        json=_purchased_body(),
    )
    assert public_domain.status_code == 200, public_domain.text
    assert purchased.status_code == 200, purchased.text
    purchased_body = purchased.json()

    reopened = SQLiteHostStore(path)
    second = TestClient(_app(reopened))
    library = second.get(
        "/marketplace/library/owner-a", headers={"x-test-user": "owner-a"}
    )
    assert library.status_code == 200
    assert {row["document_id"] for row in library.json()["documents"]} == {
        public_domain.json()["document_id"],
        purchased_body["document_id"],
    }
    assert reopened.get_receipt(purchased_body["receipt_id"])["owner_id"] == "owner-a"

    html = second.get(
        f"/hosted-documents/{purchased_body['document_id']}/html",
        headers={"x-test-user": "owner-a"},
    )
    assert html.status_code == 200
    assert html.json()["view_format"] == "html"
    assert html.json()["projection_state"] == "ready"

    hidden_library = second.get(
        "/marketplace/library/owner-a", headers={"x-test-user": "owner-b"}
    )
    hidden_document = second.get(
        f"/hosted-documents/{purchased_body['document_id']}/html",
        headers={"x-test-user": "owner-b"},
    )
    assert hidden_library.status_code == 403
    assert hidden_document.status_code == 403


def test_create_app_accepts_only_explicit_host_store(tmp_path) -> None:
    store = SQLiteHostStore(tmp_path / "marketplace.sqlite3")
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        marketplace_host_store=store,
    )
    assert app.state.marketplace_host_store is store

    with pytest.raises(RuntimeError, match="does not satisfy HostStore"):
        create_app(
            register_wrestling=False,
            register_providers=False,
            marketplace_host_store=object(),
        )
