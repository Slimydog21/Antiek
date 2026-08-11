"""Tests for the OAI-PMH sync driver (SPR-01 M3 incremental + M5 backfill path).

NO live network: the harvester's ``httpx.Client`` is an ``httpx.MockTransport``
serving recorded multi-page resumption sequences (the same convention as
``tests/test_open_access_ingest.py`` and ``tests/test_arxiv_oai_pmh.py``). Nothing
here touches the live arXiv OAI-PMH endpoint.

What this driver adds on top of the harvester (which is already tested for paging
/ throttle / mid-harvest crash-resume) is the ACROSS-run high-water mark:

  * M3 incremental: ``from`` = the last successful datestamp; the mark advances
    only on clean completion to the max datestamp seen; a second run with no new
    papers leaves the mark untouched and produces an empty census; the mark
    persists across a fresh process; re-covering an id never moves the mark
    backward.
  * M5 backfill: ``from`` = None walks the whole corpus through the SAME harvest
    call the operator's live backfill uses, verified against a mocked 3-page
    resumption sequence.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import duckdb  # noqa: E402

from acquisition.arxiv.adapter import arxiv_doc_id  # noqa: E402
from acquisition.arxiv.oai_pmh import (  # noqa: E402
    DEFAULT_OAI_BASE_URL,
    OaiPmhHarvester,
)
from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402
from tools.arxiv_oai_sync import (  # noqa: E402
    SyncCheckpoint,
    census_to_dict,
    read_checkpoint,
    run_sync,
    write_checkpoint,
)

_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_CC_BY_NC = "http://creativecommons.org/licenses/by-nc/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


# ---------------------------------------------------------------------------
# Fixtures: deterministic clock + recorded XML (copied convention)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _tmp_documents_db(tmp_path, monkeypatch):
    """Point the documents store at a per-test tmp DuckDB so the persistence
    `run_sync` now performs NEVER touches the real graph DB (copies the OA
    tests' ANTIEK_DUCKDB_PATH-monkeypatch convention). Autouse so every
    `run_sync` call in this module is isolated; tests that want to ASSERT
    against the rows read it back via ``_db_path(tmp_path)``."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    # Keep the harvester/sync state files under tmp too (defensive — the tests
    # already pass explicit state paths, but this guards the env-var defaults).
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))


def _db_path(tmp_path) -> str:
    return str(tmp_path / "graph.duckdb")


def _rows(tmp_path) -> list[tuple]:
    """Read every persisted (document_id, title, content_class, metadata) row
    back from the tmp documents store. Read-only connection."""
    con = duckdb.connect(_db_path(tmp_path), read_only=True)
    try:
        return con.execute(
            "SELECT document_id, title, content_class, metadata "
            "FROM documents ORDER BY document_id"
        ).fetchall()
    finally:
        con.close()


class _FakeClock:
    """Controllable clock; ``sleep`` advances instead of blocking so the >=3s
    throttle spacing is exercised without a real wait."""

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


def _record(arxiv_id: str, datestamp: str, license_uri) -> str:
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


def _deleted_record(arxiv_id: str, datestamp: str) -> str:
    return f"""
      <record>
        <header status="deleted">
          <identifier>oai:arXiv.org:{arxiv_id}</identifier>
          <datestamp>{datestamp}</datestamp>
        </header>
      </record>"""


def _page(*records: str, token: str | None = None) -> str:
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


_AT = datetime(2026, 5, 29, tzinfo=UTC)


def test_harvester_defaults_to_current_arxiv_oai_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTIEK_ARXIV_OAI_BASE_URL", raising=False)
    harvester = OaiPmhHarvester(
        throttle=_throttle(tmp_path, _FakeClock()),
        state_path=str(tmp_path / "harvest.json"),
    )

    assert DEFAULT_OAI_BASE_URL == "https://oaipmh.arxiv.org/oai"
    assert harvester._base_url == DEFAULT_OAI_BASE_URL


def test_harvester_preserves_explicit_oai_endpoint_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_BASE_URL", "https://env.test/oai")
    harvester = OaiPmhHarvester(
        throttle=_throttle(tmp_path, _FakeClock()),
        base_url="https://explicit.test/oai",
        state_path=str(tmp_path / "harvest.json"),
    )

    assert harvester._base_url == "https://explicit.test/oai"


# A three-page corpus: 3 CC-BY (T1), 1 arxiv-default (T3), 1 absent (T3 + amb).
_PAGE_1 = _page(
    _record("2401.0001", "2024-01-01", _CC_BY),
    _record("2401.0002", "2024-01-01", _ARXIV_DEFAULT),
    token="TOK1",
)
_PAGE_2 = _page(
    _record("2401.0003", "2024-01-02", _CC_BY),
    _record("2401.0004", "2024-01-02", None),
    token="TOK2",
)
_PAGE_3 = _page(
    _record("2401.0005", "2024-01-03", _CC_BY),
    token=None,
)


def _three_page_handler(seen_urls: list[str]):
    """Walk the 3-page sequence keyed off the resumptionToken, recording each
    request URL so a test can assert the ``from`` window on the first page."""

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen_urls.append(url)
        if "resumptionToken=TOK1" in url:
            return httpx.Response(200, content=_PAGE_2.encode())
        if "resumptionToken=TOK2" in url:
            return httpx.Response(200, content=_PAGE_3.encode())
        return httpx.Response(200, content=_PAGE_1.encode())

    return handler


# ---------------------------------------------------------------------------
# Checkpoint persistence (the across-run high-water mark)
# ---------------------------------------------------------------------------


def test_checkpoint_round_trips_through_disk(tmp_path):
    path = str(tmp_path / "sync.json")
    write_checkpoint(
        path, SyncCheckpoint(last_successful_datestamp="2024-01-03",
                             last_harvested_at="2026-05-29T00:00:00+00:00")
    )
    loaded = read_checkpoint(path)
    assert loaded.last_successful_datestamp == "2024-01-03"
    assert loaded.last_harvested_at == "2026-05-29T00:00:00+00:00"


def test_missing_checkpoint_reads_as_empty(tmp_path):
    loaded = read_checkpoint(str(tmp_path / "absent.json"))
    assert loaded == SyncCheckpoint()
    assert loaded.last_successful_datestamp is None


def test_corrupt_checkpoint_degrades_to_empty_not_crash(tmp_path):
    """A truncated/garbage file must read as the empty checkpoint (degrade to a
    backfill) rather than crash — same fail-readable discipline as the throttle."""
    path = tmp_path / "sync.json"
    path.write_text("{not valid json")
    assert read_checkpoint(str(path)) == SyncCheckpoint()


# ---------------------------------------------------------------------------
# M3: incremental harvest from the last successful datestamp
# ---------------------------------------------------------------------------


def test_first_incremental_run_has_no_lower_bound_and_sets_high_water(tmp_path):
    """With no prior checkpoint, the first incremental run behaves like a
    backfill (no ``from``) and on clean completion stamps the high-water mark at
    the MAX datestamp seen (not the first, not the last fetched — the max)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    seen: list[str] = []
    h = _harvester(tmp_path, clock, _three_page_handler(seen))

    result = run_sync(
        harvester=h, mode="incremental", sync_state_path=sync_path,
        harvested_at=_AT,
    )

    # No prior mark -> no ``from`` on the first request.
    assert "from=" not in seen[0]
    assert result.from_date is None
    # 5 records, max datestamp 2024-01-03.
    assert result.census.total == 5
    assert result.advanced is True
    assert result.new_datestamp == "2024-01-03"
    # And the mark is persisted.
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-01-03"


def test_incremental_run_uses_persisted_datestamp_as_from(tmp_path):
    """A prior high-water mark becomes the ``from`` lower bound of the next
    incremental run — that is the whole point of the daily sync."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-01"))
    seen: list[str] = []
    h = _harvester(tmp_path, clock, _three_page_handler(seen))

    result = run_sync(
        harvester=h, mode="incremental", sync_state_path=sync_path,
        harvested_at=_AT,
    )

    assert result.from_date == "2024-01-01"
    assert "from=2024-01-01" in seen[0]
    assert "metadataPrefix=arXiv" in seen[0]


def test_second_run_with_no_new_papers_writes_nothing_and_exits_clean(tmp_path):
    """M3 acceptance: a second run whose window has no records produces an empty
    census, leaves the high-water datestamp UNTOUCHED, and does not raise."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-03"))

    def empty_handler(req: httpx.Request) -> httpx.Response:
        # An empty ListRecords page (no records, no token) — the OAI shape for
        # "nothing matched the window".
        return httpx.Response(200, content=_page().encode())

    h = _harvester(tmp_path, clock, empty_handler)
    result = run_sync(
        harvester=h, mode="incremental", sync_state_path=sync_path,
        harvested_at=_AT,
    )

    assert result.census.total == 0
    assert result.advanced is False
    # The datestamp mark is exactly where it was — no silent reset, no advance.
    assert result.new_datestamp == "2024-01-03"
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-01-03"


def test_high_water_mark_persists_across_a_fresh_process(tmp_path):
    """M3 acceptance: the checkpoint survives 'restart' — a brand-new harvester
    + a brand-new run reading the same sync file sees the advanced mark."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")

    # Run 1: full 3-page harvest sets the mark to 2024-01-03.
    h1 = _harvester(tmp_path, clock, _three_page_handler([]), name="h1.json")
    run_sync(harvester=h1, mode="incremental", sync_state_path=sync_path,
             harvested_at=_AT)

    # Run 2: a SEPARATE harvester reads the persisted mark and uses it as ``from``.
    seen2: list[str] = []

    def only_after(req: httpx.Request) -> httpx.Response:
        seen2.append(str(req.url))
        return httpx.Response(200, content=_page().encode())  # nothing new

    h2 = _harvester(tmp_path, clock, only_after, name="h2.json")
    result2 = run_sync(harvester=h2, mode="incremental", sync_state_path=sync_path,
                       harvested_at=_AT)

    assert result2.from_date == "2024-01-03"
    assert "from=2024-01-03" in seen2[0]


def test_high_water_mark_is_monotonic_never_retreats(tmp_path):
    """Re-covering an OLDER slice (e.g. a targeted backfill of a past window)
    must NOT rewind the mark below where 'today' already reached."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-06-01"))

    # A window whose newest record (2024-01-03) is OLDER than the prior mark.
    h = _harvester(tmp_path, clock, _three_page_handler([]))
    result = run_sync(harvester=h, mode="incremental", sync_state_path=sync_path,
                      harvested_at=_AT)

    assert result.advanced is False
    assert result.new_datestamp == "2024-06-01"
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-06-01"


def test_max_datestamp_not_last_fetched_wins(tmp_path):
    """The high-water mark is the MAX datestamp, not the datestamp of the last
    record in fetch order — an out-of-order page must not lower the mark."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")

    # Page 1 carries the newest record; page 2 (final) carries an older one.
    p1 = _page(_record("a", "2024-03-09", _CC_BY), token="N")
    p2 = _page(_record("b", "2024-01-01", _CC_BY), token=None)

    def handler(req: httpx.Request) -> httpx.Response:
        if "resumptionToken=N" in str(req.url):
            return httpx.Response(200, content=p2.encode())
        return httpx.Response(200, content=p1.encode())

    h = _harvester(tmp_path, clock, handler)
    result = run_sync(harvester=h, mode="incremental", sync_state_path=sync_path,
                      harvested_at=_AT)
    assert result.new_datestamp == "2024-03-09"


def test_crash_mid_harvest_does_not_advance_high_water(tmp_path):
    """A crash mid-harvest must propagate BEFORE the high-water mark is written,
    so a partial harvest never advances the across-run mark; the harvester's own
    mid-harvest cursor covers re-covering the consumed pages on the next run."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2023-12-31"))

    class _Boom(RuntimeError):
        pass

    def handler(req: httpx.Request) -> httpx.Response:
        if "resumptionToken=TOK1" in str(req.url):
            raise _Boom("network died mid-harvest")
        return httpx.Response(200, content=_PAGE_1.encode())

    h = _harvester(tmp_path, clock, handler)
    with pytest.raises(_Boom):
        run_sync(harvester=h, mode="incremental", sync_state_path=sync_path,
                 harvested_at=_AT)

    # The across-run mark is untouched by the aborted run.
    assert read_checkpoint(sync_path).last_successful_datestamp == "2023-12-31"


def test_active_ban_propagates_and_leaves_mark_untouched(tmp_path):
    """A pre-existing ban raises ArxivBanned out of run_sync (the throttle pauses
    before any request) and the high-water mark is not advanced."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-01"))
    throttle = ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"), now=clock.now, sleep=clock.sleep
    )
    throttle.note_response(429, headers={"Retry-After": "3600"})  # set the ban

    seen: list[str] = []
    h = OaiPmhHarvester(
        throttle=throttle,
        client=_mock_client(_three_page_handler(seen)),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    with pytest.raises(ArxivBanned):
        run_sync(harvester=h, mode="incremental", sync_state_path=sync_path,
                 harvested_at=_AT)
    assert seen == []  # not one request issued while banned
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-01-01"


# ---------------------------------------------------------------------------
# M5: full backfill code path (LIVE backfill is operator-only)
# ---------------------------------------------------------------------------


def test_backfill_has_no_lower_bound_even_with_a_prior_mark(tmp_path):
    """M5 code path: backfill drops the ``from`` bound regardless of any prior
    incremental mark, walking the WHOLE corpus through the same harvest call the
    operator runs live against export.arxiv.org."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-02"))
    seen: list[str] = []
    h = _harvester(tmp_path, clock, _three_page_handler(seen))

    result = run_sync(
        harvester=h, mode="backfill", sync_state_path=sync_path, harvested_at=_AT,
    )

    assert result.from_date is None
    assert "from=" not in seen[0]
    assert "metadataPrefix=arXiv" in seen[0]
    # The full corpus came back across all 3 pages.
    assert result.census.total == 5
    # Backfill still advances the mark to the newest datestamp it saw.
    assert result.new_datestamp == "2024-01-03"


def test_backfill_pages_through_resumption_to_completion(tmp_path):
    """The mocked 3-page resumption sequence is driven to completion through the
    SAME paging code the operator's live backfill uses — this is the M5
    verification (no socket is opened)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    seen: list[str] = []
    h = _harvester(tmp_path, clock, _three_page_handler(seen))

    run_sync(harvester=h, mode="backfill", sync_state_path=sync_path, harvested_at=_AT)

    # Three pages fetched; first carries the prefix, the rest carry only tokens.
    assert len(seen) == 3
    assert "metadataPrefix=arXiv" in seen[0]
    assert "resumptionToken=TOK1" in seen[1] and "metadataPrefix" not in seen[1]
    assert "resumptionToken=TOK2" in seen[2] and "metadataPrefix" not in seen[2]


def test_unknown_mode_is_rejected(tmp_path):
    clock = _FakeClock()
    h = _harvester(tmp_path, clock, _three_page_handler([]))
    with pytest.raises(ValueError):
        run_sync(harvester=h, mode="sideways",
                 sync_state_path=str(tmp_path / "sync.json"), harvested_at=_AT)


# ---------------------------------------------------------------------------
# Census reproducibility + honesty (the payout-gating number)
# ---------------------------------------------------------------------------


def test_census_stamps_the_reproducing_query(tmp_path):
    """Rigor bar 5: the census carries the EXACT query that reproduces it —
    metadataPrefix + the from/until window + the harvest timestamp."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-01"))
    h = _harvester(tmp_path, clock, _three_page_handler([]))

    result = run_sync(
        harvester=h, mode="incremental", sync_state_path=sync_path,
        until_date="2024-12-31", harvested_at=_AT,
    )
    c = result.census
    assert c.metadata_prefix == "arXiv"
    assert c.from_date == "2024-01-01"
    assert c.until_date == "2024-12-31"
    assert c.harvested_at == _AT


def test_census_partition_is_exhaustive_and_ambiguous_reported(tmp_path):
    """Constraint 3 + honesty bar: T1+T2+T3==total (the self-check is live), and
    the absent-license count is reported separately — never inflated into T1 nor
    hidden inside T3."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")

    # 1 CC-BY (T1), 1 CC-BY-NC (T2), 1 arxiv-default (T3), 1 absent (T3 + amb).
    p = _page(
        _record("a", "2024-02-01", _CC_BY),
        _record("b", "2024-02-01", _CC_BY_NC),
        _record("c", "2024-02-01", _ARXIV_DEFAULT),
        _record("d", "2024-02-01", None),
        token=None,
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=p.encode())

    h = _harvester(tmp_path, clock, handler)
    result = run_sync(harvester=h, mode="backfill", sync_state_path=sync_path,
                      harvested_at=_AT)
    c = result.census
    assert (c.t1, c.t2, c.t3) == (1, 1, 2)
    assert c.total == 4
    assert c.t1 + c.t2 + c.t3 == c.total
    assert c.ambiguous == 1  # only the absent-license one, NOT arxiv-default


def test_deleted_tombstone_excluded_from_denominator_but_advances_window(tmp_path):
    """A deletion carries a datestamp (it advances the harvest window) but no
    license — counting it as unknown-license would understate T1's share of LIVE
    papers, so it is tallied separately and excluded from total."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    p = _page(
        _record("live", "2024-04-01", _CC_BY),
        _deleted_record("gone", "2024-04-02"),
        token=None,
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=p.encode())

    h = _harvester(tmp_path, clock, handler)
    result = run_sync(harvester=h, mode="backfill", sync_state_path=sync_path,
                      harvested_at=_AT)
    assert result.census.total == 1
    assert result.census.deleted == 1
    # The tombstone's datestamp is the newest -> it advances the high-water mark.
    assert result.new_datestamp == "2024-04-02"


def test_census_json_record_has_counts_and_query_no_hand_rounded_pct(tmp_path):
    """The machine-readable census record carries integer counts + the
    reproducing query and the high-water datestamp; it never emits a hand-rounded
    percentage (the reader recomputes fractions from the integers)."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    h = _harvester(tmp_path, clock, _three_page_handler([]))
    result = run_sync(harvester=h, mode="backfill", sync_state_path=sync_path,
                      harvested_at=_AT)

    record = census_to_dict(result)
    assert record["metadata_prefix"] == "arXiv"
    assert record["from_date"] is None
    assert record["total"] == 5
    assert record["t1"] == 3 and record["t3"] == 2
    assert record["ambiguous"] == 1
    assert record["high_water_datestamp"] == "2024-01-03"
    # The serialised record is integers + the query only — no float percentages.
    assert json.dumps(record)  # round-trips as JSON
    assert not any(isinstance(v, float) for v in record.values())


# ---------------------------------------------------------------------------
# M3 + M5: the harvest actually LANDS in the documents store (persistence)
# ---------------------------------------------------------------------------


def test_backfill_persists_the_full_metadata_corpus_to_the_db(tmp_path):
    """M5 acceptance: a from=None backfill over the mocked 3-page resumption
    sequence lands the WHOLE live corpus as documents rows (one per non-deleted
    record), keyed by the stable doc id — the census is no longer a count with
    no corpus behind it."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    h = _harvester(tmp_path, clock, _three_page_handler([]))

    result = run_sync(harvester=h, mode="backfill", sync_state_path=sync_path,
                      harvested_at=_AT)

    rows = _rows(tmp_path)
    # 5 live records across the 3 pages -> 5 rows; the doc ids are the stable
    # doc-arxiv-<id> keys, present for every id in the mocked corpus.
    assert len(rows) == 5
    ids = {r[0] for r in rows}
    assert ids == {arxiv_doc_id(i) for i in (
        "2401.0001", "2401.0002", "2401.0003", "2401.0004", "2401.0005",
    )}
    # The result tally agrees with what's on disk.
    assert result.persist.inserted == 5
    assert result.persist.updated == 0
    assert result.persist.persisted == 5
    assert census_to_dict(result)["persisted_rows"] == 5


def test_reingesting_same_ids_updates_never_duplicates(tmp_path):
    """M3 acceptance (the round-1 gap): re-ingesting the SAME ids UPDATES the
    rows in place — the row COUNT is unchanged and a mutated field (the title)
    is refreshed — rather than inserting duplicates."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")

    # First pass: the standard 3-page corpus.
    h1 = _harvester(tmp_path, clock, _three_page_handler([]), name="h1.json")
    r1 = run_sync(harvester=h1, mode="backfill", sync_state_path=sync_path,
                  harvested_at=_AT)
    assert len(_rows(tmp_path)) == 5
    assert r1.persist.inserted == 5 and r1.persist.updated == 0

    # Second pass: the SAME ids, but one record's title is mutated (arXiv
    # corrected the title between harvests). Build a one-page corpus carrying
    # the same five ids so the upsert is exercised on every one.
    mutated = _page(
        _record("2401.0001", "2024-01-01", _CC_BY),
        _record("2401.0002", "2024-01-01", _ARXIV_DEFAULT),
        _record("2401.0003", "2024-01-02", _CC_BY),
        _record("2401.0004", "2024-01-02", None),
        _record("2401.0005", "2024-01-03", _CC_BY),
        token=None,
    ).replace("<title>T 2401.0001</title>", "<title>CORRECTED TITLE</title>")

    def reingest_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=mutated.encode())

    h2 = _harvester(tmp_path, clock, reingest_handler, name="h2.json")
    r2 = run_sync(harvester=h2, mode="backfill", sync_state_path=sync_path,
                  harvested_at=_AT)

    rows = _rows(tmp_path)
    # No duplicates: still exactly five rows after re-ingesting the same ids.
    assert len(rows) == 5
    # All five were UPDATEd, none inserted.
    assert r2.persist.inserted == 0
    assert r2.persist.updated == 5
    # The mutated field landed: the row for 2401.0001 now carries the new title.
    titles = {r[0]: r[1] for r in rows}
    assert titles[arxiv_doc_id("2401.0001")] == "CORRECTED TITLE"


def test_persisted_rows_are_gated_floor_with_license_recorded(tmp_path):
    """Deny-by-default: every metadata-only row lands at the GATED FLOOR content
    class (there is no body yet — PDF full text is SPR-04's job). The
    AUTHORITATIVE OAI <license> URI + the resolved tier are recorded in metadata
    so SPR-04 can promote without re-harvesting."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    h = _harvester(tmp_path, clock, _three_page_handler([]))
    run_sync(harvester=h, mode="backfill", sync_state_path=sync_path,
             harvested_at=_AT)

    rows = _rows(tmp_path)
    # Deny-by-default: EVERY row is the gated floor, even the CC-BY ones —
    # a bodyless metadata row is never servable.
    assert {r[2] for r in rows} == {GATED_DEFAULT_CONTENT_CLASS}

    by_id = {r[0]: json.loads(r[3]) for r in rows}
    # A CC-BY record: the authoritative URI is recorded verbatim; the tier
    # resolves to T1; the license-derived class is preserved for SPR-04.
    cc_by_meta = by_id[arxiv_doc_id("2401.0001")]
    assert cc_by_meta["license_uri"] == _CC_BY
    assert cc_by_meta["rights_tier"] == "T1"
    assert cc_by_meta["license_content_class"] == "source_declared_open"
    assert cc_by_meta["source"] == "arxiv_oai_pmh"
    # An absent-license record: URI is None; the tier is the deny-by-default T3.
    absent_meta = by_id[arxiv_doc_id("2401.0004")]
    assert absent_meta["license_uri"] is None
    assert absent_meta["rights_tier"] == "T3"
    assert absent_meta["license_content_class"] == GATED_DEFAULT_CONTENT_CLASS


def test_deleted_tombstone_is_not_persisted_as_a_corpus_row(tmp_path):
    """A deletion advances the harvest window but carries no metadata; it must
    NOT land as a documents row (it is not a corpus row), while the live record
    on the same page does."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    p = _page(
        _record("live", "2024-04-01", _CC_BY),
        _deleted_record("gone", "2024-04-02"),
        token=None,
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=p.encode())

    h = _harvester(tmp_path, clock, handler)
    result = run_sync(harvester=h, mode="backfill", sync_state_path=sync_path,
                      harvested_at=_AT)

    rows = _rows(tmp_path)
    assert {r[0] for r in rows} == {arxiv_doc_id("live")}
    assert result.persist.persisted == 1
    assert result.persist.skipped_deleted == 1


def test_incremental_run_persists_only_the_new_window(tmp_path):
    """M3: a daily incremental run persists the records its window returned (the
    same rows the census counted), keyed by id so a later overlap re-covers
    idempotently."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2024-01-01"))
    h = _harvester(tmp_path, clock, _three_page_handler([]))

    result = run_sync(harvester=h, mode="incremental", sync_state_path=sync_path,
                      harvested_at=_AT)

    assert len(_rows(tmp_path)) == 5
    assert result.persist.persisted == 5


# ---------------------------------------------------------------------------
# SHOULD-FIX: crash-resume high-water correctness (monotonic across a crash)
# ---------------------------------------------------------------------------


def test_post_crash_high_water_is_at_least_max_consumed_pre_crash(tmp_path):
    """After a crash mid-harvest, the resumed run sees only the REMAINING (older)
    pages. The across-run mark must NOT fall below the max datestamp ALREADY
    consumed before the crash — it is seeded from the harvester's persisted max.

    Page 1 carries the NEWEST datestamp (2024-03-09); the crash hits page 2; on
    resume page 2 carries an OLDER datestamp (2024-01-05). Without the seed the
    resumed run would set the mark to 2024-01-05 (below what was consumed). With
    it, the mark stays >= 2024-03-09."""
    clock = _FakeClock()
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2023-12-31"))

    page_1 = _page(_record("new", "2024-03-09", _CC_BY), token="TOK")
    page_2 = _page(_record("old", "2024-01-05", _CC_BY), token=None)

    class _Boom(RuntimeError):
        pass

    state = {"crash": True}

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "resumptionToken=TOK" in url:
            if state["crash"]:
                raise _Boom("network died after page 1")
            return httpx.Response(200, content=page_2.encode())
        return httpx.Response(200, content=page_1.encode())

    # Crash run: page 1 (max 2024-03-09) is consumed + the cursor persisted,
    # then the page-2 request detonates.
    h = _harvester(tmp_path, clock, handler)
    with pytest.raises(_Boom):
        run_sync(harvester=h, mode="incremental", sync_state_path=sync_path,
                 harvested_at=_AT)
    # The crash did not advance the across-run mark.
    assert read_checkpoint(sync_path).last_successful_datestamp == "2023-12-31"
    # The harvester persisted the pre-crash max as its resume seed.
    assert h.persisted_max_datestamp() == "2024-03-09"

    # Resume run: the cursor replays only page 2 (older). A SEPARATE harvester
    # instance reading the SAME state path proves the seed survives a restart.
    state["crash"] = False
    h2 = _harvester(tmp_path, clock, handler, name="harvest.json")
    result = run_sync(harvester=h2, mode="incremental", sync_state_path=sync_path,
                      harvested_at=_AT)

    # The mark is monotonic with what was consumed pre-crash: it is the
    # pre-crash max (2024-03-09), NOT the older remaining page's 2024-01-05.
    assert result.new_datestamp == "2024-03-09"
    assert read_checkpoint(sync_path).last_successful_datestamp == "2024-03-09"
    assert result.new_datestamp >= "2024-03-09"
