"""Consumer double-run launch for settings leaderboard public entry."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.antiek_bench import (  # noqa: E402
    InMemoryBenchStore,
    SuiteRegistry,
    build_leaderboard,
    default_core_suite,
    project_leaderboard_html,
    register_suite,
    run_suite,
    settings_leaderboard_payload,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402

_WEEK = "2026-W28"


def _seed(store: InMemoryBenchStore, reg: SuiteRegistry) -> None:
    run_suite(
        model_id="launch-strong",
        week_id=_WEEK,
        store=store,
        registry=reg,
        provider_fn=keyword_stub_provider("launch-strong", quality=0.95),
    )
    run_suite(
        model_id="launch-weak",
        week_id=_WEEK,
        store=store,
        registry=reg,
        provider_fn=keyword_stub_provider("launch-weak", quality=0.2),
    )


def _once() -> dict[str, object]:
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    store = InMemoryBenchStore()
    _seed(store, reg)
    snap = build_leaderboard(_WEEK, store=store)
    payload = settings_leaderboard_payload(_WEEK, store=store, include_html=True)
    html = project_leaderboard_html(snap)
    assert snap.week_id == _WEEK
    assert len(snap.models) == 2
    assert snap.models[0].model_id == "launch-strong"
    assert payload["recommended_model_id"] == "launch-strong"
    assert _WEEK in html and "launch-strong" in html and "distill" in html
    assert not html.lstrip().lower().startswith("%pdf")
    assert "html" in payload and len(str(payload["html"])) > 40
    return {
        "top_model": snap.models[0].model_id,
        "top_mean": snap.models[0].mean_score,
        "run_count": snap.run_count,
        "task_classes": tuple(snap.task_classes),
        "html_len": len(html),
        "payload_models": tuple(m["model_id"] for m in payload["models"]),
    }


def test_leaderboard_consumer_double_run_stable():
    a = _once()
    b = _once()
    assert a == b
    assert a["top_model"] == "launch-strong"
    assert a["run_count"] == 2
    assert "distill" in a["task_classes"]
    assert "synthesize" in a["task_classes"]
