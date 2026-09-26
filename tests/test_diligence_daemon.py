"""Daemon ACTIVATION tests (autonomous-diligence SPR-02).

The owner-flag phase, priority over scored gaps, the hard caps (per-spawn
reserve, the new concurrency cap, the daily-cap sidecar path), the dedupe
paths, the kill switch (env unset ⇒ byte-equivalent no-op — the EXISTING
daemon suite, tests/test_continuous_daemon.py, passes UNMODIFIED and is the
standing proof), and the end-to-end launch through the REAL emit path into
a real event log surfaced by a real app (spawned_by_daemon server-side).

Nothing here edits the existing daemon suite — the gate is that it passes
as-is.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from orchestration.continuous import (  # noqa: E402
    DaemonBudget,
    DaemonConfig,
    DaemonState,
    run_one_iteration,
)
from orchestration.continuous.daemon import (  # noqa: E402
    DbFlagSource,
    make_emit_spawn_fn,
    no_op_spawn,
    spawn_enabled,
)
from orchestration.continuous.scoring import MAX_CHASE_COUNT  # noqa: E402

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    db = tmp_path / "t.duckdb"
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    monkeypatch.delenv("ANTIEK_DAEMON_SPAWN_ENABLED", raising=False)
    return {"events_dir": str(events_dir), "home": str(tmp_path), "db": str(db)}


def _seed_flag(
    db: str,
    *,
    kind: str = "concept",
    object_ref: str = "dark matter",
    note: str | None = None,
    source_investigation_id: str | None = None,
    question_label: str | None = None,
) -> str:
    """One queued flag in a REAL DuckDB (node kinds get a real node row so
    the claim query resolves the question substrate-side). Returns flag_id."""
    from runtime.db_lock import connect_write
    from substrate.diligence.store import DiligenceStore
    from substrate.graph import ensure_initialized

    ensure_initialized(db)
    with connect_write(db, purpose="test/seed-flag") as con:
        if kind != "concept":
            node_type = "question" if kind == "open_question" else "insight"
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, ?, 'depth')",
                [object_ref, question_label or object_ref, node_type],
            )
        row, _created = DiligenceStore().create_flag(
            con,
            owner_user_id="__operator__",
            kind=kind,
            object_ref=object_ref,
            note=note,
            source_investigation_id=source_investigation_id,
            source_document_id=None,
        )
        return row.flag_id


def _read_flag(db: str, flag_id: str):
    from runtime.db_lock import connect_read
    from substrate.diligence.store import DiligenceStore

    con = connect_read(db)
    try:
        return DiligenceStore().get_for_owner(
            con, owner_user_id="__operator__", flag_id=flag_id
        )
    finally:
        con.close()


def _write_evidence_gap(events_dir: str, *, investigation_id: str, gap: str) -> None:
    when = datetime.now(UTC)
    row = {
        "event_id": f"evt-{investigation_id}-ed",
        "investigation_id": investigation_id,
        "action_type": "evidence.retrieve.delivered",
        "emitted_at": when.isoformat(),
        "payload": {
            "action_type": "evidence.retrieve.delivered",
            "sub_question": "fixture sub-question",
            "answer": "fixture answer",
            "supporting_claims": [],
            "evidentiary_gaps": [
                {"gap_description": gap, "additional_retrieval_suggested": None}
            ],
            "insufficient_evidence": False,
        },
    }
    with open(Path(events_dir) / f"{investigation_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _write_start(
    events_dir: str,
    *,
    investigation_id: str,
    question: str,
    policy_id: str | None = None,
    terminal: bool = False,
) -> None:
    """An in-flight (or terminal) investigation's start event — the
    concurrency cap + in-flight-question dedupe read these."""
    when = datetime.now(UTC)
    rows = [
        {
            "event_id": f"evt-{investigation_id}-start",
            "investigation_id": investigation_id,
            "action_type": "investigation.start_requested",
            "policy_id": policy_id,
            "emitted_at": when.isoformat(),
            "payload": {
                "action_type": "investigation.start_requested",
                "question": question,
            },
        }
    ]
    if terminal:
        rows.append(
            {
                "event_id": f"evt-{investigation_id}-done",
                "investigation_id": investigation_id,
                "action_type": "investigation.completed",
                "emitted_at": when.isoformat(),
                "payload": {"action_type": "investigation.completed"},
            }
        )
    with open(Path(events_dir) / f"{investigation_id}.jsonl", "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _recording_spawn():
    calls: list[tuple[str, dict]] = []

    def spawn(question: str, context: dict):
        calls.append((question, context))
        return f"inv-daemon-{len(calls)}"

    return spawn, calls


# ── Proof 1: a queued flag spawns, with the write-back in scope ────────────


def test_queued_flag_spawns_with_question_and_marks_spawned(isolated_env):
    db = isolated_env["db"]
    flag_id = _seed_flag(
        db,
        kind="open_question",
        object_ref="q-1",
        question_label="What is the moat?",
        source_investigation_id="inv-parent",
    )
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"]),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    # Exactly one spawn: the flag's RESOLVED question, parented to its source.
    assert len(calls) == 1
    question, context = calls[0]
    assert question == "What is the moat?"
    assert context["policy_id"] == "continuous_daemon"
    assert context["parent_investigation_id"] == "inv-parent"
    assert context["flag_id"] == flag_id
    assert result.flags_queued == 1
    assert result.flags_spawned == 1

    # The write-back: status → spawned with the investigation id.
    row = _read_flag(db, flag_id)
    assert row is not None
    assert row.status == "spawned"
    assert row.spawned_investigation_id == "inv-daemon-1"


def test_concept_flag_cold_starts_with_the_key_as_question(isolated_env):
    db = isolated_env["db"]
    _seed_flag(db, kind="concept", object_ref="Dark   Matter")
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"]),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    assert result.flags_spawned == 1
    question, context = calls[0]
    assert question == "dark matter"  # normalized at flag-write time
    assert context["parent_investigation_id"] is None  # cold start


# ── Proof 2: flags outrank scores ──────────────────────────────────────────


def test_flag_spawns_before_a_higher_scored_gap(isolated_env):
    ed = isolated_env["events_dir"]
    db = isolated_env["db"]
    # A strongly-scored gap (co-occurrence 2, recent — well above threshold).
    for iid in ("inv-a", "inv-b"):
        _write_evidence_gap(ed, investigation_id=iid, gap="a well-scored evidentiary gap")
    _seed_flag(db, kind="concept", object_ref="the flagged thing")
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=ed),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    assert result.flags_spawned == 1
    assert result.spawns_succeeded == 2
    # ORDER: the flag first, the gap second — flags outrank scores.
    assert [q for q, _ in calls] == ["the flagged thing", "a well-scored evidentiary gap"]


# ── Proof 3: the caps are hard ─────────────────────────────────────────────


def test_per_spawn_reserve_failure_emits_nothing_and_halts_honestly(isolated_env):
    db = isolated_env["db"]
    _seed_flag(db, kind="concept", object_ref="too expensive")
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"], expected_cost_per_spawn_usd=3.0),
        budget=DaemonBudget(daily_cap_usd=50.0, per_investigation_cap_usd=2.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    assert calls == []
    assert result.halted_by_budget is True
    assert any("per-investigation cap exceeded" in r for r in result.skipped_reasons)


def test_concurrency_cap_emits_nothing_with_a_receipt(isolated_env):
    ed = isolated_env["events_dir"]
    db = isolated_env["db"]
    # Two in-flight daemon-policy investigations = the default cap (2).
    _write_start(ed, investigation_id="inv-live-1", question="running one", policy_id="continuous_daemon")
    _write_start(ed, investigation_id="inv-live-2", question="running two", policy_id="continuous_daemon")
    # A terminal one does NOT count toward the cap.
    _write_start(ed, investigation_id="inv-done", question="finished", policy_id="continuous_daemon", terminal=True)
    _seed_flag(db, kind="concept", object_ref="queued while at cap")
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=ed),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    assert calls == []
    assert result.flags_spawned == 0
    assert result.skipped_reasons.get("concurrency_cap") == 1
    # The flag stays queued — a later iteration (below the cap) retries it.
    queue_row = _read_flag(db, _seed_flag_id(db, "queued while at cap"))
    assert queue_row is not None and queue_row.status == "queued"


def _seed_flag_id(db: str, object_ref: str) -> str:
    from runtime.db_lock import connect_read
    from substrate.diligence.store import DiligenceStore

    con = connect_read(db)
    try:
        rows = DiligenceStore().list_for_owner(con, owner_user_id="__operator__")
    finally:
        con.close()
    return next(r.flag_id for r in rows if r.object_ref == object_ref)


def test_daily_cap_sidecar_blocks_the_spawn(isolated_env):
    """The budget.py:166-175 daily-cap path, exercised with a fabricated
    sidecar (today's spend already at the cap)."""
    home = Path(isolated_env["home"]) / "budgets"
    home.mkdir(parents=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    (home / f"daemon_{stamp}.json").write_text(
        json.dumps(
            {"date_stamp": stamp, "spent_usd": 4.75, "spawn_count": 9, "cap_usd": 5.0}
        )
    )
    db = isolated_env["db"]
    _seed_flag(db, kind="concept", object_ref="over the daily cap")
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"]),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    assert calls == []
    assert result.halted_by_budget is True
    assert any("daily cap exceeded" in r for r in result.skipped_reasons)


# ── Proof 4: the kill switch ───────────────────────────────────────────────


def test_spawn_enabled_gate(isolated_env, monkeypatch):
    monkeypatch.delenv("ANTIEK_DAEMON_SPAWN_ENABLED", raising=False)
    assert spawn_enabled(os.environ) is False
    for truthy in ("1", "true", "YES", "on"):
        monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_ENABLED", truthy)
        assert spawn_enabled(os.environ) is True
    monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_ENABLED", "no")
    assert spawn_enabled(os.environ) is False


def test_main_wiring_is_byte_equivalent_no_op_when_disabled(isolated_env, monkeypatch):
    """env unset ⇒ run_forever receives no_op_spawn and NO flag source (the
    pre-activation behavior); env set ⇒ the real emit path + queue source."""
    import orchestration.continuous.daemon as daemon_mod

    captured: dict = {}

    def fake_run_forever(**kwargs):
        captured.update(kwargs)
        return DaemonState()

    monkeypatch.setattr(daemon_mod, "run_forever", fake_run_forever)
    monkeypatch.delenv("ANTIEK_DAEMON_SPAWN_ENABLED", raising=False)
    daemon_mod.main()
    assert captured["spawn_fn"] is no_op_spawn
    assert captured["flag_source"] is None

    monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_ENABLED", "1")
    daemon_mod.main()
    assert captured["spawn_fn"] is not no_op_spawn
    assert isinstance(captured["flag_source"], DbFlagSource)


# ── Proof 5: the dedupe paths ──────────────────────────────────────────────


def test_already_spawned_and_dismissed_flags_emit_nothing(isolated_env):
    db = isolated_env["db"]
    spawned_id = _seed_flag(db, kind="concept", object_ref="already spawned")
    dismissed_id = _seed_flag(db, kind="concept", object_ref="already dismissed")
    from runtime.db_lock import connect_write
    from substrate.diligence.store import DiligenceStore

    with connect_write(db, purpose="test/force-states") as con:
        store = DiligenceStore()
        store.mark_spawned(
            con,
            owner_user_id="__operator__",
            flag_id=spawned_id,
            spawned_investigation_id="inv-earlier",
        )
        store.dismiss(con, owner_user_id="__operator__", flag_id=dismissed_id)

    spawn, calls = _recording_spawn()
    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"]),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )
    assert calls == []
    assert result.flags_queued == 0


def test_already_chased_gap_emits_nothing(isolated_env):
    from orchestration.continuous.scoring import normalize_gap_description

    ed = isolated_env["events_dir"]
    gap = "an already chased evidentiary gap"
    for iid in ("inv-a", "inv-b"):
        _write_evidence_gap(ed, investigation_id=iid, gap=gap)
    # The chase-exhaustion decay: chased MAX_CHASE_COUNT times → score 0.
    state = DaemonState()
    state.chase_counts_by_key[normalize_gap_description(gap)] = MAX_CHASE_COUNT
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=state,
        config=DaemonConfig(events_dir=ed),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(isolated_env["db"]),
    )
    assert calls == []
    assert result.gaps_eligible == 0


def test_in_flight_question_match_emits_nothing(isolated_env):
    ed = isolated_env["events_dir"]
    db = isolated_env["db"]
    _write_start(ed, investigation_id="inv-live", question="What is the moat?")
    _seed_flag(
        db, kind="open_question", object_ref="q-1", question_label="what  IS the moat?"
    )
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=ed),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )
    assert calls == []
    assert result.skipped_reasons.get("in_flight_question") == 1


# ── Proof 6: end-to-end through the REAL emit path ─────────────────────────


def test_flagged_concept_flows_through_the_real_emit_path_and_surfaces_with_the_daemon_badge(
    isolated_env, monkeypatch
):
    """The REAL launch path: a queued flag → the daemon's emit spawn_fn → a
    durable investigation.start_requested with the daemon policy id in a real
    event log → a real app surfaces the investigation with
    spawned_by_daemon server-side (the "found by the loop" badge seam)."""
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app
    from interfaces.research.api.broadcast import EventBroadcaster

    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(Path(isolated_env["home"]) / "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    db = isolated_env["db"]
    client = TestClient(create_app(register_wrestling=False))

    # The operator flags a concept through the SPR-01 API.
    created = client.post(
        "/diligence/flags", json={"kind": "concept", "object_ref": "dark matter"}
    )
    assert created.status_code == 201
    flag_id = created.json()["flag_id"]

    # The daemon iteration with the REAL emit spawn_fn (a real broadcaster,
    # the real event log — the chase mechanism's exact shape).
    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"]),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=make_emit_spawn_fn(EventBroadcaster()),
        flag_source=DbFlagSource(db),
    )
    assert result.flags_spawned == 1
    child_id = result.spawned_investigation_ids[0]

    # The emitted start event carries the daemon policy id + the question.
    from substrate.event_log import trajectory

    rows = trajectory(child_id, events_dir=isolated_env["events_dir"])
    start = next(r for r in rows if r.get("action_type") == "investigation.start_requested")
    assert start.get("policy_id") == "continuous_daemon"
    assert start["payload"]["question"] == "dark matter"

    # The queue row transitioned with the child id.
    row = _read_flag(db, flag_id)
    assert row is not None and row.status == "spawned"
    assert row.spawned_investigation_id == child_id

    # And the server surfaces the investigation with the daemon badge.
    listing = client.get("/investigations").json()
    child = next(i for i in listing["investigations"] if i["investigation_id"] == child_id)
    assert child["spawned_by_daemon"] is True
    assert child["question"] == "dark matter"


# ── SPR-03 proof 2: receipts on real store rows after a real iteration ────


def test_spawn_and_skip_receipts_land_on_the_store_rows(isolated_env):
    """A spawned flag carries the reserve receipt (amount + caps checked); a
    cap-skipped flag carries the honest skip reason — asserted from the real
    store rows after a real iteration (the sidecar fabricated so exactly ONE
    spawn fits under the daily cap)."""
    home = Path(isolated_env["home"]) / "budgets"
    home.mkdir(parents=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    # $4.25 spent: the first $0.50 reserve fits ($4.75 ≤ $5.00), the second
    # would exceed ($5.25 > $5.00).
    (home / f"daemon_{stamp}.json").write_text(
        json.dumps(
            {"date_stamp": stamp, "spent_usd": 4.25, "spawn_count": 8, "cap_usd": 5.0}
        )
    )
    db = isolated_env["db"]
    first_id = _seed_flag(db, kind="concept", object_ref="first flag")
    second_id = _seed_flag(db, kind="concept", object_ref="second flag")
    spawn, calls = _recording_spawn()

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=isolated_env["events_dir"]),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=spawn,
        flag_source=DbFlagSource(db),
    )

    assert len(calls) == 1
    assert result.flags_spawned == 1
    assert result.halted_by_budget is True

    first = _read_flag(db, first_id)
    assert first is not None and first.status == "spawned"
    spawn_receipt = json.loads(first.receipt_json or "")
    assert spawn_receipt["kind"] == "spawned"
    assert spawn_receipt["reserve_usd"] == 0.50
    assert spawn_receipt["caps_checked"] == [
        "per_spawn_reserve",
        "daily",
        "iteration",
        "concurrency",
        "topic_depth",
    ]
    assert spawn_receipt["iteration"] == 1

    second = _read_flag(db, second_id)
    assert second is not None and second.status == "queued"  # never spawned
    skip_receipt = json.loads(second.receipt_json or "")
    assert skip_receipt["kind"] == "skipped"
    assert skip_receipt["reason"] == "budget"
    assert "daily cap exceeded" in skip_receipt["detail"]


# ── SPR-03 proof 5: the operator who never flags sees ZERO change ─────────


def test_never_flags_parity_suggestions_identical_and_daemon_idle(isolated_env):
    """Kill switch off + no flags: the iteration is byte-equivalent to
    today's no-op, and the suggestions surface reads identically before and
    after (no flag phase runs, nothing is written, nothing is spawned)."""
    from orchestration.continuous.suggestions import build_suggestions

    ed = isolated_env["events_dir"]
    for iid in ("inv-a", "inv-b"):
        _write_evidence_gap(ed, investigation_id=iid, gap="a recurring evidentiary gap")

    before = build_suggestions(events_dir=ed)
    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(events_dir=ed),
        budget=DaemonBudget(daily_cap_usd=5.0),
        spawn_fn=no_op_spawn,
        flag_source=None,  # the shipped default: the flag phase never runs
    )
    after = build_suggestions(events_dir=ed)

    assert result.flags_queued == 0
    assert result.flags_spawned == 0
    assert result.spawns_succeeded == 0  # no_op_spawn — the daemon is idle
    # Parity on the STABLE fields — the score float is time-dependent
    # (recency decay reads the clock per call); what must not drift is the
    # set, the order, and the content.
    def _stable(suggestions):
        return [
            (s.key, s.question, s.seen_in_research_count, s.source_investigation_id)
            for s in suggestions
        ]

    assert _stable(before) == _stable(after)


@pytest.fixture(autouse=True)
def _scrub_operator_auth_env(monkeypatch):
    """Environment invariance (the F2 rule, extended to this chain): the
    suite must pass on the operator's own Mac, where the login shell
    exports the operator-auth env — otherwise the middleware answers 401
    and CI-clean tests fail locally."""
    for key in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(key, raising=False)

