"""Runtime invariants that must survive optimized Python."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.db_lock import connect_write
from substrate.books import ingest as book_ingest
from substrate.byot_usage.ledger import (
    ByotUsageLedger,
    OperationRow,
    SettlementEvidenceError,
)
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
)
from substrate.seams.thread import assert_single_canonical_entity, reconstruct_thread
from tests.test_thread_no_duplicate import (
    CANONICAL_INSIGHT,
    _copy_corrupted_events,
)
from tools.measure_merge_window import measure_one


def test_book_asset_recheck_fails_loudly_when_optimized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "graph.duckdb"
    con = connect_write(str(db_path), purpose="optimized-invariant-book")
    try:
        init_database(con)
        insert_document(
            con,
            document_id="book-postwrite",
            source_tier=2,
            document_type="book",
            title="Post-write invariant",
            author="Antiek",
            raw_text="body text",
        )
        monkeypatch.setattr(book_ingest, "get_book_asset", lambda *_args, **_kwargs: None)
        with pytest.raises(RuntimeError, match="book asset book-postwrite vanished"):
            book_ingest.register_book(con, document_id="book-postwrite", provenance="online")
    finally:
        con.close()


def _pending_operation(*, actual_cents: int | None, evidence_sha256: str | None) -> OperationRow:
    return OperationRow(
        api_key_id="key-1",
        owner_user_id="owner-1",
        operation_id="operation-1",
        state="settlement_pending",
        reserved_cents=10,
        actual_cents=actual_cents,
        authority_digest="authority",
        evidence_sha256=evidence_sha256,
        provider_id="provider",
        model_id="model",
        dispatch_event_id="event",
        result_text="result",
        created_at="2026-09-26T00:00:00+00:00",
        updated_at="2026-09-26T00:00:00+00:00",
    )


def test_byot_pending_operation_requires_settlement_evidence_when_optimized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    monkeypatch.setattr(
        ledger,
        "operation",
        lambda *_args, **_kwargs: _pending_operation(actual_cents=None, evidence_sha256=None),
    )
    with pytest.raises(SettlementEvidenceError, match="settlement evidence"):
        ledger.reconcile_operation("owner-1", "operation-1")


def test_byot_reconcile_recheck_fails_loudly_when_optimized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    pending = _pending_operation(actual_cents=7, evidence_sha256="evidence")
    reads = iter((pending, None))
    monkeypatch.setattr(ledger, "operation", lambda *_args, **_kwargs: next(reads))
    monkeypatch.setattr(ledger, "settle_operation", lambda *_args, **_kwargs: None)
    with pytest.raises(RuntimeError, match="operation operation-1 vanished"):
        ledger.reconcile_operation("owner-1", "operation-1")


def test_multimedia_account_recheck_fails_loudly_when_optimized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MultimediaAssetStore(tmp_path)
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="optimized invariant documentary",
            target_minutes=15,
            mode="video",
            route_policy="balanced",
        )
    )
    monkeypatch.setattr(store, "_account_dir", lambda *_args, **_kwargs: None)
    with pytest.raises(RuntimeError, match="multimedia account directory vanished"):
        store._save_unlocked(draft, draft.asset.owner_user_id)


def test_merge_count_recheck_fails_loudly_when_optimized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "tools.measure_merge_window.merge_staging",
        lambda **_kwargs: SimpleNamespace(total_inserted=0, window_s=1.0),
    )
    with pytest.raises(RuntimeError, match="merged 0 rows but staged 1"):
        measure_one(n_docs=1, n_chunks=1, dim=4)


def test_thread_copy_guard_fails_loudly_when_optimized() -> None:
    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=_copy_corrupted_events(),
        origin_entity_kind="insight_node",
    )
    with pytest.raises(AssertionError, match="thread holds a copy"):
        assert_single_canonical_entity(thread)


def test_reconcile_route_maps_missing_settlement_evidence_to_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    for name in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_CF_ACCESS_AUD",
        "ANTIEK_CF_ACCESS_TEAM_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(tmp_path / "usage.sqlite3"))
    monkeypatch.setattr(
        "interfaces.research.api.owner_byot_dispatch.authenticated_distinct_owner",
        lambda _request: "owner-1",
    )
    ledger = ByotUsageLedger()
    ledger.prepare_operation("key-1", "owner-1", "operation-1", 10, "a" * 64)
    ledger.mark_operation_sent("owner-1", "operation-1")
    connection = ledger._connect()
    try:
        connection.execute(
            "UPDATE byot_operation_journal SET state='settlement_pending' "
            "WHERE owner_user_id=? AND operation_id=?",
            ["owner-1", "operation-1"],
        )
        connection.commit()
    finally:
        connection.close()

    client = TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[]),
    )
    response = client.post("/books/model-operations/operation-1/reconcile")
    if response.status_code != 409:
        raise AssertionError(f"unexpected reconcile status: {response.status_code}")
    if response.json() != {"detail": "model_operation_settlement_evidence_missing"}:
        raise AssertionError(f"unexpected reconcile body: {response.json()}")
