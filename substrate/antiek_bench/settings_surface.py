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


def settings_usage_summary_payload(
    *,
    store: BenchStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Public entry for Settings: weekly usage summary from recorded events.

    Calls shipped ``weekly_usage_summary`` — does not re-classify events or
    run live multi-provider benches.
    """
    from .usage_bridge import weekly_usage_summary

    summary = weekly_usage_summary(store=store)
    payload: dict[str, Any] = {
        "event_count": int(summary.get("event_count") or 0),
        "by_task_class": dict(summary.get("by_task_class") or {}),
        "view_format": "html",
        "settings_panel": "antiek_bench_usage_weekly",
        "source": "antiek_bench.usage_events",
        "notes": [],
    }
    if include_html:
        payload["html"] = project_usage_summary_html(payload)
    return payload


def project_usage_summary_html(summary: dict[str, Any]) -> str:
    """HTML-first human view of a usage summary (never PDF)."""
    from substrate.engagement_spine.project import project_to_html

    count = int(summary.get("event_count") or 0)
    by_class = summary.get("by_task_class") or {}
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek-bench weekly usage"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"Events recorded: {count} · view: HTML",
                }
            ],
        },
    ]
    if not by_class:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "(no usage events yet — engagement flywheel deposits feed this summary)",
                    }
                ],
            }
        )
    else:
        for task_class, bucket in sorted(by_class.items()):
            if not isinstance(bucket, dict):
                continue
            worked = int(bucket.get("worked") or 0)
            failed = int(bucket.get("failed") or 0)
            total = int(bucket.get("total") or 0)
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{task_class}: total={total} worked={worked} failed={failed}"
                            ),
                        }
                    ],
                }
            )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id="antiek-bench-usage-summary",
        creator="antiek_bench",
    )
