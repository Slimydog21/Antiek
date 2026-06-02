"""SPR-09 M6 — observability: typed event-log metrics + read-only --status.

Properties under test:
  * Each round emits per-source ingested/rejected counts + reject rate + corpus
    size + last-merge + governor state + banned-until as typed event-log
    entries (the legacy free-form action_type path).
  * The reject rate is reported HONESTLY (a 40%-reject source shows 40%, not a
    hidden drop) — rigor card #1.
  * --status reconstructs the snapshot from PERSISTED state (event log +
    checkpoint) after a 'restart', not from in-memory counters.
  * --status is READ-ONLY — it never calls connect_write. We assert it by
    monkeypatching connect_write to explode and confirming status still works.

NO live network, NO prod DB. Event log + checkpoint are temp files; the live DB
is a real temp DuckDB built with the project schema so the read-only corpus-size
count exercises connect_read against a genuine file.
"""

from __future__ import annotations

import argparse
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.corpus_quality import CandidateRef  # noqa: E402
from substrate.event_log.events import trajectory  # noqa: E402
from substrate.ingest_budget import BudgetGovernor, BudgetReading  # noqa: E402
from substrate.ingest_checkpoint import CheckpointStore  # noqa: E402
from tools import run_corpus_ingest as rci  # noqa: E402

_GIB = 1024 ** 3
_BODY = "Real body text. " * 40


# ---------------------------------------------------------------------------
# Fixtures + helpers.
# ---------------------------------------------------------------------------


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "throttle.json"))
    events_dir = str(tmp_path / "events")
    return tmp_path, events_dir


def _candidate(source, source_id, body, *, force_reject=False):
    """A candidate; force_reject makes its quality verdict fail so the reject
    rate is exercised honestly. A failing body is empty text with assess_body
    on (the gate rejects empty/garbage bodies)."""
    def _ingest(_db_path, _basis):
        return "staged"

    if force_reject:
        # assess_body True over a tiny non-prose body trips the quality gate.
        text = "x"
        assess = True
    else:
        text = body
        assess = False
    return rci.PlannedCandidate(
        ref=CandidateRef(
            ref_id=f"{source}:{source_id}",
            source_id=f"{source}:{source_id}",
            title=f"Title {source_id}", author="Author", body=body,
        ),
        source=source, assessable_text=text, assess_body=assess, ingest=_ingest,
    )


def _args(tmp_path, events_dir, *, limit=25, sources=("public_domain",)):
    return argparse.Namespace(
        sources=list(sources), dry_run=True, db_path=None, staging_db=None,
        limit=limit, investigation_id="inv-corpus", events_dir=events_dir,
        merge_count=rci.DEFAULT_MERGE_COUNT,
        merge_size_bytes=rci.DEFAULT_MERGE_SIZE_BYTES,
        merge_interval_s=rci.DEFAULT_MERGE_INTERVAL_S,
        max_rounds=1, round_sleep_s=0.0,
        pd_subject=None, pd_search=None, pd_ids=None, pd_curated=False,
        arxiv_query=None, arxiv_category=None, arxiv_ids=None,
        arxiv_source="export", arxiv_bulk_snapshot=None,
        oa_source=None, oa_query=None, oa_author=None, oa_dois=None,
        libretexts_library=None, doab_query=None, ocw_query=None,
        biorxiv_server="biorxiv", biorxiv_interval=None,
        allow_prod_write=False, pd_min_interval=0.0,
    )


def _ok_runner(tmp_path, events_dir, candidates, *, monkeypatch, limit=25,
               sources=("public_domain",)):
    monkeypatch.setattr(
        rci, "discover_all",
        lambda args: rci.DiscoveryOutcome(candidates=tuple(candidates), rotation_log=()),
    )
    gov = BudgetGovernor(reader=lambda: BudgetReading(
        free_disk_bytes=200 * _GIB, db_size_bytes=1 * _GIB, rss_bytes=1 * _GIB,
    ))
    cp = CheckpointStore(path=str(tmp_path / "cp.json"))
    return rci.ContinuousRunner(
        _args(tmp_path, events_dir, limit=limit, sources=sources),
        checkpoint=cp, governor=gov, now=lambda: 1000.0, sleep=lambda s: None,
    ), cp


# ---------------------------------------------------------------------------
# M6 — per-round event emission.
# ---------------------------------------------------------------------------


def test_round_emits_per_source_and_governor_events(state, monkeypatch):
    tmp, events_dir = state
    cands = [_candidate("public_domain", "1", _BODY + " a"),
             _candidate("public_domain", "2", _BODY + " b")]
    runner, _ = _ok_runner(tmp, events_dir, cands, monkeypatch=monkeypatch)
    runner.run_round(1)

    rows = trajectory(rci.SYSTEM_INVESTIGATION_ID, events_dir=events_dir)
    action_types = {r["action_type"] for r in rows}
    assert rci.EVT_SOURCE in action_types
    assert rci.EVT_GOVERNOR in action_types
    assert rci.EVT_ROUND in action_types

    src_events = [r for r in rows if r["action_type"] == rci.EVT_SOURCE]
    pd = next(e for e in src_events if e["payload"]["source"] == "public_domain")
    assert pd["payload"]["discovered"] == 2
    assert pd["payload"]["ingested"] == 2
    assert "reject_rate" in pd["payload"]
    assert "banned_until" in pd["payload"]

    gov_events = [r for r in rows if r["action_type"] == rci.EVT_GOVERNOR]
    assert any(e["payload"].get("state") == "OK" for e in gov_events)

    round_events = [r for r in rows if r["action_type"] == rci.EVT_ROUND]
    assert round_events[-1]["payload"]["governor_state"] == "OK"
    assert "corpus_size_docs" in round_events[-1]["payload"]
    assert "last_merge_ts" in round_events[-1]["payload"]


def test_reject_rate_reported_honestly(state, monkeypatch):
    """A source with a real reject ratio shows that ratio — not a hidden drop.
    3 clean + 2 quality-rejected = 40% reject rate, reported verbatim."""
    tmp, events_dir = state
    cands = [
        _candidate("public_domain", "1", _BODY + " a"),
        _candidate("public_domain", "2", _BODY + " b"),
        _candidate("public_domain", "3", _BODY + " c"),
        _candidate("public_domain", "4", _BODY, force_reject=True),
        _candidate("public_domain", "5", _BODY, force_reject=True),
    ]
    runner, _ = _ok_runner(tmp, events_dir, cands, monkeypatch=monkeypatch)
    s = runner.run_round(1)
    pd = next(x for x in s["sources"] if x["source"] == "public_domain")
    assert pd["ingested"] == 3
    assert pd["rejected"] == 2
    assert pd["reject_rate"] == pytest.approx(0.4)   # 2 / (3 + 2), reported honestly


# ---------------------------------------------------------------------------
# M6 — --status reconstructs from persisted state after a restart, read-only.
# ---------------------------------------------------------------------------


def test_status_reconstructs_after_restart(state, monkeypatch):
    """Run a round (emitting events + advancing the checkpoint), then 'restart'
    by building a FRESH status_snapshot with NO in-memory counters — it
    reconstructs per-source counts, reject rate, last-merge, and cursors purely
    from the persisted event log + checkpoint store."""
    tmp, events_dir = state
    cands = [
        _candidate("public_domain", "1", _BODY + " a"),
        _candidate("public_domain", "2", _BODY, force_reject=True),
    ]
    runner, cp = _ok_runner(tmp, events_dir, cands, monkeypatch=monkeypatch)
    runner.run_round(1)
    del runner  # 'kill' the process — only the files survive

    # 'Restart': a brand-new checkpoint object over the same file + the event
    # log on disk. status_snapshot reads files, not memory.
    cp2 = CheckpointStore(path=str(tmp / "cp.json"))
    snap = rci.status_snapshot(checkpoint=cp2, events_dir=events_dir, db_path=None)
    pd = next(s for s in snap["sources"] if s["source"] == "public_domain")
    assert pd["discovered"] == 2
    assert pd["ingested"] == 1
    assert pd["rejected"] == 1
    assert pd["reject_rate"] == pytest.approx(0.5)
    assert pd["cursor"] is not None                # cursor survived the restart
    assert pd["ingested_ids_seen"] >= 1            # seen-set survived
    assert "public_domain" in snap["checkpointed_sources"]


def test_status_is_read_only_never_takes_write_lock(state, monkeypatch, tmp_path):
    """--status must never call connect_write. We build a real temp live DB,
    monkeypatch runtime.db_lock.connect_write to explode, and assert
    status_snapshot still produces a snapshot (it only ever connect_read's)."""
    tmp, events_dir = state

    # Emit a couple of source events so the snapshot has something to read.
    cands = [_candidate("public_domain", "1", _BODY)]
    runner, _ = _ok_runner(tmp, events_dir, cands, monkeypatch=monkeypatch)
    runner.run_round(1)

    # A real temp live DB with the project schema so the read-only corpus count
    # path runs against a genuine file.
    from substrate.graph.schema import init_database_at_path
    live = str(tmp_path / "live.duckdb")
    init_database_at_path(live)

    import runtime.db_lock as db_lock

    def _boom_write(*_a, **_k):
        raise AssertionError("status must be READ-ONLY: connect_write called")
    monkeypatch.setattr(db_lock, "connect_write", _boom_write)

    snap = rci.status_snapshot(
        checkpoint=CheckpointStore(path=str(tmp / "cp.json")),
        events_dir=events_dir, db_path=live,
    )
    assert "sources" in snap
    assert snap["corpus_size_docs"] == 0            # empty schema, read-only count
    assert any(s["source"] == "public_domain" for s in snap["sources"])


def test_status_cli_offline_form(state, monkeypatch, capsys):
    """The --status CLI path prints a structured JSON snapshot offline (no live
    DB). This is the offline form of G6; a prod --status against the live DB is
    operator-only."""
    tmp, events_dir = state
    cands = [_candidate("public_domain", "1", _BODY)]
    runner, _ = _ok_runner(tmp, events_dir, cands, monkeypatch=monkeypatch)
    runner.run_round(1)

    rc = rci.main(["--status", "--dry-run", "--events-dir", events_dir])
    assert rc == 0
    out = capsys.readouterr().out
    import json
    snap = json.loads(out)
    assert "sources" in snap
    assert "corpus_size_docs" in snap
    assert "last_merge_ts" in snap
    assert "governor" in snap
