"""Tests for the §7 Acquisition cost (discovery layer) section of
the weekly report. Spec: `docs/integration_exa_browserbase.md` §6.7.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from runtime.weekly_report import (
    WeeklyReport,
    _md_acquisition_section,
    collect_acquisition_cost,
    report_to_markdown,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def budget_dir(tmp_path):
    p = tmp_path / "budgets"
    p.mkdir()
    return p


def _write_budget(budget_dir: Path, date_iso: str, spent: float, calls: int, cap: float = 5.0):
    (budget_dir / f"exa_{date_iso}.json").write_text(json.dumps({
        "date_stamp": date_iso,
        "spent_usd": spent,
        "call_count": calls,
        "cap_usd": cap,
    }))


# ── collect_acquisition_cost ──────────────────────────────────────


def test_collect_with_no_budget_dir(tmp_path):
    missing = tmp_path / "no-budgets"
    A = collect_acquisition_cost(
        datetime.now(UTC) - timedelta(days=7),
        datetime.now(UTC),
        budget_dir=str(missing),
    )
    assert A["budget_dir_exists"] is False
    assert A["total_usd"] == 0.0
    assert A["by_day"] == []


def test_collect_sums_within_window(budget_dir):
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    week_ago_plus_2 = (now - timedelta(days=9)).strftime("%Y-%m-%d")

    _write_budget(budget_dir, today, 1.20, 240)
    _write_budget(budget_dir, yesterday, 0.50, 100)
    # Outside the 7-day window:
    _write_budget(budget_dir, week_ago_plus_2, 4.00, 800)

    A = collect_acquisition_cost(
        now - timedelta(days=7),
        now,
        budget_dir=str(budget_dir),
    )
    assert A["budget_dir_exists"] is True
    assert A["days_in_window"] == 2
    assert A["total_calls"] == 340
    assert abs(A["total_usd"] - 1.70) < 1e-9


def test_collect_top_day_identifies_highest_spend(budget_dir):
    now = datetime.now(UTC)
    _write_budget(budget_dir, now.strftime("%Y-%m-%d"), 0.05, 10)
    _write_budget(budget_dir, (now - timedelta(days=1)).strftime("%Y-%m-%d"), 2.50, 500)
    _write_budget(budget_dir, (now - timedelta(days=2)).strftime("%Y-%m-%d"), 0.30, 60)

    A = collect_acquisition_cost(
        now - timedelta(days=7), now, budget_dir=str(budget_dir),
    )
    assert A["top_day"]["spent_usd"] == 2.50


def test_collect_skips_malformed_sidecar(budget_dir):
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    _write_budget(budget_dir, today, 0.10, 20)
    # Malformed file — non-JSON.
    (budget_dir / f"exa_{(now - timedelta(days=1)).strftime('%Y-%m-%d')}.json").write_text("not json")
    A = collect_acquisition_cost(
        now - timedelta(days=7), now, budget_dir=str(budget_dir),
    )
    assert A["days_in_window"] == 1  # only the well-formed one counts


def test_collect_skips_unparseable_date(budget_dir):
    now = datetime.now(UTC)
    _write_budget(budget_dir, now.strftime("%Y-%m-%d"), 0.05, 10)
    (budget_dir / "exa_not-a-date.json").write_text("{}")
    A = collect_acquisition_cost(
        now - timedelta(days=7), now, budget_dir=str(budget_dir),
    )
    assert A["days_in_window"] == 1


# ── _md_acquisition_section ───────────────────────────────────────


def test_md_section_renders_when_empty():
    A = {"budget_dir": "/nope", "budget_dir_exists": False, "total_usd": 0,
         "total_calls": 0, "days_in_window": 0, "by_day": [], "top_day": None}
    md = "\n".join(_md_acquisition_section(A))
    assert "## 7. Acquisition cost" in md
    assert "/nope" in md


def test_md_section_renders_when_no_events_in_window(budget_dir):
    A = {"budget_dir": str(budget_dir), "budget_dir_exists": True,
         "total_usd": 0, "total_calls": 0, "days_in_window": 0,
         "by_day": [], "top_day": None}
    md = "\n".join(_md_acquisition_section(A))
    assert "## 7. Acquisition cost" in md
    assert "_No events in window._" in md


def test_md_section_renders_window_with_rows():
    A = {
        "budget_dir": "/x", "budget_dir_exists": True,
        "total_usd": 1.50, "total_calls": 300, "days_in_window": 2,
        "by_day": [
            {"date": "2026-05-20", "provider": "exa", "spent_usd": 1.00,
             "call_count": 200, "cap_usd": 5.0},
            {"date": "2026-05-21", "provider": "exa", "spent_usd": 0.50,
             "call_count": 100, "cap_usd": 5.0},
        ],
        "top_day": {"date": "2026-05-20", "spent_usd": 1.00,
                    "call_count": 200, "cap_usd": 5.0},
    }
    md = "\n".join(_md_acquisition_section(A))
    assert "$1.5000" in md
    assert "300" in md
    assert "Top-spending day" in md
    assert "2026-05-20" in md
    assert "exa" in md


def test_full_report_markdown_includes_acquisition_section(budget_dir):
    """End-to-end check: report_to_markdown includes the new
    §7 section."""
    now = datetime.now(UTC)
    _write_budget(budget_dir, now.strftime("%Y-%m-%d"), 0.05, 10)
    A = collect_acquisition_cost(
        now - timedelta(days=7), now, budget_dir=str(budget_dir),
    )
    # Stub out the other sections with no-event shapes.
    empty_phase = {
        "log_dir_exists": False, "log_dir": "/x",
        "investigations_in_window": 0, "phases": {},
    }
    report = WeeklyReport(
        window={"since": "x", "until": "y"},
        generated_at="z",
        phase_telemetry=empty_phase,
        lifecycle={"started": 0, "completed": 0, "failed": 0, "in_progress": 0,
                   "avg_phases_verified": None},
        constraint_distribution={"distribution": [], "total_synthesis_deliveries": 0,
                                 "non_converging_iterations_avg": None},
        phase_8_signal={"auto_patch_events_total": 0,
                        "status_distribution": {},
                        "patch_rate_against_completed": None,
                        "top_domains_patched": [],
                        "completed_count": 0},
        dispatch_cost={"total_calls": 0, "total_cost_usd": 0.0,
                       "by_tier": [], "by_model": []},
        cross_doc={"questions_identified": 0, "cross_doc_answers": 0,
                   "link_rate": None},
        acquisition_cost=A,
    )
    md = report_to_markdown(report)
    assert "## 7. Acquisition cost" in md


# ── env-var resolution for budget_dir ─────────────────────────────


def test_collect_honors_antiek_home_env(tmp_path, monkeypatch):
    home = tmp_path / "antiek-home"
    budgets = home / "budgets"
    budgets.mkdir(parents=True)
    now = datetime.now(UTC)
    _write_budget(budgets, now.strftime("%Y-%m-%d"), 0.10, 20)
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    A = collect_acquisition_cost(
        now - timedelta(days=7), now,
        # budget_dir not passed; should resolve via ANTIEK_HOME
    )
    assert A["budget_dir_exists"] is True
    assert A["days_in_window"] == 1
