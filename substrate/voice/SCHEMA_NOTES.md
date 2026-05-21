# voice_note_anchor — schema notes

Sprint SPR-02 (Wrestle Evolution Wave 1). Substrate-only. UI lands in
SPR-05.

These notes capture the design decisions that aren't obvious from
reading `anchor_schema.py` in isolation: the 30% overlap threshold,
the `chunker_version` source of truth, and the **geometry
prerequisite gap** discovered during this sprint.

---

## 1. The 30% bbox-overlap threshold

`anchor_api.MIN_CHUNK_OVERLAP_FRACTION = 0.30`. Below this, the
`chunk_id` for a newly-created anchor is `NULL`. At or above, the
chunk with the maximum overlap fraction wins.

### Why a threshold at all

Without a floor, a 1-pixel intersection between a tiny anchor and a
large page-spanning chunk would associate them — semantic retrieval
("voice notes for chunk X") would degrade into "voice notes anywhere
near chunk X". That's noise, not signal.

### Why 30%, not 50%

50% would be the "majority overlap" rule. In practice, an operator
who voice-anchors a 2-line excerpt on a page with 4-line chunks will
often produce an anchor whose intersection with the containing chunk
is well under 50% of the *anchor's* area (because the chunk extends
above and below the operator's selection):

- Anchor area: 2 lines × column width.
- Chunk that contains the anchor: 4 lines × column width.
- Intersection: 2 lines × column width = 100% of the anchor — wait,
  that's wrong only because we're measuring the denominator.

The **denominator** is the anchor's area (the operator's selection),
not the chunk's area. So:

- `overlap_fraction = intersection_area / anchor_area`.
- "What fraction of the operator's region is inside this chunk?"

With that denominator, the typical case is high (an anchor fully
inside a chunk is 100%). The threshold catches anchors that **straddle
a chunk boundary** — where the operator selected across two chunks
and we need a tiebreaker.

30% gives roughly: "the operator's region is at least one-third
inside this chunk before we associate them." Less than that and the
overlap is incidental — better to record `NULL` and let semantic
retrieval miss the anchor than to assert a misleading chunk_id.

### Why not 10%

At 10% we'd associate even glancing overlaps. A user circling a
margin note that bleeds into the body chunk by ~10% would silently
get tagged with the body chunk. That's worse than NULL because it
pollutes downstream training (the voice note is "about" the margin
content, not the body).

### What would reverse this choice

- **Evidence that operators routinely produce anchors that straddle
  chunk boundaries 40/60 between two chunks.** In that case 50%
  would orphan too many anchors (both candidates would be below
  threshold) and we'd want a lower floor.
- **A move to overlay-style anchors** (where the chunk is the
  selection unit, not a bbox) — then the threshold is irrelevant
  and we drop it entirely.

The threshold is a constant in `anchor_api.py`, not a column. Bumping
it requires the re-chunk worker to run on the whole table, which is
its job — so the threshold isn't pinned to historical writes.

---

## 2. The denominator chosen for overlap

`overlap_fraction = intersection_area / anchor_area`, NOT
`intersection_area / chunk_area` and NOT `intersection_area /
union_area` (Jaccard).

### Why anchor_area as denominator

The semantic question is **"how much of the operator's region is
inside this chunk?"** — the operator's selection is the unit of
interest. Chunks vary wildly in size; normalizing to chunk area
would mean a large chunk effectively never qualifies (a small
anchor inside a huge chunk would have a vanishing fraction).

### Why not Jaccard

Jaccard ($\frac{A \cap B}{A \cup B}$) is symmetric and penalizes
both directions, which is the right metric for "how similar are
these regions" but the wrong metric for "is the user's pick
inside this thing."

---

## 3. `chunker_version` source of truth

`substrate.voice.CHUNKER_VERSION` is a module-level string constant
in `substrate/voice/__init__.py`. It is the **single canonical**
source. The schema's `chunker_version` column records the value
that was live at anchor-write time; the re-chunk worker compares
each row against the live constant and re-resolves stale rows.

### Bump rules

Bump `CHUNKER_VERSION` when the chunker's behavior could alter
chunk identity for the same input:

- Regex change in `processing/chunking/chunker.py` (e.g., heading
  detection).
- `DEFAULT_MAX_CHUNK_TOKENS` change.
- Adding a new chunker mode (page-aware, etc.).

Do NOT bump for non-identity-affecting changes (logging,
refactoring without behavior change). A spurious bump triggers a
full table rewrite on the re-chunk worker — cheap but pointless.

### Why a string and not a hash

A semver-style string is comparable ("0.2.0 > 0.1.0"); a hash of
the chunker module is not, and would also flag every refactor as a
chunker upgrade.

### Why not a registry table

A single constant in code is the simplest form of source-of-truth.
A `chunker_versions` registry table would add a write path and a
synchronization problem (which version is "current"?). Defer until
we have multiple chunkers in flight simultaneously.

---

## 4. Geometry prerequisite gap (surfaced in this sprint)

The Antiek `chunks` table at v1 has columns:

```
chunk_id, document_id, chunk_index, section_path, text,
embedding, token_count
```

No `page`. No `bbox`. The chunker
(`processing/chunking/chunker.py:chunk_markdown`) operates on
markdown headings; it has no notion of PDF page geometry.

**Consequence**: `resolve_chunk_for_bbox` returns `None` for every
input on the current substrate. The dual-key design still works —
`(document_id, page, bbox)` is the canonical UI render key and
survives this gap — but the semantic-retrieval half of the dual
key is empty until chunks gain per-chunk page+bbox metadata.

### What's needed to close the gap

A future sprint that:

1. Adds `page` (INTEGER) and `bbox` (TEXT-JSON) columns to the
   `chunks` table.
2. Updates a PDF-aware chunker (likely under `processing/chunking/
   pdf_chunker.py`) to emit them.
3. Updates `_candidate_chunks_for_overlap` in `anchor_api.py` to
   `SELECT chunk_id, page, bbox FROM chunks WHERE document_id=? AND
   page=?` — that's a 5-line change.
4. Bumps `CHUNKER_VERSION` so the re-chunk worker picks up the new
   geometry on every existing anchor.

The overlap-math test in `tests/test_anchor_api.py`
(`test_resolve_chunk_overlap_argmax_with_stubbed_geometry`)
monkeypatches `_candidate_chunks_for_overlap` to inject fixture
chunks, so the math is exercised today and won't bit-rot before
the gap closes.

### Why we built the dual-key anyway

The diligence pass (rigor #4) was: read the chunker code, surface
the gap, *do not invent geometry*. Inventing bboxes by, e.g.,
guessing from chunk_index would produce confidently wrong data
that downstream retrieval would treat as ground truth. NULL is
honest; a fabricated bbox is not.

The schema itself is the right shape for the world where chunks
have geometry. Adding the column to the schema later would be a
migration; getting it right now keeps the contract stable for
SPR-05.

---

## 5. Voice-note storage shape (mismatch with sprint spec page)

The sprint HTML describes Sprint 13 as adding a `voice_notes`
table. The actual Sprint 13 storage (per
`acquisition/voice/adapter.py`) is **documents with
document_type='voice_note'**. There is no `voice_notes` table.

The schema reflects reality: `voice_note_id` references
`documents(document_id)`. The application layer filters on
`document_type='voice_note'` when iterating voice notes. The
migration prerequisite check looks for `documents`, not
`voice_notes`, and the error message is honest about why.

Flagged in the handoff packet (§Open questions discovered) so the
spec page can be updated.

---

## 6. Concurrency contract

Two simultaneous `create_anchor` calls for the same
`voice_note_id` must collide on the unique constraint. The
substrate's `UNIQUE` index on `voice_note_id` is the source of
truth; `create_anchor` does NOT do an application-layer "if
exists, skip". The flock in `runtime/db_lock.py` serializes the
two writers, the second writer's `INSERT` violates the unique
constraint, and DuckDB raises a `ConstraintException` (or a
`duckdb.Error` whose message mentions "unique" / "constraint" /
"duplicate" — exact class varies by DuckDB version).

`tests/test_anchor_api.py::test_concurrent_creates` exercises this
with two real `threading.Thread`s and a `threading.Barrier`. No
mocks — the rigor card requires it.
