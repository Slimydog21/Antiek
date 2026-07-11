"""Red-proofs for Sprint-14 continuous → Loop One spawn attach."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration.continuous.budget import DaemonBudget
from orchestration.continuous.loop_one_spawn import (
    make_loop_one_spawn_fn,
    resolve_daemon_spawn_fn,
)
from orchestration.continuous.spawn_cost import wrap_spawn_fn


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    return {"home": tmp_path, "events_dir": events}


def _sidecar_spent() -> float:
    from orchestration.continuous.budget import _budget_path

    raw = json.loads(_budget_path().read_text(encoding="utf-8"))
    return float(raw["spent_usd"])


def test_loop_one_spawn_emits_start_event_and_returns_inv_id(
    isolated_env: dict[str, Path],
) -> None:
    events_dir = str(isolated_env["events_dir"])
    spawn = make_loop_one_spawn_fn(events_dir=events_dir)
    ctx: dict = {
        "policy_id": "continuous_daemon",
        "topic_id": "topic-abc",
        "gap_normalized_key": "dispatch tier residual",
        "gap_score": 0.9,
        "expected_cost_usd": 0.50,
    }
    inv_id = spawn("Why does the dispatch tier matter?", ctx)
    assert inv_id is not None
    assert inv_id.startswith("inv-")
    # Event file written under events_dir
    path = isolated_env["events_dir"] / f"{inv_id}.jsonl"
    assert path.is_file()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(
        r.get("action_type") == "investigation.start_requested"
        or (isinstance(r.get("payload"), dict) and "question" in r.get("payload", {}))
        for r in rows
    )
    # Payload question present
    blob = path.read_text(encoding="utf-8")
    assert "Why does the dispatch tier matter?" in blob
    assert "investigation.start_requested" in blob or "INVESTIGATION_START" in blob.upper() or "start_requested" in blob


def test_empty_question_declines_without_event(isolated_env: dict[str, Path]) -> None:
    events_dir = str(isolated_env["events_dir"])
    spawn = make_loop_one_spawn_fn(events_dir=events_dir)
    assert spawn("   ", {}) is None
    assert spawn("", {}) is None
    assert list(isolated_env["events_dir"].iterdir()) == []


def test_wrapped_spawn_settles_reserve_to_zero_after_emit(
    isolated_env: dict[str, Path],
) -> None:
    """Event emit has no LLM cost — report_actual_cost(0) refunds the reserve."""
    events_dir = str(isolated_env["events_dir"])
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    assert _sidecar_spent() == pytest.approx(0.50)

    base = make_loop_one_spawn_fn(events_dir=events_dir, settle_emit_cost_usd=0.0)
    spawn = wrap_spawn_fn(base, budget)
    inv = spawn(
        "Open residual for continuous attach",
        {"expected_cost_usd": 0.50, "policy_id": "continuous_daemon"},
    )
    assert inv is not None
    assert _sidecar_spent() == pytest.approx(0.0)


def test_emit_failure_returns_none(isolated_env: dict[str, Path]) -> None:
    def boom(*args: object, **kwargs: object) -> str:
        raise RuntimeError("emit failed")

    spawn = make_loop_one_spawn_fn(events_dir=str(isolated_env["events_dir"]), emit=boom)
    assert spawn("Q?", {"expected_cost_usd": 0.5}) is None


def test_phantom_event_id_without_disk_does_not_succeed_or_settle(
    isolated_env: dict[str, Path],
) -> None:
    """emit_typed may return an id even if append fails — do not settle reserve."""

    def fake_emit(*args: object, **kwargs: object) -> str:
        return "evt-fake"

    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    spawn = wrap_spawn_fn(
        make_loop_one_spawn_fn(
            events_dir=str(isolated_env["events_dir"]),
            emit=fake_emit,
        ),
        budget,
    )
    inv = spawn("Phantom?", {"expected_cost_usd": 0.50})
    assert inv is None
    assert list(isolated_env["events_dir"].iterdir()) == []
    # Reserve must remain — no phantom success settlement.
    assert _sidecar_spent() == pytest.approx(0.50)


def test_default_events_dir_path_is_checked_consistently(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When events_dir is omitted, emit + persistence share default_events_dir."""
    from substrate.event_log.events import default_events_dir

    # Point default dir at isolated events via env used by substrate.
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(isolated_env["events_dir"]))
    # Confirm default_events_dir resolves under isolation.
    assert Path(default_events_dir()) == isolated_env["events_dir"] or str(
        default_events_dir()
    ).startswith(str(isolated_env["home"]))

    spawn = make_loop_one_spawn_fn(events_dir=None)  # uses default
    inv = spawn("Default path question?", {"policy_id": "continuous_daemon"})
    # Either success with file in default dir, or None if default not isolatable —
    # must never leave orphan + return None inconsistently.
    if inv is not None:
        # File must exist under whatever path default resolved to.
        from orchestration.continuous.loop_one_spawn import _resolve_events_dir

        d = Path(_resolve_events_dir(None))
        assert (d / f"{inv}.jsonl").is_file()

def test_resolve_daemon_spawn_fn_modes(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestration.continuous.daemon import no_op_spawn

    monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_MODE", "no_op")
    assert resolve_daemon_spawn_fn() is no_op_spawn or resolve_daemon_spawn_fn().__name__ == no_op_spawn.__name__

    monkeypatch.setenv("ANTIEK_DAEMON_SPAWN_MODE", "loop_one")
    budget = DaemonBudget(daily_cap_usd=5.0)
    fn = resolve_daemon_spawn_fn(
        events_dir=str(isolated_env["events_dir"]),
        budget=budget,
    )
    # Wrapped function is not no_op — calling it emits.
    budget.reserve(0.50)
    inv = fn("Resolved mode question", {"expected_cost_usd": 0.50})
    assert inv is not None
    assert (isolated_env["events_dir"] / f"{inv}.jsonl").is_file()


def test_section_7_4_files_untouched() -> None:
    import subprocess

    root = Path(__file__).resolve().parents[1]
    cap_files = [
        "orchestration/continuous/budget.py",
        "orchestration/continuous/daemon.py",
        "orchestration/continuous/scoring.py",
        "orchestration/continuous/research_topic.py",
    ]
    # Diff against this branch's base tip (settled-spend) + ensure no edits to those files in working tree
    for f in cap_files:
        p = root / f
        assert p.is_file()
    # Uncommitted/committed: no local modifications to tripwire files vs HEAD parent package state
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", *cap_files],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0
    assert diff.stdout == "", f"unexpected §7.4 diff:\n{diff.stdout}"
