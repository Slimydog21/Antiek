"""Platform-surface coverage source — activation energy for the structure loop (ask #11).

The operator's ask #11: *"...recursive where it learns from usage patterns to
understand what worked and what didn't in a given week to re-write the benchmark
(and sub-benchmarks within it of differentiating tasks as the platform
expands)."* The structure-rewrite engine (``task_rewrite.py``, #1843) consumes a
``PlatformSurfaceSignal`` to EMIT a new task when the platform gains a capability
— that is the "as the platform expands" half of the recursion.

But ``PlatformSurfaceSignal`` is a **caller-supplied parameter** there. A search
across every bench branch finds no producer: nothing derives which surfaces the
bench should grow to cover. So the emit edge is **dead** — the consumer exists,
the source does not, and "sub-benchmarks as the platform expands" never fires.
**This module is that source.** It is the activation energy: given the platform's
declared capability surfaces and the bench's existing task IDs, it proposes a
signal for every surface the bench does not yet task.

**Why pure + import-free of #1843.** ``task_rewrite.py`` ships in a separate
off-main PR; hard-importing ``PlatformSurfaceSignal`` would stack two PRs and
break independent bar-cleanliness on a frozen main. Instead this module defines
a compatible :class:`SurfaceSignal` (same fields: ``family``,
``proposed_task_id``, ``rationale``, optional ``prompt`` / ``scoring``) that the
route layer maps 1:1 to ``PlatformSurfaceSignal``. The module owns the ONE thing
no other does: the **derivation** of which surfaces are uncovered.

**The load-bearing invariants (each is a test):**

1. **A signal fires ONLY for a genuinely-uncovered surface.** A surface whose
   ``proposed_task_id`` is already in the bench's existing task set produces no
   signal — never propose redundant coverage (that would hand #1843 a no-op emit
   and clutter the operator's diff review).
2. **No surfaces → no signals.** An empty declared-surface set yields an empty
   signal list. The engine never invents a surface from nothing — "as the
   platform expands" is caller-grounded (the platform declares its surfaces),
   mirroring #1843's own "EMIT only from an explicit surface signal" rule.
3. **Dedup by ``proposed_task_id``.** Two declared surfaces that collapse to the
   same task id produce exactly one signal (idempotent — the second adds no
   information). Both source surface ids are named in the rationale for audit.
4. **``proposed_task_id`` is deterministic.** ``{family}::{slug(surface_id)}``,
   matching #1843's registry convention (``{family}::{slug}``). The slug is
   lowercase, non-alphanumerics → ``-``, collapsed and stripped — same input
   always produces the same id, never a random guid.
5. **Malformed surfaces are skipped, not fabricated.** A surface with an empty
   family or empty surface id cannot form a valid task id (``{family}::{slug}``
   needs both halves; #1843 rejects empty families) — it is dropped with a note,
   never silently coerced into a placeholder family.
6. **Deterministic + pure.** Same declared surfaces + existing task ids →
   byte-identical signals, emitted in sorted ``(family, proposed_task_id)``
   order. No I/O, no clock, no dispatch, no LLM.
7. **Advisory only.** This module PROPOSES signals; it never mutates the bench
   registry. #1843 still decides whether to emit the task diff; the operator
   still applies it. (Authority split mirrors every bench substrate: the pure
   layer never commits.)

**Composition (the structure-recursion loop):**

    platform declares capability surfaces ─┐
                                           ├─→ [THIS] uncovered-surface signals
    bench registry: existing task ids ─────┘              │
                                                          ▼
                              #1843 propose_task_rewrite(surface_signals=...) → TaskDiff(emit)
                                                          │
                                                          ▼
                                         operator applies → benchmark grows with the platform
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


class SurfaceCoverageError(ValueError):
    """A coverage input violates a load-bearing invariant."""


@dataclass(frozen=True)
class PlatformSurface:
    """One declared platform capability the benchmark may need to cover.

    ``surface_id`` is a stable, human-readable id for the capability (e.g.
    ``"arxiv-ingest"``, ``"midnight-oil-launch"``); ``family`` is the bench task
    family it belongs to (e.g. ``"acquisition"``, ``"scheduling"``). The route
    layer fills these from the platform's real declared surfaces — this module
    never introspects the runtime, keeping it pure.
    """

    surface_id: str
    family: str
    description: str = ""


@dataclass(frozen=True)
class SurfaceSignal:
    """A proposal that the benchmark grow to cover one uncovered surface.

    Field-compatible with #1843's ``PlatformSurfaceSignal`` (the route layer maps
    these 1:1). ``proposed_task_id`` follows ``{family}::{slug(surface_id)}``.
    """

    family: str
    proposed_task_id: str
    rationale: str
    prompt: str | None = None
    scoring: str | None = None


@dataclass(frozen=True)
class SurfaceCoverageReport:
    """The pure result of a coverage derivation. Advisory; never mutates."""

    signals: list[SurfaceSignal] = field(default_factory=list)
    covered_surface_ids: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()  # malformed surface ids, with reasons on notes
    notes: list[str] = field(default_factory=list)

    @property
    def has_signals(self) -> bool:
        return len(self.signals) > 0


@dataclass
class _AggBucket:
    """Internal aggregation state for surfaces collapsing to one task id."""

    family: str
    sources: list[str]
    desc: str


def _slugify(value: str) -> str:
    """Lowercase, non-alphanumerics → ``-``, collapsed and stripped.

    Deterministic: the same input always yields the same slug. Empty input →
    empty string (the caller treats an empty slug as a malformed surface).
    """
    cleaned: list[str] = []
    prev_dash = False
    for ch in value.lower():
        if ch.isalnum():
            cleaned.append(ch)
            prev_dash = False
        elif not prev_dash:
            cleaned.append("-")
            prev_dash = True
    return "".join(cleaned).strip("-")


def _task_id(family: str, surface_id: str) -> str:
    """Deterministic ``{family}::{slug(surface_id)}`` matching #1843's convention."""
    return f"{family}::{_slugify(surface_id)}"


def derive_uncovered_surface_signals(
    *,
    declared_surfaces: Sequence[PlatformSurface],
    existing_task_ids: Sequence[str],
) -> SurfaceCoverageReport:
    """Derive a coverage signal for every declared surface the bench doesn't task.

    Parameters
    ----------
    declared_surfaces:
        The platform's declared capability surfaces (caller-supplied; the route
        layer fills these from the real platform surface registry).
    existing_task_ids:
        The bench's current task ids (``{family}::{slug}``). A surface whose
        ``proposed_task_id`` is in this set is already covered → no signal.

    A signal is emitted for each uncovered surface, deduplicated by
    ``proposed_task_id`` (multiple surfaces collapsing to one task id yield one
    signal naming all sources), in deterministic sorted order. Malformed surfaces
    (empty family or surface id) are skipped with a note, never fabricated.
    """
    notes: list[str] = [
        "authority=advisory — proposes coverage signals; does not mutate antiek_bench",
        "signals derived from injected declared surfaces, not runtime introspection",
    ]
    existing = {tid.strip() for tid in existing_task_ids if tid and tid.strip()}
    covered_surface_ids: list[str] = []
    skipped: list[str] = []
    bucket: dict[str, _AggBucket] = {}

    for surface in declared_surfaces:
        sid = (surface.surface_id or "").strip()
        family = (surface.family or "").strip()
        if not sid or not family:
            reason = "empty family" if not family else "empty surface_id"
            skipped.append(f"{sid or family or '(unnamed)'}: {reason}")
            continue
        task_id = _task_id(family, sid)
        if task_id in existing:
            covered_surface_ids.append(sid)
            continue
        entry = bucket.get(task_id)
        if entry is None:
            bucket[task_id] = _AggBucket(family=family, sources=[sid], desc=surface.description)
        elif sid not in entry.sources:
            entry.sources.append(sid)

    if skipped:
        notes.append(
            f"skipped {len(skipped)} malformed surface/surfaces "
            "(empty family or surface_id) — not fabricated into placeholder tasks"
        )
    if covered_surface_ids:
        notes.append(
            f"{len(covered_surface_ids)} surface/surfaces already covered by an "
            "existing task — no redundant signal emitted"
        )

    signals: list[SurfaceSignal] = []
    for task_id in sorted(bucket):
        entry = bucket[task_id]
        if len(entry.sources) == 1:
            tail = f"source surface {entry.sources[0]!r}"
        else:
            tail = f"source surfaces {', '.join(repr(src) for src in entry.sources)}"
        desc_clause = f"; description={entry.desc!r}" if entry.desc else ""
        signals.append(
            SurfaceSignal(
                family=entry.family,
                proposed_task_id=task_id,
                rationale=f"platform surface uncovered by bench ({tail}{desc_clause})",
            )
        )

    return SurfaceCoverageReport(
        signals=signals,
        covered_surface_ids=tuple(covered_surface_ids),
        skipped=tuple(skipped),
        notes=notes,
    )
