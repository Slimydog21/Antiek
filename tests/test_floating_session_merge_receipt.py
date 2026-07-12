"""Cross-process and crash-state proof for floating-session merge receipts."""

from __future__ import annotations

import multiprocessing

import pytest

from substrate.floating_session.merge_receipt import (
    FileMergeReceiptStore,
    merge_material_sha256,
    merge_receipt_id,
)


def _claim_worker(root, receipt, barrier, queue):
    store = FileMergeReceiptStore(root)
    barrier.wait()
    row, created = store.claim(receipt)
    queue.put((row["receipt_id"], created))


def _receipt(owner: str = "alice", key: str = "merge-key-001") -> dict:
    material = {
        "owner_id": owner,
        "parent_asset_id": "asset-a",
        "session_ids": ["fsess_0123456789abcdef"],
        "mode": "into_parent",
        "expected_parent_sha256": "a" * 64,
    }
    return {
        "receipt_id": merge_receipt_id(owner, key),
        "owner_id": owner,
        "idempotency_key": key,
        "material_sha256": merge_material_sha256(material),
        "expected_parent_sha256": "a" * 64,
        "state": "claimed",
    }


def test_file_receipt_claim_has_one_cross_process_winner(tmp_path):
    receipt = _receipt()
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(3)
    queue = ctx.Queue()
    workers = [
        ctx.Process(target=_claim_worker, args=(tmp_path, receipt, barrier, queue))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    barrier.wait()
    results = [queue.get(timeout=5) for _ in workers]
    for worker in workers:
        worker.join(timeout=5)
        assert worker.exitcode == 0
    assert sorted(created for _receipt_id, created in results) == [False, True]


def test_file_receipt_reopens_prepared_and_settled_state(tmp_path):
    receipt = _receipt()
    store = FileMergeReceiptStore(tmp_path)
    claimed, created = store.claim(receipt)
    assert created is True
    result = {
        "document_id": "asset-a",
        "document_sha256": "b" * 64,
        "source_session_ids": ["fsess_0123456789abcdef"],
    }
    prepared = store.prepare(
        claimed["receipt_id"], claimed["material_sha256"], result
    )
    assert prepared["state"] == "prepared"

    reopened = FileMergeReceiptStore(tmp_path)
    replay, created_again = reopened.claim(receipt)
    assert created_again is False
    assert replay["result"] == result
    settled = reopened.settle(
        replay["receipt_id"], replay["material_sha256"], "b" * 64
    )
    assert settled["state"] == "applied"

    conflicting = {**receipt, "material_sha256": "c" * 64}
    with pytest.raises(ValueError, match="different merge material"):
        reopened.claim(conflicting)


@pytest.mark.parametrize(
    "receipt_id",
    ["mrcpt_../../outside00000000", "mrcpt_gggggggggggggggggggggggg"],
)
def test_file_receipt_rejects_noncanonical_storage_identity(tmp_path, receipt_id):
    receipt = {**_receipt(), "receipt_id": receipt_id}
    with pytest.raises(ValueError, match="invalid merge receipt identity"):
        FileMergeReceiptStore(tmp_path).claim(receipt)
