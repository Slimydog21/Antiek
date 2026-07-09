"""Settings-panel consumption shape for Antiek-bench leaderboard.

Pure adapter: turns a leaderboard snapshot into the JSON object a Settings
API/UI would return. Does not touch #440 budget projection or model inventory.
"""

from __future__ import annotations

from typing import Any

from .leaderboard import LeaderboardSnapshot, build_leaderboard, project_leaderboard_html
from .store import BenchStore


def settings_leaderboard_payload(
    week_id: str,
    *,
    store: BenchStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Public entry for Settings: structured leaderboard (+ optional HTML)."""
    snap = build_leaderboard(week_id, store=store)
    payload = snap.to_dict()
    payload["settings_panel"] = "antiek_bench_weekly"
    # Top model hint for decision-tree tab (advisory only — not auto-routing).
    if snap.models:
        top = snap.models[0]
        payload["recommended_model_id"] = top.model_id
        payload["recommended_mean_score"] = top.mean_score
    else:
        payload["recommended_model_id"] = None
        payload["recommended_mean_score"] = None
    if include_html:
        payload["html"] = project_leaderboard_html(snap)
    return payload


def leaderboard_from_snapshot(snapshot: LeaderboardSnapshot) -> dict[str, Any]:
    return snapshot.to_dict()
