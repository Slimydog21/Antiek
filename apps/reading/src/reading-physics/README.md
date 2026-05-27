# reading-physics — the Physics of Reading, facet engine (SPR-02 → SPR-05)

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
| `facets/anchored-widgets.ts` | The **anchored-widgets facet** (SPR-04). `combineAnchoredWidgets` is the §5.2 de-overlap: group by `lane`, order by `weight` DESC then `id` ASC, emit lanes in fixed `LANE_ORDER` — a pure function of the widget set (no geometry). `resolveAnchoredWidgets`/`enactWidgetLayout` resolve each anchor via the layout-map and stack same-lane vertical overlaps; a null-resolving widget consumes no slot. |
| `layout-map.ts` | The **layout-map service** (SPR-04; PR-4/PR-5). `createLayoutMap(base, transforms)` returns a queryable `resolve(anchor) → Rect \| null` that folds a sorted `SpatialTransform[]` pipeline (empty until SPR-05) over surface-measured `BaseGeometry`. The **one** place `getBoundingClientRect` is called; augmentations never measure pixels. This is the single seam SPR-05's spatial transform drops into. |
| `anchors.ts` | Shared semantic-anchor constructors (e.g. `synthesisHeaderAnchor()` / `SYNTHESIS_HEADER_CLAIM_ID`) so widgets pin to the same substrate identity without importing one another. |
| `augmentations/servability.ts` | The §9.0 servability augmentation (re-homed SPR-02). Declares a verdict-class decoration per source. |
| `augmentations/ip-holder.ts` | The "whose work grounds this" IP-holder augmentation (re-homed SPR-03 M5). Declares an `attribution` payload per source with a known owner. **Composes** with servability through the facet — neither imports the other. |
| `augmentations/skim.ts` | **Skim** (SPR-06 M1) — rhetorical-role colors. Declares a colored-background decoration per claim by its coarse role (objective/method/result). Reads a substrate-derived `RhetoricalRoleView` (see below); writes nothing. **Composes** with SiteSee through the `decorations` facet — neither imports the other. |
| `augmentations/sitesee.ts` | **SiteSee** (SPR-06 M2) — citation tints + a hover card. Declares a tint decoration per cited source by its reading-history state, plus an `inline-end` hover-card anchored widget (via the surface-injected `SiteSeeHoverCard`). Reuses the §9.0 servability gate for the card metadata. **Composes** with Skim through the facets — neither imports the other. |

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

## Spatial transforms + the minimap (SPR-05)

SPR-05 fills the SPR-04 layout-map seam with the talk's signature reading
capability — a **spatial transform** (section collapse) — and proves the
what/where separation (PR-4 + PR-5) by adding a **minimap** that is a *second
render pass of the same facets*.

### ⚠️ Not yet live — wiring gap (read this first)

**The spatial-transform facet, the collapse controller, and the minimap are
complete and tested, but they CANNOT run live yet.** They are mounted NOWHERE on
the production reading surface. The reason is a single, identifiable gap:

- The reading surface (`apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx`)
  feeds **`EMPTY_LAYOUT_MAP`** into every render context (it imports it at the top
  and passes it at lines ~581/591/593). `EMPTY_LAYOUT_MAP.resolve` returns `null`
  for every anchor — the surface measures **no DOM geometry**. With no real
  `BaseGeometry`, `createLayoutMap` has nothing to fold a collapse pipeline over,
  so the collapse and the minimap have no positions to transform or project.
- **No sprint has built the surface's geometry-measurement pass** — the piece that
  would, in a `useLayoutEffect`, call `getBoundingClientRect()` per laid-out
  anchor, assemble an `anchorKey → Rect` map, and hand it to `baseGeometryFromMap`
  → `createLayoutMap` so the layout-map resolves **real** geometry. (Per PR-4/PR-5
  this pass is the **one** place `getBoundingClientRect` is called — inside the
  surface, never in an augmentation; the reading-physics CI guard forbids it
  anywhere under `augmentations/`/`facets/`.)

**Why this is correct, not a regression.** SPR-05's milestone is the
reading-physics-`/`-scoped capability: the transform math, the
widgets-follow-the-transform proof, the minimap-shares-the-facet proof, the
viewport-scoping perf mitigation — all proved against in-memory `BaseGeometry`
fixtures in `spatial-transform.test.ts`. Building the live DOM-geometry pass is a
**separate, cross-cutting surface integration** (it touches `MasterMdViewer`'s
render lifecycle and scroll handling), deliberately out of SPR-05's scope. So the
capability ships **dormant-but-on-the-real-engine**: it runs on the actual
layout-map seam, not a prototype, and flips on the moment the geometry pass exists.

**The exact next step (one cross-cutting integration).** Build the surface
geometry-measurement pass described above; then (1) wire the `⌘/Ctrl+scroll`
collapse gesture to mutate the ephemeral `CollapseState` and feed
`collapsePipelineFor(state)` into `createLayoutMap`/`createViewportScopedLayoutMap`,
and (2) mount `renderMinimap` as a second pass. That single integration unblocks
collapse, the minimap, **and** the not-yet-live `AccrualView` / `ChaseThread`
gutter widgets simultaneously (they all wait on the same real `BaseGeometry`; only
`QualityCue` is live today, and it renders without geometry because it pins to the
header). Filed in full at `docs/decisions/spr-05-geometry-pass-gap.md`.

| File | What it is |
|---|---|
| `facets/spatial-transform.ts` | Builds `SpatialTransform` instances (the frozen §6 shape) — `makeCollapseTransform({ id, order, range, mode:"collapse", targetHeight })` returns a pure `apply(anchor, rect) → rect \| null` that compresses a vertical band (above → unchanged, inside → compressed, below → shifted up, straddling → contiguous). `buildCollapsePipeline` maps specs to transforms; the **layout-map** owns the sort (ascending `order`, ties by `id`). |
| `augmentations/collapse.ts` | The **surface's collapse controller** (cmd+scroll). `CollapseState` is the **ephemeral PR-2-escape view-state** (immutable, reconstructible-from-nothing, never persisted). `collapsePipelineFor(state)` → the transform pipeline; `fingerprintPlan(...)` marks decorations inside a collapsed band for the compressed **fingerprint** (NOT dropped). |
| `minimap.tsx` | The **minimap** (a second render pass). `projectDecorationsToMinimap(resolved, minimapLayout)` re-projects the *exact* `ResolvedDecoration[]` the main view paints through a `minimapLayoutFrom(mainLayout, scale, width)` second layout-map — a second `RenderContext` with `pass:"minimap"`, **sharing the facet, not re-implementing it**. |
| `layout-map.ts` | (extended) `createViewportScopedLayoutMap(base, viewport, transforms)` — the **M5 perf mitigation**: an off-screen anchor resolves `null` (skips the pipeline fold), capping per-frame work to on-screen anchors. Same `resolve` seam → PR-5 intact. |

### The fragment-shader / vertex-shader model (defensibility)

The talk's metaphor, made literal here: a **spatial transform is the vertex
shader** — it moves *where* content appears (the geometry the layout-map
reports). **Decorations are the fragment shader** — they paint *what* appears
and **follow the moved geometry automatically**, because they only ever query the
layout-map's *final* rect, never a pre-transform pixel. The collapse moves the
vertices; the rhetorical/servability colors squeeze into a band and follow. No
augmentation learns the document was reshaped (PR-5). The load-bearing proof:
`spatial-transform.test.ts` collapses a band spanning a shipped widget's anchor
and asserts the widget lands at its **post-transform** position with **zero
changes to its code** — because every widget routes through the one layout-map
seam (PR-4).

### Collapse state is the allowed ephemeral PR-2 exception

Which sections are collapsed is genuinely **view-state, not reading data** — the
canon's one bounded PR-2 escape (view-only, reconstructible-from-nothing, holds
no authored datum). It lives in an immutable in-memory `CollapseState`, **never
persisted** (no `localStorage`, no event-log write); a reload starts fully
expanded. The `// PR-2 escape:` rationale comment sits on the state declaration
in `augmentations/collapse.ts` so the boundary lint's audit trail records it.

### OQ2 resolution — spatial transforms are SURFACE-DECLARED ONLY

The canon's §9 open question 2 (owned by SPR-05) asked whether spatial transforms
are surface-reserved or augmentation-declarable. **SPR-05 resolves it the safe
way: surface-declared only.** A `ReadingAugmentation` never calls
`registry.declareSpatialTransform` — the surface (which owns geometry + the
collapse view-state) constructs the pipeline and hands it to `createLayoutMap`.
This sidesteps the cross-augmentation ordering conflict OQ2 names (two
augmentations declaring conflicting transforms at the same `order`). The frozen
`declareSpatialTransform` sink stays in `FacetRegistry` (no canon change); the
surface is its only caller. SPR-08's agent authors decorations/widgets — which
*follow* transforms for free — not transforms.

### Performance — the measured recompute number + the viewport-scoping decision (M5)

Measured (`spatial-transform.test.ts`, perf block, logged each run — the number
is machine-dependent and varies with runtime warmth, so we state the
load-bearing FACT, not a precise figure):

- **Full-document recompute under collapse takes tens of ms on a worst-case
  full-document fold** (2,000 decorated anchors × 20 collapsed sections = 40,000
  `apply` calls) — **over one frame budget (16.67 ms)**. That is the load-bearing
  fact: resolving the *whole* document every frame WOULD jank the main scroll.
  (The measured figure swings with machine + JIT warmth — the test's own comment
  records ~50–60 ms cold; a warm re-run can be a few ms — which is exactly why we
  do not assert a frame budget on the unscoped path and do not pin a number here.)
- **A single resolve through 20 collapses is sub-microsecond-to-a-few-µs** — the
  per-anchor pipeline fold is trivially cheap; the cost was purely doing it
  2,000× per frame.
- **Decision: VIEWPORT-SCOPE the recompute** (per the sprint manual: "if it janks
  … scope to the viewport and re-measure; do not ship a janky scroll silently").
  `createViewportScopedLayoutMap` resolves only on-screen anchors.
- **Viewport-scoped recompute is comfortably within one frame budget** (~30/2,000
  anchors on-screen) — the asserted gate (`< FRAME_BUDGET_MS × 2`, with CI
  headroom). This is the path the surface ships. Proven behavior-preserving: an
  in-band anchor resolves the identical post-transform rect as the unscoped map.

## Two augmentations that compose — Skim + SiteSee (SPR-06)

SPR-06 is the **headline composability proof on new ideas**: two augmentations
from two unrelated talk demos — **Skim** (rhetorical-role colors) and **SiteSee**
(citation tints + a hover card) — ship as **two independent augmentations that
compose on one synthesis** through the SPR-03/04 facets, **neither importing the
other**, both grounded in the substrate. The composition is the deliverable, not
the two features — proven in `skim-sitesee.compose.test.ts` (both sets of
decorations present + merged, the hover card on the anchored-widgets facet, the
overlap of a cited "result" sentence resolving deterministically, and the PR-3
no-cross-import assertion).

Why two modules and not one combined "annotations" augmentation (the steelman):
a combined module is fewer files, but it proves **nothing** about the physics —
the whole thesis is that two *independent* authors' ideas compose without
coupling. A combined module can't be split later and demonstrates no
`O(facets)`-not-`O(N²)` property (canon §4). Two modules is the cost of the proof
that matters.

### Skim's rhetorical-role taxonomy + where the role comes from (M1 + the open question)

The sprint's open question, resolved in diligence: **`ParsedClaim` /
`thesis_components` (synthesisParser.ts) carry NO explicit rhetorical-role
field** — only `{ index, claim, rationale, confidence, effectiveSourceTier,
hedgingRequired, chunkIds, supportingPathIndices }`. So Skim must **derive** the
role. Per canon PR-2 + the sprint manual there are two paths:

- **(a) derive a coarse role from the synthesis STRUCTURE** (a claim's position /
  section / the chunk's `section_path`), or
- **(b) run a classifier and write its output to the SUBSTRATE as an event** —
  never a private store (that violates PR-2, breaks composition, trips the guard).

**RESOLUTION: path (a), STRUCTURE — chosen, shipped.** No classifier, no event
write. The taxonomy is four **coarse** roles:

| Role | className (the WHAT) | When |
|---|---|---|
| `objective` | `skim--objective` (→ green) | a goal/aim/research-question claim |
| `method` | `skim--method` (→ blue) | a how/approach/procedure claim |
| `result` | `skim--result` (→ orange) | a finding/outcome/result claim |
| `other` | **none** (no color) | role not determined by the structure |

The **surface** resolves a coarse `RhetoricalRoleView { claimId, role }` per
claim from substrate-derived structure (the synthesis section the claim sits in
+ the chunk's `section_path`) and hands it to Skim; Skim only **declares** a
color per role. This keeps Skim contract-only (imports ONLY `../types`), pure
(PR-1), and makes the no-data state honest: **a claim whose role is `other` (or
absent) declares nothing — no guessed color (M5)**. Path (b)'s classifier-event
is the **documented fallback** if a future synthesis genuinely needs
per-*sentence* roles that structure can't give: the classifier would emit a
typed event through the one shipped write funnel (PR-6) and Skim would read the
resolved role exactly as it reads the structural one — **never a private store**.
It is **not needed** for the coarse claim-level signal this sprint ships, and a
coarse honest role that composes beats a precise one that doesn't (manual). No
classifier accuracy is reported because **no classifier was built** — the role
is a deterministic read of structure, not a probabilistic guess.

### Where SiteSee's read/cited history lives in the substrate (M4)

SiteSee tints a citation marker by the reader's **history** with that source,
read from the **substrate event log** (`api.ts`: the typed event log,
`TypedEventEnvelope` / `getTrajectory`). The taxonomy + their sources:

| State | className | Substrate source |
|---|---|---|
| `cited` | `sitesee--cited` | already substrate-derived — a claim cites chunks (`supporting_chunk_ids` on `synthesize.delivered`; `cited_chunk_ids` on an authored section). |
| `saved` | `sitesee--saved` | a promoted/saved source (the `saved`/`saved_and_promoted` status on a section update). |
| `read` | `sitesee--read` | a **`source.read`** typed event — **new this sprint** (see below). |
| `unseen` | **none** (no tint) | the honest default — no history ⇒ **tints nothing (M5)**. |

The `cited` and `saved` signals already exist in the substrate. A **per-source
"READ"** signal (the reader opened this source) **did not exist as a
first-class event**. SiteSee does **NOT** invent a private store for it (PR-2 —
that would break composition + trip the guard). The decision: **the SURFACE
emits a `source.read` typed event** through the ONE shipped write funnel
(`postTypedEvent` → `POST /events/typed` → `runtime/db_lock`, the single-writer
invariant — PR-6) when a reader opens a source, and resolves the per-source
history back **from the event log** into the `SiteSeeSourceView` it hands the
augmentation. **The augmentation only READS the resolved state; it opens no
writer and emits no event itself.** (The event *emission* is a surface
integration — the same shape as the SPR-05 geometry-pass gap: the augmentation
ships dormant-correct against the resolved view, and lights up fully the moment
the surface wires the `source.read` emit + the event-log history resolution.
This is the one net-new substrate signal the sprint allows; everything else is
read from existing events.)

### §9.0 — the hover card shows only bounded metadata (reused, not re-implemented)

SiteSee's hover card **reuses the §9.0 servability gate exactly as the shipped
`SourceCitation` does** (PR-6 — never recomputed). The surface resolves each
cited source's `servable` verdict + (only when servable) its `ip_holder_name`
from `getChunk`; SiteSee passes the verdict THROUGH to the card and, for a
**non-servable** source, supplies **ONLY the title** — never the owner (the
endpoint already withheld it with the body) and — structurally — **never any
body** (the `SiteSeeHoverCard` prop shape has no body field, so it is impossible
to leak one). Proven in `skim-sitesee.compose.test.ts` (§9.0 block): a
deliberately-populated owner on a non-servable source is **dropped** by the
augmentation and never appears in the rendered card.

### The overlap case — a cited "result" sentence (rigor #3)

The load-bearing composition edge: a claim that is BOTH a Skim **`result`** AND a
SiteSee **`cited`** source — both decorate the **exact same claim range**. The
`decorations` facet's §5.1 rule is **range union, order-independent**: the
resolved decoration carries **both** classes (`skim--result` + `sitesee--cited`),
sorted, as a single resolved range — deterministic regardless of which
augmentation was enabled first. There is **no winner-takes-all**; within the
facet both classes paint, and cross-facet visual stacking (if it ever mattered)
is a z-order the surface owns, never a function of declaration order.

## Byte-equivalence baseline (still enforced)

The pre-SPR-02 `SourceCitation` render is pinned by `MasterMdViewer.test.tsx`
("byte-equivalence of the re-homed §9.0 render"). SPR-03's generalization +
the IP-holder re-home keep it **byte-identical** (the IP-holder name now flows
through the facet's `attribution` payload instead of an inline string, with the
same rendered "published by …"). Any diff is a regression — do not adjust the
baseline.
