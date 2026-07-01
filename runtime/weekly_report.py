"""Weekly cross-cutting observability report (Sprint 9 day 1-2 port
of Researchmaxx ``weekly_report.py``).

Trajectory-driven, not DB-driven. Walks the per-investigation event
files (``$ANTIEK_RESEARCH_EVENTS_DIR/*.{jsonl,parquet}``) + phase
log JSON files and aggregates six signal sources that, taken
together, answer "is the system compounding?":

  1. **Phase telemetry** — entered / exited / verified per phase
     across all investigations whose phase_log ``created_at`` falls
     in the window. Keystone callout fires when Phase 8 verify rate
     is below the floor (default 80%).

  2. **Investigation lifecycle** — INVESTIGATION_START_REQUESTED
     vs INVESTIGATION_COMPLETED vs INVESTIGATION_FAILED counts.
     Average phases verified per completed investigation.

  3. **Constraint loop terminal-status distribution** — over all
     SYNTHESIZE_DELIVERED events, group by ``constraint_loop_status``
     (single_pass / passed / regressed / max_iterations_reached /
     escalated / preflight_failed). Average iteration count for
     the non-converging statuses.

  4. **Phase 8 compounding signal** — AUTO_PATCH_APPLIED count by
     status; total domains patched; the patch rate (successful
     patches / total completed investigations).

  5. **Dispatch cost by tier** — DISPATCH_CALL cost_usd totals
     grouped by tier and by (provider, model). Lets the operator
     see which roles are dominating cost.

  6. **Cross-doc link rate** — ratio of
     CROSS_DOC_QUESTION_ANSWERED events to QUESTION_IDENTIFIED
     events. Measures Loop 2's success at bridging questions
     across documents.

Output: Markdown by default; HTML wrapper via ``--html`` flag.
``ANTIEK_REPORTS_DIR`` env var picks the output directory (default
``~/.antiek/reports``).

CLI:

    python -m runtime.weekly_report
    python -m runtime.weekly_report --since 2026-05-01 --until 2026-05-08
    python -m runtime.weekly_report --output /tmp/report.md
    python -m runtime.weekly_report --html --output /tmp/report.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure repo root on path for direct CLI invocation.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from orchestration.phase_log import default_log_dir as phase_log_default_dir  # noqa: E402
from substrate.event_log import default_events_dir, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    AutoPatchAppliedPayload,
    CrossDocQuestionAnsweredPayload,
    DispatchCallPayload,
    Event,
    InvestigationCompletedPayload,
    InvestigationFailedPayload,
    QuestionIdentifiedPayload,
    SynthesizeDeliveredPayload,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


PHASE_NAMES: dict[int, str] = {
    1: "orient",
    2: "round1_landscape",
    3: "round1_critique",
    4: "round2_deepdive",
    5: "round2_critique",
    6: "synthesis",
    7: "delivery",
    8: "knowledge_extraction",
    9: "completion",
}
PHASE_IDS = tuple(sorted(PHASE_NAMES))
KEYSTONE_PHASE = 8
KEYSTONE_VERIFY_FLOOR = 0.8

CONSTRAINT_NON_CONVERGING: frozenset[str] = frozenset({
    "regressed", "max_iterations_reached", "escalated", "preflight_failed",
})


# ---------------------------------------------------------------------------
# Window + path helpers
# ---------------------------------------------------------------------------


def default_reports_dir() -> str:
    """Where reports land by default. ``ANTIEK_REPORTS_DIR`` env var
    overrides; default ``~/.antiek/reports``."""
    return os.environ.get(
        "ANTIEK_REPORTS_DIR",
        os.path.join(
            os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")),
            "reports",
        ),
    )


def _parse_date(s: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not s:
        return None
    dt = datetime.strptime(s, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def _resolve_window(
    since: str | None, until: str | None,
) -> tuple[datetime, datetime]:
    """Default window = last 7 days ending now (UTC, tzinfo-naive)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    end = _parse_date(until, end_of_day=True) or now
    start = _parse_date(since) or (end - timedelta(days=7))
    return start, end


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _pct(num: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return round(num / denom, 3)


def _parse_event_ts(s: Any) -> datetime | None:
    """ISO 8601 with optional ``Z`` suffix. Returns tzinfo-naive UTC."""
    if not s:
        return None
    try:
        ts = datetime.fromisoformat(str(s).rstrip("Z"))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts


# ---------------------------------------------------------------------------
# Trajectory iteration across all investigations
# ---------------------------------------------------------------------------


def _iter_investigation_ids(events_dir: str | None = None) -> Iterator[str]:
    """Walk the events directory; yield the investigation_id of every
    persisted trajectory (Parquet or JSONL)."""
    d = events_dir or default_events_dir()
    if not os.path.isdir(d):
        return
    seen: set[str] = set()
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".parquet"):
            iid = fn[: -len(".parquet")]
        elif fn.endswith(".jsonl"):
            iid = fn[: -len(".jsonl")]
        else:
            continue
        if iid not in seen:
            seen.add(iid)
            yield iid


def iter_window_events(
    start: datetime, end: datetime,
    *,
    events_dir: str | None = None,
) -> Iterator[Event]:
    """Walk every persisted trajectory and yield validated ``Event``
    objects whose ``emitted_at`` lies in ``[start, end]``. Malformed
    rows are skipped silently — the report's job is to surface
    aggregate signal, not relitigate per-row corruption."""
    for iid in _iter_investigation_ids(events_dir):
        for row in trajectory(iid, events_dir=events_dir):
            ts = _parse_event_ts(row.get("emitted_at"))
            if ts is None:
                continue
            if not (start <= ts <= end):
                continue
            try:
                yield Event.model_validate(row)
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Section 1 — Phase telemetry (walks the phase_log JSON dir)
# ---------------------------------------------------------------------------


def collect_phase_telemetry(
    start: datetime, end: datetime,
    *,
    log_dir: str | None = None,
) -> dict[str, Any]:
    """Aggregate per-phase entered / exited / verified counts across
    all investigations whose phase_log ``created_at`` falls in the
    window."""
    d = log_dir or phase_log_default_dir()
    if not os.path.isdir(d):
        return {
            "log_dir": d, "log_dir_exists": False,
            "investigations_in_window": 0, "phases": {},
            "keystone_callout": None,
        }

    counters: dict[int, dict[str, int]] = {
        pid: {"entered": 0, "exited": 0, "verified": 0}
        for pid in PHASE_IDS
    }
    n_inv = 0
    investigation_ids_seen: list[str] = []
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(d, fname)
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue
        created = _parse_event_ts(data.get("created_at"))
        if created is None or not (start <= created <= end):
            continue
        n_inv += 1
        investigation_ids_seen.append(
            data.get("investigation_id") or fname[:-5],
        )
        for k, rec in (data.get("phases") or {}).items():
            try:
                pid = int(k)
            except (TypeError, ValueError):
                continue
            if pid not in counters:
                continue
            if rec.get("entered_at"):
                counters[pid]["entered"] += 1
            if rec.get("exited_at"):
                counters[pid]["exited"] += 1
            if rec.get("verified"):
                counters[pid]["verified"] += 1

    phases_out: dict[int, dict[str, Any]] = {}
    for pid in PHASE_IDS:
        c = counters[pid]
        phases_out[pid] = {
            "phase_id": pid, "name": PHASE_NAMES[pid],
            "entered": c["entered"], "exited": c["exited"],
            "verified": c["verified"],
            "verify_rate": _pct(c["verified"], c["entered"]),
        }

    p8 = phases_out[KEYSTONE_PHASE]
    callout: str | None = None
    if n_inv == 0:
        callout = None
    elif p8["entered"] == 0:
        callout = (
            f"KEYSTONE ALERT — Phase {KEYSTONE_PHASE} "
            f"({PHASE_NAMES[KEYSTONE_PHASE]}) was never entered for any of "
            f"the {n_inv} investigation(s) in the window."
        )
    elif (p8["verify_rate"] or 0) < KEYSTONE_VERIFY_FLOOR:
        callout = (
            f"KEYSTONE ALERT — Phase {KEYSTONE_PHASE} verify_rate is "
            f"{(p8['verify_rate'] or 0):.0%} (floor "
            f"{KEYSTONE_VERIFY_FLOOR:.0%}). Entered {p8['entered']}× but "
            f"verified only {p8['verified']}×."
        )

    return {
        "log_dir": d, "log_dir_exists": True,
        "investigations_in_window": n_inv,
        "investigation_ids": investigation_ids_seen,
        "phases": phases_out,
        "keystone_callout": callout,
    }


# ---------------------------------------------------------------------------
# Section 2 — Investigation lifecycle
# ---------------------------------------------------------------------------


def collect_investigation_lifecycle(events: list[Event]) -> dict[str, Any]:
    """INVESTIGATION_START_REQUESTED vs COMPLETED vs FAILED counts.
    Avg phases verified per completed investigation."""
    starts: set[str] = set()
    completed: list[InvestigationCompletedPayload] = []
    failed: list[InvestigationFailedPayload] = []
    for e in events:
        at = (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        if at == ActionType.INVESTIGATION_START_REQUESTED.value:
            starts.add(e.investigation_id)
        elif at == ActionType.INVESTIGATION_COMPLETED.value:
            if isinstance(e.payload, InvestigationCompletedPayload):
                completed.append(e.payload)
        elif at == ActionType.INVESTIGATION_FAILED.value:
            if isinstance(e.payload, InvestigationFailedPayload):
                failed.append(e.payload)

    avg_phases_verified = (
        round(
            sum(p.total_phases_verified for p in completed) / len(completed),
            2,
        )
        if completed else None
    )
    failed_phase_dist = Counter(p.phase for p in failed)

    return {
        "started": len(starts),
        "completed": len(completed),
        "failed": len(failed),
        "in_progress": max(0, len(starts) - len(completed) - len(failed)),
        "avg_phases_verified_when_completed": avg_phases_verified,
        "failed_phase_distribution": dict(failed_phase_dist),
    }


# ---------------------------------------------------------------------------
# Section 3 — Constraint loop terminal-status distribution
# ---------------------------------------------------------------------------


def collect_constraint_distribution(events: list[Event]) -> dict[str, Any]:
    """Group SYNTHESIZE_DELIVERED events by ``constraint_loop_status``.
    Avg / max iterations for non-converging statuses."""
    deliveries = [
        e.payload for e in events
        if isinstance(e.payload, SynthesizeDeliveredPayload)
    ]
    status_counts: Counter = Counter()
    iter_by_status: dict[str, list[int]] = defaultdict(list)
    for d in deliveries:
        status_counts[d.constraint_loop_status] += 1
        if d.constraint_loop_status in CONSTRAINT_NON_CONVERGING:
            iter_by_status[d.constraint_loop_status].append(
                d.constraint_loop_iterations,
            )

    distribution: dict[str, dict[str, Any]] = {}
    total = len(deliveries)
    for status, count in status_counts.most_common():
        entry: dict[str, Any] = {
            "count": count, "pct": _pct(count, total),
        }
        iters = iter_by_status.get(status)
        if iters:
            entry["avg_iterations_used"] = round(sum(iters) / len(iters), 2)
            entry["max_iterations_used"] = max(iters)
        distribution[status] = entry

    return {
        "total_synthesis_deliveries": total,
        "distribution": distribution,
    }


# ---------------------------------------------------------------------------
# Section 4 — Phase 8 compounding signal
# ---------------------------------------------------------------------------


def collect_phase_8_signal(
    events: list[Event], *,
    completed_count: int,
) -> dict[str, Any]:
    """Walk AUTO_PATCH_APPLIED events. Patch rate = successful patches
    / total completed investigations."""
    patches = [
        e.payload for e in events
        if isinstance(e.payload, AutoPatchAppliedPayload)
    ]
    status_counts: Counter = Counter()
    domain_counts: Counter = Counter()
    for p in patches:
        status_counts[p.status] += 1
        for d in p.patched:
            domain_counts[d] += 1

    successful = status_counts.get("patched", 0)
    return {
        "auto_patch_events_total": len(patches),
        "status_distribution": dict(status_counts.most_common()),
        "patch_rate_against_completed": _pct(successful, completed_count),
        "top_domains_patched": [
            {"domain": d, "patch_count": n}
            for d, n in domain_counts.most_common(10)
        ],
    }


# ---------------------------------------------------------------------------
# Section 5 — Dispatch cost by tier
# ---------------------------------------------------------------------------


def collect_dispatch_cost(events: list[Event]) -> dict[str, Any]:
    """Sum cost_usd over DISPATCH_CALL events. Group by tier and by
    (provider, model)."""
    calls = [
        e.payload for e in events
        if isinstance(e.payload, DispatchCallPayload)
    ]
    cost_by_tier: dict[str, float] = defaultdict(float)
    count_by_tier: Counter = Counter()
    cost_by_model: dict[str, float] = defaultdict(float)
    count_by_model: Counter = Counter()
    total_cost = 0.0
    for c in calls:
        cost_by_tier[c.tier] += c.cost_usd
        count_by_tier[c.tier] += 1
        model_key = f"{c.provider}/{c.model}"
        cost_by_model[model_key] += c.cost_usd
        count_by_model[model_key] += 1
        total_cost += c.cost_usd

    return {
        "total_calls": len(calls),
        "total_cost_usd": round(total_cost, 4),
        "by_tier": [
            {
                "tier": tier,
                "calls": count_by_tier[tier],
                "cost_usd": round(cost, 4),
            }
            for tier, cost in sorted(
                cost_by_tier.items(), key=lambda kv: -kv[1],
            )
        ],
        "by_model": [
            {
                "model": model,
                "calls": count_by_model[model],
                "cost_usd": round(cost, 4),
            }
            for model, cost in sorted(
                cost_by_model.items(), key=lambda kv: -kv[1],
            )[:10]
        ],
    }


# ---------------------------------------------------------------------------
# Section 6 — Cross-doc link rate
# ---------------------------------------------------------------------------


def collect_cross_doc_link_rate(events: list[Event]) -> dict[str, Any]:
    """Count QUESTION_IDENTIFIED vs CROSS_DOC_QUESTION_ANSWERED.
    Link rate = answered / identified."""
    n_questions = sum(
        1 for e in events if isinstance(e.payload, QuestionIdentifiedPayload)
    )
    n_answered = sum(
        1 for e in events if isinstance(e.payload, CrossDocQuestionAnsweredPayload)
    )
    return {
        "questions_identified": n_questions,
        "cross_doc_answers": n_answered,
        "link_rate": _pct(n_answered, n_questions),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class WeeklyReport:
    """Top-level report payload. ``to_dict`` for JSON; ``to_markdown``
    + ``to_html`` for the operator-facing renderings."""

    window: dict[str, str | None]
    generated_at: str
    phase_telemetry: dict[str, Any]
    lifecycle: dict[str, Any]
    constraint_distribution: dict[str, Any]
    phase_8_signal: dict[str, Any]
    dispatch_cost: dict[str, Any]
    cross_doc: dict[str, Any]
    acquisition_cost: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "generated_at": self.generated_at,
            "phase_telemetry": self.phase_telemetry,
            "lifecycle": self.lifecycle,
            "constraint_distribution": self.constraint_distribution,
            "phase_8_signal": self.phase_8_signal,
            "dispatch_cost": self.dispatch_cost,
            "cross_doc": self.cross_doc,
            "acquisition_cost": self.acquisition_cost,
        }


def collect_acquisition_cost(
    start: datetime, end: datetime,
    *,
    budget_dir: str | None = None,
) -> dict[str, Any]:
    """Sum discovery-layer spend from the Exa budget sidecars
    (`~/.antiek/budgets/exa_<utc-date>.json`).

    Per `docs/integration_exa_browserbase.md` §6.7: the operator
    needs to see Exa spend alongside dispatch spend. The sidecars
    are the source of truth — the events carry per-call cost but
    the sidecars carry the realized daily totals.
    """
    if budget_dir:
        budget_path = Path(budget_dir)
    elif os.environ.get("ANTIEK_HOME"):
        budget_path = Path(os.environ["ANTIEK_HOME"]) / "budgets"
    else:
        budget_path = Path.home() / ".antiek" / "budgets"

    by_day: list[dict[str, Any]] = []
    total_usd = 0.0
    total_calls = 0

    if not budget_path.exists():
        return {
            "budget_dir": str(budget_path),
            "budget_dir_exists": False,
            "total_usd": 0.0,
            "total_calls": 0,
            "days_in_window": 0,
            "by_day": [],
            "top_day": None,
        }

    # Normalize the window bounds to naive UTC ONCE. `day` (below) is naive-UTC
    # (parsed from the YYYY-MM-DD sidecar stem); callers pass EITHER naive bounds
    # (`_window_default`) OR tz-aware bounds, and comparing mixed tz raises
    # "can't compare offset-naive and offset-aware datetimes". Coercing both to
    # naive UTC here makes the comparison caller-tz-agnostic.
    _start_day = (
        start.astimezone(UTC).replace(tzinfo=None) if start.tzinfo is not None else start
    ).replace(hour=0, minute=0, second=0, microsecond=0)
    _end_naive = (
        end.astimezone(UTC).replace(tzinfo=None) if end.tzinfo is not None else end
    )

    # Walk each provider sidecar in the date window. Format:
    #   exa_<YYYY-MM-DD>.json
    # Future providers extend by glob pattern.
    for f in sorted(budget_path.glob("exa_*.json")):
        try:
            stem_date = f.stem.replace("exa_", "")
            # Naive UTC (a YYYY-MM-DD stem carries no tz); compared against the
            # tz-normalized bounds computed above.
            day = datetime.strptime(stem_date, "%Y-%m-%d")
        except ValueError:
            continue
        if day < _start_day:
            continue
        if day > _end_naive:
            continue
        try:
            data = json.loads(f.read_text())
        except (ValueError, OSError):
            continue
        spent = float(data.get("spent_usd", 0.0))
        calls = int(data.get("call_count", 0))
        by_day.append({
            "date": stem_date,
            "provider": "exa",
            "spent_usd": spent,
            "call_count": calls,
            "cap_usd": float(data.get("cap_usd", 0.0)),
        })
        total_usd += spent
        total_calls += calls

    top_day = max(by_day, key=lambda r: r["spent_usd"], default=None)
    return {
        "budget_dir": str(budget_path),
        "budget_dir_exists": True,
        "total_usd": total_usd,
        "total_calls": total_calls,
        "days_in_window": len(by_day),
        "by_day": by_day,
        "top_day": top_day,
    }


def build_report(
    start: datetime, end: datetime,
    *,
    events_dir: str | None = None,
    log_dir: str | None = None,
    budget_dir: str | None = None,
) -> WeeklyReport:
    """Aggregate all sections. Reads the entire window's event
    history into memory once and partitions it across the section
    aggregators — keeps each event read once."""
    events = list(iter_window_events(start, end, events_dir=events_dir))
    phase = collect_phase_telemetry(start, end, log_dir=log_dir)
    lifecycle = collect_investigation_lifecycle(events)
    constraint = collect_constraint_distribution(events)
    p8 = collect_phase_8_signal(events, completed_count=lifecycle["completed"])
    cost = collect_dispatch_cost(events)
    crossdoc = collect_cross_doc_link_rate(events)
    acq = collect_acquisition_cost(start, end, budget_dir=budget_dir)
    return WeeklyReport(
        window={"since": _iso(start), "until": _iso(end)},
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        phase_telemetry=phase,
        lifecycle=lifecycle,
        constraint_distribution=constraint,
        phase_8_signal=p8,
        dispatch_cost=cost,
        cross_doc=crossdoc,
        acquisition_cost=acq,
    )


# ---------------------------------------------------------------------------
# Rendering — Markdown
# ---------------------------------------------------------------------------


_NO_EVENTS = "_No events in window._"


def _md_phase_section(p: dict[str, Any]) -> list[str]:
    lines = ["## 1. Phase telemetry"]
    if not p.get("log_dir_exists"):
        lines.append(f"Phase-log dir does not exist: `{p['log_dir']}`")
        lines.append(_NO_EVENTS)
        return lines
    n = p["investigations_in_window"]
    lines.append(f"Investigations in window: **{n}**")
    if n == 0:
        lines.append(_NO_EVENTS)
        return lines
    if p.get("keystone_callout"):
        lines.append(f"\n> {p['keystone_callout']}\n")
    lines.append("")
    lines.append("| # | phase | entered | exited | verified | verify_rate |")
    lines.append("|---|-------|--------:|-------:|---------:|------------:|")
    for pid in PHASE_IDS:
        row = p["phases"][pid]
        vr = row["verify_rate"]
        vr_s = f"{vr:.0%}" if vr is not None else "n/a"
        lines.append(
            f"| {pid} | {row['name']} | {row['entered']} | "
            f"{row['exited']} | {row['verified']} | {vr_s} |"
        )
    return lines


def _md_lifecycle_section(L: dict[str, Any]) -> list[str]:
    lines = ["## 2. Investigation lifecycle"]
    if L["started"] == 0:
        lines.append(_NO_EVENTS)
        return lines
    lines.append(f"Started: **{L['started']}**, "
                 f"completed: **{L['completed']}**, "
                 f"failed: **{L['failed']}**, "
                 f"in progress: **{L['in_progress']}**")
    if L["completed"] > 0:
        lines.append(
            f"\nAverage phases verified per completed investigation: "
            f"**{L['avg_phases_verified_when_completed']}**"
        )
    if L["failed"] > 0:
        lines.append("\nFailed-phase distribution:")
        for phase, count in sorted(L["failed_phase_distribution"].items()):
            lines.append(f"  - phase {phase}: {count}")
    return lines


def _md_constraint_section(C: dict[str, Any]) -> list[str]:
    lines = ["## 3. Constraint loop terminal-status distribution"]
    total = C["total_synthesis_deliveries"]
    if total == 0:
        lines.append(_NO_EVENTS)
        return lines
    lines.append(f"Total synthesis deliveries: **{total}**")
    lines.append("")
    lines.append("| status | count | pct | avg_iters | max_iters |")
    lines.append("|--------|------:|----:|----------:|----------:|")
    for status, e in C["distribution"].items():
        pct = e["pct"]
        pct_s = f"{pct:.0%}" if pct is not None else "n/a"
        ai = e.get("avg_iterations_used", "")
        mi = e.get("max_iterations_used", "")
        lines.append(f"| {status} | {e['count']} | {pct_s} | {ai} | {mi} |")
    return lines


def _md_phase_8_section(P: dict[str, Any]) -> list[str]:
    lines = ["## 4. Phase 8 compounding signal"]
    if P["auto_patch_events_total"] == 0:
        lines.append(_NO_EVENTS)
        return lines
    lines.append(
        f"Auto-patch events: **{P['auto_patch_events_total']}**, "
        f"patch rate vs completed: **"
        f"{P['patch_rate_against_completed'] or 0:.0%}**"
    )
    lines.append("\n**Status distribution:**")
    for status, count in P["status_distribution"].items():
        lines.append(f"  - {status}: {count}")
    if P["top_domains_patched"]:
        lines.append("\n**Top domains patched:**")
        for d in P["top_domains_patched"]:
            lines.append(f"  - {d['domain']}: {d['patch_count']}")
    return lines


def _md_dispatch_section(D: dict[str, Any]) -> list[str]:
    lines = ["## 5. Dispatch cost by tier"]
    if D["total_calls"] == 0:
        lines.append(_NO_EVENTS)
        return lines
    lines.append(
        f"Total dispatch calls: **{D['total_calls']}**, "
        f"total cost: **${D['total_cost_usd']:.4f}**"
    )
    lines.append("\n**By tier:**")
    lines.append("")
    lines.append("| tier | calls | cost_usd |")
    lines.append("|------|------:|---------:|")
    for t in D["by_tier"]:
        lines.append(
            f"| {t['tier']} | {t['calls']} | ${t['cost_usd']:.4f} |"
        )
    if D["by_model"]:
        lines.append("\n**Top models (by cost):**")
        lines.append("")
        lines.append("| model | calls | cost_usd |")
        lines.append("|-------|------:|---------:|")
        for m in D["by_model"]:
            lines.append(
                f"| {m['model']} | {m['calls']} | ${m['cost_usd']:.4f} |"
            )
    return lines


def _md_acquisition_section(A: dict[str, Any]) -> list[str]:
    lines = ["## 7. Acquisition cost (discovery layer)"]
    if not A or not A.get("budget_dir_exists"):
        lines.append(f"_Budget dir does not exist: `{A.get('budget_dir')}`_")
        return lines
    if A["days_in_window"] == 0:
        lines.append(_NO_EVENTS)
        return lines
    lines.append(
        f"Total Exa spend in window: **${A['total_usd']:.4f}** "
        f"across **{A['total_calls']}** calls "
        f"over **{A['days_in_window']}** day(s)."
    )
    if A.get("top_day"):
        td = A["top_day"]
        lines.append(
            f"Top-spending day: **{td['date']}** "
            f"(${td['spent_usd']:.4f} / {td['call_count']} calls, "
            f"cap ${td['cap_usd']:.2f})."
        )
    lines.append("")
    lines.append("| date | provider | calls | spent_usd | cap_usd |")
    lines.append("|------|----------|------:|----------:|--------:|")
    for r in A["by_day"]:
        lines.append(
            f"| {r['date']} | {r['provider']} | {r['call_count']} | "
            f"${r['spent_usd']:.4f} | ${r['cap_usd']:.2f} |"
        )
    return lines


def _md_cross_doc_section(X: dict[str, Any]) -> list[str]:
    lines = ["## 6. Cross-doc link rate"]
    if X["questions_identified"] == 0:
        lines.append(_NO_EVENTS)
        return lines
    rate = X["link_rate"]
    rate_s = f"{rate:.0%}" if rate is not None else "n/a"
    lines.append(
        f"Questions identified: **{X['questions_identified']}**, "
        f"cross-doc answers: **{X['cross_doc_answers']}**, "
        f"link rate: **{rate_s}**"
    )
    return lines


def report_to_markdown(r: WeeklyReport) -> str:
    """Render the full report as markdown."""
    lines: list[str] = [
        "# Antiek weekly observability report",
        "",
        f"_Window: {r.window['since']} → {r.window['until']}_  ",
        f"_Generated at: {r.generated_at}_",
        "",
    ]
    lines.extend(_md_phase_section(r.phase_telemetry))
    lines.append("")
    lines.extend(_md_lifecycle_section(r.lifecycle))
    lines.append("")
    lines.extend(_md_constraint_section(r.constraint_distribution))
    lines.append("")
    lines.extend(_md_phase_8_section(r.phase_8_signal))
    lines.append("")
    lines.extend(_md_dispatch_section(r.dispatch_cost))
    lines.append("")
    lines.extend(_md_cross_doc_section(r.cross_doc))
    lines.append("")
    lines.extend(_md_acquisition_section(r.acquisition_cost))
    lines.append("")
    return "\n".join(lines)


def report_to_html(r: WeeklyReport) -> str:
    """Minimal HTML wrapper around the markdown rendering — keeps
    monospace tables intact and adds a stylesheet hook."""
    md = report_to_markdown(r)
    # Best-effort table conversion: leave markdown source inside a
    # <pre> block. Operator-facing tooling can pipe through a real
    # markdown processor; the raw HTML wrap is sufficient for
    # dashboards that embed via iframe.
    return (
        "<!DOCTYPE html>\n"
        "<html><head><meta charset=\"utf-8\">"
        "<title>Antiek weekly report</title>"
        "<style>body{font-family:-apple-system,sans-serif;"
        "max-width:960px;margin:2em auto;padding:0 1em}"
        "pre{background:#f6f8fa;padding:1em;overflow-x:auto;"
        "white-space:pre-wrap;font-family:Menlo,monospace}"
        "</style></head><body>\n"
        f"<pre>{md.replace('&', '&amp;').replace('<', '&lt;')}</pre>"
        "\n</body></html>"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Antiek weekly observability report — aggregates phase "
            "telemetry + investigation lifecycle + constraint loop + "
            "Phase 8 compounding + dispatch cost + cross-doc link rate "
            "over the trajectory."
        ),
    )
    p.add_argument("--since", help="ISO date YYYY-MM-DD (default: 7 days ago)")
    p.add_argument("--until", help="ISO date YYYY-MM-DD (default: now)")
    p.add_argument("--events-dir", default=None,
                   help="Trajectory dir (default: $ANTIEK_RESEARCH_EVENTS_DIR)")
    p.add_argument("--log-dir", default=None,
                   help="Phase-log dir (default: $ANTIEK_RESEARCH_PHASE_LOG_DIR)")
    p.add_argument("--output", default=None,
                   help="Output file (default: stdout)")
    p.add_argument("--html", action="store_true",
                   help="Emit HTML instead of markdown.")
    p.add_argument("--json", action="store_true",
                   help="Emit raw JSON (overrides --html).")
    args = p.parse_args(argv)

    start, end = _resolve_window(args.since, args.until)
    report = build_report(
        start, end,
        events_dir=args.events_dir, log_dir=args.log_dir,
    )

    if args.json:
        out = json.dumps(report.to_dict(), indent=2, default=str)
    elif args.html:
        out = report_to_html(report)
    else:
        out = report_to_markdown(report)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
