# SPR-06 — the `source.read` substrate event (SiteSee "read" tint) — CLOSED in SPR-07

**Date:** 2026-05-27 (filed) · **2026-05-28 (CLOSED — SPR-07 M4)** ·
**2026-06-30 (chunk-anchor follow-up closed)**
**Branch:** `physics/spr-06` (worktree `antiek-physics-spr06`) → closed on `caffen/lr-spr07`
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-06 sprint + SPR-07 M4
**Status:** ✅ **CLOSED end-to-end for the book reader.** The net-new
`source.read` typed event is defined (`substrate/schemas/events.py`
`SourceReadPayload`, `SOURCE_READ`, EVENT_SCHEMA_VERSION bumped 19→20), emitted
from the reader on a justified dwell threshold through the single-writer funnel
(`apps/reading/src/modes/Reading/sourceRead.ts`), resolved back into
`CitationHistoryState`
(`apps/reading/src/modes/Reading/resolveCitationHistory.ts`), and now attributed
to a real book chunk anchor (`representative_chunk_id`) returned by
`/books/{document_id}/full-text` when the full body is served. The `cited`/`saved`
tints are unaffected.
**Owner:** ~~Read-surface instance + operator~~ — done (SPR-07).

### Chunk-anchor follow-up (closed 2026-06-30)

The SiteSee `read` tint keys on **`chunk_id`** (the resolver builds a
chunk→state map). The book reader now receives that anchor from the same backend
response that serves the full body: `FullTextResponse.representative_chunk_id`.
The handler selects the document's first chunk (`ORDER BY chunk_index, chunk_id`)
and returns it **only when `full_text` is served**; gated/taken-down books still
return `null`, so a withheld body does not expose a content anchor. The reader
uses that value for `emitSourceRead(...)` and selection provenance, so SiteSee's
read tint can light from the persisted event without inventing a client-side id.

## ✅ Closure (SPR-07 M4)

| Step | Where | Done |
|---|---|---|
| **Define** the `source.read` event | `substrate/schemas/events.py` (`SourceReadPayload`, `SOURCE_READ`; v20 bump; in the typed union + `TYPED_PAYLOAD_ACTION_TYPES` + `__all__`; codegen emit list; narrateEvent suppression row) | ✅ |
| **Emit** through the single-writer funnel | `apps/reading/src/modes/Reading/sourceRead.ts` (`emitSourceRead` → `postTypedEvent → /events/typed → runtime/db_lock`); wired in `modes/Reading/index.tsx` on the dwell threshold (once per source per session, coalesced) | ✅ |
| **Expose reader chunk anchor** | `interfaces/research/api/books.py` (`FullTextResponse.representative_chunk_id`, gated with full-body serve); consumed in `modes/Reading/index.tsx` | ✅ |
| **Resolve** into `CitationHistoryState` | `apps/reading/src/modes/Reading/resolveCitationHistory.ts` (`resolveCitationHistory` builds the chunk→state map; precedence cited ≻ saved ≻ read ≻ unseen) | ✅ |
| SiteSee maps the resolved view → tints | unchanged (`makeSiteSeeAugmentation`); proven lit by `resolveCitationHistory.test.ts` | ✅ |
| Tests | `tests/test_source_read_event.py` (pytest round-trip + no-body), `sourceRead.test.ts` (threshold + funnel + no body), `resolveCitationHistory.test.ts` (resolved `read` → read tint) | ✅ |

### "What counts as read" — the justified threshold (rigor #5)

A `read` verdict fires when **BOTH**: focused dwell ≥ **30 s** (`READ_DWELL_MS_THRESHOLD`)
**AND** the reader moved past the opening page (`READ_MIN_PAGES` ≥ **2**), measured
by the SAME focused-dwell clock the ad-impression tracker already runs
(`useReaderImpressions` — dwell accrues only while the tab is focused;
`visibilitychange` pauses it, so `read` inherits the "attention not while idle"
honesty). **Why 30 s + page 2:** it is the smallest signal that separates
"actually reading" from "opened and bounced" — well beyond an accidental open or
a metadata skim, well under the time to read even one short page closely. It is a
deliberately LOW bar: the tint says "you've been here", not "you finished it".
The event carries **NO body** (§9.0): only the chunk anchor + the dwell evidence
(`dwell_ms`, `page_count`) that justifies the verdict, so the verdict is
reconstructable from the event alone and a withheld body can never ride it
(structurally — there is no body field).

**Reconsider-if:** bump the threshold if the tint proves noisy (everything goes
green); split into "started"/"read" tiers if a single bar is too coarse; defer
the emit if read-tracking raises a privacy concern at the single-operator stage
(the `cited`/`saved` tints still work). It is a v1 tint signal — reversible (a
tint, not a gate), so it ships now and tunes later.

---

_Original gap record (pre-closure) follows._

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

- ✅ **DONE — the surface emits + resolves `source.read`** (SPR-07 M4; see the
  closure table at the top). This branch of the reconsider-if is the one that
  fired: the gap is closed, not deferred.
- A `read` signal turns out to already exist under another event name → checked
  during SPR-07 (grep clean: no prior `source.read`/`source_read`); a new event
  was the right call, no duplicate signal.
- Read-tracking raises a privacy/telemetry concern at the single-operator stage →
  did NOT fire (single-operator, the reader's own history; the event carries no
  body). If it later does, the emit can be disabled and the `cited`/`saved` tints
  keep working — see the top-section reconsider-if.
