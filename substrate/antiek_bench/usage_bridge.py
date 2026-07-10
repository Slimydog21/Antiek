"""Bridge workstation outcomes → Antiek-bench usage events for suite rewrite.

When deep-research / twin-promote / collective sessions complete, record
usage-shaped events so ``propose_suite_delta`` can learn weekly task patterns
and propose recursive suite rewrites (operator still approves/promotes).
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .store import BenchStore

TaskClass = Literal["distill", "synthesize", "wrestle", "book_qa"]
Outcome = Literal["worked", "failed"]
USAGE_EVENT_SCHEMA_VERSION = 1
USAGE_EVENT_RETENTION_LIMIT = 5_000
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
_SAFE_OPAQUE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
_USAGE_APPEND_LOCK = threading.RLock()


@dataclass(frozen=True)
class UsageEvent:
    task_class: TaskClass
    outcome: Outcome
    prompt_hint: str = ""
    source: str = "engagement"
    model_id: str | None = None
    week_id: str | None = None
    source_ref: str | None = None
    benchmark_seed: str = ""
    benchmark_seed_reviewed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "outcome": self.outcome,
            "prompt_hint": self.prompt_hint,
            "source": self.source,
            "model_id": self.model_id,
            "week_id": self.week_id,
            "source_ref": self.source_ref,
            "benchmark_seed": self.benchmark_seed,
            "benchmark_seed_reviewed": self.benchmark_seed_reviewed,
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
    raw = event.to_dict() if isinstance(event, UsageEvent) else dict(event)
    row = _minimize_usage_event(raw)
    with _usage_store_lock(store):
        existing = store.get_run("_usage_events") or {"events": []}
        events = _minimize_stored_events(existing.get("events"))
        events.append(row)
        overflow = max(0, len(events) - USAGE_EVENT_RETENTION_LIMIT)
        evicted = int(existing.get("evicted_event_count") or 0) + overflow
        if overflow:
            events = events[overflow:]
        payload = {
            "run_id": "_usage_events",
            "schema_version": USAGE_EVENT_SCHEMA_VERSION,
            "retention_limit": USAGE_EVENT_RETENTION_LIMIT,
            "evicted_event_count": evicted,
            "events": events,
        }
        store.put_run("_usage_events", payload)
    return row


def _minimize_usage_event(raw: dict[str, Any]) -> dict[str, Any]:
    from .rewrite import reviewed_benchmark_seed

    task = str(raw.get("task_class") or "")
    outcome = str(raw.get("outcome") or "")
    if task not in ("distill", "synthesize", "wrestle", "book_qa"):
        raise ValueError("usage event has invalid task_class")
    if outcome not in ("worked", "failed"):
        raise ValueError("usage event has invalid outcome")
    source = str(raw.get("source") or "engagement").strip()
    model = str(raw.get("model_id") or "").strip() or None
    week = str(raw.get("week_id") or "").strip() or None
    source_ref = str(raw.get("source_ref") or "").strip() or None
    for name, value in (
        ("source", source),
        ("model_id", model),
        ("week_id", week),
    ):
        if value is not None and _SAFE_ID.fullmatch(value) is None:
            raise ValueError(f"usage event has invalid {name}")
    if source_ref is not None and _SAFE_OPAQUE_REF.fullmatch(source_ref) is None:
        raise ValueError("usage event has invalid source_ref")
    reviewed_seed = reviewed_benchmark_seed(raw)
    reviewed_requested = raw.get("benchmark_seed_reviewed") is True
    prompt_present = raw.get("prompt_hint_present")
    if prompt_present is not None and not isinstance(prompt_present, bool):
        raise ValueError("usage event has invalid prompt_hint_present")
    row: dict[str, Any] = {
        "schema_version": USAGE_EVENT_SCHEMA_VERSION,
        "task_class": task,
        "outcome": outcome,
        "source": source,
        "model_id": model,
        "week_id": week,
        "source_ref": source_ref,
        "prompt_hint_present": bool(str(raw.get("prompt_hint") or "").strip())
        or prompt_present is True,
        "benchmark_seed": reviewed_seed or "",
        "benchmark_seed_reviewed": reviewed_seed is not None,
        "benchmark_seed_rejected": (
            reviewed_requested and reviewed_seed is None
        ) or raw.get("benchmark_seed_rejected") is True,
    }
    if raw.get("has_body") is not None:
        if not isinstance(raw.get("has_body"), bool):
            raise ValueError("usage event has invalid has_body")
        row["has_body"] = raw["has_body"]
    return row


def list_usage_events(*, store: BenchStore) -> list[dict[str, Any]]:
    with _usage_store_lock(store):
        stored = store.get_run("_usage_events")
        if not stored:
            return []
        events = _minimize_stored_events(stored.get("events"))
        if events != stored.get("events"):
            payload = {
                "run_id": "_usage_events",
                "schema_version": USAGE_EVENT_SCHEMA_VERSION,
                "retention_limit": USAGE_EVENT_RETENTION_LIMIT,
                "evicted_event_count": int(stored.get("evicted_event_count") or 0),
                "events": events[-USAGE_EVENT_RETENTION_LIMIT:],
            }
            store.put_run("_usage_events", payload)
        return events[-USAGE_EVENT_RETENTION_LIMIT:]


@contextmanager
def _usage_store_lock(store: BenchStore) -> Iterator[None]:
    """Serialize process-local stores and file stores shared by worker processes."""
    with _USAGE_APPEND_LOCK:
        root = getattr(store, "root", None)
        if not isinstance(root, Path):
            yield
            return
        import fcntl

        lock_path = root / ".usage-events.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _minimize_stored_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    minimized: list[dict[str, Any]] = []
    for candidate in value:
        if not isinstance(candidate, dict):
            continue
        try:
            minimized.append(_minimize_usage_event(candidate))
        except (TypeError, ValueError):
            continue
    return minimized


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
    has_body: bool | None = None,
) -> dict[str, Any] | None:
    """Residual (qy/ra): record Write twin_seed handoff → Antiek-bench usage.

    Feeds recursive suite rewrite by_source for DR session/terminal seeds and
    dual-handoff matrix sources (MO, marketplace, merges, hosted HTML).
    twin_draft_selected returns None (covered by twin_chase).

    Residual (act): optional ``has_body`` stamps body honesty from the
    engagement Open Write matrix (acf–acs). Title-only seeds
    (``has_body=False``) record outcome=failed so weekly rewrite learns which
    Write paths lack real body substrate; omit has_body for legacy callers.
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
    # Residual (act): title-only twin_seed is weak recursive-rewrite signal.
    outcome: Outcome = "failed" if has_body is False else "worked"
    row = UsageEvent(
        task_class=task,
        outcome=outcome,
        prompt_hint=hint[:280],
        source=src,
        model_id=model_id,
        week_id=week_id,
    ).to_dict()
    if has_body is not None:
        row["has_body"] = bool(has_body)
    return record_usage_event(row, store=store)


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
    # Residual (aaj): catalog HTML projection Write seed.
    "marketplace_catalog",
    # Residual (asl): free HTML host-into-account Write seed (parity asj vision).
    "marketplace_free_host",
    "floating_deep_research",
    # Residual (asu): highlight-passage session open (asq HTML reading path).
    "highlight_dr_launch",
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
    # Residual (asl): knowledge-dense attach path Write seed (parity asj vision).
    "publication_attach",
    "session_flywheel_complete",
    "context_search",
    "research_context_pack",
    "twin_promote_context",
    # Residual (tt): multi-spawn cohesive unit prompt float → Write seed feed.
    "collective_unit_prompt",
    # Residual (vd): recursive note-taker cross-asset merge → Write seed feed.
    "twin_cross_asset_merge",
    # Residual (vk): collective written analysis float → Write seed feed.
    "collective_written_analysis",
    # Residual (anw): MetaReading HTML synthesis → Write seed feed.
    "meta_reading_deliverable",
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
        # Residual (aaj): catalog HTML projection Write seed.
        "marketplace_catalog",
        # Residual (asl): free HTML host-into-account Write seed (parity asj vision).
        "marketplace_free_host",
        "spawn_merge",
        "collective_doc_merge",
        "hosted_html_document",
        "evidence_pack",
        "publication_hydrate",
        # Residual (asl): knowledge-dense attach path Write seed (parity asj vision).
        "publication_attach",
        "session_flywheel_complete",
        "context_search",
        "research_context_pack",
        "twin_promote_context",
        "collective_unit_prompt",
        # Residual (vd): cross-asset twin merge Write seed.
        "twin_cross_asset_merge",
        # Residual (vk): collective written analysis Write seed.
        "collective_written_analysis",
        # Residual (anw): MetaReading HTML synthesis Write seed.
        "meta_reading_deliverable",
    }
)


def weekly_usage_summary(*, store: BenchStore) -> dict[str, Any]:
    """Aggregate recorded usage for settings / Antiek-bench display.

    Residual (ha): also aggregate ``by_source`` so operators see interactive
    investigation starts vs Midnight Oil / session flywheel deposits.
    Residual (nx): known_sources legend for twin_chase / floating_deep_research
    (session open feed) so Settings UI can label the recursive rewrite feed.
    Residual (act): write-seed body honesty aggregates for recursive rewrite
    (has_body true/false/unknown from engagement Open Write matrix).
    """
    events = list_usage_events(store=store)
    stored = store.get_run("_usage_events") or {}
    by_class: dict[str, dict[str, int]] = {}
    by_source: dict[str, int] = {}
    write_seed_with_body_count = 0
    write_seed_title_only_count = 0
    write_seed_body_unknown_count = 0
    for e in events:
        tc = str(e.get("task_class") or "unknown")
        oc = str(e.get("outcome") or "unknown")
        src = str(e.get("source") or "unknown")
        bucket = by_class.setdefault(tc, {"worked": 0, "failed": 0, "total": 0})
        if oc in ("worked", "failed"):
            bucket[oc] += 1
        bucket["total"] += 1
        by_source[src] = by_source.get(src, 0) + 1
        if src in TWIN_WRITE_SEED_USAGE_SOURCES:
            hb = e.get("has_body")
            if hb is True:
                write_seed_with_body_count += 1
            elif hb is False:
                write_seed_title_only_count += 1
            else:
                write_seed_body_unknown_count += 1
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
        "retention_limit": int(
            stored.get("retention_limit") or USAGE_EVENT_RETENTION_LIMIT
        ),
        "evicted_event_count": int(stored.get("evicted_event_count") or 0),
        "by_task_class": by_class,
        "by_source": by_source,
        # Residual (nx): closed catalog of feed sources (not counts).
        "known_sources": known,
        "write_seed_by_source": write_seed_by_source,
        "write_seed_source_count": write_seed_source_count,
        "write_seed_event_count": write_seed_event_count,
        "write_seed_known_count": write_seed_known_count,
        # Residual (act): body honesty for recursive suite rewrite quality.
        "write_seed_with_body_count": write_seed_with_body_count,
        "write_seed_title_only_count": write_seed_title_only_count,
        "write_seed_body_unknown_count": write_seed_body_unknown_count,
        "view_format": "html",
    }
