"""Bridge workstation outcomes → Antiek-bench usage events for suite rewrite.

When deep-research / twin-promote / collective sessions complete, record
usage-shaped events so ``propose_suite_delta`` can learn weekly task patterns
and propose recursive suite rewrites (operator still approves/promotes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from .store import BenchStore

TaskClass = Literal["distill", "synthesize", "wrestle", "book_qa"]
Outcome = Literal["worked", "failed"]


@dataclass(frozen=True)
class UsageEvent:
    task_class: TaskClass
    outcome: Outcome
    prompt_hint: str = ""
    source: str = "engagement"
    model_id: str | None = None
    week_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "outcome": self.outcome,
            "prompt_hint": self.prompt_hint,
            "source": self.source,
            "model_id": self.model_id,
            "week_id": self.week_id,
        }


def classify_engagement_task(
    *,
    has_twins: bool = False,
    has_source_refs: bool = False,
    is_collective: bool = False,
    is_book_asset: bool = False,
) -> TaskClass:
    """Heuristic task_class for usage events from engagement surfaces."""
    if is_book_asset:
        return "book_qa"
    if is_collective:
        return "synthesize"
    if has_source_refs and has_twins:
        return "wrestle"
    if has_twins:
        return "distill"
    return "synthesize"


def research_tier_to_task_class(research_tier: str | None) -> TaskClass | None:
    """Residual (gv): map curated ResearchTier → Antiek-bench task_class.

    Returns None when unset so callers keep heuristic classify_engagement_task.
    """
    if research_tier is None:
        return None
    raw = str(research_tier).strip().lower()
    if not raw:
        return None
    if raw in ("wrestle",):
        return "wrestle"
    if raw in ("fast", "flash"):
        return "distill"
    if raw in ("deep", "pro"):
        return "synthesize"
    return None


def record_usage_event(
    event: UsageEvent | dict[str, Any],
    *,
    store: BenchStore,
) -> dict[str, Any]:
    """Append one usage event to the bench store (durable list under usage_events)."""
    row = event.to_dict() if isinstance(event, UsageEvent) else dict(event)
    if "task_class" not in row or "outcome" not in row:
        raise ValueError("usage event requires task_class and outcome")
    existing = store.get_run("_usage_events") or {"events": []}
    events = list(existing.get("events") or [])
    events.append(row)
    payload = {"run_id": "_usage_events", "events": events}
    store.put_run("_usage_events", payload)
    return row


def list_usage_events(*, store: BenchStore) -> list[dict[str, Any]]:
    row = store.get_run("_usage_events")
    if not row:
        return []
    return list(row.get("events") or [])


def record_session_flywheel_usage(
    *,
    store: BenchStore,
    twin_count: int,
    ref_count: int,
    status: str,
    model_id: str | None = None,
    prompt_hint: str = "",
    week_id: str | None = None,
    is_book_asset: bool = False,
    research_tier: str | None = None,
    task_class: TaskClass | None = None,
) -> dict[str, Any]:
    """Record usage from complete_session_with_context_flywheel outcome.

    Residual (gv): optional ``research_tier`` / ``task_class`` overrides the
    heuristic so Midnight Oil wrestle jobs feed the wrestle bench bucket.
    """
    outcome: Outcome = "worked" if status == "complete" else "failed"
    task = (
        task_class
        or research_tier_to_task_class(research_tier)
        or classify_engagement_task(
            has_twins=twin_count > 0,
            has_source_refs=ref_count > 0,
            is_book_asset=is_book_asset,
        )
    )
    return record_usage_event(
        UsageEvent(
            task_class=task,
            outcome=outcome,
            prompt_hint=prompt_hint[:280],
            source="session_flywheel",
            model_id=model_id,
            week_id=week_id,
        ),
        store=store,
    )


def record_collective_merge_usage(
    *,
    store: BenchStore,
    spawn_count: int,
    research_tier: str | None = None,
    prompt_hint: str = "",
    model_id: str | None = None,
    week_id: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Residual (oi): record multi-spawn collective merge → Antiek-bench usage.

    Feeds recursive suite rewrite when operators multi-select chase/float
    spawns into a cohesive unit (prompt merge, draft_combined, into_parent).
    task_class prefers research_tier, else synthesize (collective heuristic).
    """
    task = research_tier_to_task_class(research_tier) or classify_engagement_task(
        is_collective=True,
    )
    hint = (prompt_hint or "").strip()
    if mode:
        hint = f"[{mode}] {hint}".strip()
    if spawn_count > 0 and "spawn" not in hint.lower():
        hint = f"{hint} · spawns={spawn_count}".strip(" ·")
    return record_usage_event(
        UsageEvent(
            task_class=task,
            outcome="worked",
            prompt_hint=hint[:280],
            source="collective_merge",
            model_id=model_id,
            week_id=week_id,
        ),
        store=store,
    )


def record_twin_write_seed_usage(
    *,
    store: BenchStore,
    seed_source: str,
    prompt_hint: str = "",
    model_id: str | None = None,
    week_id: str | None = None,
    research_tier: str | None = None,
) -> dict[str, Any] | None:
    """Residual (qy/ra): record Write twin_seed handoff → Antiek-bench usage.

    Feeds recursive suite rewrite by_source for DR session/terminal seeds and
    dual-handoff matrix sources (MO, marketplace, merges, hosted HTML).
    twin_draft_selected returns None (covered by twin_chase).
    """
    src = str(seed_source or "").strip()
    if src not in TWIN_WRITE_SEED_USAGE_SOURCES:
        return None
    # Book-adjacent surfaces prefer book_qa when tier unset.
    is_book = src in ("marketplace_host", "hosted_html_document")
    is_collective = src in ("collective_doc_merge", "spawn_merge")
    task = research_tier_to_task_class(research_tier) or classify_engagement_task(
        has_twins=True,
        is_book_asset=is_book,
        is_collective=is_collective,
    )
    hint = (prompt_hint or "").strip()
    if src and src not in hint:
        hint = f"[{src}] {hint}".strip()
    return record_usage_event(
        UsageEvent(
            task_class=task,
            outcome="worked",
            prompt_hint=hint[:280],
            source=src,
            model_id=model_id,
            week_id=week_id,
        ),
        store=store,
    )


def propose_from_recorded_usage(
    *,
    store: BenchStore,
    registry: Any = None,
) -> Any:
    """Propose suite rewrite from recorded engagement usage events."""
    from .rewrite import propose_suite_delta

    events = list_usage_events(store=store)
    return propose_suite_delta(events, store=store, registry=registry)


# Residual (nx): known engagement feed sources for Settings honesty legend.
# Includes twin_chase + floating_deep_research from residual (nw).
# Residual (qy): deep_research_session + research_progress_complete from
# Write twin_seed handoffs (qv/qw recursive note-taker → Write path).
# Residual (ra): dual-handoff Write seed sources (MO deposit, marketplace,
# spawn/collective merge, hosted HTML) join known feed for recursive rewrite.
KNOWN_USAGE_FEED_SOURCES: tuple[str, ...] = (
    "investigation_start",
    "session_flywheel",
    "midnight_oil",
    "midnight_oil_deposit",
    "marketplace_host",
    "floating_deep_research",
    "twin_chase",
    "collective_merge",
    "collective_doc_merge",
    "spawn_merge",
    "hosted_html_document",
    "deep_research_session",
    "research_progress_complete",
    "research_progress_draft",
    "evidence_pack",
    "publication_hydrate",
    "session_flywheel_complete",
    "context_search",
    "research_context_pack",
    "twin_promote_context",
    # Residual (tt): multi-spawn cohesive unit prompt float → Write seed feed.
    "collective_unit_prompt",
    # Residual (vd): recursive note-taker cross-asset merge → Write seed feed.
    "twin_cross_asset_merge",
    "antiek_bench.offline_dogfood",
    "engagement",
)

# Twin-write seed sources that feed Antiek-bench by_source (qy…rr).
# twin_draft_selected omitted — multi-select draft already covered by twin_chase.
# Residual (tt): collective_unit_prompt joins Write seed feed (tr float path).
TWIN_WRITE_SEED_USAGE_SOURCES: frozenset[str] = frozenset(
    {
        "deep_research_session",
        "research_progress_complete",
        "research_progress_draft",
        "midnight_oil_deposit",
        "marketplace_host",
        "spawn_merge",
        "collective_doc_merge",
        "hosted_html_document",
        "evidence_pack",
        "publication_hydrate",
        "session_flywheel_complete",
        "context_search",
        "research_context_pack",
        "twin_promote_context",
        "collective_unit_prompt",
        # Residual (vd): cross-asset twin merge Write seed.
        "twin_cross_asset_merge",
    }
)


def weekly_usage_summary(*, store: BenchStore) -> dict[str, Any]:
    """Aggregate recorded usage for settings / Antiek-bench display.

    Residual (ha): also aggregate ``by_source`` so operators see interactive
    investigation starts vs Midnight Oil / session flywheel deposits.
    Residual (nx): known_sources legend for twin_chase / floating_deep_research
    (session open feed) so Settings UI can label the recursive rewrite feed.
    """
    events = list_usage_events(store=store)
    by_class: dict[str, dict[str, int]] = {}
    by_source: dict[str, int] = {}
    for e in events:
        tc = str(e.get("task_class") or "unknown")
        oc = str(e.get("outcome") or "unknown")
        src = str(e.get("source") or "unknown")
        bucket = by_class.setdefault(tc, {"worked": 0, "failed": 0, "total": 0})
        if oc in ("worked", "failed"):
            bucket[oc] += 1
        bucket["total"] += 1
        by_source[src] = by_source.get(src, 0) + 1
    # Residual (ry): Write twin_seed aggregates — single source of truth for
    # Settings + HTML honesty (parity frontend WRITE_SEED_FEED_SOURCES).
    write_seed_by_source = {
        src: n
        for src, n in by_source.items()
        if src in TWIN_WRITE_SEED_USAGE_SOURCES and n > 0
    }
    write_seed_source_count = len(write_seed_by_source)
    write_seed_event_count = int(sum(write_seed_by_source.values()))
    known = list(KNOWN_USAGE_FEED_SOURCES)
    write_seed_known_count = sum(
        1 for s in known if s in TWIN_WRITE_SEED_USAGE_SOURCES
    )
    return {
        "event_count": len(events),
        "by_task_class": by_class,
        "by_source": by_source,
        # Residual (nx): closed catalog of feed sources (not counts).
        "known_sources": known,
        "write_seed_by_source": write_seed_by_source,
        "write_seed_source_count": write_seed_source_count,
        "write_seed_event_count": write_seed_event_count,
        "write_seed_known_count": write_seed_known_count,
        "view_format": "html",
    }
