"""Repeated live events retain their receipts across SQL batch partitions."""

from __future__ import annotations

import json

import pytest

from acquisition.arxiv import oai_persist
from acquisition.arxiv.adapter import arxiv_doc_id
from runtime.db_lock import connect_read, connect_write
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph import ensure_initialized
from substrate.schemas.documents import ArxivOaiRecord

_A = "2401.00001"
_B = "2401.00002"


def _records() -> list[ArxivOaiRecord]:
    return [
        ArxivOaiRecord(
            arxiv_id=arxiv_id,
            datestamp="2026-01-01",
            title=f"Synthetic event {index}",
            license_uri="http://creativecommons.org/licenses/by/4.0/",
            categories=("cs.AI",),
        )
        for index, arxiv_id in enumerate((_A, _A, _B, _A, _B, _A))
    ]


def _initialize(db_path: str, existing: tuple[str, ...]) -> None:
    ensure_initialized(db_path)
    with connect_write(db_path, purpose="test-logical-count-seed", keepalive_s=0) as con:
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, status, metadata) "
            "VALUES ('synthetic-arxiv-holder', 'Synthetic holder', 'claimed', ?)",
            [json.dumps({"domains": ["arxiv.org"]})],
        )
        for arxiv_id in existing:
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_uri, title, source_tier, document_type, "
                "metadata, content_class) VALUES (?, ?, ?, 3, 'academic_paper', ?, ?)",
                [
                    arxiv_doc_id(arxiv_id),
                    f"https://arxiv.org/abs/{arxiv_id}",
                    "Synthetic seed",
                    '{"source": "synthetic_seed"}',
                    GATED_DEFAULT_CONTENT_CLASS,
                ],
            )


def _snapshot(db_path: str) -> list[tuple[object, ...]]:
    with connect_read(db_path) as con:
        return con.execute(
            "SELECT document_id, title, source_uri, metadata, source_tier, "
            "document_type, content_class, ip_holder_id "
            "FROM documents ORDER BY document_id"
        ).fetchall()


@pytest.mark.parametrize(
    ("existing", "expected"),
    [((), (2, 4)), ((_A,), (1, 5)), ((_A, _B), (0, 6))],
    ids=["initially-absent", "mixed-membership", "initially-existing"],
)
@pytest.mark.parametrize(
    "partition", [(6,), (1, 1, 1, 1, 1, 1), (2, 1, 3), (3, 3)],
    ids=["one-batch", "single-record-batches", "uneven-batches", "equal-batches"],
)
def test_repeated_event_counts_values_and_resolver_order_are_partition_invariant(
    tmp_path, monkeypatch, existing, expected, partition,
):
    records = _records()
    reference = str(tmp_path / "per-record.duckdb")
    batched = str(tmp_path / "batched.duckdb")
    for db_path in (reference, batched):
        _initialize(db_path, existing)

    resolution_calls: list[tuple[str, str]] = []
    real_resolve = oai_persist.resolve_and_apply

    def observe_resolution(con, *, document_id, source_uri):
        resolution_calls.append((document_id, source_uri))
        return real_resolve(con, document_id=document_id, source_uri=source_uri)

    monkeypatch.setattr(oai_persist, "resolve_and_apply", observe_resolution)
    inserted = updated = 0
    with (
        connect_write(reference, purpose="test-logical-count-reference", keepalive_s=0) as con,
        con.transaction(),
    ):
        for record in records:
            if oai_persist.persist_oai_record(con, record):
                inserted += 1
            else:
                updated += 1
    assert (inserted, updated) == expected
    reference_calls = list(resolution_calls)
    resolution_calls.clear()

    inserted = updated = offset = 0
    with (
        connect_write(batched, purpose="test-logical-count-batched", keepalive_s=0) as con,
        con.transaction(),
    ):
        for size in partition:
            new, refreshed = oai_persist.persist_oai_records_batched(
                con, records[offset:offset + size],
            )
            inserted += new
            updated += refreshed
            offset += size

    assert offset == len(records)
    assert (inserted, updated) == expected
    assert inserted + updated == len(records)
    assert resolution_calls == reference_calls == [
        (arxiv_doc_id(record.arxiv_id), f"https://arxiv.org/abs/{record.arxiv_id}")
        for record in records
    ]
    assert _snapshot(batched) == _snapshot(reference)
    assert all(row[6] == GATED_DEFAULT_CONTENT_CLASS for row in _snapshot(batched))
    assert all(row[7] == "synthetic-arxiv-holder" for row in _snapshot(batched))
