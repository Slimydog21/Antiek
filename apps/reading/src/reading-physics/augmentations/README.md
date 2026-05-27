# reading-physics/augmentations — where augmentations live

Every reading augmentation is a `ReadingAugmentation` (see `../types.ts`): a
stable `id` plus a pure `contribute(ctx, registry)` that **declares** into named
facets and returns nothing. Drop a new augmentation module here; the surface
runs it once per render pass and combines its declarations with every other
enabled augmentation's (the seed of the SPR-08 authoring kit — full contract in
`../README.md`).

## The boundary this directory is held to (CI-guarded)

`tools/lint/reading_physics_check.py` scans **every module in this directory**
(excluding `*.test.*` / `*.stories.*` / this README) and fails the build (under
ratified canon + `--enforce`) on:

- **PR-2** — a private store: `localStorage` / `sessionStorage` / `indexedDB`, a
  persistence/store client import, or a direct `fetch`/`axios`/`XHR`. Your data
  lives in the substrate, visible to every other augmentation. *(A bounded,
  view-only, derivable-from-substrate cache is allowed with a `// PR-2 escape:`
  comment on the line.)*
- **PR-1** — a DOM mutation (`innerHTML=`, `appendChild`, `classList.add`,
  `document.querySelector`, `createPortal`, …). You **declare**; the surface
  enacts.
- **PR-3** — importing **another augmentation** in this directory. Augmentations
  couple only through named facets, never by importing a sibling. (`../types.ts`,
  `../facet.ts`, `../facets/*`, and the substrate read API are fine.)
- **PR-4/PR-5** — measuring pixel geometry (`getBoundingClientRect`, `offset*`,
  `scrollTop`, `window.innerWidth`, `matchMedia`). Anchors are semantic; the
  layout-map owns pixels.
- **PR-6 (import half)** — importing a substrate **write** path. The physics
  reads; it never writes the substrate.

**What the guard cannot catch** (so don't rely on it to): dynamic `import()`, a
store hidden behind a shared util, a module-level mutable singleton, a write
through React context, and the PR-6 §7-5b *recompute* of a substrate verdict.
Those are review-owned (canon §7 & §9). See `../README.md` for the full honest
scope.

## The two shipped augmentations (worked examples)

- `servability.ts` — declares the §9.0 verdict class per source.
- `ip-holder.ts` — declares the "published by …" owner per source.

They decorate the **same** source range and the facet merges them — the first
two-augmentation composition (`../composition.test.ts`). Neither imports the
other. Read them before authoring a third.
