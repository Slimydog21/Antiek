"""Settings-facing leaderboard over offline Antiek-bench runs.

Aggregates stored ``run_suite`` records for a ``week_id`` into an ordered
snapshot consumable by Settings (JSON-serializable). Does not re-run the suite,
call live providers, or auto-switch production traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.engagement_spine.project import project_to_html

from .store import BenchStore


@dataclass(frozen=True)
class ModelLeaderboardRow:
    model_id: str
    mean_score: float
    by_task_class: dict[str, float]
    run_count: int
    run_ids: tuple[str, ...]
    suite_versions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "mean_score": self.mean_score,
            "by_task_class": dict(self.by_task_class),
            "run_count": self.run_count,
            "run_ids": list(self.run_ids),
            "suite_versions": list(self.suite_versions),
        }


@dataclass(frozen=True)
class LeaderboardSnapshot:
    """Week-scoped leaderboard for the Settings panel."""

    week_id: str
    models: tuple[ModelLeaderboardRow, ...]
    task_classes: tuple[str, ...]
    run_count: int
    suite_versions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "models": [m.to_dict() for m in self.models],
            "task_classes": list(self.task_classes),
            "run_count": self.run_count,
            "suite_versions": list(self.suite_versions),
            "view_format": "html",
            "source": "antiek_bench.offline_runs",
        }


def build_leaderboard(
    week_id: str,
    *,
    store: BenchStore,
) -> LeaderboardSnapshot:
    """Build a stable leaderboard for ``week_id`` from offline stored runs.

    Models are ordered by mean_score descending (ties: model_id ascending).
    Multiple runs for the same model are averaged (mean of means; per-class
    averages of that model's run-level by_task_class values).
    """
    wid = (week_id or "").strip()
    if not wid:
        raise ValueError("week_id is required")

    runs = [r for r in store.list_runs() if str(r.get("week_id") or "") == wid]
    if not runs:
        return LeaderboardSnapshot(
            week_id=wid,
            models=(),
            task_classes=(),
            run_count=0,
            suite_versions=(),
        )

    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in runs:
        mid = str(r.get("model_id") or "").strip()
        if not mid:
            continue
        by_model.setdefault(mid, []).append(r)

    rows: list[ModelLeaderboardRow] = []
    all_classes: set[str] = set()
    all_suites: set[str] = set()

    for mid, model_runs in by_model.items():
        means = [float(r.get("mean_score") or 0.0) for r in model_runs]
        mean_score = round(sum(means) / len(means), 6) if means else 0.0

        class_buckets: dict[str, list[float]] = {}
        run_ids: list[str] = []
        suites: list[str] = []
        for r in model_runs:
            rid = str(r.get("run_id") or "")
            if rid:
                run_ids.append(rid)
            sv = str(r.get("suite_version") or "")
            if sv:
                suites.append(sv)
                all_suites.add(sv)
            btc = r.get("by_task_class") or {}
            if isinstance(btc, dict):
                for tc, sc in btc.items():
                    class_buckets.setdefault(str(tc), []).append(float(sc))
                    all_classes.add(str(tc))

        by_class = {
            tc: round(sum(vs) / len(vs), 6)
            for tc, vs in sorted(class_buckets.items())
        }
        rows.append(
            ModelLeaderboardRow(
                model_id=mid,
                mean_score=mean_score,
                by_task_class=by_class,
                run_count=len(model_runs),
                run_ids=tuple(sorted(set(run_ids))),
                suite_versions=tuple(sorted(set(suites))),
            )
        )

    # Rank: higher mean first; stable tie-break on model_id
    rows.sort(key=lambda m: (-m.mean_score, m.model_id))

    return LeaderboardSnapshot(
        week_id=wid,
        models=tuple(rows),
        task_classes=tuple(sorted(all_classes)),
        run_count=len(runs),
        suite_versions=tuple(sorted(all_suites)),
    )


def project_leaderboard_html(snapshot: LeaderboardSnapshot) -> str:
    """HTML human view of a leaderboard snapshot (PDF never required)."""
    lines: list[str] = [
        f"Antiek-bench leaderboard — week {snapshot.week_id}",
        f"Runs: {snapshot.run_count} · Suite versions: {', '.join(snapshot.suite_versions) or '(none)'}",
        f"Task classes: {', '.join(snapshot.task_classes) or '(none)'}",
    ]
    if not snapshot.models:
        lines.append("No offline runs recorded for this week.")
    for i, m in enumerate(snapshot.models, start=1):
        class_bits = ", ".join(
            f"{tc}={sc}" for tc, sc in sorted(m.by_task_class.items())
        )
        lines.append(
            f"#{i} model={m.model_id} mean_score={m.mean_score} "
            f"runs={m.run_count} [{class_bits}]"
        )

    content: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek-bench leaderboard"}],
        }
    ]
    for line in lines:
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": content},
        document_id=f"leaderboard-{snapshot.week_id}",
        creator="antiek_bench.leaderboard",
    )
    if not html or not html.strip():
        raise RuntimeError("empty leaderboard HTML")
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid leaderboard view surface")
    if snapshot.week_id not in html:
        raise RuntimeError("week_id missing from leaderboard HTML")
    return html
