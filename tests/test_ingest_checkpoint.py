"""SPR-09 M2 + M3 — resumable checkpoint store + source rotation.

The property under test (rigor card #3): a kill mid-batch + restart resumes
from the persisted cursor, re-ingests NOTHING (dedup-key check), and the cursor
ADVANCES rather than resets. Plus M3: a banned source is skipped this round and
the others advance (fair round-robin honoring SPR-03's banned_until sentinel).

NO live network, NO prod DB. The checkpoint store is a temp JSON file; the
throttle sentinel is a temp JSON file; discovery is faked with deterministic
candidates so a "restart" is a second ContinuousRunner over the same persisted
files. We assert BEHAVIOR (no second ingest of the same dedup basis; cursor
strictly increasing) — not a private file schema.
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
from substrate.dedup import identity_basis  # noqa: E402
from substrate.ingest_budget import BudgetGovernor, BudgetReading  # noqa: E402
from substrate.ingest_checkpoint import CheckpointStore  # noqa: E402
from tools import run_corpus_ingest as rci  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures — temp state files, deterministic faked discovery, OK governor.
# ---------------------------------------------------------------------------


@pytest.fixture
def state_files(tmp_path, monkeypatch):
    """Point every persisted-state file at the temp dir so no test ever writes
    ~/.antiek state (which would pollute the operator's real run)."""
    monkeypatch.setenv("ANTIEK_INGEST_CHECKPOINT_PATH", str(tmp_path / "cp.json"))
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "throttle.json"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    return tmp_path


def _candidate(source: str, source_id: str, body: str) -> rci.PlannedCandidate:
    """A PlannedCandidate whose dedup basis is stable on its source_id+body, with
    an ingest thunk that records nothing (we count via the runner, not writes)."""
    def _ingest(_db_path: str, _basis: str) -> str:
        return "staged"

    return rci.PlannedCandidate(
        ref=CandidateRef(
            ref_id=f"{source}:{source_id}",
            source_id=f"{source}:{source_id}",
            title=f"Title {source_id}",
            author="Author",
            body=body,
        ),
        source=source,
        assessable_text=body,
        assess_body=False,  # gate metadata-only so the body never spuriously fails
        ingest=_ingest,
    )


# A fixed, deterministic discovery: two public_domain works. The SAME basis is
# returned every round, so a correctly-resuming engine must skip them after the
# first round (resume dedup) — a broken engine would re-stage them every round.
_BODY = "Real body text. " * 40  # clears the content-hash floor for a stable id


def _fake_discover_factory(candidates):
    def _fake_discover_all(args):
        # Honor the limit so the PACE-band test can shrink it; honor source
        # rotation by only returning sources NOT banned in the shared throttle.
        from substrate.source_throttle import SourceThrottle
        thr = SourceThrottle()
        kept = [c for c in candidates if not thr.is_banned(c.source)]
        kept = kept[: args.limit] if args.limit else kept
        log = []
        for c in candidates:
            if thr.is_banned(c.source):
                log.append(f"skip {c.source} (banned)")
        return rci.DiscoveryOutcome(
            candidates=tuple(kept), rotation_log=tuple(log)
        )
    return _fake_discover_all


def _runner(tmp_path, candidates, *, monkeypatch, limit=25, discover=None):
    """Build a ContinuousRunner over faked discovery + an always-OK governor +
    a no-op merge (dry-run staging-less), with deterministic time. ``discover``
    overrides the faked discover_all (used by the all-banned halt test)."""
    monkeypatch.setattr(
        rci, "discover_all", discover or _fake_discover_factory(candidates)
    )
    args = argparse.Namespace(
        sources=["public_domain"], dry_run=True, db_path=None, staging_db=None,
        limit=limit, investigation_id="inv-corpus", events_dir=str(tmp_path / "events"),
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
    cp = CheckpointStore(path=str(tmp_path / "cp.json"))
    # Always-OK governor (the budget HALT path is exercised in the budget test).
    gov = BudgetGovernor(reader=lambda: BudgetReading(
        free_disk_bytes=500 * 1024**3, db_size_bytes=0, rss_bytes=0,
    ))
    clock = {"t": 1000.0}
    runner = rci.ContinuousRunner(
        args, checkpoint=cp, governor=gov,
        now=lambda: clock["t"], sleep=lambda s: None,
    )
    return runner, cp, clock


# ---------------------------------------------------------------------------
# M2 — kill + restart resumes; no double ingest; cursor advances.
# ---------------------------------------------------------------------------


def test_resume_does_not_reingest_same_basis(state_files, monkeypatch):
    """Round 1 stages two works; a 'kill' (drop the runner) + 'restart' (a fresh
    runner over the SAME persisted checkpoint) must NOT re-stage either — their
    SPR-04 dedup bases are already in the checkpoint's seen-set."""
    tmp = state_files
    cands = [
        _candidate("public_domain", "100", _BODY + " one"),
        _candidate("public_domain", "200", _BODY + " two"),
    ]
    runner, cp, _ = _runner(tmp, cands, monkeypatch=monkeypatch)

    s1 = runner.run_round(1)
    pd1 = next(s for s in s1["sources"] if s["source"] == "public_domain")
    assert pd1["discovered"] == 2
    assert pd1["ingested"] == 2          # both staged this first round
    assert pd1["skipped_seen"] == 0

    # The two bases are now persisted as seen.
    for c in cands:
        basis = identity_basis(c.ref.identity_record())
        assert cp.has_seen("public_domain", basis)

    # "Restart": a brand-new runner + checkpoint OBJECT over the same file.
    runner2, cp2, _ = _runner(tmp, cands, monkeypatch=monkeypatch)
    s2 = runner2.run_round(2)
    pd2 = next(s for s in s2["sources"] if s["source"] == "public_domain")
    assert pd2["discovered"] == 2
    assert pd2["ingested"] == 0           # nothing re-ingested
    assert pd2["skipped_seen"] == 2       # both recognized as already-seen


def test_cursor_advances_not_resets_across_restart(state_files, monkeypatch):
    """The per-source cursor STRICTLY increases across rounds + a restart — it
    never rewinds to the start (the resume contract)."""
    tmp = state_files
    cands = [_candidate("public_domain", "100", _BODY)]
    runner, cp, _ = _runner(tmp, cands, monkeypatch=monkeypatch)
    runner.run_round(1)
    c1 = cp.cursor("public_domain")
    assert c1 is not None

    # Restart with a fresh runner/checkpoint object reading the same file.
    runner2, cp2, _ = _runner(tmp, cands, monkeypatch=monkeypatch)
    runner2.run_round(2)
    c2 = cp2.cursor("public_domain")
    assert int(c2) > int(c1)              # advanced, not reset


def test_checkpoint_atomic_write_survives_corrupt_temp(state_files, tmp_path):
    """A leftover .tmp file (a crash mid-write artifact) does not corrupt the
    real checkpoint: the store reads the committed file, and the next write
    replaces atomically."""
    path = tmp_path / "cp.json"
    cp = CheckpointStore(path=str(path))
    cp.record_unit("public_domain", cursor="1", new_bases={"doi:abc"})
    # Simulate a crashed half-write leaving a bogus temp file.
    (tmp_path / "cp.json.tmp").write_text("{ this is not json", encoding="utf-8")
    # The committed file is still valid + readable.
    assert cp.cursor("public_domain") == "1"
    assert cp.has_seen("public_domain", "doi:abc")
    # A subsequent write still succeeds atomically.
    cp.record_unit("public_domain", cursor="2", new_bases={"doi:def"})
    assert cp.cursor("public_domain") == "2"
    assert cp.has_seen("public_domain", "doi:def")


def test_checkpoint_seen_set_is_bounded(tmp_path):
    """The per-source seen-set is trimmed to max_seen so the file cannot grow
    unbounded over a long-running engine (cursor is the real resume guarantee)."""
    cp = CheckpointStore(path=str(tmp_path / "cp.json"), max_seen_per_source=5)
    for i in range(20):
        cp.record_unit("src", cursor=str(i), new_bases={f"doi:{i:03d}"})
    seen = cp.get("src").ingested_ids_seen
    assert len(seen) == 5
    assert cp.cursor("src") == "19"       # cursor unaffected by trimming


# ---------------------------------------------------------------------------
# M3 — source rotation honors SPR-03 banned_until; fair round-robin.
# ---------------------------------------------------------------------------


def test_rotation_skips_banned_source_others_advance(state_files, monkeypatch):
    """A source with a FUTURE banned_until is skipped this round while the other
    sources still advance (the run makes progress; one flaky source does not
    stall the rest). Honors SPR-03's persisted sentinel — the orchestrator does
    not invent its own ban logic."""
    tmp = state_files
    from substrate.source_throttle import SourceThrottle
    thr = SourceThrottle()
    # Ban arxiv into the future; public_domain stays available.
    thr.note_response_at("arxiv", 9_999_999_999.0)
    assert thr.is_banned("arxiv")
    assert not thr.is_banned("public_domain")

    cands = [
        _candidate("public_domain", "100", _BODY + " pd"),
        _candidate("arxiv", "2401.00001", _BODY + " ax"),
    ]
    runner, cp, _ = _runner(tmp, cands, monkeypatch=monkeypatch)
    s = runner.run_round(1)
    by_src = {x["source"]: x for x in s["sources"]}
    # public_domain advanced (discovered + ingested); arxiv did not appear as a
    # discovered source this round (it was skipped by the banned filter).
    assert "public_domain" in by_src
    assert by_src["public_domain"]["ingested"] == 1
    assert "arxiv" not in by_src or by_src["arxiv"]["discovered"] == 0


def test_rotation_fair_round_robin_via_next_available_source():
    """SPR-03's next_available_source picks the first NON-banned source in
    priority order and records the skipped (banned) ones — the fair round-robin
    primitive the orchestrator schedules through (not a reimplemented one)."""
    import tempfile

    from substrate.source_throttle import (
        SourceThrottle,
        next_available_source,
    )

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.json")
        thr = SourceThrottle(state_path=path)
        thr.note_response_at("gutendex", 9_999_999_999.0)  # banned
        decision = next_available_source(thr, ["gutendex", "arxiv_export", "core"])
        assert decision.next_source == "arxiv_export"     # first non-banned
        assert decision.skipped and decision.skipped[0][0] == "gutendex"
        assert not decision.all_banned


def test_rotation_all_banned_halts_cleanly(state_files, monkeypatch):
    """When every selected source is banned, the round halts cleanly carrying a
    soonest-resume time — not a tight retry loop, not an abort."""
    tmp = state_files
    from substrate.source_throttle import SourceThrottle
    thr = SourceThrottle()
    thr.note_response_at("public_domain", 9_999_999_999.0)

    # Faked discovery that returns the all-banned outcome when everything is
    # banned (mirrors discover_all's real all-banned halt).
    def _all_banned_discover(args):
        return rci.DiscoveryOutcome(
            candidates=(), rotation_log=("skip public_domain (banned)",),
            all_banned=True, soonest_resume=9_999_999_999.0,
        )

    cands = [_candidate("public_domain", "100", _BODY)]
    runner, cp, _ = _runner(
        tmp, cands, monkeypatch=monkeypatch, discover=_all_banned_discover
    )
    s = runner.run_round(1)
    assert s["halted"] is True
    assert s["reason"] == "all_banned"
    assert s["soonest_resume"] == 9_999_999_999.0
