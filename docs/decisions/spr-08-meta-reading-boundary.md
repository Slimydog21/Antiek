# Meta-reading boundary — PROPOSED resolution, operator sign-off PENDING

**Date:** 2026-05-28
**Branch:** `caffen/lr-spr08`
**Source spec:** Read SPR-08 (talk-to-book + meta-reading + audiobook/TTS), M4
**Status:** ⚠️ **PROPOSED — operator sign-off PENDING.** This is NOT a ratified
boundary. The meta-reading deliverable is built to the operator's PROPOSED
resolution behind a visible "proposed (sign-off pending)" banner, kept
reversible to a soft corpus scope.

## The question

"Meta-reading" is the feature: *"deep-research my owned corpus → make me an
asset (X pages / X minutes)."* The open boundary is **where it lives**: it
looks like Research (a deep-research over many sources) but the operator's
framing is *"learn from / make an asset of MY corpus while reading."* Research
and Read are lenses over **one graph** (no second silo); the question is which
lens owns this, because that decides intent, scope, and what the deliverable
*is*.

This is recorded OPEN in `docs/roadmap/ROADMAP.html` (the FLUID open-questions
register). The roadmap entry is a minimal OPEN pointer; **this doc is the
record.**

## The PROPOSED resolution (build to this; it is NOT ratified)

Keep meta-reading in **Read, not Research.** The boundary splits by **intent +
corpus scope**, made concrete as four properties:

1. **Owned-corpus-only, internet-agnostic.** Retrieval is *exclusively*
   `substrate.graph.search.search` over a bounded set of owned document ids
   (`document_ids=...`) — the owned DuckDB graph. There is **no acquisition /
   Exa / Browserbase / open-web call** anywhere on this path. *If it touched
   the internet it would be Research, not Read* — that is the line. (Verified
   by tracing the code path: `substrate/books/meta_reading.py` →
   `generate_meta_reading` → `search(document_ids=...)`; the only model call is
   the synthesis dispatch, not a retrieval crawl. A pytest asserts the
   synthesis' `corpus_document_ids` are exactly the owned set and that a
   restricted/foreign doc never enters context.)

2. **Hard length-box (X pages / X minutes).** Built to size up front via a word
   budget, **not** post-hoc trimmed. If the synthesis cannot fit, it is labelled
   `truncated`. Degenerate sizes (0 / negative / above the cap) are **rejected
   with a stated bound**, never silently clamped.

3. **One-shot READ-ONLY cited report.** Not an editable living document. It is
   generated once, saved as a re-openable Read asset, and its citations open the
   SPR-07 in-book reader (a chunk's `section_path` → reader page via
   `page_anchor.page_index_from_section_path`; **approximate** when it does not
   resolve to a `Page N` marker — the UI says so, never a fabricated page).

4. **Promote-into-Research is suggest-only.** The asset offers to promote into a
   related Research investigation **on explicit user action** — never auto. It
   reuses the EXISTING `seam.read_to_research` typed event (a `document_region`
   handoff that names the launched investigation), so promotion is **not a new
   silo** and the one-graph invariant is untouched.

### The length-box mappings (operator decision 3 — documented, not magic)

- **minutes → words: `X × 150`.** 150 wpm is the SPR-14 narration pace
  (`apps/reading/src/api/tts.ts` `NARRATION_WPM`); an "X minutes" asset is built
  to ~X×150 words so its narration lands near X minutes. The python side mirrors
  the constant (`substrate/books/meta_reading.py` `NARRATION_WPM = 150`) — the
  two MUST stay equal.
- **pages → words: `X × 300`.** 300 words/page is the dense end of the
  manuscript convention (a double-spaced page ≈ 250–300 words). A readability
  choice, stated so a maintainer can re-pick it — not a derived constant.
- **Bounds (stated, not silent):** pages 1–60, minutes 1–120. The minutes
  ceiling matches the TTS `MAX_NARRATION_MINUTES` so the two length-boxes agree.

## Why Read, not Research (the verdict — fairness, rigor #2)

**Steelman of folding it INTO Research:** meta-reading is, mechanically, a
deep-research over many sources — it decomposes a prompt, retrieves across a
corpus, and synthesizes a cited report. Research already owns decomposition, the
cascade, and synthesis; building a parallel synthesis path in Read risks two
codebases for "retrieve + synthesize + cite," and a maintainer could reasonably
say "this IS Research, scoped." The honest pull toward Research is real.

**What tipped it to Read:** the operator's framing — *"learn from / make an
asset of MY corpus while reading"* — is an intent and a scope, not a research
question about the world. The boundary that makes the two coherent is
**corpus scope + internet-agnosticism**: Research reaches the open world; Read's
meta-reading is bounded to what you already own and never crawls. The
deliverable shape follows from intent: Research produces a live, steerable
investigation; Read's meta-reading produces a *finished, re-openable reading
asset* you narrate and shelve. Those are genuinely different objects.

**The hedge that lets either future win:** the promote-into-Research link is
**suggest-only**. If the operator later decides this belongs in Research, the
suggestion is already the bridge — nothing has to be torn out, the asset just
flows into Research on the path that already exists. We did not bet the
architecture on the boundary being right; we built it reversible.

## Why this does NOT reuse the DRW cascade (the operative reason)

The SPR-08 spec's M4 asked the corpus-research to **reuse the DRW cascade
scoped to owned docs, not a re-implementation** (an acceptance criterion + an
out-of-scope line). This deliverable does **not** reuse the cascade, and that is
a deliberate, documented trade — recorded here so a maintainer can reconstruct
*why* the explicit criterion was traded rather than dodged.

The operative reason is that the cascade is **not functionally reusable for real
synthesis today**, independent of the boundary argument above:

- The cascade's prod factory loop is `make_contract_gather_stub`
  (`cascade_routes._research_loop_factory`) — an honest **gather placeholder**
  labeled `[gather-stub]` with **zero** calls to `substrate.graph.search`,
  dispatch/synthesis, or retrieval. `make_demo_loop` remains for benchmark MOCK
  and unit tests only. Reusing the cascade "scoped to owned docs" would still
  produce gather-only non-synthesis until Path A convergence (SPR-DRL-06).
- The only **real** retrieval loop on the roadmap is the unwired Exa→Browserbase
  **internet** loop (`interfaces/research/api/cascade_routes.py`, same factory
  seam) — i.e. an **open-web** path,
  which is exactly what an internet-agnostic owned-corpus feature must NOT use.
- No owned-corpus / `document_id` scope is threaded through the cascade's
  `Leaf` / `ResearchPlan` / `LoopContext`, so even the skeleton would need new
  plumbing before it could be scoped.

So the two ways to "reuse the cascade" today are: inherit a stub that synthesizes
nothing, or inherit an internet loop this feature is defined to forbid. Neither
satisfies M4. The honest way to meet the **outcome** criteria — a real cited
synthesis bounded to the owned corpus — is the direct
`search(document_ids=owned) + dispatch` path in `substrate/books/meta_reading.py`,
which is internet-agnostic by construction and verifiable by tracing the one
retrieval call. We traded the **process** criterion ("reuse the cascade") to keep
the **outcome** criteria (cited owned-corpus synthesis, internet-agnostic) honest
— not to cut scope.

**Reconsider-if:** when a *real* owned-corpus retrieval+synthesis loop is wired
into the cascade (so the cascade becomes a working engine that can be scoped to
owned docs without opening an internet path), migrate this synthesis onto it so
Read stays the *entry* and the cascade owns the *engine*. Until that loop exists,
the direct path is the only one that actually synthesizes.

## Reversibility (the rollback if sign-off is withheld)

The PROPOSED boundary is a HARD corpus boundary **at the planner** that is
**reversible**:

- The retrieval scope is a parameter, `corpus_scope ∈ {hard, soft}`. **Hard**
  (the proposed boundary) = owned servable docs, optionally an explicit pick.
  **Soft** (the rollback) = the whole owned readable corpus, no explicit-pick
  intersection. **Neither reaches the internet** — soft only *widens within the
  owned graph*.
- **If the operator withholds sign-off:** relax `corpus_scope` to `soft` and
  **drop the "proposed (sign-off pending)" banner**. That is the minimal,
  documented rollback. A fuller revert removes the route + `MetaReading/`
  surface entirely; the `read.meta_reading.generated` event stays in the schema
  (reserved), harmless.
- **What ratifies it:** the operator signing off on the Research↔Read split for
  owned-corpus synthesis.

## What SPR-08 built (and the discipline it kept)

- **Backend.** `POST /corpus/meta-reading` (`interfaces/research/api/books.py`)
  → `substrate/books/meta_reading.generate_meta_reading`. Retrieval is
  `search(document_ids=owned_set)` ONLY (internet-agnostic). The model call is
  the ONE Hermes-routed dispatch path (`substrate.dispatch.router.dispatch`,
  research tier choosing the provider — §16, no new runtime). The deliverable is
  persisted through the **single-writer typed-event funnel** as
  `read.meta_reading.generated` (schema v21) — substrate truth, re-openable; NOT
  a client side-store, NOT a new table/silo.
- **§9.0.** The synthesis is grounded on owned **servable** chunks; the
  retrieval gate (`search.py` `RESTRICTED_CONTENT_CLASSES`) excludes withheld
  content, so a withheld body never enters the report or a citation — enforced
  at retrieval, the SAME gate chunk-search uses.
- **Why an event, not sessionStorage.** The deliverable must survive reload, be
  re-opened / narrated / promoted — it is substrate truth. (The *running
  talk-to-book chat thread* is the opposite case: ephemeral session view-state,
  kept in `sessionStorage` per the `usePosition` precedent, NOT an event.)

## Reconsider-if

- "Soft" scope is what's actually used in practice (the hard boundary never
  bites) → drop the parameter, default to the owned corpus, and the
  Research↔Read line is purely intent-based.
- The promote-into-Research suggestion is accepted on nearly every asset → that
  is the signal the operator's instinct was Research after all; keep Read as the
  *entry* and move the synthesis into the cascade — **but only once the cascade
  has a real owned-corpus loop** (see "Why this does NOT reuse the DRW cascade":
  today its only loops are a demo stub and an unwired internet path, so there is
  nothing functional to fold into yet).
