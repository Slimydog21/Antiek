"""Antiek-bench offline product path — run dogfood suite into the store.

Closes the Settings flywheel: fixtures → offline run → leaderboard → install
driver. Never calls live multi-provider APIs; uses ``keyword_stub_provider``
with quality tiers so models differentiate without network.
"""

from __future__ import annotations

from typing import Any, Sequence

from .dogfood_fixtures import competitive_dogfood_suite
from .run import BenchRunResult, keyword_stub_provider, run_suite
from .settings_surface import settings_leaderboard_payload
from .store import BenchStore
from .summary import project_run_html

# Default offline cohort: quality tiers for honest differentiation.
DEFAULT_OFFLINE_MODELS: tuple[tuple[str, float], ...] = (
    ("stub-strong", 0.95),
    ("stub-mid", 0.55),
    ("stub-weak", 0.25),
)


def run_offline_dogfood_product(
    *,
    week_id: str,
    store: BenchStore,
    models: Sequence[tuple[str, float]] | None = None,
    include_html: bool = True,
) -> dict[str, Any]:
    """Product entry: run competitive dogfood suite offline for a model cohort.

    Records one run per model via ``run_suite`` + stub providers. Returns
    run summaries + refreshed leaderboard payload for the same week.
    """
    wid = (week_id or "").strip()
    if not wid:
        raise ValueError("week_id is required")

    cohort = list(models) if models is not None else list(DEFAULT_OFFLINE_MODELS)
    if not cohort:
        raise ValueError("at least one model (model_id, quality) is required")

    suite = competitive_dogfood_suite()
    runs: list[dict[str, Any]] = []
    for model_id, quality in cohort:
        mid = (model_id or "").strip()
        if not mid:
            raise ValueError("model_id entries must be non-empty")
        result: BenchRunResult = run_suite(
            model_id=mid,
            week_id=wid,
            store=store,
            suite=suite,
            provider_fn=keyword_stub_provider(mid, quality=float(quality)),
        )
        entry = result.to_dict()
        entry["quality_stub"] = float(quality)
        runs.append(entry)

    leaderboard = settings_leaderboard_payload(wid, store=store, include_html=include_html)

    payload: dict[str, Any] = {
        "week_id": wid,
        "suite_version": suite.suite_version,
        "suite_label": suite.label,
        "run_count": len(runs),
        "runs": runs,
        "models_run": [r["model_id"] for r in runs],
        "recommended_model_id": leaderboard.get("recommended_model_id"),
        "recommended_mean_score": leaderboard.get("recommended_mean_score"),
        "leaderboard": leaderboard,
        "view_format": "html",
        "offline": True,
        "auto_promoted": False,
        "settings_panel": "antiek_bench_run_offline",
        "source": "antiek_bench.product_path.run_offline_dogfood",
        "product_panel": "antiek_bench_run_offline",
        "notes": [
            "Offline dogfood suite run — keyword stub providers only.",
            "No live multi-provider calls; quality tiers differentiate stubs.",
            "Leaderboard is advisory for decision-tree install — never auto-routes.",
        ],
    }

    if include_html:
        # Prefer first run HTML + leaderboard HTML combined note surface
        first_rid = runs[0]["run_id"] if runs else None
        parts: list[str] = []
        if first_rid:
            try:
                parts.append(project_run_html(first_rid, store=store))
            except Exception:
                pass
        lb_html = leaderboard.get("html")
        if lb_html:
            parts.append(str(lb_html))
        # Minimal combined HTML if projectors failed
        if not parts:
            parts.append(
                f"<article data-view-format='html'>"
                f"<h1>Antiek-bench offline dogfood</h1>"
                f"<p>Week {wid} · suite {suite.suite_version} · runs {len(runs)}</p>"
                f"</article>"
            )
        combined = "\n".join(parts)
        if "application/pdf" in combined.lower() or combined.lstrip().lower().startswith(
            "%pdf"
        ):
            raise RuntimeError("PDF is not a valid bench product view")
        payload["html"] = combined

    return payload
