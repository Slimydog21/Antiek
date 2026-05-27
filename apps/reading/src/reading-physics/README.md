# reading-physics — the Physics of Reading, facet engine (SPR-02 → SPR-03)

This module is Antiek's read-side **composition layer**, implementing
*A Physics of Reading* (`docs/philosophy/physics-of-reading.md`). An
augmentation never mutates the reading surface: it **declares** contributions
into named **facets**, and the surface combines all declarations and enacts the
result (the CodeMirror pattern). Augmentations compose for free because they
only ever touch facets the surface owns, never each other or the DOM.

SPR-02 proved the physics on ONE facet (`decorations`) with one re-homed
augmentation (§9.0 servability), byte-identical. **SPR-03 turns that seed into
the engine**: a generic facet runtime, a hardened decorations facet (range +
widget), the augmentation lifecycle, a CI guard that makes PR-2 binding, and the
first real **two-augmentation composition** (servability + IP-holder).

This is the contract a SPR-08 agent will author augmentations against — so it is
written to be **true of the actual code**, not aspirational.

## The facet API surface

| File | What it is |
|---|---|
| `types.ts` | The **frozen §6 facet-API signature** (types-only). `Decoration`, `Anchor`, `FacetRegistry`, `ReadingContext`, `ReadingAugmentation`, plus the future `AnchoredWidget` / `SpatialTransform` shapes. SPR-03 **additively widened** `Decoration` with `widget?` (M2) and `attribution?` (M5) — no field renamed/narrowed, so SPR-02 type-checks unchanged (§6 allows additive widening). |
| `facet.ts` | The **generic facet runtime** (M1): `Facet<TContribution, TResolved>` — a `name`, a z-order `priority`, and a pure, order-independent `combine(T[]) => R`. `defineFacet` constructs one; `assertDistinctPriorities` rejects a z-order collision. A facet is a **value (a combine rule)**, never a store. |
| `facets/decorations.ts` | The **decorations facet** (`decorationsFacet`, priority 0). `combineDecorations` is the §5.1 combine: group by stable semantic `anchorKey`, union classes (sorted), join the sorted title set by `" · "`, union the sorted widget set, union the sorted IP-holder-name set. Exposes `ResolvedDecoration`. |
| `registry.ts` | The **registry + lifecycle** (M1/M3). `CollectingRegistry` implements the frozen `FacetRegistry` sink, bucketing declarations by facet name. `collectDecorations(augs, ctx)` is the collect → combine half. `EnabledAugmentations` is the immutable enable set; `resolveEnabled` is the lifecycle-aware front door. |
| `augmentations/servability.ts` | The §9.0 servability augmentation (re-homed SPR-02). Declares a verdict-class decoration per source. |
| `augmentations/ip-holder.ts` | The "whose work grounds this" IP-holder augmentation (re-homed SPR-03 M5). Declares an `attribution` payload per source with a known owner. **Composes** with servability through the facet — neither imports the other. |

### The augmentation contract (what an agent implements)

```ts
interface ReadingAugmentation {
  readonly id: string;                                       // stable, for lifecycle + diagnostics
  contribute(ctx: ReadingContext, registry: FacetRegistry): void;  // PURE; returns nothing
}
```

`contribute` reads a **read-only** `ReadingContext` (the parsed synthesis, the
layout-map, the substrate **read** API) and pushes **declarations** into the
`FacetRegistry`. It returns nothing and mutates nothing. The surface runs it
once per render pass, combines every facet, and enacts.

### The combine rule, and why it is order-independent

`combineDecorations` groups declarations by a stable **semantic anchor key**
(`chunk:…` / `claim:…` / `passage:…` — never a pixel) and, per range, produces
the **sorted** union of class names, the **sorted** title set joined by `" · "`,
the **sorted** widget set, and the **sorted** IP-holder-name set. Because every
output is a pure function of the **set** of declarations, the result is
**independent of the order augmentations were enabled in** — the property
CodeMirror-style free composition rests on (canon §4, the `O(facets)` claim).
Proven in `composition.test.ts` (every permutation of three declarations is
deep-equal; forward/reverse enable orders are deep-equal).

### Overlap & z-order (M2)

- **Same-range overlap (within the decorations facet):** both decorations
  apply; classes/titles/widgets/owners union deterministically as above.
- **Cross-facet overlap (z-order):** when two *facets'* painted treatments
  visually overlap, the surface stacks them by ascending `Facet.priority` —
  higher paints on top. Priority is fixed by the **surface**, not by which
  augmentation declared first, so stacking stays order-independent. Decorations
  are the base layer (priority 0); SPR-04's gutter widgets will sit above.
  `assertDistinctPriorities` rejects a duplicate priority as an authoring error.

### Widget decorations (M2)

A `Decoration` may carry a `widget` — an affordance painted **alongside** its
range (the talk's quote-leap button). It is **data from a closed vocabulary**
(`{ kind: "quote-leap" | "preview" | "open-source"; label }`), never a render
callback: the augmentation declares *what* affordance; the surface owns *how* it
looks and behaves (PR-1). This is distinct from SPR-04's gutter-lane
`AnchoredWidget`; a decoration widget is inline with its range.

### Lifecycle (M3)

`EnabledAugmentations` is immutable: `enable`/`disable` return a new set.
Disabling an augmentation removes **exactly** its contributions with **no
residue** — because `contribute` is pure and the registry is rebuilt every pass
(no side store), "disable" is just "don't run it next pass." A stateful plugin
would leave residue; a declarative augmentation cannot. Proven in
`composition.test.ts` (disable ⇒ deep-equal to never-enabled).

## The PR invariants an augmentation must honor

| Invariant | What it requires of an augmentation |
|---|---|
| **PR-1 declare, don't act** | Never touch the DOM. Declare into a facet; the surface enacts. |
| **PR-2 no side store** | Data lives in the substrate, not a private store. A bounded view-only/ephemeral/derivable cache is allowed *with* a `// PR-2 escape:` comment. |
| **PR-3 named facets only** | Never import another augmentation. Couple only through facets. |
| **PR-4/PR-5 semantic anchors** | Anchor by chunk/claim/passage, never a measured pixel. The layout-map resolves geometry. |
| **PR-6 substrate is upstream** | Read substrate verdicts (`servable`, owner, rubric); never write the substrate, never recompute a verdict locally. |
| **PR-8 agent-authorable** | The whole contract is `types.ts` + the substrate read API — small enough to author from the contract alone. |

## What the CI guard enforces — and what it CANNOT

`tools/lint/reading_physics_check.py` (wired into `.github/workflows/ci.yml`'s
**tsc** job) statically scans the augmentations + facets directories.

**It catches** (each has a literal signature):
- **PR-2** — `localStorage`/`sessionStorage`/`indexedDB`; a persistence/store
  client import; a direct `fetch`/`axios`/`XHR`. (A `// PR-2 escape:` comment
  exempts the bounded cache.)
- **PR-1** — `innerHTML=`, `appendChild`/`insertBefore`/`removeChild`,
  `classList.add/remove/toggle`, `document.querySelector`/`getElementById`,
  `createPortal`.
- **PR-3** — importing a sibling augmentation (resolved relative or absolute).
- **PR-4/PR-5** — `getBoundingClientRect`, `offset*`, `scrollTop`,
  `window.innerWidth`, `matchMedia`.
- **PR-6 (import half)** — importing a substrate **write** path (`db_lock`,
  event-append/POST-mutation client).

**It CANNOT catch (review-owned — honest scope, canon §7 & §9):**
- **Dynamic import** (`await import(var)`) — no literal module string.
- **Indirection through a shared util** — a store hidden one hop away; the guard
  scans the file, not the transitive call graph.
- **A module-level mutable singleton** used as a store of record — no banned
  identifier.
- **A write through React context / a prop callback** — no banned token.
- **PR-6 §7-pattern-5b: substrate-verdict *recompute*** — re-deriving a
  servability verdict / rubric / attribution share is arbitrary arithmetic with
  no signature to match. **Advisory / review-owned.** (The import half is caught.)
- **PR-7 anti-purgatory** — "shipped to production, not a prototype reader?" is a
  product judgment. The guard emits an **advisory** grep only; it never blocks.

**Advisory ↔ blocking.** Blocking requires BOTH the canon front-matter
`status: ratified` AND the `--enforce` flag. While the canon is `draft` the
guard only warns (exit 0); after ratification, the first PR stays advisory and a
follow-up adds `--enforce` (the standing informational-then-blocking discipline).

## Byte-equivalence baseline (still enforced)

The pre-SPR-02 `SourceCitation` render is pinned by `MasterMdViewer.test.tsx`
("byte-equivalence of the re-homed §9.0 render"). SPR-03's generalization +
the IP-holder re-home keep it **byte-identical** (the IP-holder name now flows
through the facet's `attribution` payload instead of an inline string, with the
same rendered "published by …"). Any diff is a regression — do not adjust the
baseline.
