# reading-physics — the Physics of Reading, decorations slice (SPR-02)

This module is the **proving slice** of *A Physics of Reading*
(`docs/philosophy/physics-of-reading.md`). It implements **exactly one
facet — `decorations` — and nothing else.** Its whole job is to prove the
physics on real, shipped code: the §9.0 servability / IP-holder annotations
that were hand-wired into `MasterMdViewer`'s `SourceCitation` are now
re-expressed as a declared augmentation rendering into a minimal facet, with
a **byte-identical** render and zero regression.

## What this slice IS

- **`types.ts`** — the **frozen §6 facet-API signature**, transcribed verbatim
  (types-only, no runtime values). The whole signature is here so SPR-03+ import
  the real module as-is; the slice only *uses* the decorations path.
- **`facets/decorations.ts`** — the **combine rule** (§5.1): range union,
  deterministic, **order-independent**. Decorations are grouped by a stable
  semantic `anchorKey` (never a pixel — PR-4); per range the classes union
  (de-duplicated, **sorted**) and same-range titles join as the sorted set
  joined by `" · "`. **This file is the SEED SPR-03 generalizes** into the full
  facet engine + CI guard.
- **`registry.ts`** — the `FacetRegistry` sink (PR-1: declare, don't act).
  Only `declareDecoration` is enacted; `declareAnchoredWidget` /
  `declareSpatialTransform` are present (the frozen sink) but collect-only this
  sprint. `collectDecorations()` is the surface's collect → combine half; the
  surface owns enact (the single apply pass that paints).
- **`augmentations/servability.ts`** — the **re-homed §9.0 augmentation**. It
  *declares* one decoration per source, anchored to the source's representative
  chunk, carrying a closed-vocabulary verdict class (`servability--servable` /
  `servability--restricted`) + the matching tooltip. It **reads** the
  substrate's `servable` verdict (PR-6: never recomputes it) and declares
  nothing that could reveal a withheld body or owner.

## Why sort everywhere (the combine rule's reason)

The combine sorts by a stable anchor key and unions/sorts classes + titles so
the result is a pure function of the **set** of declarations — **independent of
the order augmentations are enabled in**. That order-independence is exactly
what gives CodeMirror-style free composition (§4, the `O(facets)` claim): two
augmentations never depend on each other's enable order, so the Nth augmentation
costs "declare into an existing facet," not "reason about the prior N−1."

## What this slice is NOT (SPR-03+)

- **No anchored-widgets, transaction-filters, spatial-transform, or
  multi-render facets** — those are SPR-04 / SPR-05 (and the Write/notes
  surface for transaction-filter). The frozen registry already accepts their
  declarations so those sprints add no new sink method.
- **No CI guard.** The augmentation-boundary lint (§7) is **SPR-03**. This slice
  only *respects* PR-1/PR-2/PR-6 (declare-don't-act; no side store; substrate
  verdict is upstream); it does not yet enforce them in CI.
- **No registry generalization beyond decorations.** That is precisely SPR-03's
  job; the slice deliberately resists it.
- **No new augmentation.** Re-homing one shipped behavior proves *equivalence*,
  which is what de-risks SPR-03; a new augmentation would prove only novelty.

## No side store (PR-2)

Nothing under `reading-physics/` persists anything of its own — no
`localStorage`, `indexedDB`, `sessionStorage`, or store of record. The registry
and the resolved decorations are reconstructed every render from the
augmentations + the substrate-derived source model (resolved via the shipped
`api.getChunk`). Losing them loses nothing. A `grep -rE
"localStorage|indexedDB|new Store|persist"` over this directory returns no match.

## OQ4 — the `ReadonlySynthesis` / `ResolvedSource` boundary

Canon §9 open question 4: the frozen `ReadonlySynthesis` is opaque-minimal and
carries no resolved sources, while the real shipped surface resolves a
`ResolvedSource` (servable + ipHolderName + a representative chunk id) from
`getChunk`. SPR-02 adapts the real resolved shape to the frozen decorations path
**at the surface boundary**: `MasterMdViewer` resolves the sources (as it
already did — PR-6: the substrate supplies `servable`), then hands a minimal
`ServabilitySourceView` (substrate-derived, invents nothing) to the
augmentation, which declares a `Decoration` per source anchored to the source's
representative chunk (`{kind:"chunk"}` — the closest semantic identity the
frozen `Anchor` vocabulary offers for "this source"). This is an **additive
adaptation, not a fork** of the frozen signature. Open for SPR-03+: whether the
frozen `ReadonlySynthesis` should be additively widened to carry resolved
sources directly (so a future source-level augmentation reads them off the
context rather than via a render-scoped factory).

## Byte-equivalence baseline (recorded for SPR-03)

The pre-slice `SourceCitation` render, pinned by
`MasterMdViewer.test.tsx` ("byte-equivalence of the re-homed §9.0 render"):

- **Servable** → `<button class="text-[11px] text-ink-soft dark:text-starlight
  bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 px-1.5 py-0.5 rounded
  transition-colors" title="Click to preview · ⌘-click to open the source">from
  <Title>, <locator>, published by <Owner></button>`
- **Restricted** → `<span class="text-[11px] text-ink-soft dark:text-starlight
  bg-ice-2 dark:bg-charcoal-1 px-1.5 py-0.5 rounded inline-flex items-center
  gap-1" title="This source isn’t available to open here (its license restricts
  it).">from <Title>, <locator><span class="text-[10px] text-shadow-1
  dark:text-moonlight">· not available to open</span></span>` — **no body, no
  owner** (§9.0 withholds both).

SPR-03's broader changes must keep this render byte-identical (re-prove against
the test above).
