"""Tests for the weekly bench HTML render (ask #11 presentation)."""

from __future__ import annotations

from substrate.antiek_bench.weekly_render import (
    ModelScore,
    TaskFamilyResult,
    WeeklyBenchSnapshot,
    render_weekly_bench,
)


def _snapshot(**overrides) -> WeeklyBenchSnapshot:
    defaults = dict(
        week_id="2026-W29",
        generated_at_label="2026-07-12T20:00:00+03:00",
        task_families=(),
        overall_ranking=(),
        source_record_count=0,
        incomplete=False,
        honesty_notes=(),
    )
    defaults.update(overrides)
    return WeeklyBenchSnapshot(**defaults)


# --------------------------------------------------------------------------- #
# Banner reflects the authoritative incomplete flag.
# --------------------------------------------------------------------------- #
def test_complete_week_banner():
    html_out = render_weekly_bench(_snapshot(incomplete=False))
    assert "Week complete." in html_out
    assert 'class="banner complete"' in html_out


def test_incomplete_week_banner_flagged():
    html_out = render_weekly_bench(_snapshot(incomplete=True))
    assert "Week incomplete" in html_out
    assert 'class="banner incomplete"' in html_out


# --------------------------------------------------------------------------- #
# Ranking: completed models ranked by score; ties share the best star.
# --------------------------------------------------------------------------- #
def test_models_ranked_by_score_descending():
    family = TaskFamilyResult(
        task_family="exact-reasoning",
        scoring_method="exact",
        models=(
            ModelScore("weak-model", 0.4, completed_runs=5),
            ModelScore("strong-model", 0.95, completed_runs=5),
            ModelScore("mid-model", 0.7, completed_runs=5),
        ),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,), incomplete=False))
    # strong before mid before weak in document order
    assert out.index("strong-model") < out.index("mid-model") < out.index("weak-model")
    assert "strong-model &#9733;" in out  # best gets the star
    assert "weak-model &#9733;" not in out


def test_tie_names_all_best_models():
    family = TaskFamilyResult(
        task_family="rubric-synthesis",
        models=(
            ModelScore("model-a", 0.8, completed_runs=3),
            ModelScore("model-b", 0.8, completed_runs=3),
            ModelScore("model-c", 0.6, completed_runs=3),
        ),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,)))
    assert "model-a &#9733;" in out
    assert "model-b &#9733;" in out
    assert "model-c &#9733;" not in out


# --------------------------------------------------------------------------- #
# A model with no completed runs is NOT ranked (no fabricated score).
# --------------------------------------------------------------------------- #
def test_pending_model_not_ranked_but_listed():
    family = TaskFamilyResult(
        task_family="human-judged",
        scoring_method="human",
        models=(
            ModelScore("scored-model", 0.9, completed_runs=2),
            ModelScore("pending-model", None, completed_runs=0, pending_runs=2),
        ),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,), incomplete=True))
    assert "pending-model &#9733;" not in out  # not the winner
    assert "No completed runs (pending/unknown): pending-model" in out
    # scored-model is still ranked with its real score
    assert "0.900" in out


def test_all_pending_family_no_fabricated_winner():
    family = TaskFamilyResult(
        task_family="future-task",
        models=(ModelScore("only-model", None, completed_runs=0, pending_runs=1),),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,), incomplete=True))
    assert "No completed runs." in out
    assert "&#9733;" not in out  # no fabricated winner


# --------------------------------------------------------------------------- #
# Empty/unknown values shown honestly (em-dash, never 0.0 or blank).
# --------------------------------------------------------------------------- #
def test_none_score_renders_em_dash():
    family = TaskFamilyResult(
        task_family="t",
        models=(ModelScore("m", None, completed_runs=0),),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,), incomplete=True))
    assert "&mdash;" in out


def test_empty_snapshot_renders_honest_empty_notes():
    out = render_weekly_bench(_snapshot())
    assert "No task families recorded this week." in out
    assert "No overall data this week." in out


# --------------------------------------------------------------------------- #
# HTML escaping — all interpolated values escaped (XSS safety).
# --------------------------------------------------------------------------- #
def test_model_ids_escaped():
    family = TaskFamilyResult(
        task_family="<script>x</script>",
        models=(ModelScore("<img src=x onerror=alert(1)>", 0.5, completed_runs=1),),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,)))
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;img" in out


def test_notes_escaped():
    family = TaskFamilyResult(
        task_family="t",
        models=(ModelScore("m", 0.5, completed_runs=1, notes="<b>bold</b>"),),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,)))
    assert "<b>bold</b>" not in out
    assert "&lt;b&gt;" in out


def test_week_id_and_label_escaped():
    out = render_weekly_bench(
        _snapshot(week_id='2026-W29<">', generated_at_label="<i>now</i>")
    )
    assert "<i>now</i>" not in out
    assert "&lt;i&gt;" in out


# --------------------------------------------------------------------------- #
# Provenance footer carries real data.
# --------------------------------------------------------------------------- #
def test_footer_carries_provenance():
    out = render_weekly_bench(
        _snapshot(
            week_id="2026-W29",
            generated_at_label="2026-07-12",
            source_record_count=42,
            honesty_notes=("weights rewritten", "2 tasks graduated"),
        )
    )
    assert "Source records: 42" in out
    assert "Week: <code>2026-W29</code>" in out
    assert "Generated: 2026-07-12" in out
    assert "weights rewritten" in out
    assert "2 tasks graduated" in out


# --------------------------------------------------------------------------- #
# Family with pending runs surfaces the incomplete note.
# --------------------------------------------------------------------------- #
def test_family_with_pending_runs_notes_incomplete():
    family = TaskFamilyResult(
        task_family="t",
        models=(
            ModelScore("m1", 0.8, completed_runs=2, pending_runs=1),
        ),
    )
    out = render_weekly_bench(_snapshot(task_families=(family,), incomplete=True))
    assert "This family has pending/incomplete runs." in out


# --------------------------------------------------------------------------- #
# Overall ranking section renders.
# --------------------------------------------------------------------------- #
def test_overall_ranking_section():
    out = render_weekly_bench(
        _snapshot(
            overall_ranking=(
                ModelScore("champ", 0.88, completed_runs=10),
                ModelScore("contender", 0.82, completed_runs=10),
            )
        )
    )
    assert "Overall ranking" in out
    assert "champ &#9733;" in out


# --------------------------------------------------------------------------- #
# Purity + self-contained HTML.
# --------------------------------------------------------------------------- #
def test_purity_no_io_imports():
    import inspect

    from substrate.antiek_bench import weekly_render as mod

    src = inspect.getsource(mod)
    for forbidden in ("import os", "import time", "import asyncio", "open(", "datetime.now", "requests"):
        assert forbidden not in src, f"purity breach: {forbidden!r}"


def test_output_is_self_contained_html_document():
    out = render_weekly_bench(_snapshot())
    assert out.startswith("<!DOCTYPE html>")
    assert "<style>" in out  # CSS inlined (self-contained)
    assert "</html>" in out
    # no JS
    assert "<script" not in out


def test_native_details_summary_used():
    family = TaskFamilyResult(
        task_family="t", models=(ModelScore("m", 0.5, completed_runs=1),)
    )
    out = render_weekly_bench(_snapshot(task_families=(family,)))
    assert "<details>" in out
    assert "<summary>" in out


# --------------------------------------------------------------------------- #
# Boundary types frozen.
# --------------------------------------------------------------------------- #
def test_boundary_types_frozen():
    import dataclasses

    from substrate.antiek_bench.weekly_render import (
        ModelScore,
        TaskFamilyResult,
        WeeklyBenchSnapshot,
    )

    for cls in (ModelScore, TaskFamilyResult, WeeklyBenchSnapshot):
        assert dataclasses.is_dataclass(cls)
