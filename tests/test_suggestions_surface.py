"""SPR-09 — the compounding flywheel, surfaced.

The §7 continuous daemon already computes scored evidentiary gaps (covered by
``test_continuous_daemon.py``). This sprint SURFACES that existing output as
plain-language "suggested next researches". These tests pin the load-bearing
invariants the sprint page names:

* §7.4 caps unchanged — the daemon's budget/cadence/decay constants are
  byte-identical; surfacing imports them, it does not widen them.
* Surfacing adds no spend — building suggestions reserves no budget and writes
  no spawn / start event (read-only).
* Launch = explicit click — nothing in the surface path launches a research;
  the only spend is an operator chase through the existing capped path.
* Dedupe + distinction — an already-chased gap (daemon decay OR a launched
  question) is not re-suggested; a daemon-spawned research is distinguished
  from an operator one via policy_id (translated to a boolean, id not shown).
* Single-writer — the surface opens no DB connection and writes nothing.
* Honest no-key / no-daemon — no gaps → empty list, never a fabricated thread.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from orchestration.continuous import (  # noqa: E402
    DAEMON_SPAWN_POLICY_ID,
    DaemonConfig,
    build_suggestions,
    policy_is_daemon,
)
from orchestration.continuous.suggestions import _chased_question_keys  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    return {"events_dir": str(events_dir), "home": str(tmp_path)}


def _write_gap(
    events_dir: str,
    *,
    investigation_id: str,
    gaps: list[tuple[str, str | None]],
    emitted_at: datetime | None = None,
) -> None:
    when = emitted_at or datetime.now(timezone.utc)
    path = Path(events_dir) / f"{investigation_id}.jsonl"
    row = {
        "event_id": f"evt-{investigation_id}-gap",
        "investigation_id": investigation_id,
        "action_type": "evidence.retrieve.delivered",
        "emitted_at": when.isoformat(),
        "payload": {
            "evidentiary_gaps": [
                {"gap_description": d, "additional_retrieval_suggested": h}
                for d, h in gaps
            ],
        },
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _write_start(
    events_dir: str,
    *,
    investigation_id: str,
    question: str,
    policy_id: str = "operator-cli",
) -> None:
    path = Path(events_dir) / f"{investigation_id}.jsonl"
    row = {
        "event_id": f"evt-{investigation_id}-start",
        "investigation_id": investigation_id,
        "action_type": "investigation.start_requested",
        "policy_id": policy_id,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"question": question},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ── §7.4 caps unchanged ───────────────────────────────────────────────


def test_section_7_4_caps_are_byte_unchanged_vs_origin_main():
    """The surface must not widen the daemon's §7.4 cost-runaway caps. Assert
    the cap-bearing daemon modules are byte-identical to origin/main (the
    sprint page's gate: ``git diff origin/main -- …daemon.py``)."""
    import subprocess

    cap_files = [
        "orchestration/continuous/budget.py",
        "orchestration/continuous/daemon.py",
        "orchestration/continuous/scoring.py",
        "orchestration/continuous/research_topic.py",
    ]
    diff = subprocess.run(
        ["git", "diff", "origin/main", "--", *cap_files],
        cwd=_PKG_ROOT,
        capture_output=True,
        text=True,
    )
    assert diff.returncode == 0, diff.stderr
    assert diff.stdout == "", (
        "SPR-09 surfaces the daemon's output read-only; it must not modify the "
        f"§7.4 cap-bearing daemon code. Unexpected diff:\n{diff.stdout}"
    )


def test_section_7_4_cap_constants_have_their_shipped_defaults():
    """A belt-and-braces check that the named §7.4 constants still carry their
    shipped defaults (independent of the git diff above)."""
    from orchestration.continuous.budget import (
        DEFAULT_DAILY_CAP_USD,
        MAX_TOPIC_DEPTH,
        PER_INVESTIGATION_CAP_USD,
    )
    from orchestration.continuous.scoring import MAX_CHASE_COUNT

    assert DEFAULT_DAILY_CAP_USD == 5.0
    assert PER_INVESTIGATION_CAP_USD == 2.0
    assert MAX_TOPIC_DEPTH == 5
    assert MAX_CHASE_COUNT == 3


# ── Surfacing adds no spend / is read-only ─────────────────────────────


def test_build_suggestions_reserves_no_budget(isolated_env):
    """Surfacing must not touch the daemon's daily-spend sidecar. After
    building suggestions the budget tally is exactly as it was — nothing
    reserved, nothing recorded."""
    from orchestration.continuous import DaemonBudget

    ed = isolated_env["events_dir"]
    _write_gap(ed, investigation_id="inv-A", gaps=[("a substantive gap to chase", None)])
    _write_gap(ed, investigation_id="inv-B", gaps=[("a substantive gap to chase", None)])

    budget = DaemonBudget(daily_cap_usd=5.0)
    before = budget.remaining_today()
    out = build_suggestions(events_dir=ed)
    after = budget.remaining_today()

    assert out, "the gap should surface as a suggestion"
    assert before == after == pytest.approx(5.0)


def test_build_suggestions_writes_no_events(isolated_env):
    """Read-only: building suggestions does not append any event to the log
    (no spawn, no start_requested). The event-log file set + byte sizes are
    unchanged across the call."""
    ed = isolated_env["events_dir"]
    _write_gap(ed, investigation_id="inv-A", gaps=[("gap that should surface", None)])
    _write_gap(ed, investigation_id="inv-B", gaps=[("gap that should surface", None)])

    def snapshot() -> dict[str, int]:
        return {
            f: os.path.getsize(os.path.join(ed, f))
            for f in os.listdir(ed)
        }

    before = snapshot()
    build_suggestions(events_dir=ed)
    after = snapshot()
    assert before == after, "surfacing must not write to the event log"


def test_build_suggestions_does_not_run_the_daemon(isolated_env, monkeypatch):
    """Surfacing must never trigger a daemon iteration / spawn. If anything in
    the surface path called ``run_one_iteration``, this would catch it."""
    import orchestration.continuous.daemon as daemon_mod

    def _boom(*a, **k):  # pragma: no cover — only fires on a regression
        raise AssertionError("build_suggestions must not run the daemon")

    monkeypatch.setattr(daemon_mod, "run_one_iteration", _boom)
    ed = isolated_env["events_dir"]
    _write_gap(ed, investigation_id="inv-A", gaps=[("a gap", None)])
    # Must not raise.
    build_suggestions(events_dir=ed)


# ── Dedupe ─────────────────────────────────────────────────────────────


def test_suggestions_dedupe_one_per_underlying_gap(isolated_env):
    """The same gap seen across multiple researches is ONE suggestion (deduped
    on the normalized question), with an honest cross-research count."""
    ed = isolated_env["events_dir"]
    for iid in ("inv-1", "inv-2", "inv-3"):
        _write_gap(ed, investigation_id=iid, gaps=[("What is the dispatch threshold?", None)])
    out = build_suggestions(events_dir=ed)
    assert len(out) == 1
    assert out[0].seen_in_research_count == 3


def test_suggestions_exclude_already_chased_question(isolated_env):
    """A gap whose underlying question has already been LAUNCHED (an operator
    chase, or a daemon spawn) is not re-suggested — dedupe on the underlying
    question, independent of the daemon's own chase-count."""
    ed = isolated_env["events_dir"]
    gap = "How does the §9.0 retrieval gate behave under takedown?"
    _write_gap(ed, investigation_id="inv-A", gaps=[(gap, None)])
    _write_gap(ed, investigation_id="inv-B", gaps=[(gap, None)])
    # Before any chase: surfaced.
    assert len(build_suggestions(events_dir=ed)) == 1
    # The operator chases it (a new research whose question == the gap).
    _write_start(ed, investigation_id="inv-chase", question=gap)
    # Now it is not re-suggested.
    assert build_suggestions(events_dir=ed) == []


def test_chased_question_keys_reads_start_and_spawn_events(isolated_env):
    ed = isolated_env["events_dir"]
    _write_start(ed, investigation_id="inv-1", question="a launched question")
    keys = _chased_question_keys(ed)
    from orchestration.continuous import normalize_gap_description

    assert normalize_gap_description("a launched question") in keys


# ── Distinction (policy_id → "found by the loop") ──────────────────────


def test_policy_is_daemon_matches_the_daemon_spawn_policy():
    """The translation seam: the daemon's spawn policy is recognised as
    daemon-spawned; an operator policy is not. The constant is the same string
    the daemon stamps on its spawns."""
    assert DAEMON_SPAWN_POLICY_ID == DaemonConfig.spawn_policy_id
    assert policy_is_daemon(DAEMON_SPAWN_POLICY_ID) is True
    assert policy_is_daemon("operator-cli") is False
    assert policy_is_daemon(None) is False


# ── Honest no-key / no-daemon ──────────────────────────────────────────


def test_build_suggestions_empty_when_no_gaps(isolated_env):
    """No daemon output (no keys, daemon never ran → no gap events) yields an
    empty list — the honest no-result state, never a fabricated thread."""
    ed = isolated_env["events_dir"]
    assert build_suggestions(events_dir=ed) == []


def test_build_suggestions_empty_when_events_dir_missing(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    assert build_suggestions(events_dir=missing) == []


# ── Ranking + display cap (rigor #3) ───────────────────────────────────


def test_suggestions_ranked_and_capped(isolated_env):
    """A flood of gaps is ranked by the daemon's score and capped at the
    display limit — not dumped. Higher co-occurrence ranks higher."""
    ed = isolated_env["events_dir"]
    # 6 distinct gaps; one seen across 3 researches (highest co-occurrence).
    top = "the most-corroborated gap across many researches"
    for iid in ("inv-1", "inv-2", "inv-3"):
        _write_gap(ed, investigation_id=iid, gaps=[(top, None)])
    for i in range(5):
        _write_gap(ed, investigation_id=f"inv-solo-{i}", gaps=[(f"a one-off gap number {i}", None)])

    out = build_suggestions(events_dir=ed, max_suggestions=3)
    assert len(out) == 3  # capped
    assert out[0].question == top  # ranked first by co-occurrence
