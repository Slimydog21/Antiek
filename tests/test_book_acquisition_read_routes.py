from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.book_acquisition_read_routes import (
    create_book_acquisition_read_router,
)
from runtime.db_lock import connect_write
from substrate.book_acquisition import (
    AuthorizationDecision,
    authorize_purchase_intent,
    create_purchase_intent,
    ensure_schema,
)
from substrate.book_acquisition.port import ensure_port_schema, port_authorized_epub
from substrate.graph.schema import init_database

KEY = b"book-acquisition-recovery-signing-key"


def _epub(title: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            f'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0"><metadata><dc:title>{title}</dc:title></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/c1.xhtml",
            f"<html><body><h1>{title}</h1><p>Verified recovery content.</p></body></html>",
        )
    return out.getvalue()


def _initialize(db_path: Path) -> None:
    with connect_write(str(db_path), purpose="book-recovery-test-init") as con:
        init_database(con)
        ensure_schema(con)
        ensure_port_schema(con)


def _seed(
    db_path: Path,
    *,
    operator_id: str,
    title: str,
    decision: AuthorizationDecision | None = None,
    port: bool = False,
):  # type: ignore[no-untyped-def]
    with connect_write(str(db_path), purpose="book-recovery-test-seed") as con:
        intent = create_purchase_intent(
            con,
            operator_id=operator_id,
            title=title,
            author="A. Researcher",
            store="publisher.example",
            max_price_usd_cents=3000,
            signing_key=KEY,
        )
        if decision is None:
            return intent, None, None
        authorization = authorize_purchase_intent(
            con,
            intent_receipt_id=intent.intent_receipt_id,
            operator_id=operator_id,
            decision=decision,
            authorized_price_ceiling_usd_cents=(
                2500 if decision is AuthorizationDecision.AUTHORIZED else 0
            ),
            signing_key=KEY,
        )
        result = None
        if port:
            result = port_authorized_epub(
                con,
                authorization_receipt_id=authorization.authorization_receipt_id,
                operator_id=operator_id,
                signing_key=KEY,
                epub_bytes=_epub(title),
            )
        return intent, authorization, result


def _client(db_path: Path) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "alice")
        return await call_next(request)

    app.include_router(create_book_acquisition_read_router(db_path=str(db_path), signing_key=KEY))
    return TestClient(app)


def _get(client: TestClient, *, user: str = "alice", query: str = ""):
    return client.get(
        f"/book-acquisition/records{query}",
        headers={"x-test-auth": "yes", "x-test-user": user},
    )


def test_recovery_returns_honest_pending_denied_authorized_and_ported_states(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "books.duckdb"
    _initialize(db_path)
    _seed(db_path, operator_id="alice", title="Pending")
    _seed(
        db_path,
        operator_id="alice",
        title="Denied",
        decision=AuthorizationDecision.DENIED,
    )
    _seed(
        db_path,
        operator_id="alice",
        title="Authorized",
        decision=AuthorizationDecision.AUTHORIZED,
    )
    _seed(
        db_path,
        operator_id="alice",
        title="Ported",
        decision=AuthorizationDecision.AUTHORIZED,
        port=True,
    )
    _seed(db_path, operator_id="bob", title="Private to Bob")

    response = _get(_client(db_path))
    assert response.status_code == 200, response.text
    rows = {row["intent"]["title"]: row for row in response.json()["records"]}
    assert set(rows) == {"Pending", "Denied", "Authorized", "Ported"}
    assert rows["Pending"]["authorization"] is None
    assert rows["Pending"]["port"] is None
    assert rows["Denied"]["authorization"]["decision"] == "denied"
    assert rows["Denied"]["authorization"]["purchase_occurred"] is False
    assert rows["Denied"]["port"] is None
    assert rows["Authorized"]["authorization"]["decision"] == "authorized"
    assert rows["Authorized"]["port"] is None
    assert rows["Ported"]["port"]["reader_route"].startswith("/read/")
    assert response.json()["next_cursor"] is None


def test_keyset_pagination_is_bounded_stable_and_nonoverlapping(tmp_path: Path) -> None:
    db_path = tmp_path / "books.duckdb"
    _initialize(db_path)
    for index in range(5):
        _seed(db_path, operator_id="alice", title=f"Book {index}")
    client = _client(db_path)

    first = _get(client, query="?limit=2")
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["records"]) == 2
    assert first_body["next_cursor"]
    second = _get(
        client,
        query=f"?limit=2&after={first_body['next_cursor']}",
    )
    assert second.status_code == 200
    first_ids = {row["intent"]["intent_receipt_id"] for row in first_body["records"]}
    second_ids = {row["intent"]["intent_receipt_id"] for row in second.json()["records"]}
    assert first_ids.isdisjoint(second_ids)
    assert len(second_ids) == 2
    assert _get(client, query="?limit=0").status_code == 422
    assert _get(client, query="?limit=101").status_code == 422
    assert _get(client, query="?limit=2.5").status_code == 422


def test_recovery_requires_auth_and_fails_closed_on_tamper_or_orphan(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "books.duckdb"
    _initialize(db_path)
    intent, _, _ = _seed(db_path, operator_id="alice", title="Tampered")
    client = _client(db_path)
    assert client.get("/book-acquisition/records").status_code == 401

    with connect_write(str(db_path), purpose="book-recovery-test-tamper") as con:
        con.execute(
            "UPDATE book_purchase_intents SET intent_mac = 'forged' WHERE intent_receipt_id = ?",
            [intent.intent_receipt_id],
        )
    assert _get(client).status_code == 409

    orphan_db = tmp_path / "orphan.duckdb"
    _initialize(orphan_db)
    orphan, _, _ = _seed(orphan_db, operator_id="alice", title="Orphan")
    with connect_write(str(orphan_db), purpose="book-recovery-test-orphan") as con:
        con.execute(
            "UPDATE book_purchase_intents SET status = 'authorized' WHERE intent_receipt_id = ?",
            [orphan.intent_receipt_id],
        )
    assert _get(_client(orphan_db)).status_code == 409


def test_recovery_fails_closed_on_authorization_and_port_tamper(tmp_path: Path) -> None:
    authorization_db = tmp_path / "authorization-tamper.duckdb"
    _initialize(authorization_db)
    _, authorization, _ = _seed(
        authorization_db,
        operator_id="alice",
        title="Authorization tamper",
        decision=AuthorizationDecision.AUTHORIZED,
    )
    assert authorization is not None
    with connect_write(
        str(authorization_db), purpose="book-recovery-test-authorization-tamper"
    ) as con:
        con.execute(
            "UPDATE book_purchase_authorizations SET authorization_mac = 'forged' "
            "WHERE authorization_receipt_id = ?",
            [authorization.authorization_receipt_id],
        )
    assert _get(_client(authorization_db)).status_code == 409

    port_db = tmp_path / "port-tamper.duckdb"
    _initialize(port_db)
    _, _, port = _seed(
        port_db,
        operator_id="alice",
        title="Port tamper",
        decision=AuthorizationDecision.AUTHORIZED,
        port=True,
    )
    assert port is not None
    with connect_write(str(port_db), purpose="book-recovery-test-port-tamper") as con:
        con.execute(
            "UPDATE book_authorized_ports SET port_mac = 'forged' WHERE port_receipt_id = ?",
            [port.port_receipt_id],
        )
    assert _get(_client(port_db)).status_code == 409
