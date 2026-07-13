# Write-to-reader trace transport

Status: executable decision for Write SPR-07 / Read SPR-03

## Problem

Write resolves a citation to a servable document and ordered `chunk_ids`, then
throws away the chunk identity and opens `/read/{document_id}` at whichever page
the reader last stored. The reader receives one flat served body and explicitly
uses a null representative chunk, so it cannot reconstruct the intended source
from the document id alone.

The existing chunk metadata supports an exact page only when
`chunks.section_path` is literally `Page N`. It does not contain canonical
character offsets inside the served body. Calling that an exact span would be
false precision.

## Decision

Land a truthful two-level transport contract:

1. Write opens a servable trace with a single primary `chunk` query parameter
   and an optional closed `return_write` deliverable id.
2. A book-owned metadata endpoint verifies that the chunk belongs to the
   requested document and that the same full-text serve gate permits the body.
   It returns a page index only through the existing
   `page_index_from_section_path` authority.
3. Read matches the resolved page number against the actual page markers in the
   served body, then jumps through its existing `setPageIndex` path. It never
   clamps evidence locators: an absent page is unresolved rather than silently
   redirected to the nearest page.
4. `return_write` can navigate only to `/write/{encoded-id}`. It is not a free
   URL and cannot become an open redirect.

The first `chunk_ids` entry is the primary anchor because provenance resolution
orders the node's own metadata chunk before edge-derived chunks. Secondary
chunks remain available in the trace response; this slice does not pretend one
reader viewport can highlight disjoint evidence simultaneously.

## Rights boundary

The anchor endpoint returns identifiers, resolution state, and page index only;
it never returns chunk text. It reuses the full-text serve guard and refuses an
anchor for gated or taken-down bodies. A manually constructed reader URL cannot
turn chunk metadata into a side door around servability.

## Required red proofs

- A servable chunk belonging to the document resolves `Page N` to `N - 1`.
- A chapter-shaped or null section path returns an honest unresolved result.
- A chunk belonging to another document is not accepted.
- A gated or taken-down document returns no page anchor or body text.
- Write preserves the primary chunk and closed return deliverable in navigation.
- Write with no chunk still opens the document root.
- Read uses the existing pager to land on a resolved page after body load.
- A backend-resolved page absent from the served body is not clamped or labeled
  as the cited page.
- An unresolved or missing anchor leaves the current/root page unchanged and
  displays an honest message.
- The return action can construct only the local Write route.

## Deferred exact-span contract

Exact in-page highlighting requires ingestion to persist a canonical manifest
mapping each `chunk_id` to offsets in the exact HTML/text projection served to
the reader. The manifest must be versioned by body digest so re-extraction
cannot silently move an old anchor. A future sprint should specify that schema,
projection-version migration, overlapping chunks, and DOM-range rendering.
Until then this feature is named chunk-to-page trace, never exact-span trace.
