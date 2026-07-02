"""Tests for runtime/weekly_report.py (Sprint 9 day 1-2).

Coverage:

1. Empty trajectory + no phase logs → all sections emit "no events
   in window" gracefully.
2. Phase telemetry: synthesize phase_log JSON files in the window;
   counts entered/exited/verified correctly; keystone callout fires
   when Phase 8 verify_rate < floor.
3. Lifecycle: emit start + completed + failed events; counts split
   correctly; avg_phases_verified computed.
4. Constraint distribution: emit SYNTHESIZE_DELIVERED events with
   varied statuses; grouped + counted + non-converging gets
   avg/max iterations.
5. Phase 8: AUTO_PATCH_APPLIED with patched domains; patch_rate
   computed against completed count.
6. Dispatch cost: DISPATCH_CALL events; cost_usd summed by tier
   and by model.
7. Cross-doc: QUESTION_IDENTIFIED + CROSS_DOC_QUESTION_ANSWERED;
   link rate computed.
8. Markdown + HTML + JSON renderings all produce non-empty strings
   that include section headers.
9. Window filtering: events outside the window are excluded.
10. CLI smoke: --help works; --since/--until parsing; JSON output.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from runtime.weekly_report import (  # noqa: E402
    build_report,
    collect_constraint_distribution,
    collect_cross_doc_link_rate,
    collect_dispatch_cost,
    collect_investigation_lifecycle,
    collect_phase_8_signal,
    collect_phase_telemetry,
    iter_window_events,
    report_to_html,
    report_to_markdown,
)
from substrate.event_log import emit_typed  # noqa: E402
from substrate.schemas import (  # noqa: E402
    AutoPatchAppliedPayload,
    ConstraintCompliance,
    CrossDocQuestionAnsweredPayload,
    DispatchCallPayload,
    InvestigationCompletedPayload,
    InvestigationFailedPayload,
    InvestigationStartRequestedPayload,
    QuestionIdentifiedPayload,
    SynthesizeDeliveredPayload,
)


@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    d = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(d))
    return str(d)


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "phase_logs"
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(d))
    return str(d)


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def window(now: datetime) -> tuple[datetime, datetime]:
    return now - timedelta(days=7), now + timedelta(hours=1)


# ---------------------------------------------------------------------------
# 1. Empty state
# ---------------------------------------------------------------------------


def test_empty_state_renders_no_events(events_dir, log_dir, window):
    start, end = window
    report = build_report(start, end)
    md = report_to_markdown(report)
    # Each section header should be present.
    for header in (
        "## 1. Phase telemetry", "## 2. Investigation lifecycle",
        "## 3. Constraint loop", "## 4. Phase 8 compounding",
        "## 5. Dispatch cost", "## 6. Cross-doc link rate",
    ):
        assert header in md
    # "No events in window" appears in lifecycle + constraint + Phase 8
    # + dispatch + cross-doc.
    assert md.count("No events in window") >= 5


# ---------------------------------------------------------------------------
# 2. Phase telemetry
# ---------------------------------------------------------------------------


def _write_phase_log(
    log_dir: str, investigation_id: str, *,
    created_at: datetime,
    phases: dict[int, dict[str, str | bool]],
) -> None:
    os.makedirs(log_dir, exist_ok=True)
    data = {
        "investigation_id": investigation_id,
        "topic": "stub",
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "param_version": "0.1.0",
        "phases": {str(p): rec for p, rec in phases.items()},
    }
    with open(os.path.join(log_dir, f"{investigation_id}.json"), "w") as f:
        json.dump(data, f)


def test_phase_telemetry_counts_entered_exited_verified(log_dir, now, window):
    start, end = window
    # Two investigations: one with Phase 8 verified, one not.
    _write_phase_log(log_dir, "inv-pt-1", created_at=now - timedelta(hours=1),
                     phases={
                         1: {"entered_at": "ts", "exited_at": "ts", "verified": True},
                         8: {"entered_at": "ts", "exited_at": "ts", "verified": True},
                     })
    _write_phase_log(log_dir, "inv-pt-2", created_at=now - timedelta(hours=2),
                     phases={
                         1: {"entered_at": "ts", "exited_at": "ts", "verified": True},
                         8: {"entered_at": "ts", "exited_at": "ts", "verified": False},
                     })
    p = collect_phase_telemetry(start, end)
    assert p["investigations_in_window"] == 2
    assert p["phases"][1]["entered"] == 2
    assert p["phases"][1]["verified"] == 2
    assert p["phases"][8]["entered"] == 2
    assert p["phases"][8]["verified"] == 1
    # Phase 8 verify_rate = 1/2 = 0.5, below 0.8 floor → callout.
    assert p["keystone_callout"] is not None
    assert "KEYSTONE ALERT" in p["keystone_callout"]


def test_phase_telemetry_excludes_out_of_window(log_dir, now, window):
    start, end = window
    # Old investigation — out of window.
    _write_phase_log(log_dir, "inv-old", created_at=now - timedelta(days=30),
                     phases={8: {"entered_at": "ts", "verified": True}})
    p = collect_phase_telemetry(start, end)
    assert p["investigations_in_window"] == 0


def test_phase_telemetry_no_dir(window):
    p = collect_phase_telemetry(*window, log_dir="/this/path/does/not/exist")
    assert p["log_dir_exists"] is False
    assert p["investigations_in_window"] == 0


# ---------------------------------------------------------------------------
# 3. Lifecycle
# ---------------------------------------------------------------------------


def test_lifecycle_splits_started_completed_failed(events_dir, window):
    # Emit start + completed for inv-A; start + failed for inv-B;
    # start only for inv-C (in-progress).
    emit_typed(
        "inv-A",
        InvestigationStartRequestedPayload(
            question="A?", context="", topic_slug="a", max_sub_questions=4,
        ),
        role="operator",
    )
    emit_typed(
        "inv-A",
        InvestigationCompletedPayload(
            thesis_summary="A", implicit_recommendation="proceed",
            constraint_loop_status="single_pass",
            constraint_loop_iterations=1,
            master_md_path="/tmp/A.md", domains_patched=["a"],
            total_phases_verified=8,
        ),
        role="orchestrator",
    )
    emit_typed(
        "inv-B",
        InvestigationStartRequestedPayload(
            question="B?", context="", topic_slug="b", max_sub_questions=4,
        ),
        role="operator",
    )
    emit_typed(
        "inv-B",
        InvestigationFailedPayload(
            phase=6, reason="postcondition failed", last_completed_phase=5,
        ),
        role="orchestrator",
    )
    emit_typed(
        "inv-C",
        InvestigationStartRequestedPayload(
            question="C?", context="", topic_slug="c", max_sub_questions=4,
        ),
        role="operator",
    )

    events = list(iter_window_events(*window))
    L = collect_investigation_lifecycle(events)
    assert L["started"] == 3
    assert L["completed"] == 1
    assert L["failed"] == 1
    assert L["in_progress"] == 1
    assert L["avg_phases_verified_when_completed"] == 8.0
    assert L["failed_phase_distribution"] == {6: 1}


# ---------------------------------------------------------------------------
# 4. Constraint distribution
# ---------------------------------------------------------------------------


def _emit_synth(
    investigation_id: str, *,
    status: str = "single_pass",
    iterations: int = 1,
) -> None:
    emit_typed(
        investigation_id,
        SynthesizeDeliveredPayload(
            thesis_summary="x",
            implicit_recommendation="proceed",
            thesis_components=[],
            falsification_conditions=[],
            execution_risks=[],
            constraint_compliance=ConstraintCompliance(
                hard_constraints_satisfied=True,
                soft_constraints_violated=[], violations_justified=[],
            ),
            reasoning_paths_used=[],
            constraint_loop_status=status,  # type: ignore[arg-type]
            constraint_loop_iterations=iterations,
        ),
        role="synthesizer",
    )


def test_constraint_distribution_groups_by_status(events_dir, window):
    _emit_synth("inv-c-1", status="single_pass")
    _emit_synth("inv-c-2", status="passed", iterations=2)
    _emit_synth("inv-c-3", status="max_iterations_reached", iterations=3)
    _emit_synth("inv-c-4", status="max_iterations_reached", iterations=3)

    events = list(iter_window_events(*window))
    C = collect_constraint_distribution(events)
    assert C["total_synthesis_deliveries"] == 4
    assert C["distribution"]["max_iterations_reached"]["count"] == 2
    # Non-converging → avg_iterations populated.
    assert C["distribution"]["max_iterations_reached"]["avg_iterations_used"] == 3.0
    assert C["distribution"]["max_iterations_reached"]["max_iterations_used"] == 3
    # Converging statuses don't get iteration stats.
    assert "avg_iterations_used" not in C["distribution"]["single_pass"]


# ---------------------------------------------------------------------------
# 5. Phase 8 signal
# ---------------------------------------------------------------------------


def test_phase_8_signal_patch_rate_against_completed(events_dir, window):
    # 2 investigations completed, 1 of them patched.
    emit_typed(
        "inv-p8-1",
        AutoPatchAppliedPayload(
            synthesis_id="syn-1", matched_domains=["q-knowledge"],
            patched=["q-knowledge"], skipped=[], errors=[], status="patched",
        ),
        synthesis_id="syn-1", role="auto_patch",
    )
    emit_typed(
        "inv-p8-2",
        AutoPatchAppliedPayload(
            synthesis_id="syn-2", matched_domains=[], patched=[],
            skipped=[], errors=[], status="no_match",
        ),
        synthesis_id="syn-2", role="auto_patch",
    )

    events = list(iter_window_events(*window))
    P = collect_phase_8_signal(events, completed_count=2)
    assert P["auto_patch_events_total"] == 2
    assert P["status_distribution"] == {"patched": 1, "no_match": 1}
    assert P["patch_rate_against_completed"] == 0.5
    assert P["top_domains_patched"] == [
        {"domain": "q-knowledge", "patch_count": 1},
    ]


# ---------------------------------------------------------------------------
# 6. Dispatch cost
# ---------------------------------------------------------------------------


def test_dispatch_cost_groups_by_tier_and_model(events_dir, window):
    emit_typed(
        "inv-d-1",
        DispatchCallPayload(
            provider="anthropic", model="claude-opus-4-7", tier="synthesis",
            target_role="synthesizer",
            prompt_hash="abc", input_tokens=100, output_tokens=200,
            cost_usd=0.05, latency_ms=1000, finish_reason="stop",
        ),
        role="dispatch",
    )
    emit_typed(
        "inv-d-1",
        DispatchCallPayload(
            provider="anthropic", model="claude-opus-4-7", tier="synthesis",
            target_role="synthesizer",
            prompt_hash="def", input_tokens=50, output_tokens=100,
            cost_usd=0.02, latency_ms=500, finish_reason="stop",
        ),
        role="dispatch",
    )
    emit_typed(
        "inv-d-2",
        DispatchCallPayload(
            provider="deepseek", model="deepseek-v4-flash", tier="flash",
            target_role="evidence_retriever",
            prompt_hash="ghi", input_tokens=200, output_tokens=300,
            cost_usd=0.001, latency_ms=300, finish_reason="stop",
        ),
        role="dispatch",
    )

    events = list(iter_window_events(*window))
    D = collect_dispatch_cost(events)
    assert D["total_calls"] == 3
    assert D["total_cost_usd"] == pytest.approx(0.071, abs=1e-4)
    by_tier = {t["tier"]: t for t in D["by_tier"]}
    assert by_tier["synthesis"]["calls"] == 2
    assert by_tier["synthesis"]["cost_usd"] == pytest.approx(0.07, abs=1e-4)
    assert by_tier["flash"]["calls"] == 1
    assert by_tier["flash"]["cost_usd"] == pytest.approx(0.001, abs=1e-4)


# ---------------------------------------------------------------------------
# 7. Cross-doc link rate
# ---------------------------------------------------------------------------


def test_cross_doc_link_rate(events_dir, window):
    for i in range(5):
        emit_typed(
            "inv-x",
            QuestionIdentifiedPayload(
                question_id=f"q-{i}",
                question_text=f"open question {i}",
            ),
            document_id="doc-A",  # wrestling event requires document_id
            role="note_taker",
        )
    for i in range(2):
        emit_typed(
            "inv-x",
            CrossDocQuestionAnsweredPayload(
                question_id=f"q-{i}",
                question_document_id="doc-A",
                answer_document_id="doc-B",
                answer_note_id=f"n-{i}",
            ),
            role="cross_doc",
        )
    events = list(iter_window_events(*window))
    X = collect_cross_doc_link_rate(events)
    assert X["questions_identified"] == 5
    assert X["cross_doc_answers"] == 2
    assert X["link_rate"] == 0.4


# ---------------------------------------------------------------------------
# 8. Rendering
# ---------------------------------------------------------------------------


def test_markdown_render_contains_all_section_headers(events_dir, log_dir, window):
    _emit_synth("inv-r-1", status="passed", iterations=2)
    report = build_report(*window)
    md = report_to_markdown(report)
    assert "# Antiek weekly observability report" in md
    for header in (
        "## 1. Phase telemetry", "## 2. Investigation lifecycle",
        "## 3. Constraint loop", "## 4. Phase 8 compounding",
        "## 5. Dispatch cost", "## 6. Cross-doc link rate",
    ):
        assert header in md


def test_html_render_wraps_markdown(events_dir, log_dir, window):
    report = build_report(*window)
    html = report_to_html(report)
    assert html.startswith("<!DOCTYPE html>")
    assert "Antiek weekly report" in html
    assert "<pre>" in html
    # No raw bracket content in the HTML output that would break.
    assert "</body></html>" in html


def test_to_dict_serializable(events_dir, log_dir, window):
    report = build_report(*window)
    d = report.to_dict()
    # Must round-trip through json without raising.
    out = json.dumps(d, default=str)
    assert "phase_telemetry" in out
    assert "lifecycle" in out


# ---------------------------------------------------------------------------
# 9. Window filtering
# ---------------------------------------------------------------------------


def test_window_filtering_excludes_out_of_range_events(
    events_dir, now,
):
    """An event emitted now appears when window covers now; doesn't
    appear when window ends before now."""
    _emit_synth("inv-wf-1", status="passed")

    # Window covers now.
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=1)
    events_in = list(iter_window_events(start, end))
    assert any(
        isinstance(e.payload, SynthesizeDeliveredPayload) for e in events_in
    )

    # Window ends BEFORE now.
    past_start = now - timedelta(days=10)
    past_end = now - timedelta(days=5)
    events_out = list(iter_window_events(past_start, past_end))
    assert not any(
        isinstance(e.payload, SynthesizeDeliveredPayload) for e in events_out
    )


# ---------------------------------------------------------------------------
# 10. CLI smoke
# ---------------------------------------------------------------------------


def test_cli_help_runs():
    from runtime.weekly_report import main
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_cli_emits_json_to_file(events_dir, log_dir, tmp_path):
    from runtime.weekly_report import main
    output = tmp_path / "report.json"
    rc = main([
        "--since", "2026-01-01", "--until", "2026-12-31",
        "--json", "--output", str(output),
    ])
    assert rc == 0
    assert output.exists()
    body = json.loads(output.read_text())
    assert "phase_telemetry" in body
    assert "window" in body


# ---------------------------------------------------------------------------
# 11. Aware-bounds tolerance — every public window function is
# caller-tz-agnostic. Regression for the half-hardened seam: the sidecar
# `day` path in collect_acquisition_cost tolerated aware bounds, but
# iter_window_events / collect_phase_telemetry / build_report compared raw
# caller bounds against naive-UTC data timestamps, so a programmatic caller
# passing `datetime.now(UTC)`-style bounds hit "TypeError: can't compare
# offset-naive and offset-aware datetimes" as soon as one event or phase
# log existed. Bounds are now normalized once at each public seam.
# ---------------------------------------------------------------------------


@pytest.fixture
def aware_window(window: tuple[datetime, datetime]) -> tuple[datetime, datetime]:
    """The same instants as `window`, expressed tz-aware (UTC)."""
    start, end = window
    return start.replace(tzinfo=UTC), end.replace(tzinfo=UTC)


def test_iter_window_events_tolerates_aware_bounds(events_dir, window, aware_window):
    emit_typed(
        "inv-tz-1",
        InvestigationStartRequestedPayload(
            question="tz?", context="", topic_slug="tz", max_sub_questions=4,
        ),
        role="operator",
    )
    naive = list(iter_window_events(*window))
    aware = list(iter_window_events(*aware_window))
    assert len(naive) == 1
    assert [e.event_id for e in aware] == [e.event_id for e in naive]


def test_collect_phase_telemetry_tolerates_aware_bounds(log_dir, now, window, aware_window):
    _write_phase_log(log_dir, "inv-tz-pt", created_at=now - timedelta(hours=1),
                     phases={
                         1: {"entered_at": "ts", "exited_at": "ts", "verified": True},
                     })
    naive = collect_phase_telemetry(*window)
    aware = collect_phase_telemetry(*aware_window)
    assert naive["investigations_in_window"] == 1
    assert aware == naive


def test_build_report_tolerates_aware_bounds(events_dir, log_dir, now, window, aware_window):
    emit_typed(
        "inv-tz-2",
        InvestigationStartRequestedPayload(
            question="tz?", context="", topic_slug="tz", max_sub_questions=4,
        ),
        role="operator",
    )
    _write_phase_log(log_dir, "inv-tz-2", created_at=now - timedelta(hours=1),
                     phases={
                         1: {"entered_at": "ts", "exited_at": "ts", "verified": True},
                     })
    r_naive = build_report(*window)
    r_aware = build_report(*aware_window)
    assert r_aware.lifecycle["started"] == 1
    assert r_aware.lifecycle == r_naive.lifecycle
    assert r_aware.phase_telemetry == r_naive.phase_telemetry
    # The rendered window reflects the normalized bounds actually used for
    # filtering — identical whichever tz representation the caller passed.
    assert r_aware.window == r_naive.window
