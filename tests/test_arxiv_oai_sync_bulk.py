"""Tests for bulk-dump-aware OAI sync (throughput path).

The pure-OAI nightly crawl is structurally too slow under arXiv's 1-req/3s
rule (~1000 records/page × 3.5s ≈ 50 min/page → ~22h for 26K docs, past the
6h systemd TimeoutStartSec). ``run_bulk_sync`` streams the free bulk metadata
snapshot for mass throughput, then OAI-PMH only for the tail newer than the
snapshot.

NO live network: the bulk snapshot is a tmp JSON-Lines fixture; the OAI tail
uses ``httpx.MockTransport`` (same convention as ``tests/test_arxiv_oai_sync.py``).
Crash-safety invariants (high-water never advances mid-run; post-crash seed
from the harvester cursor) are re-asserted on the bulk path.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import duckdb  # noqa: E402

from acquisition.arxiv.adapter import arxiv_doc_id  # noqa: E402
from acquisition.arxiv.bulk import (  # noqa: E402
    discover_bulk_feed,
    download_bulk_snapshot,
    ensure_bulk_snapshot,
    iter_bulk_oai_records,
    open_bulk_snapshot,
    record_dict_to_oai_record,
)
from acquisition.arxiv.oai_pmh import OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402
from tools.arxiv_oai_sync import (  # noqa: E402
    SyncCheckpoint,
    read_checkpoint,
    run_bulk_sync,
    write_checkpoint,
)

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'
_AT = datetime(2026, 5, 29, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _tmp_documents_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))
    monkeypatch.setenv(
        "ANTIEK_ARXIV_BULK_SNAPSHOT", str(tmp_path / "bulk-snapshot.json")
    )


def _db_path(tmp_path) -> str:
    return str(tmp_path / "graph.duckdb")


def _rows(tmp_path) -> list[tuple]:
    con = duckdb.connect(_db_path(tmp_path), read_only=True)
    try:
        return con.execute(
            "SELECT document_id, title, content_class, metadata "
            "FROM documents ORDER BY document_id"
        ).fetchall()
    finally:
        con.close()


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _throttle(tmp_path, clock: _FakeClock) -> ArxivThrottle:
    return ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"),
        now=clock.now,
        sleep=clock.sleep,
    )


def _bulk_record(
    arxiv_id: str,
    *,
    update_date: str,
    license_uri: str | None = _CC_BY,
    categories: str = "cs.LG",
    title: str | None = None,
) -> dict:
    return {
        "id": arxiv_id,
        "title": title or f"T {arxiv_id}",
        "abstract": f"Abstract for {arxiv_id}.",
        "categories": categories,
        "license": license_uri,
        "authors_parsed": [["Author", "A", ""]],
        "versions": [
            {"version": "v1", "created": "Mon, 1 Jan 2024 10:00:00 GMT"},
        ],
        "update_date": update_date,
    }


def _write_snapshot(path: Path, records: list[dict]) -> str:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return str(path)


def _oai_record(arxiv_id: str, datestamp: str, license_uri) -> str:
    lic = f"<license>{license_uri}</license>" if license_uri is not None else ""
    return f"""
      <record>
        <header>
          <identifier>oai:arXiv.org:{arxiv_id}</identifier>
          <datestamp>{datestamp}</datestamp>
        </header>
        <metadata>
          <arXiv {_ARXIV_BODY_NS}>
            <id>{arxiv_id}</id><title>T {arxiv_id}</title>
            <categories>cs.LG</categories>{lic}
          </arXiv>
        </metadata>
      </record>"""


def _oai_page(*records: str, token: str | None = None) -> str:
    rt = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_NS}>
  <responseDate>2026-05-29T00:00:00Z</responseDate>
  <ListRecords>{''.join(records)}{rt}</ListRecords>
</OAI-PMH>"""


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _harvester(tmp_path, clock, handler, *, name="harvest.json") -> OaiPmhHarvester:
    return OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(handler),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / name),
    )


# ---------------------------------------------------------------------------
# bulk.py helpers: record mapping, streaming, download, tar
# ---------------------------------------------------------------------------


def test_record_dict_to_oai_record_maps_license_and_datestamp():
    rec = record_dict_to_oai_record(
        _bulk_record("2401.00001", update_date="2024-02-15", license_uri=_CC_BY)
    )
    assert rec.arxiv_id == "2401.00001"
    assert rec.datestamp == "2024-02-15"
    assert rec.license_uri == _CC_BY
    assert rec.title == "T 2401.00001"
    assert rec.categories == ("cs.LG",)
    assert rec.deleted is False


def test_record_dict_to_oai_record_absent_license_is_none():
    rec = record_dict_to_oai_record(
        _bulk_record("2401.00002", update_date="2024-02-15", license_uri=None)
    )
    assert rec.license_uri is None


def test_iter_bulk_oai_records_respects_since_until_and_limit(tmp_path):
    records = [
        _bulk_record("a", update_date="2024-01-01"),
        _bulk_record("b", update_date="2024-02-01"),
        _bulk_record("c", update_date="2024-03-01"),
        _bulk_record("d", update_date="2024-04-01"),
    ]
    text = "\n".join(json.dumps(r) for r in records) + "\n"
    out = list(
        iter_bulk_oai_records(
            io.StringIO(text), since="2024-02-01", until="2024-03-01"
        )
    )
    assert [r.arxiv_id for r in out] == ["b", "c"]

    capped = list(iter_bulk_oai_records(io.StringIO(text), limit=2))
    assert len(capped) == 2


def test_open_bulk_snapshot_reads_plain_jsonl(tmp_path):
    snap = tmp_path / "snap.json"
    _write_snapshot(
        snap, [_bulk_record("x", update_date="2024-01-01")]
    )
    with open_bulk_snapshot(str(snap)) as fh:
        rows = list(iter_bulk_oai_records(fh))
    assert [r.arxiv_id for r in rows] == ["x"]


def test_open_bulk_snapshot_reads_tar_gz(tmp_path):
    """stdlib tarfile + gzip — no new heavy deps. A .tar.gz wrapping one
    JSON-Lines member is accepted (the shape some mirrors publish)."""
    inner = tmp_path / "arxiv-metadata-oai-snapshot.json"
    _write_snapshot(
        inner,
        [
            _bulk_record("t1", update_date="2024-05-01"),
            _bulk_record("t2", update_date="2024-05-02"),
        ],
    )
    tar_path = tmp_path / "snap.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(inner, arcname="arxiv-metadata-oai-snapshot.json")

    with open_bulk_snapshot(str(tar_path)) as fh:
        rows = list(iter_bulk_oai_records(fh))
    assert [r.arxiv_id for r in rows] == ["t1", "t2"]


class _FakeHeaders(dict):
    def get(self, key, default=None):  # type: ignore[override]
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeResp:
    def __init__(self, body: bytes, *, status: int = 200, headers: dict | None = None):
        self._body = body
        self._pos = 0
        self.status = status
        self.headers = _FakeHeaders(headers or {})

    def getcode(self) -> int:
        return self.status

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk = self._body[self._pos :]
            self._pos = len(self._body)
            return chunk
        chunk = self._body[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_discover_and_download_bulk_snapshot(tmp_path):
    body = (
        json.dumps(_bulk_record("dl1", update_date="2024-06-01")) + "\n"
    ).encode()

    def opener(req, timeout=None):
        if req.get_method() == "HEAD":
            return _FakeResp(
                b"",
                headers={
                    "Content-Length": str(len(body)),
                    "ETag": '"abc"',
                    "Last-Modified": "Wed, 01 Jun 2024 00:00:00 GMT",
                },
            )
        return _FakeResp(body, headers={"Content-Length": str(len(body))})

    feed = discover_bulk_feed(
        candidate_urls=("https://example.test/snap.json",),
        opener=opener,
    )
    assert feed.url == "https://example.test/snap.json"
    assert feed.content_length == len(body)
    assert feed.etag == '"abc"'

    dest = tmp_path / "downloaded.json"
    path = download_bulk_snapshot(str(dest), feed=feed, opener=opener)
    assert Path(path).read_bytes() == body


def test_ensure_bulk_snapshot_reuses_existing_file(tmp_path):
    """An existing non-empty snapshot is reused — no network (opener would
    raise if called)."""
    snap = tmp_path / "existing.json"
    _write_snapshot(snap, [_bulk_record("e", update_date="2024-01-01")])

    def boom_opener(*a, **k):
        raise AssertionError("must not download when snapshot exists")

    path = ensure_bulk_snapshot(
        snapshot_path=str(snap), force=False, opener=boom_opener
    )
    assert path == str(snap.resolve())


# ---------------------------------------------------------------------------
# run_bulk_sync — mass path + OAI tail + crash safety
# ---------------------------------------------------------------------------


def test_bulk_only_backfill_persists_snapshot_without_oai(tmp_path):
    """``oai_tail=False``: the snapshot alone lands the corpus; the OAI
    handler is never called (export/OAI free)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [
            _bulk_record("2401.0001", update_date="2024-01-01", license_uri=_CC_BY),
            _bulk_record(
                "2401.0002", update_date="2024-01-02", license_uri=_ARXIV_DEFAULT
            ),
            _bulk_record(
                "2401.0003", update_date="2024-01-03", license_uri=None
            ),
        ],
    )

    def boom(req: httpx.Request) -> httpx.Response:
        raise AssertionError(f"OAI must not be called in bulk-only mode: {req.url}")

    h = _harvester(tmp_path, clock, boom)
    result = run_bulk_sync(
        harvester=h,
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
    )

    assert result.census.total == 3
    assert result.census.t1 == 1
    assert result.census.t3 == 2
    assert result.census.ambiguous == 1
    assert result.new_datestamp == "2024-01-03"
    assert result.advanced is True
    assert result.persist.inserted == 3
    rows = _rows(tmp_path)
    assert len(rows) == 3
    assert {r[0] for r in rows} == {
        arxiv_doc_id(i) for i in ("2401.0001", "2401.0002", "2401.0003")
    }
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-01-03"


def test_bulk_incremental_filters_by_prior_high_water(tmp_path):
    """Incremental bulk mode only streams records on/after the prior mark."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(
        sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-02")
    )
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [
            _bulk_record("old", update_date="2024-01-01"),
            _bulk_record("edge", update_date="2024-01-02"),
            _bulk_record("new", update_date="2024-01-05"),
        ],
    )

    def empty_oai(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_oai_page().encode())

    h = _harvester(tmp_path, clock, empty_oai)
    result = run_bulk_sync(
        harvester=h,
        mode="incremental",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=True,
    )

    # since=2024-01-02 includes edge + new (inclusive lower bound, same as OAI).
    assert result.from_date == "2024-01-02"
    assert result.census.total == 2
    ids = {r[0] for r in _rows(tmp_path)}
    assert arxiv_doc_id("old") not in ids
    assert arxiv_doc_id("edge") in ids
    assert arxiv_doc_id("new") in ids
    assert result.new_datestamp == "2024-01-05"


def test_bulk_then_oai_tail_merges_newer_records(tmp_path):
    """After the bulk stream, OAI ListRecords from max(bulk_max, prior) pulls
    records newer than the snapshot. Both land in the documents store and the
    high-water mark is the newest of either stage."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [
            _bulk_record("bulk1", update_date="2024-01-01"),
            _bulk_record("bulk2", update_date="2024-01-10"),  # bulk max
        ],
    )
    seen_urls: list[str] = []

    def oai_handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen_urls.append(url)
        # Tail: one record newer than the bulk max.
        page = _oai_page(
            _oai_record("tail1", "2024-01-20", _CC_BY),
            token=None,
        )
        return httpx.Response(200, content=page.encode())

    h = _harvester(tmp_path, clock, oai_handler)
    result = run_bulk_sync(
        harvester=h,
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=True,
    )

    assert result.census.total == 3
    assert result.new_datestamp == "2024-01-20"
    # OAI was called with from= bulk max (2024-01-10).
    assert any("from=2024-01-10" in u for u in seen_urls)
    ids = {r[0] for r in _rows(tmp_path)}
    assert ids == {
        arxiv_doc_id(i) for i in ("bulk1", "bulk2", "tail1")
    }


def test_bulk_crash_mid_stream_does_not_advance_high_water(tmp_path):
    """A crash while streaming the bulk snapshot must NOT write the across-run
    high-water mark — same invariant as
    ``test_crash_mid_harvest_does_not_advance_high_water`` on the pure-OAI
    path. The next run re-covers via arxiv_id upserts (idempotent)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(
        sync_path, SyncCheckpoint(last_successful_datestamp="2023-12-31")
    )
    # Build a snapshot, then wrap the iterator to detonate after first yield.
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [
            _bulk_record("a", update_date="2024-03-09"),
            _bulk_record("b", update_date="2024-03-10"),
        ],
    )

    class _Boom(RuntimeError):
        pass

    def boom_oai(req: httpx.Request) -> httpx.Response:
        raise _Boom("should not reach OAI if bulk crashes first")

    h = _harvester(tmp_path, clock, boom_oai)

    # Monkeypatch open_bulk_snapshot's consumer by replacing iter at call site
    # via a sabotaged snapshot file that raises mid-read through a custom path.
    # Simpler: inject a crashing stream by patching iter_bulk_oai_records.
    import tools.arxiv_oai_sync as sync_mod

    real_iter = sync_mod.iter_bulk_oai_records

    def crashing_iter(fh, **kwargs):
        for n, rec in enumerate(real_iter(fh, **kwargs), start=1):
            yield rec
            if n >= 1:
                raise _Boom("disk died mid-bulk")

    original = sync_mod.iter_bulk_oai_records
    sync_mod.iter_bulk_oai_records = crashing_iter  # type: ignore[assignment]
    try:
        with pytest.raises(_Boom):
            run_bulk_sync(
                harvester=h,
                mode="incremental",
                sync_state_path=sync_path,
                bulk_snapshot_path=snap,
                harvested_at=_AT,
                oai_tail=True,
            )
    finally:
        sync_mod.iter_bulk_oai_records = original

    # Across-run mark untouched.
    assert read_checkpoint(sync_path).last_successful_datestamp == "2023-12-31"


def test_bulk_crash_mid_oai_tail_does_not_advance_high_water(tmp_path):
    """Bulk half completes, OAI tail crashes → high-water mark still not
    advanced (checkpoint only on clean completion of BOTH stages)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(
        sync_path, SyncCheckpoint(last_successful_datestamp="2023-12-31")
    )
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [_bulk_record("bulk", update_date="2024-01-05")],
    )

    class _Boom(RuntimeError):
        pass

    def crash_oai(req: httpx.Request) -> httpx.Response:
        raise _Boom("OAI tail network died")

    h = _harvester(tmp_path, clock, crash_oai)
    with pytest.raises(_Boom):
        run_bulk_sync(
            harvester=h,
            mode="incremental",
            sync_state_path=sync_path,
            bulk_snapshot_path=snap,
            harvested_at=_AT,
            oai_tail=True,
        )

    assert read_checkpoint(sync_path).last_successful_datestamp == "2023-12-31"


def test_bulk_reingest_updates_never_duplicates(tmp_path):
    """Re-running bulk over the same ids UPDATEs in place (M3 idempotency)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    records = [
        _bulk_record("2401.0001", update_date="2024-01-01"),
        _bulk_record("2401.0002", update_date="2024-01-02"),
    ]
    snap = _write_snapshot(tmp_path / "snap.json", records)

    def empty_oai(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_oai_page().encode())

    h1 = _harvester(tmp_path, clock, empty_oai, name="h1.json")
    r1 = run_bulk_sync(
        harvester=h1,
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
    )
    assert r1.persist.inserted == 2

    # Mutate title in the snapshot and re-run.
    records[0]["title"] = "CORRECTED BULK TITLE"
    _write_snapshot(tmp_path / "snap.json", records)
    h2 = _harvester(tmp_path, clock, empty_oai, name="h2.json")
    r2 = run_bulk_sync(
        harvester=h2,
        mode="backfill",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=False,
    )
    assert r2.persist.inserted == 0
    assert r2.persist.updated == 2
    rows = _rows(tmp_path)
    assert len(rows) == 2
    titles = {r[0]: r[1] for r in rows}
    assert titles[arxiv_doc_id("2401.0001")] == "CORRECTED BULK TITLE"


def test_bulk_high_water_is_monotonic_across_older_snapshot(tmp_path):
    """An older bulk window must not rewind a newer prior high-water mark."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(
        sync_path, SyncCheckpoint(last_successful_datestamp="2024-06-01")
    )
    snap = _write_snapshot(
        tmp_path / "snap.json",
        [_bulk_record("old", update_date="2024-01-03")],
    )

    def empty_oai(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_oai_page().encode())

    h = _harvester(tmp_path, clock, empty_oai)
    result = run_bulk_sync(
        harvester=h,
        mode="incremental",
        sync_state_path=sync_path,
        bulk_snapshot_path=snap,
        harvested_at=_AT,
        oai_tail=True,
    )
    # since=2024-06-01 filters the older bulk record out; empty OAI; mark stays.
    assert result.advanced is False
    assert result.new_datestamp == "2024-06-01"
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-06-01"
