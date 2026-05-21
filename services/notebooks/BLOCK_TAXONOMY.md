# Notebook Block Taxonomy (SPR-08)

**Owner:** `services/notebooks/`
**Surface:** `/wrestle/<document_id>/notebook` (per-document, single-user)
**Status:** Sprint 18 Wedge 2 recast, ratified 2026-05-21.

This document is the closed set of block types that may appear in a
per-document notebook, the Tier-1 behavior-event types each block is
sourced from, and the rationale for the no-authoring decision.

A future maintainer reopening the "+ new block" question should read
the **Why no `+ new block`** section before proposing the inverse.

---

## Block types (closed set)

The notebook is rendered by TipTap; each block type below maps to a
TipTap node-view component in
`apps/reading/src/modes/Notebook/blocks/`.

| Block type         | Source event type(s)                          | Renderer                       |
| ------------------ | --------------------------------------------- | ------------------------------ |
| `highlight_card`   | `highlight_created`                           | `HighlightCard.tsx`            |
| `voice_block`      | `voice_note_recorded`                         | `VoiceBlock.tsx`               |
| `ai_qa`            | `ai_response_accepted` (state.prompt_id pairs the prompt) | `AiQa.tsx`         |
| `cite_link`        | `cite_jump`                                   | `CiteLink.tsx`                 |
| `cross_doc_jump`   | `cross_doc_link_clicked`                      | `CrossDocJump.tsx`             |
| `prose`            | **none — operator-editable only**             | `Prose.tsx`                    |

`prose` is the editable-text node that wraps every other block (the
operator may refine framing around an auto-populated card). The
substrate emits `prose` only as the container for an existing block;
there is no path by which the user creates a standalone `prose` block
from nothing. See "Why no `+ new block`" below.

### Closed-set discipline

Adding a block type later requires a schema migration AND a bump of
`BLOCK_TAXONOMY_VERSION`. The auto-populator refuses unknown block
types; the API refuses payloads naming a type outside this set.

The cost of the discipline is one migration per added type; the cost
of NOT being disciplined is policy-level garbage data in the Tier-2
reward join. Same argument as the behavior taxonomy
(`substrate/behavior/taxonomy.py`).

---

## Event → block mapping (canonical)

The auto-populator (`services/notebooks/auto_populate.py`) walks the
Tier-1 event stream scoped to one `document_id` and emits / upserts
blocks. The mapping is one-event-to-one-block by default, with two
documented merge rules:

1. **Highlight edit merges into the same card.** A new
   `highlight_created` event whose action's `highlight_id` matches an
   existing block's `source_event_ids` updates the existing
   `highlight_card` in place rather than creating a duplicate. Detected
   by content-equality on `(highlight_id, document_id)`.

2. **AI Q&A pairs.** An `ai_response_accepted` event is the source of
   record for the `ai_qa` block; the `prompt_id` in its `state` is the
   foreign key into the matching `ai_prompt_sent` event the
   auto-populator joins for the question text. If the prompt event is
   missing (out-of-order delivery), the block stores the response
   alone and stamps `prompt_missing: true` so a later run can fill the
   gap when the prompt event arrives.

Events not in the table above are SKIPPED, not erroneous. The
populator logs a debug breadcrumb per unknown type so the operator can
notice a missing mapping; `document_opened` / `document_closed` are
intentionally skipped — they bookend the per-doc span but don't merit
a block.

### Block storage shape

Every block row carries:

- `block_id` (TEXT PK)
- `notebook_id` (FK)
- `block_type` (one of the closed set above)
- `source_event_ids` (TEXT[] — at least one entry; populated by the
  auto-populator)
- `content_json` (TEXT, JSON-encoded — TipTap document fragment)
- `position` (DOUBLE — fractional ordering; reorder rewrites this)
- `demoted_at` (TIMESTAMP, nullable)
- `edited_at` (TIMESTAMP, nullable; bumped on operator edit)
- `created_at` (TIMESTAMP, autopopulated)

`source_event_ids` is the load-bearing column for the reward join
documented in `substrate/behavior/REWARD_PROXY.md` §Worker 2.

---

## Why no `+ new block`

### The decision

The per-document notebook offers NO "+ new block" affordance. Blocks
are created exclusively by the auto-populator from Tier-1 events on
the document. Block CONTENT is editable (the operator can refine
framing) but the block ITSELF cannot be conjured from nothing.

### Steelman of the alternative

A reasonable operator will say: *"some thoughts have no event trace —
a passing intuition, a stray reading note, a footnote about a
methodology I want to revisit. Forcing every block to come from an
event filters out organic thought."*

This argument is **real**. Researchers do have ungrounded thoughts and
the notebook is the natural place to capture them.

### Why the verdict still holds

1. **Tier-1 events are the truth-bearing primitive.** The reading
   surface (SPR-04+) already emits a closed taxonomy of events; if the
   operator's thought matters enough to record, it should hit one of
   those event types (highlight, voice note, AI Q&A). An ungrounded
   thought that has nowhere to land in the event taxonomy is a signal
   the taxonomy needs an entry, not that the notebook needs free-text
   authoring.

2. **Authored blocks would conflate trace with annotation.** The
   reward proxy worker `reward_medium` joins behavior events to
   notebook blocks on `(user_id, document_id)`. A free-text block with
   no `source_event_id` either has to be excluded from the join (then
   it's not "real" notebook content for RL purposes) or stamped with a
   synthetic event id (then we've corrupted the event store).

3. **Prose IS editable; framing is preserved.** M4 ships a TipTap-
   editable text affordance on every block, so the operator can
   contextualise an auto-populated card with as much prose as they
   want. The constraint is only that the block has at least one
   `source_event_id`. The operator who wants to write three paragraphs
   about a highlight can do so — the paragraphs hang off the
   `highlight_card`.

4. **An empty notebook is a true signal.** An operator who has done no
   work on a document sees an empty notebook. That is correct. Adding
   a "+ new block" affordance lets the operator fill it with
   synthetic content that looks like work, polluting the reward
   signal. See rigor card #1 in the sprint HTML.

### When this verdict reopens

If dogfood shows that operators (a) repeatedly leave the notebook
empty despite doing relevant reading, and (b) emit a measurable amount
of voice notes or AI Q&A pairs that are *about* the document but
flagged in the system as orphans (no `document_id` resolves), then the
verdict reopens. The fix at that point is to grow the event taxonomy,
not to add free-text authoring.

A future maintainer who wants to reopen this MUST:

- Document the dogfood data showing the gap.
- Propose the new event type(s) that would fill the gap before
  proposing the "+ new block" affordance.
- Bump `BLOCK_TAXONOMY_VERSION`.

---

## Versioning

`BLOCK_TAXONOMY_VERSION = 1` (see `services/notebooks/blocks.py`).

Bumping the version requires a schema migration if new columns are
introduced, and an entry in this document explaining the change. The
version is stamped on every saved notebook (`notebook_documents.format_version`)
so downstream renderers can branch on it.

---

## Lineage

- Originated in master-product-spec.md:557-566 (Sprint 18 Wedge 2, the
  PostHog notebook surface).
- Recast on 2026-05-21 to drop authoring + tighten to per-document
  (sprint HTML at `specs/wrestle-evolution/sprint-08-per-doc-notebook-recast.html`).
- Block types pruned from the original wider set (region embed,
  claim card, master_md_section, image, latex, etc.) — those are
  candidates for later sprints; the six in the table above are the
  minimum surface for SPR-08.
