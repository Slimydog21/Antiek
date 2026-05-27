# SPR-06 — the `source.read` substrate event is not yet emitted (SiteSee "read" tint ships dormant)

**Date:** 2026-05-27
**Branch:** `physics/spr-06` (worktree `antiek-physics-spr06`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-06 sprint
**Status:** SPR-06 capability complete + tested; the `cited`/`saved` tints are
substrate-grounded and resolvable today; the **`read`** tint is **dormant** —
it depends on a net-new `source.read` event the surface does not yet emit.
**Owner:** Read-surface instance (whoever builds the surface read-tracking) +
operator (sequencing the integration).

## What was decided

SiteSee tints citation markers by the reader's history with each cited source —
`cited`, `saved`, `read`. Diligence found that `cited` (from a claim's
`supporting_chunk_ids` / `cited_chunk_ids`) and `saved` (section-update status)
are **already substrate-derived** and resolvable from the shipped data. A
per-source **`read`** signal did **not** exist as a first-class event.

The decision (per canon PR-2: augmentation data lives in the substrate, never a
side store): the SURFACE will emit a new typed **`source.read`** event through
the **one shipped funnel** (`postTypedEvent` → `/events/typed` →
`runtime/db_lock`, the single-writer path, PR-6), and SiteSee reads a resolved
`CitationHistoryState` view back from the event log. SiteSee itself opens no
writer and emits nothing — it only reads the resolved view (verified: no
persistence import; the CI guard is clean on `sitesee.ts`).

This doc files the net-new signal prominently so it is tracked where closure
gates live (`docs/decisions/`), not only in the feature README — the
verifier-critic flagged that the `read` tint is the one deferred piece most at
risk of "never lighting up."

## The gap, precisely

- `cited` / `saved`: resolvable from shipped substrate data **today**; SiteSee
  tints them correctly against the resolved `CitationHistoryState` view.
- `read`: there is **no `source.read` event** in the codebase (grep clean). Until
  the surface emits one when the reader opens/dwells on a cited source and
  resolves it back into the view, SiteSee's `read` state is always empty — the
  "you've read this" tint never appears. The augmentation is **dormant-correct**:
  it renders the `read` tint the moment the resolved view carries a `read` entry.

## Why this is separate from the SPR-05 geometry-pass gap (NOT subsumed)

The SPR-05 gap (`spr-05-geometry-pass-gap.md`) is a **read-time geometry
measurement pass** — one `useLayoutEffect` that lights up every layout-dependent
widget (collapse, minimap, AccrualView, ChaseThread) at once. SiteSee's hover
card rides that same geometry pass.

But the `source.read` signal is a **write-path emit** driven by a user gesture
(reading a source), not a read-time geometry computation. It does **not** light
up when the geometry pass is built; it needs its own surface integration: detect
the read, `postTypedEvent("source.read", …)` through the funnel, resolve history
from the log into the view. Two distinct integration points — recorded here so
neither is mistaken for the other.

## The exact next step

1. **Emit:** in the reading surface, when the reader opens / dwells on a cited
   source, call `postTypedEvent` with a `source.read` typed event (the single
   funnel → `/events/typed` → `runtime/db_lock`; single-writer, PR-6). No side
   store; no second writer.
2. **Resolve:** assemble the `CitationHistoryState` view for the synthesis by
   reading `read` (the new event) + `cited`/`saved` (already substrate-derived)
   from the log, and hand it to `makeSiteSeeAugmentation`.
3. SiteSee already maps the resolved view → tints; no augmentation change needed.

## Reconsider if

- The surface emits + resolves `source.read` (this gap closes) → mark superseded
  and record the wiring commit.
- A `read` signal turns out to already exist under another event name → point the
  resolver at it instead of emitting a new one (avoid a duplicate signal).
- Read-tracking raises a privacy/telemetry concern at the single-operator stage →
  defer the emit (the `cited`/`saved` tints still work; only the `read` tint
  waits), and record that call here.
