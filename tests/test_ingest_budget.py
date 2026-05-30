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
