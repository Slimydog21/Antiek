"""Book acquisition intents are gated on procurement (SPR-07 task 2).

``POST /book-acquisition/intents`` was the one ingestion path that accepted
arbitrary book bytes with no procurement check: ``store`` was unconstrained
free text. Now the store is run through ``default_legal_gate().check_url``
at intent creation, before the writer lock and before
``create_purchase_intent``, so a shadow-library source is refused with 422
naming the banned host and no intent row (hence no authorization, no port,
no bytes) ever exists for it.

Every refusal test here is paired with a negative control: the route still
creates intents for a clean store, and emptying the registry flips the same
banned URL to 201. Without those, a refusal test cannot tell "the gate
bites" from "the route is broken".
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.book_acquisition_routes import (
    create_book_acquisition_router,
)
from runtime.db_lock import connect_write
from substrate.book_acquisition import (
    ProcurementRefusedError,
    check_store_procurement,
    create_purchase_intent,
    ensure_schema,
)
from substrate.graph.schema import init_database
from substrate.legal_gate import registry

KEY = b"book-acquisition-legal-gate-test-key-32b"
INTENTS = "/book-acquisition/intents"
BANNED_URL = "https://annas-archive.org/md5/abc"


@pytest.fixture(autouse=True)
def real_gate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither escape hatch may swap the real gate for the placeholder."""
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", raising=False)
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_DISABLED", raising=False)


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "books.duckdb"
    with connect_write(str(db_path), purpose="book-acquisition-legal-gate-init") as con:
        init_database(con)

    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = "alice"
        return await call_next(request)

    app.include_router(create_book_acquisition_router(db_path=str(db_path), signing_key=KEY))
    return TestClient(app), db_path


def _post_intent(client: TestClient, store: str, *, authed: bool = True):
    headers = {"x-test-auth": "yes"} if authed else {}
    return client.post(
        INTENTS,
        headers=headers,
        json={
            "title": f"Jet Engines {uuid.uuid4()}",
            "author": "A. Researcher",
            "store": store,
            "max_price_usd_cents": 3000,
            "desired_format": "epub",
        },
    )


def _intent_rows(db_path: Path) -> int:
    with connect_write(str(db_path), purpose="book-acquisition-legal-gate-count") as con:
        ensure_schema(con)
        return int(con.execute("SELECT COUNT(*) FROM book_purchase_intents").fetchone()[0])


def test_banned_store_url_is_refused_and_clean_store_is_accepted(tmp_path: Path) -> None:
    """The spec's done-bar: both outcomes in one run."""
    client, db_path = _client(tmp_path)

    refused = _post_intent(client, BANNED_URL)
    assert refused.status_code == 422, refused.text
    assert "annas-archive.org" in refused.json()["detail"]

    accepted = _post_intent(client, "Kobo")
    assert 200 <= accepted.status_code < 300, accepted.text
    assert accepted.json()["store"] == "Kobo"
    assert accepted.json()["status"] == "needs_operator_authorization"

    assert _intent_rows(db_path) == 1, "only the clean intent may be recorded"


@pytest.mark.parametrize(
    "store",
    [
        "annas-archive.org",  # bare host, no scheme
        "http://libgen.rs/main/ABC",  # http, not https
        "https://mirror.z-lib.org/book/1",  # subdomain of a banned host
        "order from annas-archive.org today",  # host embedded in prose
    ],
)
def test_banned_store_forms_are_all_refused(tmp_path: Path, store: str) -> None:
    client, db_path = _client(tmp_path)
    response = _post_intent(client, store)
    assert response.status_code == 422, response.text
    assert "banned domain" in response.json()["detail"]
    assert _intent_rows(db_path) == 0


@pytest.mark.parametrize("store", ["Kobo", "publisher.example", "https://shop.kobo.com/x"])
def test_clean_store_forms_are_all_accepted(tmp_path: Path, store: str) -> None:
    client, db_path = _client(tmp_path)
    response = _post_intent(client, store)
    assert response.status_code == 201, response.text
    assert _intent_rows(db_path) == 1


def test_refusal_is_caused_by_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Differential proof: same URL, registry seeded -> 422, registry
    emptied -> 201. If the 422 came from anywhere but the registry the
    second half would stay refused."""
    client, _ = _client(tmp_path)
    seeded = _post_intent(client, BANNED_URL).status_code
    monkeypatch.setattr(registry, "BANNED_DOMAINS", ())
    mutated = _post_intent(client, BANNED_URL).status_code
    assert (seeded, mutated) == (422, 201)


def test_unauthenticated_request_is_401_before_the_gate(tmp_path: Path) -> None:
    """Auth stays first: a banned store from an anonymous caller is 401,
    never a 422 that would confirm which hosts the registry names."""
    client, _ = _client(tmp_path)
    response = _post_intent(client, BANNED_URL, authed=False)
    assert response.status_code == 401


def test_substrate_create_purchase_intent_refuses_banned_store(tmp_path: Path) -> None:
    """The gate is in the substrate too, so a caller that bypasses the HTTP
    adapter still cannot record a banned-source intent."""
    db_path = tmp_path / "books.duckdb"
    with connect_write(str(db_path), purpose="book-acquisition-legal-gate-substrate") as con:
        init_database(con)
        ensure_schema(con)
        with pytest.raises(ProcurementRefusedError, match="annas-archive.org"):
            create_purchase_intent(
                con,
                operator_id="alice",
                title="Jet Engines",
                author="A. Researcher",
                store=BANNED_URL,
                max_price_usd_cents=3000,
                signing_key=KEY,
            )
        assert con.execute("SELECT COUNT(*) FROM book_purchase_intents").fetchone()[0] == 0


def test_check_store_procurement_returns_normalized_clean_store() -> None:
    assert check_store_procurement("  Kobo  ") == "Kobo"
    with pytest.raises(ValueError, match="store is required"):
        check_store_procurement("   ")
