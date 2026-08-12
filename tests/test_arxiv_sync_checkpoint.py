"""Checkpoint/resume hardening tests for the arXiv OAI-PMH sync (2026-08-12).

Builds on ``test_arxiv_oai_pmh.py`` / ``test_arxiv_oai_sync.py`` conventions:
NO live network — the ``httpx.Client`` is an ``httpx.MockTransport`` serving a
recorded multi-page resumption-token sequence, and the documents store is a
per-test tmp DuckDB.

What THIS module verifies (the schema-v2 hardening):

  * a first run writes the versioned state file (``schema_version: 2``) with
    the resumption token + skip counter + last-completed-page timestamp after
    every page;
  * a simulated kill mid-harvest then a fresh process resumes from the stored
    token (no re-fetch of consumed pages) and the skip counter continues
    cumulatively across the crash boundary;
  * a completed harvest clears the harvester cursor AND advances the sync's
    across-run high-water mark;
  * ``--reset-state`` (operator recovery) removes BOTH checkpoint files so the
    next incremental run behaves like a first-run backfill, while the throttle
    state is untouched;
  * schema versioning on load: v1 files migrate in place, an unknown FUTURE
    version reads as fresh (degrade, don't crash), a non-object state file
    reads as fresh;
  * the OAI channel's User-Agent carries the arXiv-required contact (audit §6).
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

from acquisition.arxiv import oai_pmh as oai_pmh_mod  # noqa: E402
from acquisition.arxiv.oai_pmh import (  # noqa: E402
    DEFAULT_USER_AGENT,
    SCHEMA_VERSION,
    OaiPmhHarvester,
)
from acquisition.arxiv.oai_pmh import HarvestState  # noqa: E402
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402
from tools.arxiv_oai_sync import (  # noqa: E402
    build_parser,
    read_checkpoint,
    reset_state_files,
    run_sync,
    write_checkpoint,
    SyncCheckpoint,
)

_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"

_PINNED_PAGE_AT = "2026-08-12T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures: deterministic clock + recorded XML (copied convention)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _tmp_documents_db(tmp_path, monkeypatch):
    """Point the documents store + ALL arXiv state files (including the
    host-global throttle state and the governor's flock sidecar) at per-test
    tmp paths so run_sync persistence and the env-var defaults never touch the
    real graph DB or ~/.antiek (copies test_arxiv_oai_sync.py's convention).

    The throttle/governor pins are load-bearing for hermeticity: every harvest
    send routes through ``governed_request``, whose flock defaults to the REAL
    ~/.antiek/arxiv_throttle.json.governor.lock. Without the override a test
    run contends with every other arXiv job on the machine (observed: an
    orphaned pytest held that lock for 18h and stalled this suite 17 minutes)."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(tmp_path / "throttle.json"))
    monkeypatch.setenv(
        "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", str(tmp_path / "throttle.json.governor.lock")
    )
    monkeypatch.setattr(oai_pmh_mod, "_now_iso", lambda: _PINNED_PAGE_AT)


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


def _page(*records: str, token: str | None = None) -> str:
    rt = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_NS}>
  <responseDate>2026-05-29T00:00:00Z</responseDate>
  <ListRecords>{''.join(records)}{rt}</ListRecords>
</OAI-PMH>"""


# A three-page harvest: page1 -> TOK1, page2 -> TOK2, page3 -> done.
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


def _multi_page_handler(seen_urls: list[str], seen_uas: list[str] | None = None):
    """Serve the 3-page sequence keyed off the resumptionToken in the request
    URL, recording each URL (and, optionally, each User-Agent header)."""

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen_urls.append(url)
        if seen_uas is not None:
            seen_uas.append(req.headers.get("User-Agent", ""))
        if "resumptionToken=TOK1" in url:
            return httpx.Response(200, content=_PAGE_2.encode())
        if "resumptionToken=TOK2" in url:
            return httpx.Response(200, content=_PAGE_3.encode())
        return httpx.Response(200, content=_PAGE_1.encode())

    return handler


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _harvester(tmp_path, clock, handler, *, state_path="harvest.json") -> OaiPmhHarvester:
    return OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(handler),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / state_path),
    )


class _Boom(RuntimeError):
    """Simulated kill: the network dies mid-harvest."""


# ---------------------------------------------------------------------------
# 1. First run writes the versioned state file with progress bookkeeping
# ---------------------------------------------------------------------------


def test_first_run_writes_versioned_state_with_progress(tmp_path, monkeypatch):
    """After the first page of a fresh harvest the state file exists with
    schema_version=2, the next resumption token, the skip counter (= records
    consumed so far) and the pinned last-completed-page timestamp."""
    clock = _FakeClock()
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if len(seen) == 2:
            raise _Boom("network died after page 1")  # kill before page 2
        return httpx.Response(200, content=_PAGE_1.encode())

    h = _harvester(tmp_path, clock, handler)
    state_path = tmp_path / "harvest.json"

    with pytest.raises(_Boom):
        for _ in h.harvest(from_date="2024-01-01", until_date="2024-01-31"):
            pass

    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION == 2
    assert raw["resumption_token"] == "TOK1"
    assert raw["last_datestamp"] == "2024-01-01"  # max datestamp consumed
    assert raw["skip_count"] == 2  # two records on page 1
    assert raw["last_page_at"] == _PINNED_PAGE_AT


# ---------------------------------------------------------------------------
# 2. Simulated kill then resume continues from the stored token
# ---------------------------------------------------------------------------


def test_simulated_kill_then_resume_continues_from_stored_token(tmp_path):
    """Run 1 dies after page 1. Run 2 (a FRESH process: new harvester, new
    client) resumes from the persisted token — it never re-requests the
    first page — and the skip counter continues cumulatively across the crash
    boundary."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"

    # --- run 1: page 1 consumed, then the network dies before page 2. ---
    seen1: list[str] = []

    def killer(req: httpx.Request) -> httpx.Response:
        seen1.append(str(req.url))
        if len(seen1) == 2:
            raise _Boom("network died mid-harvest")
        return httpx.Response(200, content=_PAGE_1.encode())

    h1 = _harvester(tmp_path, clock, killer)
    with pytest.raises(_Boom):
        for _ in h1.harvest():
            pass
    assert json.loads(state_path.read_text(encoding="utf-8"))["resumption_token"] == "TOK1"

    # --- run 2: a brand-new harvester resumes from the stored cursor. ---
    seen2: list[str] = []
    h2 = _harvester(tmp_path, clock, _multi_page_handler(seen2))
    got = [r.arxiv_id for r in h2.harvest()]

    # Only the REMAINING pages were fetched — never the first (tokenless) page.
    assert got == ["2401.0003", "2401.0004", "2401.0005"]
    assert len(seen2) == 2  # TOK1 page + TOK2 page
    assert "resumptionToken=TOK1" in seen2[0]
    assert "resumptionToken=TOK2" in seen2[1]
    assert "metadataPrefix" not in seen2[0]  # a resumed page never re-carries the window
    # The completed harvest cleared the cursor.
    assert not state_path.exists()


def test_skip_counter_cumulative_two_phase(tmp_path):
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"

    # Phase 1: page 1, then the network dies.
    seen1: list[str] = []

    def killer(req: httpx.Request) -> httpx.Response:
        seen1.append(str(req.url))
        if len(seen1) == 2:
            raise _Boom("network died mid-harvest")
        return httpx.Response(200, content=_PAGE_1.encode())

    h1 = _harvester(tmp_path, clock, killer)
    with pytest.raises(_Boom):
        for _ in h1.harvest():
            pass
    assert json.loads(state_path.read_text(encoding="utf-8"))["skip_count"] == 2

    # Phase 2: resume, then die again after the TOK1 page (before TOK2).
    seen2: list[str] = []

    def killer2(req: httpx.Request) -> httpx.Response:
        seen2.append(str(req.url))
        if len(seen2) == 2:
            raise _Boom("network died again")
        return httpx.Response(200, content=_PAGE_2.encode())

    h2 = _harvester(tmp_path, clock, killer2)
    with pytest.raises(_Boom):
        for _ in h2.harvest():
            pass

    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["resumption_token"] == "TOK2"
    assert raw["skip_count"] == 4  # 2 (pre-crash) + 2 (resumed page) — never reset
    assert raw["last_page_at"] == _PINNED_PAGE_AT


# ---------------------------------------------------------------------------
# 3. Completed harvest clears the cursor AND advances the sync high-water mark
# ---------------------------------------------------------------------------


def test_completed_harvest_clears_cursor_and_advances_sync_checkpoint(tmp_path):
    """A clean 3-page harvest removes the harvester cursor file and advances
    the sync's across-run high-water mark to the max datestamp seen."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"
    sync_path = tmp_path / "sync.json"

    seen: list[str] = []
    h = _harvester(tmp_path, clock, _multi_page_handler(seen))
    result = run_sync(
        harvester=h,
        mode="backfill",
        sync_state_path=str(sync_path),
        harvested_at=datetime(2026, 5, 29, tzinfo=UTC),
    )

    assert not state_path.exists()  # harvester cursor cleared
    assert result.advanced
    assert result.new_datestamp == "2024-01-03"
    cp = read_checkpoint(str(sync_path))
    assert cp.last_successful_datestamp == "2024-01-03"
    assert cp.last_harvested_at is not None


# ---------------------------------------------------------------------------
# 4. --reset-state: operator recovery removes BOTH checkpoint files
# ---------------------------------------------------------------------------


def test_reset_state_removes_both_checkpoints(tmp_path, monkeypatch):
    harvest_path = tmp_path / "harvest.json"
    sync_path = tmp_path / "sync.json"
    harvest_path.write_text(json.dumps({"schema_version": 2, "resumption_token": "TOK1"}))
    sync_path.write_text(json.dumps({"last_successful_datestamp": "2024-01-03"}))

    removed = reset_state_files(
        harvest_state_path=str(harvest_path), sync_state_path=str(sync_path)
    )

    assert {str(p) for p in removed} == {str(harvest_path), str(sync_path)}
    assert not harvest_path.exists()
    assert not sync_path.exists()
    # And the throttle state is NOT in scope: an untouched third file survives.
    throttle_path = tmp_path / "throttle.json"
    throttle_path.write_text(json.dumps({"banned_until": 999999.0}))
    reset_state_files(harvest_state_path=str(harvest_path), sync_state_path=str(sync_path))
    assert throttle_path.exists()


def test_reset_state_with_no_files_returns_empty(tmp_path):
    assert (
        reset_state_files(
            harvest_state_path=str(tmp_path / "nope.json"),
            sync_state_path=str(tmp_path / "nope2.json"),
        )
        == ()
    )


def test_reset_state_flag_wired_into_cli_and_defaults(tmp_path, monkeypatch):
    """The CLI flag exists and the default-path resolution honors the env
    overrides (so a `--reset-state` run on the box clears exactly the files
    systemd pins)."""
    args = build_parser().parse_args(["incremental", "--reset-state"])
    assert args.reset_state is True
    # Defaults resolve to the env-pinned paths (autouse fixture).
    removed = reset_state_files()
    assert removed == ()
    assert not (tmp_path / "harvest.json").exists()
    assert not (tmp_path / "sync.json").exists()


def test_reset_state_makes_next_incremental_a_fresh_backfill(tmp_path):
    """End-to-end: after reset_state_files, an incremental run has no high-water
    mark and no mid-harvest cursor, so it requests the FIRST page with the full
    window (no `from=` bound) — i.e. it behaves like a first-run backfill."""
    clock = _FakeClock()
    sync_path = tmp_path / "sync.json"
    harvest_path = tmp_path / "harvest.json"
    # A prior wedged state: mid-harvest cursor + a high-water mark.
    harvest_path.write_text(json.dumps({"schema_version": 2, "resumption_token": "TOK1"}))
    write_checkpoint(str(sync_path), SyncCheckpoint(last_successful_datestamp="2024-01-03"))

    reset_state_files(harvest_state_path=str(harvest_path), sync_state_path=str(sync_path))

    seen: list[str] = []
    h = _harvester(tmp_path, clock, _multi_page_handler(seen))
    result = run_sync(
        harvester=h,
        mode="incremental",
        sync_state_path=str(sync_path),
        harvested_at=datetime(2026, 5, 29, tzinfo=UTC),
    )
    assert result.from_date is None  # no high-water mark -> full window
    assert "metadataPrefix=arXiv" in seen[0]  # fresh first page, not a token resume
    assert result.new_datestamp == "2024-01-03"


# ---------------------------------------------------------------------------
# 5. Schema versioning on load
# ---------------------------------------------------------------------------


def test_schema_v1_file_migrates_on_load(tmp_path):
    """A pre-v2 state file (no schema_version key) loads with its token intact
    and resumes from it; the schema_version field reads as 1 and the next page
    write upgrades the file to v2 in place."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"
    state_path.write_text(
        json.dumps({"resumption_token": "TOK1", "last_datestamp": "2024-01-01"}),
        encoding="utf-8",
    )

    seen: list[str] = []
    h = _harvester(tmp_path, clock, _multi_page_handler(seen))
    loaded = h._read_state()
    assert loaded.schema_version == 1
    assert loaded.resumption_token == "TOK1"
    assert loaded.skip_count == 0  # v1 carried no progress bookkeeping

    got = [r.arxiv_id for r in h.harvest()]
    assert got == ["2401.0003", "2401.0004", "2401.0005"]  # resumed, not restarted
    assert "resumptionToken=TOK1" in seen[0]
    assert not state_path.exists()  # completed harvest cleared it (never written back)


def test_unknown_future_schema_version_reads_fresh(tmp_path):
    """A state file from a NEWER schema must not be guessed at: it reads as
    fresh (degrade, don't crash) and the harvest restarts from the first page.
    The operator can then decide whether to --reset-state."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"
    state_path.write_text(
        json.dumps({"schema_version": 99, "resumption_token": "FUTURE", "skip_count": 10}),
        encoding="utf-8",
    )

    seen: list[str] = []
    h = _harvester(tmp_path, clock, _multi_page_handler(seen))
    assert h._read_state() == HarvestState()  # fresh: no token, no counters

    got = [r.arxiv_id for r in h.harvest()]
    assert got == ["2401.0001", "2401.0002", "2401.0003", "2401.0004", "2401.0005"]
    assert "metadataPrefix=arXiv" in seen[0]  # restarted from the first page
    assert not state_path.exists()


def test_non_object_state_file_reads_fresh(tmp_path):
    """A JSON array/string state file (torn or hand-edited) must read as fresh
    and NOT crash the nightly (regression: pre-hardening this raised
    AttributeError on `.get`)."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"
    state_path.write_text("[]", encoding="utf-8")

    seen: list[str] = []
    h = _harvester(tmp_path, clock, _multi_page_handler(seen))
    assert h._read_state().resumption_token is None
    got = [r.arxiv_id for r in h.harvest()]
    assert len(got) == 5
    assert not state_path.exists()


# ---------------------------------------------------------------------------
# 6. OAI channel User-Agent carries the arXiv-required contact (audit §6)
# ---------------------------------------------------------------------------


def test_oai_user_agent_carries_contact(tmp_path):
    """The OAI-PMH channel — the busiest, most ban-prone egress — must send a
    User-Agent with a reachable contact (previously a static string with
    none). The header is asserted on the wire via the mock transport."""
    assert "antiek.ai/contact" in DEFAULT_USER_AGENT  # default contact URL

    clock = _FakeClock()
    seen_uas: list[str] = []
    h = _harvester(tmp_path, clock, _multi_page_handler([], seen_uas))
    list(h.harvest())
    assert len(seen_uas) == 3
    assert all(ua == DEFAULT_USER_AGENT for ua in seen_uas)
    assert "(" in DEFAULT_USER_AGENT and ";" in DEFAULT_USER_AGENT  # contact form
