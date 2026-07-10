"""Residual (rx): HTML usage projection stamps Write twin_seed feeds."""

from __future__ import annotations

from substrate.antiek_bench.settings_surface import project_usage_summary_html
from substrate.antiek_bench.usage_bridge import TWIN_WRITE_SEED_USAGE_SOURCES


def test_usage_html_marks_write_seed_by_source() -> None:
    html = project_usage_summary_html(
        {
            "event_count": 5,
            "by_task_class": {"wrestle": {"worked": 5, "failed": 0, "total": 5}},
            "by_source": {
                "twin_promote_context": 3,
                "twin_chase": 2,
            },
            "known_sources": ["twin_promote_context", "twin_chase"],
        }
    )
    assert "twin_promote_context=3 [write seed]" in html
    assert "twin_chase=2" in html
    assert "twin_chase=2 [write seed]" not in html
    assert "Write seed feeds: 1" in html
    assert "recursive note-taker" in html
    assert "twin_promote_context" in TWIN_WRITE_SEED_USAGE_SOURCES
    assert "twin_chase" not in TWIN_WRITE_SEED_USAGE_SOURCES


def test_usage_html_known_sources_write_seed_count() -> None:
    html = project_usage_summary_html(
        {
            "event_count": 0,
            "by_task_class": {},
            "by_source": {},
            "known_sources": [
                "deep_research_session",
                "twin_chase",
                "evidence_pack",
            ],
        }
    )
    assert "Write seed feeds: 2" in html
    assert "Known feed sources:" in html
