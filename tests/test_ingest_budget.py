"""SPR-09 M5 — budget governor: measure the ceiling, then OK / PACE / HALT.

The load-bearing property (rigor card #5, defensibility): "box-bounded" is
enforced by CODE, not hope. A seeded near-ceiling reading yields HALT and the
runner stops scheduling new work / refuses to start a merge — no write past the
ceiling. A PACE-band reading measurably reduces throughput vs OK. An OK reading
runs normally.

NO real disk/DB/RSS dependency: every BudgetReading is seeded directly through
the injectable reader, so the governor logic is unit-tested deterministically.
The thresholds carry a commented derivation in substrate/ingest_budget.py tied
to the real CCX23 numbers (160 GB NVMe / 16 GB RAM); these tests exercise the
state machine, not the box.
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
from substrate.ingest_budget import (  # noqa: E402
    DEFAULT_HARD_MIN_FREE_DISK_BYTES,
    DEFAULT_SOFT_MIN_FREE_DISK_BYTES,
    BudgetGovernor,
    BudgetReading,
    BudgetState,
)
from substrate.ingest_checkpoint import CheckpointStore  # noqa: E402
from tools import run_corpus_ingest as rci  # noqa: E402

_GIB = 1024 ** 3


def _gov(reading: BudgetReading) -> BudgetGovernor:
    return BudgetGovernor(reader=lambda: reading)


# ---------------------------------------------------------------------------
# The OK / PACE / HALT state machine on seeded readings.
# ---------------------------------------------------------------------------


def test_ok_band_runs_normally():
    """Plenty of free disk, small DB, low RSS -> OK."""
    v = _gov(BudgetReading(
        free_disk_bytes=100 * _GIB, db_size_bytes=1 * _GIB, rss_bytes=1 * _GIB,
    )).check()
    assert v.state is BudgetState.OK
    assert v.should_schedule is True


def test_pace_band_on_low_disk():
    """Free disk between soft (16 GiB) and hard (8 GiB) floors -> PACE."""
    v = _gov(BudgetReading(
        free_disk_bytes=12 * _GIB, db_size_bytes=1 * _GIB, rss_bytes=1 * _GIB,
    )).check()
    assert v.state is BudgetState.PACE
    assert v.should_schedule is True
    assert any("free disk" in r for r in v.reasons)


def test_halt_band_on_near_ceiling_disk():
    """Free disk at/under the hard floor (8 GiB) -> HALT; no scheduling."""
    v = _gov(BudgetReading(
        free_disk_bytes=4 * _GIB, db_size_bytes=1 * _GIB, rss_bytes=1 * _GIB,
    )).check()
    assert v.state is BudgetState.HALT
    assert v.should_schedule is False
    assert any("free disk" in r for r in v.reasons)


def test_halt_on_db_size_ceiling():
    v = _gov(BudgetReading(
        free_disk_bytes=100 * _GIB, db_size_bytes=120 * _GIB, rss_bytes=1 * _GIB,
    )).check()
    assert v.state is BudgetState.HALT
    assert any("antiek.duckdb" in r for r in v.reasons)


def test_halt_on_rss_ceiling():
    v = _gov(BudgetReading(
        free_disk_bytes=100 * _GIB, db_size_bytes=1 * _GIB, rss_bytes=13 * _GIB,
    )).check()
    assert v.state is BudgetState.HALT
    assert any("RSS" in r for r in v.reasons)


def test_most_restrictive_dimension_wins():
    """Any single endangered dimension halts even if others are fine — and the
    reason names the contributing dimension(s) honestly (not a bare HALT)."""
    v = _gov(BudgetReading(
        free_disk_bytes=4 * _GIB,       # HALT
        db_size_bytes=85 * _GIB,        # PACE
        rss_bytes=1 * _GIB,             # OK
    )).check()
    assert v.state is BudgetState.HALT
    # Both the disk HALT and the DB-size PACE reasons are surfaced.
    assert any("free disk" in r for r in v.reasons)
    assert any("antiek.duckdb" in r for r in v.reasons)


def test_unreadable_dimension_is_unconstrained_not_fabricated():
    """A -1 (unreadable) dimension contributes nothing — the governor never
    fabricates a passing OR failing number for a dimension it could not read."""
    v = _gov(BudgetReading(
        free_disk_bytes=-1, db_size_bytes=-1, rss_bytes=-1,
    )).check()
    assert v.state is BudgetState.OK
    assert v.reasons == ()


def test_forecast_refuses_round_that_would_cross_floor():
    """would_cross_hard_floor uses the per-doc extrapolation to refuse a round
    BEFORE it writes when ingesting N docs would cross the hard disk floor."""
    gov = _gov(BudgetReading(
        free_disk_bytes=DEFAULT_HARD_MIN_FREE_DISK_BYTES + 100 * 1024 * 1024,
        db_size_bytes=1 * _GIB, rss_bytes=1 * _GIB,
    ))
    # 100 MiB of headroom over the floor; at 250 KB/doc, 1000 docs = ~244 MiB
    # would cross. A small batch would not.
    assert gov.would_cross_hard_floor(1000) is True
    assert gov.would_cross_hard_floor(10) is False


def test_soft_and_hard_disk_thresholds_ordered():
    """Sanity: the soft floor is ABOVE the hard floor (PACE before HALT as free
    disk shrinks) — the derivation in the module must not invert them."""
    assert DEFAULT_SOFT_MIN_FREE_DISK_BYTES > DEFAULT_HARD_MIN_FREE_DISK_BYTES


# ---------------------------------------------------------------------------
# Governor wired into the runner: HALT stops scheduling; PACE reduces throughput.
# ---------------------------------------------------------------------------


_BODY = "Real body text. " * 40


def _candidate(source: str, source_id: str, body: str) -> rci.PlannedCandidate:
    def _ingest(_db_path: str, _basis: str) -> str:
        return "staged"

    return rci.PlannedCandidate(
        ref=CandidateRef(
            ref_id=f"{source}:{source_id}",
            source_id=f"{source}:{source_id}",
            title=f"Title {source_id}", author="Author", body=body,
        ),
        source=source, assessable_text=body, assess_body=False, ingest=_ingest,
    )


def _args(tmp_path, limit):
    return argparse.Namespace(
        sources=["public_domain"], dry_run=True, db_path=None, staging_db=None,
        limit=limit, investigation_id="inv-corpus",
        events_dir=str(tmp_path / "events"),
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


def test_runner_halt_stops_scheduling_no_write(tmp_path, monkeypatch):
    """A near-ceiling governor makes the runner HALT a round: NO discovery is
    even attempted, no work is scheduled, the round reports halted=budget, and
    the checkpoint is not advanced past its prior state (clean stop)."""
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "throttle.json"))

    discover_calls = {"n": 0}

    def _discover(args):
        discover_calls["n"] += 1
        return rci.DiscoveryOutcome(
            candidates=(_candidate("public_domain", "1", _BODY),), rotation_log=()
        )
    monkeypatch.setattr(rci, "discover_all", _discover)

    cp = CheckpointStore(path=str(tmp_path / "cp.json"))
    gov = _gov(BudgetReading(free_disk_bytes=2 * _GIB, db_size_bytes=0, rss_bytes=0))
    runner = rci.ContinuousRunner(
        _args(tmp_path, limit=25), checkpoint=cp, governor=gov,
        now=lambda: 1000.0, sleep=lambda s: None,
    )
    s = runner.run_round(1)
    assert s["halted"] is True
    assert s["reason"] == "budget"
    assert discover_calls["n"] == 0           # never even discovered -> no write path
    assert cp.cursor("public_domain") is None  # checkpoint untouched (clean stop)


def test_pace_band_reduces_throughput_vs_ok(tmp_path, monkeypatch):
    """The PACE band shrinks the per-source discovery limit (fewer docs/round)
    measurably below the OK band's limit — a real throughput reduction, tested
    by the effective_limit the runner passes to discovery."""
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "throttle.json"))

    seen_limits = []

    def _discover(args):
        seen_limits.append(args.limit)
        return rci.DiscoveryOutcome(candidates=(), rotation_log=())
    monkeypatch.setattr(rci, "discover_all", _discover)

    # OK band run.
    cp_ok = CheckpointStore(path=str(tmp_path / "cp_ok.json"))
    gov_ok = _gov(BudgetReading(free_disk_bytes=100 * _GIB, db_size_bytes=0, rss_bytes=0))
    rci.ContinuousRunner(
        _args(tmp_path, limit=100), checkpoint=cp_ok, governor=gov_ok,
        now=lambda: 1.0, sleep=lambda s: None,
    ).run_round(1)
    ok_limit = seen_limits[-1]

    # PACE band run (low disk, above hard floor).
    cp_pace = CheckpointStore(path=str(tmp_path / "cp_pace.json"))
    gov_pace = _gov(BudgetReading(free_disk_bytes=12 * _GIB, db_size_bytes=0, rss_bytes=0))
    rci.ContinuousRunner(
        _args(tmp_path, limit=100), checkpoint=cp_pace, governor=gov_pace,
        now=lambda: 1.0, sleep=lambda s: None,
    ).run_round(1)
    pace_limit = seen_limits[-1]

    assert ok_limit == 100
    assert pace_limit < ok_limit          # measurably less throughput in PACE
    assert pace_limit == 25               # 100 * PACE_LIMIT_FACTOR (0.25)


def test_merge_not_started_when_governor_halts(tmp_path, monkeypatch):
    """The in-flight-merge safety contract: if the governor HALTs at the pre-
    merge re-check, the merge is NOT started (no partial INSERT...SELECT on the
    live DB). We drive _do_merge directly with a HALT governor and a fake
    merge_staging that would record a call."""
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "throttle.json"))
    merge_calls = {"n": 0}

    import tools.merge_staging as ms

    def _fake_merge(*, live_db, staging_db, **_k):
        merge_calls["n"] += 1
        raise AssertionError("merge must NOT be started under a HALT governor")
    monkeypatch.setattr(ms, "merge_staging", _fake_merge)

    args = _args(tmp_path, limit=25)
    args.dry_run = False
    args.staging_db = str(tmp_path / "staging.duckdb")
    args.db_path = str(tmp_path / "live.duckdb")
    # Seed a staging file so the accumulator exists; governor HALTs.
    (tmp_path / "staging.duckdb").write_bytes(b"x" * 10)
    gov = _gov(BudgetReading(free_disk_bytes=2 * _GIB, db_size_bytes=0, rss_bytes=0))
    runner = rci.ContinuousRunner(
        args, checkpoint=CheckpointStore(path=str(tmp_path / "cp.json")),
        governor=gov, now=lambda: 1.0, sleep=lambda s: None,
    )
    assert runner._accum is not None
    runner._accum.count = 999  # would trip the count trigger
    out = runner._do_merge(1, "count")
    assert out.get("skipped") == "budget_halt"
    assert merge_calls["n"] == 0           # merge never started


# ---------------------------------------------------------------------------
# The POSITIVE cadence path: a tripped trigger fires SPR-01's merge EXACTLY
# once, resets the accumulator, and emits EVT_MERGE. The negative test above
# only proves HALT *skips* a merge; this proves the live merge path runs once
# per trip, composes the unchanged merge_staging, and never re-fires while the
# accumulator is empty (the 'exactly one merge per cadence trip' property).
# ---------------------------------------------------------------------------


def _merge_runner(tmp_path, monkeypatch, *, merge_calls, clock):
    """A non-dry-run runner with a live + staging DB path, an OK governor, faked
    EMPTY discovery (so a round stages nothing — we drive the accumulator count
    directly), and merge_staging replaced by a counting fake returning a real
    MergeResult. discover_all is faked at module scope so no live network is
    touched. Returns the runner."""
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "throttle.json"))

    # Empty discovery: no new staging this round, so the ONLY thing that can
    # trip the cadence is the count we set on the accumulator.
    monkeypatch.setattr(
        rci, "discover_all",
        lambda args: rci.DiscoveryOutcome(candidates=(), rotation_log=()),
    )

    import tools.merge_staging as ms
    from tools.merge_staging import MergeResult, TableMergeResult

    def _fake_merge(*, live_db, staging_db, **_k):
        merge_calls["n"] += 1
        merge_calls["live_db"] = live_db
        merge_calls["staging_db"] = staging_db
        return MergeResult(
            tables=(TableMergeResult(table="documents", inserted=7, skipped=0),),
            window_s=0.012,
        )
    monkeypatch.setattr(ms, "merge_staging", _fake_merge)

    args = _args(tmp_path, limit=25)
    args.dry_run = False
    args.staging_db = str(tmp_path / "staging.duckdb")
    args.db_path = str(tmp_path / "live.duckdb")
    # Seed a staging file so the accumulator exists (size trigger reads its size).
    (tmp_path / "staging.duckdb").write_bytes(b"x" * 10)
    gov = _gov(BudgetReading(free_disk_bytes=200 * _GIB, db_size_bytes=1 * _GIB, rss_bytes=1 * _GIB))
    return rci.ContinuousRunner(
        args, checkpoint=CheckpointStore(path=str(tmp_path / "cp.json")),
        governor=gov, now=lambda: clock["t"], sleep=lambda s: None,
    )


def test_count_trigger_fires_merge_once_resets_and_emits(tmp_path, monkeypatch):
    """A count trigger over the OK governor: should_merge -> _do_merge fires the
    real (faked) merge_staging EXACTLY once, resets the accumulator (count=0,
    last_merge_ts stamped to now), composes the UNCHANGED merge_staging with the
    resolved live+staging paths, and emits an EVT_MERGE event carrying the
    window + rows. No content_class is touched (the loop only schedules)."""
    merge_calls = {"n": 0}
    clock = {"t": 5000.0}
    runner = _merge_runner(tmp_path, monkeypatch, merge_calls=merge_calls, clock=clock)

    assert runner._accum is not None
    runner._accum.count = rci.DEFAULT_MERGE_COUNT + 5   # trips the count trigger
    prev_ts = runner._accum.last_merge_ts               # stamped at construction
    # Advance the clock so the post-merge stamp is a NEW, distinguishable value.
    clock["t"] = 5050.0

    s = runner.run_round(1)

    # Merge fired exactly once, through the unchanged merge_staging, on the
    # resolved live + staging paths.
    assert merge_calls["n"] == 1
    assert merge_calls["live_db"] == runner.args.db_path
    assert merge_calls["staging_db"] == runner._accum.staging_db
    # Accumulator reset: count back to 0, last_merge_ts advanced to the new now.
    assert runner._accum.count == 0
    assert runner._accum.last_merge_ts == clock["t"]    # == 5050.0
    assert runner._accum.last_merge_ts > prev_ts        # strictly advanced
    # The round summary carries the merge, and an EVT_MERGE was emitted.
    assert s["merged"] is not None
    assert s["merged"]["trigger"] == "count"
    assert s["merged"]["total_inserted"] == 7
    assert s["merged"]["window_s"] == pytest.approx(0.012)
    rows = trajectory(rci.SYSTEM_INVESTIGATION_ID, events_dir=runner.events_dir)
    merge_events = [r for r in rows if r["action_type"] == rci.EVT_MERGE]
    assert len(merge_events) == 1
    assert merge_events[0]["payload"]["trigger"] == "count"


def test_exactly_one_merge_per_cadence_trip(tmp_path, monkeypatch):
    """Drive TWO rounds via run_round. Round 1 trips the count trigger and fires
    one merge (resetting count to 0). Round 2 — with the accumulator now empty
    and discovery returning nothing — must NOT fire a second merge. The property
    is 'exactly one merge per trip', not 'a merge every round'."""
    merge_calls = {"n": 0}
    clock = {"t": 5000.0}
    runner = _merge_runner(tmp_path, monkeypatch, merge_calls=merge_calls, clock=clock)

    runner._accum.count = rci.DEFAULT_MERGE_COUNT + 1   # round 1 trips
    s1 = runner.run_round(1)
    assert merge_calls["n"] == 1
    assert s1["merged"] is not None
    assert runner._accum.count == 0

    # Round 2: nothing staged (empty discovery), accumulator empty -> no merge.
    clock["t"] = 6000.0
    s2 = runner.run_round(2)
    assert merge_calls["n"] == 1            # STILL one — no second merge fired
    assert s2["merged"] is None


def test_run_loop_fires_merge_then_stops_at_max_rounds(tmp_path, monkeypatch):
    """End-to-end through the ONLY while-True loop: run() with max_rounds=1 drives
    exactly one round, fires the merge on a tripped count trigger, and returns a
    clean exit code 0 (bounded — no unbounded loop). This is the offline-bounded
    form of the G5 continuous smoke (faked discovery + bounded max_rounds), not a
    live-network run."""
    merge_calls = {"n": 0}
    clock = {"t": 5000.0}
    runner = _merge_runner(tmp_path, monkeypatch, merge_calls=merge_calls, clock=clock)
    runner.max_rounds = 1
    runner._accum.count = rci.DEFAULT_MERGE_COUNT + 1

    rc = runner.run()
    assert rc == 0                          # clean, bounded exit
    assert merge_calls["n"] == 1            # the single round fired one merge


# ---------------------------------------------------------------------------
# should_merge() trigger precedence — count, then size, then interval; never
# fires with an empty accumulator (count == 0 short-circuits every trigger).
# ---------------------------------------------------------------------------


def test_should_merge_trigger_precedence(tmp_path):
    """The first-tripped-trigger selector returns count before size before
    interval, and returns None when nothing trips. A zero count never trips ANY
    trigger (an empty accumulator must not fire a vacuous merge)."""
    staging = tmp_path / "staging.duckdb"
    staging.write_bytes(b"x" * 1024)        # 1 KiB on disk
    accum = rci._StagingAccumulator(staging_db=str(staging), last_merge_ts=100.0)

    # Nothing staged: no trigger regardless of thresholds / elapsed time.
    assert accum.should_merge(
        count_threshold=1, size_threshold=1, interval_threshold=1.0, now=1_000.0,
    ) is None

    # Count trips first when count >= count_threshold.
    accum.count = 50
    assert accum.should_merge(
        count_threshold=50, size_threshold=10 ** 12, interval_threshold=10 ** 12, now=101.0,
    ) == "count"

    # Below count threshold but staging size over the size floor -> size.
    accum.count = 1
    assert accum.should_merge(
        count_threshold=1_000, size_threshold=512, interval_threshold=10 ** 12, now=101.0,
    ) == "size"

    # Below count + size, but the merge interval has elapsed -> interval.
    accum.count = 1
    assert accum.should_merge(
        count_threshold=1_000, size_threshold=10 ** 12, interval_threshold=10.0, now=200.0,
    ) == "interval"

    # The interval trigger needs a prior merge stamp (last_merge_ts > 0); a
    # fresh accumulator that never merged does not trip interval on count==1.
    fresh = rci._StagingAccumulator(staging_db=str(staging), last_merge_ts=0.0)
    fresh.count = 1
    assert fresh.should_merge(
        count_threshold=1_000, size_threshold=10 ** 12, interval_threshold=10.0, now=10_000.0,
    ) is None
