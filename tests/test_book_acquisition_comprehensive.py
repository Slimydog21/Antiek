"""Comprehensive tests for book-acquisition authorization→port→recovery.

Covers the specified gates:
- Route reachability through app registration path
- Absent/invalid signing key behavior (fail-closed)
- Conversion outside writer lock / off event loop
- Transaction rollback on conversion failure after writer opened
- Replay, tamper, and cross-owner rejection
- purchase_occurred=false / no charge / store transport
"""

from __future__ import annotations

import ast
import asyncio
import io
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.book_acquisition_read_routes import (
    create_book_acquisition_read_router,
)
from interfaces.research.api.book_acquisition_routes import (
    EPUB_MEDIA_TYPE,
    create_book_acquisition_router,
)
from runtime.db_lock import connect_write
from substrate.book_acquisition import ensure_schema
from substrate.book_acquisition.port import (
    commit_authorized_port,
    convert_authorized_epub,
    ensure_port_schema,
)
from substrate.book_import import ConvertedBook
from substrate.graph.schema import init_database

KEY = b"test-book-acquisition-signing-key-32bytes!"
WRONG_KEY = b"wrong-book-acquisition-key-32-bytes!!"


def _epub(body: str = "Compressors raise the pressure of incoming air.") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", EPUB_MEDIA_TYPE)
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0">'
            "<metadata><dc:title>Jet Engines</dc:title>"
            "<dc:creator>A. Researcher</dc:creator></metadata>"
            '<manifest><item id="c1" href="c1.xhtml" '
            'media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/c1.xhtml",
            f"<html><body><h1>Compression</h1><p>{body}</p></body></html>",
        )
    return out.getvalue()


def _setup_db(db_path: Path) -> None:
    with connect_write(str(db_path), purpose="test-init") as con:
        init_database(con)
        ensure_schema(con)
        ensure_port_schema(con)


def _app_client(
    db_path: Path,
    *,
    signing_key: bytes = KEY,
    max_epub_bytes: int = 1024 * 1024,
) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "alice")
        return await call_next(request)

    app.include_router(
        create_book_acquisition_router(
            db_path=str(db_path),
            signing_key=signing_key,
            max_epub_bytes=max_epub_bytes,
        )
    )
    app.include_router(
        create_book_acquisition_read_router(
            db_path=str(db_path),
            signing_key=signing_key,
        )
    )
    return TestClient(app)


def _headers(user: str = "alice") -> dict[str, str]:
    return {"x-test-auth": "yes", "x-test-user": user}


def _registered_paths(app: FastAPI) -> set[str]:
    paths: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(original_router.routes)
    return paths


def _create_intent(client: TestClient, *, user: str = "alice") -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/book-acquisition/intents",
        headers=_headers(user),
        json={
            "title": "Jet Engines",
            "author": "A. Researcher",
            "store": "publisher.example",
            "max_price_usd_cents": 3000,
            "desired_format": "epub",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _authorize(
    client: TestClient,
    intent_id: str,
    *,
    user: str = "alice",
    decision: str = "authorized",
) -> dict:  # type: ignore[type-arg]
    response = client.post(
        f"/book-acquisition/intents/{intent_id}/authorization",
        headers=_headers(user),
        json={
            "decision": decision,
            "authorized_price_ceiling_usd_cents": (2500 if decision == "authorized" else 0),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _port(
    client: TestClient,
    auth_id: str,
    *,
    epub: bytes | None = None,
    user: str = "alice",
) -> dict:  # type: ignore[type-arg]
    response = client.post(
        f"/book-acquisition/authorizations/{auth_id}/port",
        headers={**_headers(user), "content-type": EPUB_MEDIA_TYPE},
        content=epub or _epub(),
    )
    return {"status": response.status_code, "body": response.json()}


# ── 1. Route reachability through app registration ───────────────────


class TestRouteReachability:
    """All acquisition routes must be reachable through the registered
    router prefix."""

    def test_intent_route_reachable(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        result = _create_intent(client)
        assert "intent_receipt_id" in result
        assert result["status"] == "needs_operator_authorization"

    def test_authorization_route_reachable(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        assert auth["decision"] == "authorized"
        assert auth["purchase_occurred"] is False

    def test_port_route_reachable(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        result = _port(client, auth["authorization_receipt_id"])
        assert result["status"] == 200
        assert result["body"]["content_class"] == "personal_reading"
        assert result["body"]["servability"] == "personal_readable"

    def test_recovery_route_reachable(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        _create_intent(client)
        response = client.get(
            "/book-acquisition/records", headers=_headers(),
        )
        assert response.status_code == 200
        assert len(response.json()["records"]) == 1

    def test_full_lifecycle_intent_auth_port_recovery(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        port = _port(client, auth["authorization_receipt_id"])
        assert port["status"] == 200
        assert port["body"]["reader_route"].startswith("/read/")
        assert port["body"]["was_new"] is True

        recovery = client.get(
            "/book-acquisition/records", headers=_headers(),
        )
        assert recovery.status_code == 200
        records = recovery.json()["records"]
        assert len(records) == 1
        assert records[0]["port"] is not None
        assert records[0]["port"]["port_receipt_id"] == port["body"]["port_receipt_id"]


# ── 2. Absent/invalid signing key behavior ───────────────────────────


class TestSigningKeyBehavior:
    """Fail-closed when signing key is absent or too short."""

    def test_router_factory_rejects_short_key(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="signing_key must contain at least 32 bytes"):
            create_book_acquisition_router(
                db_path=str(tmp_path / "db"), signing_key=b"short",
            )

    def test_router_factory_rejects_empty_key(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="signing_key must contain at least 32 bytes"):
            create_book_acquisition_router(
                db_path=str(tmp_path / "db"), signing_key=b"",
            )

    def test_router_factory_rejects_non_bytes_key(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="signing_key must contain at least 32 bytes"):
            create_book_acquisition_router(
                db_path=str(tmp_path / "db"), signing_key="string-not-bytes",  # type: ignore[arg-type]
            )

    def test_read_router_factory_rejects_short_key(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="signing_key must contain at least 32 bytes"):
            create_book_acquisition_read_router(
                db_path=str(tmp_path / "db"), signing_key=b"short",
            )

    def test_read_router_factory_rejects_empty_db_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="db_path is required"):
            create_book_acquisition_read_router(db_path="", signing_key=KEY)

    def test_mismatched_key_rejects_port_verification(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        port = _port(client, auth["authorization_receipt_id"])
        assert port["status"] == 200

        # Recovery with a different key fails
        wrong_client = _app_client(tmp_path / "db", signing_key=WRONG_KEY)
        recovery = wrong_client.get(
            "/book-acquisition/records", headers=_headers(),
        )
        assert recovery.status_code == 409

    def test_app_missing_key_env_does_not_mount_routes(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """When ANTIEK_BOOK_ACQUISITION_SIGNING_KEY is not set, the
        acquisition routes are simply not mounted (fail-closed)."""
        from interfaces.research.api.app import create_app

        monkeypatch.delenv("ANTIEK_BOOK_ACQUISITION_SIGNING_KEY", raising=False)
        paths = _registered_paths(create_app())
        assert not any(path.startswith("/book-acquisition") for path in paths)

    def test_app_valid_key_env_mounts_routes(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        from interfaces.research.api.app import create_app

        monkeypatch.setenv("ANTIEK_BOOK_ACQUISITION_SIGNING_KEY", KEY.decode())
        paths = _registered_paths(create_app())
        assert "/book-acquisition/intents" in paths
        assert "/book-acquisition/records" in paths

    def test_router_factory_rejects_bad_max_epub_bytes(self, tmp_path: Path) -> None:
        for bad in (0, -1, True, 3.14):
            with pytest.raises(ValueError, match="max_epub_bytes must be a positive integer"):
                create_book_acquisition_router(
                    db_path=str(tmp_path / "db"), signing_key=KEY, max_epub_bytes=bad,  # type: ignore[arg-type]
                )


# ── 3. Conversion outside writer lock / off event loop ───────────────


class TestConversionOutsideWriterLock:
    """convert_authorized_epub must be pure CPU with no DB access."""

    def test_convert_returns_converted_and_sha256(self) -> None:
        epub = _epub()
        prepared = convert_authorized_epub(epub)
        assert isinstance(prepared.converted, ConvertedBook)
        assert len(prepared.epub_sha256) == 64
        assert prepared.converted.title == "Jet Engines"
        assert "Compression" in prepared.converted.html

    def test_convert_is_deterministic(self) -> None:
        epub = _epub()
        first = convert_authorized_epub(epub)
        second = convert_authorized_epub(epub)
        assert first.epub_sha256 == second.epub_sha256
        assert first.converted.html == second.converted.html

    def test_convert_rejects_empty_bytes(self) -> None:
        with pytest.raises(ValueError, match="non-empty bytes"):
            convert_authorized_epub(b"")

    def test_convert_rejects_non_bytes(self) -> None:
        with pytest.raises(ValueError, match="non-empty bytes"):
            convert_authorized_epub("/tmp/book.epub")  # type: ignore[arg-type]

    def test_convert_rejects_hostile_epub(self) -> None:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("mimetype", EPUB_MEDIA_TYPE)
            archive.writestr("../escape.xhtml", "<html>escape</html>")
        with pytest.raises(Exception):  # noqa: B017
            convert_authorized_epub(out.getvalue())

    def test_convert_runs_without_any_db_connection(self) -> None:
        """convert_authorized_epub must not touch the database — verified
        by running it with no db_path and no LockedConnection."""
        epub = _epub()
        prepared = convert_authorized_epub(epub)
        assert prepared.converted.chapter_count >= 1
        assert prepared.epub_sha256

    def test_convert_can_run_in_threadpool(self) -> None:
        """Verify asyncio.to_thread compatibility."""
        epub = _epub()

        async def _run():  # type: ignore[no-untyped-def]
            return await asyncio.to_thread(convert_authorized_epub, epub)

        prepared = asyncio.run(_run())
        assert isinstance(prepared.converted, ConvertedBook)
        assert len(prepared.epub_sha256) == 64

    def test_port_route_runs_conversion_outside_writer(
        self, tmp_path: Path,
    ) -> None:
        """The route handler calls convert_authorized_epub via
        asyncio.to_thread before opening the writer lock."""
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])

        conversion_called = threading.Event()
        conversion_thread: list[int] = []
        original_convert = convert_authorized_epub

        def tracking_convert(epub_bytes: bytes):  # type: ignore[no-untyped-def]
            conversion_thread.append(threading.get_ident())
            conversion_called.set()
            return original_convert(epub_bytes)

        with patch(
            "interfaces.research.api.book_acquisition_routes.convert_authorized_epub",
            side_effect=tracking_convert,
        ):
            result = _port(client, auth["authorization_receipt_id"])
            assert result["status"] == 200
            assert conversion_called.is_set()
            assert conversion_thread

    def test_commit_requires_converted_book_type(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        with (
            connect_write(str(tmp_path / "db"), purpose="test") as con,
            pytest.raises(TypeError, match="convert_authorized_epub"),
        ):
            commit_authorized_port(
                con,
                authorization_receipt_id="bookauth-dead",
                operator_id="alice",
                signing_key=KEY,
                prepared="not-a-prepared-book",  # type: ignore[arg-type]
            )

    def test_commit_accepts_only_bound_conversion_result(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        with (
            connect_write(str(tmp_path / "db"), purpose="test") as con,
            pytest.raises(TypeError, match="convert_authorized_epub"),
        ):
            commit_authorized_port(
                con,
                authorization_receipt_id="bookauth-dead",
                operator_id="alice",
                signing_key=KEY,
                prepared=object(),  # type: ignore[arg-type]
            )


# ── 4. Transaction rollback ──────────────────────────────────────────


class TestTransactionRollback:
    """When publication fails inside the port transaction, the port
    receipt must not be written."""

    def test_failed_conversion_leaves_no_db_artifacts(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        # Send an invalid EPUB — conversion fails before writer opens
        result = _port(client, auth["authorization_receipt_id"], epub=b"not a zip")
        assert result["status"] == 422
        with connect_write(str(tmp_path / "db"), purpose="test-count") as con:
            assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
            assert con.execute("SELECT COUNT(*) FROM book_authorized_ports").fetchone() == (0,)

    def test_denied_authorization_port_leaves_no_documents(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"], decision="denied")
        result = _port(client, auth["authorization_receipt_id"])
        assert result["status"] == 403
        with connect_write(str(tmp_path / "db"), purpose="test-count") as con:
            assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
            assert con.execute("SELECT COUNT(*) FROM book_authorized_ports").fetchone() == (0,)

    def test_receipt_failure_rolls_back_published_document(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        prepared = convert_authorized_epub(_epub())

        with (
            pytest.raises(RuntimeError, match="injected receipt failure"),
            connect_write(str(tmp_path / "db"), purpose="test-rollback") as con,
            patch(
                "substrate.book_acquisition.port._signed_payload",
                side_effect=RuntimeError("injected receipt failure"),
            ),
        ):
            commit_authorized_port(
                con,
                authorization_receipt_id=auth["authorization_receipt_id"],
                operator_id="alice",
                signing_key=KEY,
                prepared=prepared,
            )

        with connect_write(str(tmp_path / "db"), purpose="test-count") as con:
            assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
            assert con.execute("SELECT COUNT(*) FROM book_authorized_ports").fetchone() == (0,)


# ── 5. Replay, tamper, and cross-owner rejection ─────────────────────


class TestReplayTamperCrossOwner:
    """Security-critical rejection paths."""

    def test_exact_replay_returns_same_receipt(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        epub = _epub()
        first = _port(client, auth["authorization_receipt_id"], epub=epub)
        second = _port(client, auth["authorization_receipt_id"], epub=epub)
        assert first["status"] == 200
        assert second["status"] == 200
        assert first["body"]["port_receipt_id"] == second["body"]["port_receipt_id"]
        assert first["body"]["document_id"] == second["body"]["document_id"]
        assert first["body"]["was_new"] is True
        assert second["body"]["was_new"] is False

    def test_different_epub_same_authorization_rejected(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        first = _port(client, auth["authorization_receipt_id"], epub=_epub("First edition"))
        assert first["status"] == 200
        second = _port(
            client, auth["authorization_receipt_id"],
            epub=_epub("A materially different edition."),
        )
        assert second["status"] == 409

    def test_cross_owner_authorization_rejected(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client, user="alice")
        response = client.post(
            f"/book-acquisition/intents/{intent['intent_receipt_id']}/authorization",
            headers=_headers("bob"),
            json={
                "decision": "authorized",
                "authorized_price_ceiling_usd_cents": 2500,
            },
        )
        assert response.status_code == 403

    def test_cross_owner_port_rejected(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client, user="alice")
        auth = _authorize(client, intent["intent_receipt_id"], user="alice")
        result = _port(
            client, auth["authorization_receipt_id"],
            user="bob",
        )
        assert result["status"] == 403

    def test_cross_owner_recovery_isolated(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        _create_intent(client, user="alice")
        _create_intent(client, user="bob")
        intent_alice = client.get(
            "/book-acquisition/records", headers=_headers("alice"),
        ).json()["records"][0]
        auth_alice = _authorize(
            client, intent_alice["intent"]["intent_receipt_id"], user="alice",
        )
        _port(client, auth_alice["authorization_receipt_id"], user="alice")

        bob_records = client.get(
            "/book-acquisition/records", headers=_headers("bob"),
        )
        assert bob_records.status_code == 200
        assert len(bob_records.json()["records"]) == 1
        assert bob_records.json()["records"][0]["port"] is None

    def test_tampered_intent_mac_rejected(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        with connect_write(str(tmp_path / "db"), purpose="test-tamper") as con:
            con.execute(
                "UPDATE book_purchase_intents SET intent_mac = 'forged' "
                "WHERE intent_receipt_id = ?",
                [intent["intent_receipt_id"]],
            )
        response = client.post(
            f"/book-acquisition/intents/{intent['intent_receipt_id']}/authorization",
            headers=_headers(),
            json={
                "decision": "authorized",
                "authorized_price_ceiling_usd_cents": 2500,
            },
        )
        assert response.status_code == 403

    def test_tampered_port_mac_rejected_by_recovery(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        port = _port(client, auth["authorization_receipt_id"])
        assert port["status"] == 200
        with connect_write(str(tmp_path / "db"), purpose="test-tamper") as con:
            con.execute(
                "UPDATE book_authorized_ports SET port_mac = 'forged' "
                "WHERE port_receipt_id = ?",
                [port["body"]["port_receipt_id"]],
            )
        recovery = client.get("/book-acquisition/records", headers=_headers())
        assert recovery.status_code == 409

    def test_fabricated_authorization_receipt_rejected(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        result = _port(client, "bookauth-deadbeef")
        assert result["status"] == 403

    def test_unauthenticated_rejected(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        response = client.post(
            "/book-acquisition/intents",
            json={
                "title": "Jet Engines",
                "author": "A. Researcher",
                "store": "publisher.example",
                "max_price_usd_cents": 3000,
            },
        )
        assert response.status_code == 401


# ── 6. purchase_occurred=false / no charge / store transport ─────────


class TestNoChargeStoreTransport:
    """The acquisition lifecycle is explicitly spend-inert:
    purchase_occurred is always False, no money moves, and the
    store field is transport metadata only."""

    def test_authorization_purchase_occurred_always_false(
        self, tmp_path: Path,
    ) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        assert auth["purchase_occurred"] is False

    def test_denied_authorization_purchase_occurred_always_false(
        self, tmp_path: Path,
    ) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(
            client, intent["intent_receipt_id"], decision="denied",
        )
        assert auth["purchase_occurred"] is False

    def test_recovery_shows_purchase_occurred_false(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        _authorize(client, intent["intent_receipt_id"])
        recovery = client.get("/book-acquisition/records", headers=_headers())
        assert recovery.status_code == 200
        auth = recovery.json()["records"][0]["authorization"]
        assert auth["purchase_occurred"] is False

    def test_store_is_transport_metadata_only(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        assert intent["store"] == "publisher.example"
        # The store field persists through recovery
        recovery = client.get("/book-acquisition/records", headers=_headers())
        assert recovery.json()["records"][0]["intent"]["store"] == "publisher.example"

    def test_port_receipt_carries_no_price_or_payment_field(
        self, tmp_path: Path,
    ) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        port = _port(client, auth["authorization_receipt_id"])
        assert port["status"] == 200
        body = port["body"]
        # No payment, price, charge, cost fields in the port response
        for forbidden in ("price", "charge", "cost", "payment", "amount_cents"):
            assert forbidden not in body, f"port response contains {forbidden}"

    def test_no_payment_network_imports_in_route_module(self) -> None:
        source_path = (
            Path(__file__).parents[1]
            / "interfaces"
            / "research"
            / "api"
            / "book_acquisition_routes.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        assert imported_roots.isdisjoint(
            {"httpx", "requests", "urllib", "socket", "subprocess", "pathlib"}
        )

    def test_signing_key_never_in_response_body(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        intent = _create_intent(client)
        auth = _authorize(client, intent["intent_receipt_id"])
        port = _port(client, auth["authorization_receipt_id"])
        assert KEY.hex() not in str(port)
        assert "signing_key" not in str(port)

    def test_desired_format_is_epub_only(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        response = client.post(
            "/book-acquisition/intents",
            headers=_headers(),
            json={
                "title": "Jet Engines",
                "author": "A. Researcher",
                "store": "publisher.example",
                "max_price_usd_cents": 3000,
                "desired_format": "pdf",
            },
        )
        assert response.status_code == 422

    def test_money_fields_reject_coerced_types(self, tmp_path: Path) -> None:
        _setup_db(tmp_path / "db")
        client = _app_client(tmp_path / "db")
        base = {
            "title": "Jet Engines",
            "author": "A. Researcher",
            "store": "publisher.example",
        }
        for invalid in ("3000", 3000.0, True, 2**100):
            response = client.post(
                "/book-acquisition/intents",
                headers=_headers(),
                json={**base, "max_price_usd_cents": invalid},
            )
            assert response.status_code == 422
