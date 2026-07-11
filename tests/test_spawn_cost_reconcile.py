"""Red-proofs for settled-cost spawn reconciliation (tripwire-safe seam)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration.continuous.budget import DaemonBudget, _budget_path
from orchestration.continuous.daemon import DaemonConfig, DaemonState, run_one_iteration
from orchestration.continuous.spawn_cost import (
    actual_was_reported,
    install_spawn_cost_hooks,
    report_actual_cost,
    wrap_spawn_fn,
)


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    events = tmp_path / "events"
    events.mkdir()
    return {"home": tmp_path, "events_dir": events}


def _sidecar_spent() -> float:
    raw = json.loads(_budget_path().read_text(encoding="utf-8"))
    return float(raw["spent_usd"])


def test_report_actual_reconciles_reserved_hold_to_true_cost(
    isolated_env: dict[str, Path],
) -> None:
    """Reserve $0.50 then report actual $0.03 → ledger spent is $0.03, not $0.50."""
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    assert _sidecar_spent() == pytest.approx(0.50)

    ctx: dict = {"expected_cost_usd": 0.50}
    install_spawn_cost_hooks(ctx, budget)
    delta = ctx["report_actual_cost"](0.03)

    assert delta == pytest.approx(-0.47)
    assert _sidecar_spent() == pytest.approx(0.03)
    assert actual_was_reported(ctx) is True
    # Headroom under a $5 display/enforcement cap reflects actual, not reserve.
    assert budget.remaining_today() == pytest.approx(4.97)


def test_unreported_success_leaves_reserved_hold(
    isolated_env: dict[str, Path],
) -> None:
    """If spawn never reports actual, reserved remains — never invent settled $0."""
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    ctx: dict = {"expected_cost_usd": 0.50}
    install_spawn_cost_hooks(ctx, budget)

    # Successful spawn path that forgets to report.
    assert actual_was_reported(ctx) is False
    assert _sidecar_spent() == pytest.approx(0.50)
    assert budget.remaining_today() == pytest.approx(4.50)


def test_report_without_hooks_fails_closed(isolated_env: dict[str, Path]) -> None:
    ctx: dict = {"expected_cost_usd": 0.50}
    with pytest.raises(RuntimeError, match="record_actual_cb"):
        report_actual_cost(ctx, 0.03)


def test_negative_actual_rejected(isolated_env: dict[str, Path]) -> None:
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    ctx: dict = {"expected_cost_usd": 0.50}
    install_spawn_cost_hooks(ctx, budget)
    with pytest.raises(ValueError, match="non-negative"):
        ctx["report_actual_cost"](-0.01)
    assert _sidecar_spent() == pytest.approx(0.50)


def test_wrap_spawn_fn_injects_hooks_and_reconciles_on_report(
    isolated_env: dict[str, Path],
) -> None:
    """wrap_spawn_fn is the production boundary that installs hooks without
    editing daemon.py (tripwire)."""
    budget = DaemonBudget(daily_cap_usd=5.0)
    seen: list[dict] = []

    def spawn_that_reports(question: str, context: dict) -> str:
        seen.append(context)
        assert callable(context.get("record_actual_cb"))
        assert callable(context.get("report_actual_cost"))
        # Real call costs $0.03 vs $0.50 reserve.
        context["report_actual_cost"](0.03)
        return "inv-real-1"

    wrapped = wrap_spawn_fn(spawn_that_reports, budget)
    budget.reserve(0.50)
    iid = wrapped("why does dispatch tier matter?", {"expected_cost_usd": 0.50})

    assert iid == "inv-real-1"
    assert len(seen) == 1
    assert actual_was_reported(seen[0]) is True
    assert _sidecar_spent() == pytest.approx(0.03)


def test_wrap_spawn_fn_unreported_keeps_reserved(
    isolated_env: dict[str, Path],
) -> None:
    budget = DaemonBudget(daily_cap_usd=5.0)

    def spawn_silent(question: str, context: dict) -> str:
        # Hooks present but unused — honest reserved remains.
        assert "record_actual_cb" in context
        return "inv-silent"

    wrapped = wrap_spawn_fn(spawn_silent, budget)
    budget.reserve(0.50)
    wrapped("open question", {"expected_cost_usd": 0.50})
    assert _sidecar_spent() == pytest.approx(0.50)


def _write_evidence_delivered(
    events_dir: Path,
    *,
    investigation_id: str,
    gaps: list[tuple[str, str | None]],
) -> None:
    """Mirror tests/test_continuous_daemon.py fixture format."""
    from datetime import UTC, datetime

    path = events_dir / f"{investigation_id}.jsonl"
    payload = {
        "action_type": "evidence.retrieve.delivered",
        "sub_question": "fixture sub-question",
        "answer": "fixture answer",
        "supporting_claims": [],
        "evidentiary_gaps": [
            {"gap_description": desc, "additional_retrieval_suggested": hint}
            for desc, hint in gaps
        ],
        "insufficient_evidence": False,
    }
    row = {
        "event_id": f"evt-{investigation_id}-{len(gaps)}",
        "investigation_id": investigation_id,
        "action_type": "evidence.retrieve.delivered",
        "emitted_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_wrap_integrates_with_run_one_iteration_without_daemon_edit(
    isolated_env: dict[str, Path],
) -> None:
    """End-to-end: daemon loop + wrap_spawn_fn reconciles actual on success.

    Does not modify daemon.py; uses the documented spawn_fn injection point.
    """
    ed = isolated_env["events_dir"]
    gap = "dispatch tier residual that needs chase"
    # Co-occurrence ≥2 (three investigations same gap) so scoring spawns.
    for inv in ("inv-a", "inv-b", "inv-c"):
        _write_evidence_delivered(ed, investigation_id=inv, gaps=[(gap, None)])

    budget = DaemonBudget(daily_cap_usd=5.0)
    reported: list[float] = []

    def spawn_with_actual(question: str, context: dict) -> str:
        # $0.50 reserved by daemon; true cost $0.03.
        context["report_actual_cost"](0.03)
        reported.append(0.03)
        return "inv-spawned-actual"

    result = run_one_iteration(
        state=DaemonState(),
        config=DaemonConfig(
            events_dir=str(ed),
            expected_cost_per_spawn_usd=0.50,
            max_spawns_per_iteration=1,
        ),
        budget=budget,
        spawn_fn=wrap_spawn_fn(spawn_with_actual, budget),
    )

    assert result.spawns_succeeded >= 1
    assert reported == [0.03]
    # One spawn reserved 0.50 then reconciled to 0.03.
    assert _sidecar_spent() == pytest.approx(0.03)


def test_double_absolute_report_fails_closed(isolated_env: dict[str, Path]) -> None:
    """Second absolute report must not re-subtract expected (fake $0 spent)."""
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    ctx: dict = {"expected_cost_usd": 0.50}
    install_spawn_cost_hooks(ctx, budget)
    ctx["report_actual_cost"](0.03)
    assert _sidecar_spent() == pytest.approx(0.03)
    with pytest.raises(RuntimeError, match="already reported"):
        ctx["report_actual_cost"](0.03)
    # Ledger unchanged after refused second report.
    assert _sidecar_spent() == pytest.approx(0.03)


def test_non_finite_actual_rejected(isolated_env: dict[str, Path]) -> None:
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    ctx: dict = {"expected_cost_usd": 0.50}
    install_spawn_cost_hooks(ctx, budget)
    with pytest.raises(ValueError, match="finite non-negative"):
        ctx["report_actual_cost"](float("nan"))
    with pytest.raises(ValueError, match="finite non-negative"):
        ctx["report_actual_cost"](float("inf"))
    assert _sidecar_spent() == pytest.approx(0.50)


def test_record_actual_cb_rejects_non_finite_delta(
    isolated_env: dict[str, Path],
) -> None:
    """Public record_actual_cb must not let NaN floor spent to fake $0."""
    budget = DaemonBudget(daily_cap_usd=5.0)
    budget.reserve(0.50)
    ctx: dict = {"expected_cost_usd": 0.50}
    install_spawn_cost_hooks(ctx, budget)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finite"):
            ctx["record_actual_cb"](bad)
    assert _sidecar_spent() == pytest.approx(0.50)


def test_cli_module_uses_settled_entry() -> None:
    """Production __main__ must call settled/wrap paths, not bare run_one_iteration."""
    src = Path("orchestration/continuous/__main__.py").read_text(encoding="utf-8")
    assert "run_one_iteration_settled" in src
    assert "wrap_spawn_fn" in src
    # Must not call bare run_one_iteration( for the once path.
    assert "run_one_iteration(state=" not in src


def test_section_7_4_tripwire_files_untouched() -> None:
    """This residual must not modify §7.4 cap-bearing modules."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cap_files = [
        "orchestration/continuous/budget.py",
        "orchestration/continuous/daemon.py",
        "orchestration/continuous/scoring.py",
        "orchestration/continuous/research_topic.py",
    ]
    diff = subprocess.run(
        ["git", "diff", "origin/main", "--", *cap_files],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0, diff.stderr
    assert diff.stdout == "", f"unexpected §7.4 file diff:\n{diff.stdout}"
