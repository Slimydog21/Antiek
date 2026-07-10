from __future__ import annotations

import ast
import hashlib
import hmac
import inspect
import json
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import LockedConnection, connect_write
from substrate.book_acquisition import (
    AcquisitionConflictError,
    AcquisitionIntegrityError,
    AuthorizationDecision,
    DesiredFormat,
    authorize_purchase_intent,
    create_purchase_intent,
    ensure_schema,
    verify_authorization,
)

_SIGNING_KEY = b"antiek-test-book-acquisition-key-32-bytes"


@pytest.fixture
def writer(tmp_path: Path):
    with connect_write(str(tmp_path / "acquisition.duckdb"), purpose="book-auth-test") as con:
        ensure_schema(con)
        yield con


def _intent(writer: LockedConnection):
    return create_purchase_intent(
        writer,
        operator_id="operator-alice",
        title="Aircraft Engines",
        author="A. Researcher",
        store="publisher.example",
        max_price_usd_cents=2599,
        signing_key=_SIGNING_KEY,
        desired_format=DesiredFormat.EPUB,
    )


def _authorize(writer: LockedConnection, intent_id: str):
    return authorize_purchase_intent(
        writer,
        intent_receipt_id=intent_id,
        operator_id="operator-alice",
        decision=AuthorizationDecision.AUTHORIZED,
        authorized_price_ceiling_usd_cents=2500,
        signing_key=_SIGNING_KEY,
    )


def test_exact_intent_replay_is_content_addressed(writer: LockedConnection) -> None:
    first = _intent(writer)
    second = _intent(writer)
    assert second == first
    assert first.intent_receipt_id == f"bookintent-{first.intent_hash}"
    assert writer.execute("SELECT COUNT(*) FROM book_purchase_intents").fetchone() == (1,)


def test_intent_digest_matches_independent_known_vector(writer: LockedConnection) -> None:
    intent = _intent(writer)
    assert intent.intent_hash == "1e12487219f1a61820090097588e195379a61f28e2db4b6d02facd15ed173d22"
    row = writer.execute(
        "SELECT intent_mac FROM book_purchase_intents WHERE intent_receipt_id = ?",
        [intent.intent_receipt_id],
    ).fetchone()
    assert row == ("6e48fea005f8838c1154c2426721349fc9db2b9f0e305c667fd0f970eb41e489",)


def test_exact_authorization_replay_is_idempotent(writer: LockedConnection) -> None:
    intent = _intent(writer)
    first = _authorize(writer, intent.intent_receipt_id)
    second = _authorize(writer, intent.intent_receipt_id)
    assert second == first
    assert first.purchase_occurred is False
    assert writer.execute("SELECT COUNT(*) FROM book_purchase_authorizations").fetchone() == (1,)


def test_conflicting_terminal_decision_fails_closed(writer: LockedConnection) -> None:
    intent = _intent(writer)
    _authorize(writer, intent.intent_receipt_id)
    with pytest.raises(AcquisitionConflictError):
        authorize_purchase_intent(
            writer,
            intent_receipt_id=intent.intent_receipt_id,
            operator_id="operator-alice",
            decision=AuthorizationDecision.DENIED,
            authorized_price_ceiling_usd_cents=0,
            signing_key=_SIGNING_KEY,
        )
    assert writer.execute("SELECT COUNT(*) FROM book_purchase_authorizations").fetchone() == (1,)


def test_orphaned_terminal_status_cannot_be_adopted(writer: LockedConnection) -> None:
    intent = _intent(writer)
    writer.execute(
        "UPDATE book_purchase_intents SET status='authorized' WHERE intent_receipt_id=?",
        [intent.intent_receipt_id],
    )
    with pytest.raises(AcquisitionIntegrityError, match="no authorization receipt"):
        _authorize(writer, intent.intent_receipt_id)
    assert writer.execute("SELECT COUNT(*) FROM book_purchase_authorizations").fetchone() == (0,)


def test_replay_rejects_status_receipt_mismatch(writer: LockedConnection) -> None:
    intent = _intent(writer)
    _authorize(writer, intent.intent_receipt_id)
    writer.execute(
        "UPDATE book_purchase_intents SET status='denied' WHERE intent_receipt_id=?",
        [intent.intent_receipt_id],
    )
    with pytest.raises(AcquisitionIntegrityError, match="does not match"):
        _authorize(writer, intent.intent_receipt_id)


def test_fabricated_authorization_is_rejected(writer: LockedConnection) -> None:
    with pytest.raises(AcquisitionIntegrityError, match="does not exist"):
        verify_authorization(
            writer,
            authorization_receipt_id="bookauth-deadbeef",
            expected_operator_id="operator-alice",
            signing_key=_SIGNING_KEY,
        )


def test_tampered_intent_cannot_be_authorized(writer: LockedConnection) -> None:
    intent = _intent(writer)
    writer.execute(
        "UPDATE book_purchase_intents SET max_price_usd_cents = 999999 "
        "WHERE intent_receipt_id = ?",
        [intent.intent_receipt_id],
    )
    with pytest.raises(AcquisitionIntegrityError, match="tampered"):
        _authorize(writer, intent.intent_receipt_id)
    assert writer.execute("SELECT COUNT(*) FROM book_purchase_authorizations").fetchone() == (0,)


def test_coherent_intent_rewrite_without_signing_key_is_rejected(
    writer: LockedConnection,
) -> None:
    intent = _intent(writer)
    payload = {
        "author": "Attacker",
        "desired_format": "epub",
        "max_price_usd_cents": 1,
        "operator_id": "operator-alice",
        "store": "attacker.example",
        "title": "Rewritten",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    attacker_mac = hmac.new(b"x" * 32, canonical.encode(), hashlib.sha256).hexdigest()
    rewritten_id = f"bookintent-{digest}"
    writer.execute(
        "UPDATE book_purchase_intents SET intent_receipt_id=?, title=?, author=?, "
        "store=?, max_price_usd_cents=?, intent_hash=?, intent_mac=? "
        "WHERE intent_receipt_id=?",
        [rewritten_id, "Rewritten", "Attacker", "attacker.example", 1, digest,
         attacker_mac, intent.intent_receipt_id],
    )
    with pytest.raises(AcquisitionIntegrityError, match="signature"):
        _authorize(writer, rewritten_id)


def test_tampered_authorization_fails_verification(writer: LockedConnection) -> None:
    intent = _intent(writer)
    authorization = _authorize(writer, intent.intent_receipt_id)
    writer.execute(
        "UPDATE book_purchase_authorizations SET intent_hash = ? "
        "WHERE authorization_receipt_id = ?",
        ["0" * 64, authorization.authorization_receipt_id],
    )
    with pytest.raises(AcquisitionIntegrityError, match="predecessor"):
        verify_authorization(
            writer,
            authorization_receipt_id=authorization.authorization_receipt_id,
            expected_operator_id="operator-alice",
            signing_key=_SIGNING_KEY,
        )


def test_coherent_denied_to_authorized_rewrite_is_rejected(
    writer: LockedConnection,
) -> None:
    intent = _intent(writer)
    denied = authorize_purchase_intent(
        writer,
        intent_receipt_id=intent.intent_receipt_id,
        operator_id="operator-alice",
        decision=AuthorizationDecision.DENIED,
        authorized_price_ceiling_usd_cents=0,
        signing_key=_SIGNING_KEY,
    )
    payload = {
        "authorized_price_ceiling_usd_cents": 1,
        "decision": "authorized",
        "intent_hash": intent.intent_hash,
        "intent_receipt_id": intent.intent_receipt_id,
        "operator_id": "operator-alice",
        "purchase_occurred": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    attacker_mac = hmac.new(b"x" * 32, canonical.encode(), hashlib.sha256).hexdigest()
    rewritten_id = f"bookauth-{digest}"
    writer.execute(
        "UPDATE book_purchase_authorizations SET authorization_receipt_id=?, "
        "decision='authorized', authorized_price_ceiling_usd_cents=1, "
        "authorization_hash=?, authorization_mac=? WHERE authorization_receipt_id=?",
        [rewritten_id, digest, attacker_mac, denied.authorization_receipt_id],
    )
    writer.execute(
        "UPDATE book_purchase_intents SET status='authorized' WHERE intent_receipt_id=?",
        [intent.intent_receipt_id],
    )
    with pytest.raises(AcquisitionIntegrityError, match="signature"):
        verify_authorization(
            writer,
            authorization_receipt_id=rewritten_id,
            expected_operator_id="operator-alice",
            signing_key=_SIGNING_KEY,
        )


def test_cross_operator_and_ceiling_increase_are_rejected(writer: LockedConnection) -> None:
    intent = _intent(writer)
    with pytest.raises(AcquisitionIntegrityError, match="does not own"):
        authorize_purchase_intent(
            writer,
            intent_receipt_id=intent.intent_receipt_id,
            operator_id="operator-bob",
            decision=AuthorizationDecision.AUTHORIZED,
            authorized_price_ceiling_usd_cents=100,
            signing_key=_SIGNING_KEY,
        )
    with pytest.raises(AcquisitionIntegrityError, match="exceeds"):
        authorize_purchase_intent(
            writer,
            intent_receipt_id=intent.intent_receipt_id,
            operator_id="operator-alice",
            decision=AuthorizationDecision.AUTHORIZED,
            authorized_price_ceiling_usd_cents=2600,
            signing_key=_SIGNING_KEY,
        )


def test_denial_is_not_a_verified_authorization(writer: LockedConnection) -> None:
    intent = _intent(writer)
    denied = authorize_purchase_intent(
        writer,
        intent_receipt_id=intent.intent_receipt_id,
        operator_id="operator-alice",
        decision=AuthorizationDecision.DENIED,
        authorized_price_ceiling_usd_cents=0,
        signing_key=_SIGNING_KEY,
    )
    with pytest.raises(AcquisitionIntegrityError, match="not authorized"):
        verify_authorization(
            writer,
            authorization_receipt_id=denied.authorization_receipt_id,
            expected_operator_id="operator-alice",
            signing_key=_SIGNING_KEY,
        )


def test_authorized_receipt_verifies(writer: LockedConnection) -> None:
    intent = _intent(writer)
    authorization = _authorize(writer, intent.intent_receipt_id)
    assert verify_authorization(
        writer,
        authorization_receipt_id=authorization.authorization_receipt_id,
        expected_operator_id="operator-alice",
        signing_key=_SIGNING_KEY,
    ) == authorization


@pytest.mark.parametrize("bad", [-1, 1.5, True])
def test_money_requires_non_negative_integer_cents(
    writer: LockedConnection, bad: object
) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        create_purchase_intent(
            writer,
            operator_id="operator-alice",
            title="Book",
            author="Author",
            store="Store",
            max_price_usd_cents=bad,  # type: ignore[arg-type]
            signing_key=_SIGNING_KEY,
        )


def test_raw_duckdb_connection_cannot_write() -> None:
    raw = duckdb.connect(":memory:")
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            ensure_schema(raw)  # type: ignore[arg-type]
    finally:
        raw.close()


def test_every_public_operation_requires_locked_connection() -> None:
    raw = duckdb.connect(":memory:")
    try:
        operations = (
            lambda: create_purchase_intent(
                raw, operator_id="o", title="t", author="a", store="s",
                max_price_usd_cents=1, signing_key=_SIGNING_KEY,
            ),
            lambda: authorize_purchase_intent(
                raw, intent_receipt_id="i", operator_id="o",
                decision=AuthorizationDecision.AUTHORIZED,
                authorized_price_ceiling_usd_cents=1, signing_key=_SIGNING_KEY,
            ),
            lambda: verify_authorization(
                raw, authorization_receipt_id="a", expected_operator_id="o",
                signing_key=_SIGNING_KEY,
            ),
        )
        for operation in operations:
            with pytest.raises(TypeError, match="LockedConnection"):
                operation()
    finally:
        raw.close()


def test_no_spend_surface_or_transport_imports() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "substrate"
        / "book_acquisition"
        / "authorization.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    }
    imported |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= {
        "__future__", "hashlib", "hmac", "json", "collections", "contextlib",
        "dataclasses", "enum", "runtime",
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint({"__import__", "eval", "exec", "open"})
    for function in (
        create_purchase_intent,
        authorize_purchase_intent,
        verify_authorization,
    ):
        names = set(inspect.signature(function).parameters)
        assert not any(
            token in name
            for name in names
            for token in ("provider", "transport", "checkout", "payment")
        )
