# Authoring kit — write a composable reading augmentation

*The contract for SPR-08 (agent-authorable / PR-8). This is everything you need
to author a new reading augmentation that **composes** with every shipped one
and **passes the same gates** a hand-written augmentation passes. If you only
read one file, read this one — but read the worked examples in
`augmentations/` too, because they ARE the proof this kit is true.*

> **This kit is verified true against the real code**, not aspirational. Every
> signature below is quoted from `reading-physics/types.ts`; every gate maps to a
> named check in `tools/lint/reading_physics_check.py`. The frozen API is
> `docs/philosophy/physics-of-reading.md` §6 (transcribed verbatim into
> `types.ts`). Do not invent a new facet, do not import outside the allowlist,
> do not relax a gate — an augmentation that fails the guard is rejected.

---

## 0. TL;DR — the whole job in six lines

1. Copy `augmentations/_template.ts`, rename it `<your-idea>.ts`.
2. Implement the frozen `ReadingAugmentation`: a stable `id` + a pure
   `contribute(ctx, registry)` that returns nothing.
3. Read substrate-derived data at **declare time** (off `ctx`), CAPTURE it in a
   closure; **declare** into a facet via `registry.declareDecoration(...)` /
   `declareAnchoredWidget(...)` / `declareSpatialTransform(...)`.
4. Import **only** `../types` (and `react` if you build a widget view).
   Nothing else.
5. Never touch the DOM, never store anything, never import a sibling
   augmentation, never measure pixels.
6. Run the two gates (§7). Green ⇒ done.

---

## 1. The augmentation contract (the one shape you implement)

Quoted verbatim from `types.ts` (the `ReadingAugmentation` interface,
`types.ts:459-468`):

```ts
export interface ReadingAugmentation {
  /** Stable id, for diagnostics and multi-render reconciliation. */
  readonly id: string;
  /**
   * Declare this augmentation's contributions. Called by the surface, once
   * per render context (PR multi-render). MUST be pure w.r.t. (ctx, registry):
   * the same inputs always produce the same declarations.
   */
  contribute(ctx: ReadingContext, registry: FacetRegistry): void;
}
```

That is the **entire** shape. An augmentation reads a read-only `ReadingContext`,
emits declarations into a `FacetRegistry`, and **returns nothing / mutates
nothing**. The surface calls `contribute()` once per render pass, collects every
augmentation's declarations per facet, applies each facet's combine rule, and
enacts the composed result. You never paint; the surface does.

### The factory pattern (how every shipped augmentation is built)

The shipped augmentations are not bare singletons — they are **factories** that
close over render-scoped, substrate-derived data, then return a
`ReadingAugmentation`. Example, `servability.ts:94-116` (lightly elided):

```ts
export function makeServabilityAugmentation(
  sources: readonly ServabilitySourceView[],
): ReadingAugmentation {
  return {
    id: "servability",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      for (const source of sources) {
        const decoration: Decoration = {
          anchor: { kind: "chunk", chunkId: source.representativeChunkId as ChunkId },
          className: source.servable ? SERVABLE_CLASS : RESTRICTED_CLASS,
          title: source.servable ? SERVABLE_TITLE : RESTRICTED_TITLE,
        };
        registry.declareDecoration(decoration);
      }
    },
  };
}
```

Why a factory: the data is resolved per synthesis, per render. The augmentation
closes over THIS render's data — pure w.r.t. its inputs, no cache that survives
a reload (PR-2: losing the closure loses nothing; the next render re-resolves
from the substrate). `_template.ts` follows this pattern exactly.

---

## 2. ReadingContext vs RenderContext — the trap (read this twice)

> **This is the single most common way an augmentation fails.** SPR-04 hit it.
> They are two different types, used at two different times. Mixing them is a
> type error at best and a substrate read inside a render closure at worst.

### `ReadingContext` — the **declare-time** context (off `contribute`'s `ctx`)

Quoted from `types.ts:396-408`:

```ts
export interface ReadingContext {
  /** The synthesis being read, already parsed (substrate-derived, read-only). */
  readonly synthesis: ReadonlySynthesis;
  /** The read-time resolver (PR-5). */
  readonly layout: LayoutMap;
  /**
   * The substrate read API (PR-2): the ONLY way to pull more substrate data
   * (e.g. resolve a chunk → document title + §9.0 servability verdict). An
   * augmentation that imports any OTHER persistence client violates PR-2 and
   * SPR-03's guard flags it.
   */
  readonly substrate: SubstrateReadApi;
}
```

This is what `contribute(ctx, registry)` receives. **Read substrate data HERE**,
during `contribute`, and **capture it in a closure**. `ctx.synthesis` is the
parsed synthesis; `ctx.substrate` is the only door to more substrate data;
`ctx.layout` is the read-time geometry resolver.

### `RenderContext` — the **render-time** context (what a widget's `render` gets)

Quoted from `types.ts:118-142`:

```ts
export interface RenderContext {
  /** "main" is the primary reading column; others are secondary passes. */
  readonly pass: "main" | "minimap" | (string & {});
  readonly layout: LayoutMap;
  /** SPR-04 — the SURFACE-OWNED heavy-component map (PR-1 / PR-8). … */
  readonly components?: AnchoredWidgetComponents;
}
```

This is what an `AnchoredWidget.render(rect, ctx)` closure receives. **It has NO
`synthesis` and NO `substrate` field.** It carries only `pass`, `layout`, and the
optional surface-injected `components` map. A widget render closure must **not**
reach for substrate data — there is none on `RenderContext`, and there must not
be: the closure must already have captured everything it needs at declare time.

### The rule, stated plainly

> **Read substrate at declare time (`ReadingContext`), capture it in the closure,
> render from the closure (`RenderContext`).** The QualityCue augmentation does
> exactly this — `quality-cue.ts:194-206` reads the score at declare time (the
> factory param), captures it, and the `render(_rect, _ctx: RenderContext)` reads
> only the captured `score`, never a substrate field. If you find yourself
> wanting `ctx.substrate` inside a `render(...)`, you have the wrong `ctx` — you
> are looking at the render-time `RenderContext`, which deliberately omits it.

---

## 3. The registry — the sink you declare INTO

Quoted from `types.ts:384-388` (the frozen `FacetRegistry`):

```ts
export interface FacetRegistry {
  declareDecoration(d: Decoration): void;
  declareAnchoredWidget(w: AnchoredWidget): void;
  declareSpatialTransform(t: SpatialTransform): void;
}
```

These three `declare*` methods are the **entire** surface area you may touch.
Every method is "declare," never "act" (PR-1). You call them inside
`contribute`; the surface owns the combine + the enact.

> **Do not declare a `SpatialTransform` from an augmentation.** The canon (§9 OQ
> 2) holds spatial-transform as **surface-declared-only** until SPR-05 resolves
> the cross-augmentation ordering conflict. The method is on the frozen sink for
> completeness, but an augmentation that declares a transform is contributing to
> an unresolved facet — don't. Stick to decorations and anchored-widgets.

---

## 4. The two facets you'll use

### 4a. Decorations — a visual treatment on a semantic RANGE

Quoted from `types.ts:249-290` (the `Decoration` interface; the SPR-03 `widget`
and `attribution` fields are additive — you may use them or omit them):

```ts
export interface Decoration {
  /** What range receives the treatment. */
  readonly anchor: Anchor;
  /**
   * The class(es) the surface paints onto the resolved range. A closed
   * vocabulary the surface understands — NOT arbitrary CSS, NOT inline DOM,
   * so the combine stays order-independent (PR-1: declare, don't act).
   */
  readonly className: string;
  /** Optional title/aria text. … */
  readonly title?: string;
  /** Optional WIDGET affordance painted ALONGSIDE this range (SPR-03 M2). … */
  readonly widget?: WidgetDecorationSpec;
  /** Optional ATTRIBUTION payload (SPR-03 M5) — the "whose work grounds this"
   *  IP-holder name the surface paints inline. … */
  readonly attribution?: AttributionSpec;
}
```

- **`className` is a CLOSED VOCABULARY** the surface maps to its concrete paint —
  it is NOT raw CSS, NOT a style string. Pick a verdict word (`"skim--result"`,
  `"servability--restricted"`), export it as a constant, and let the surface own
  how it renders. Inventing arbitrary CSS or DOM is a PR-1 violation.
- **Combine rule (§5.1):** range UNION, deterministic, **order-independent**. Two
  decorations on the same range both apply; on overlap their class sets stack;
  when both carry a `title` the surface joins them sorted, `" · "`-separated. So
  your decoration composes with another augmentation's on the same range **for
  free** — neither knows the other exists (this is the Skim × SiteSee proof:
  `skim-sitesee.compose.test.ts`).
- `widget?` (a `WidgetDecorationSpec` — a closed `kind` + a `label`) is for an
  inline affordance painted *alongside* the range (e.g. a quote-leap button). It
  is **data, not a render callback** — the surface owns how it looks.
  `attribution?` (an `AttributionSpec` — `{ ipHolderName: string }`) is for the
  substrate-resolved owner name. Both are optional; omit if your idea doesn't
  need them.

**Worked example to copy:** `skim.ts` (claim-anchored colored backgrounds,
imports only `../types`) and `servability.ts` / `ip-holder.ts` (chunk-anchored,
the two-augmentation composition).

### 4b. Anchored widgets — a view pinned to a semantic anchor

Quoted from `types.ts:326-350` (the `AnchoredWidget` interface):

```ts
export interface AnchoredWidget {
  /** Stable id so multi-render (PR / multi-render) can reconcile passes. */
  readonly id: string;
  /** WHERE it pins (PR-4 semantic, resolved by layout-map at read time). */
  readonly anchor: Anchor;
  /** Which gutter/lane the widget lives in. … */
  readonly lane: WidgetLane;   // "left-gutter" | "right-gutter" | "inline-end"
  /** Tie-break weight for same-lane same-position collisions. … */
  readonly weight: number;
  /**
   * The render function. Receives the resolved rect (post-transform, PR-5) and
   * the context (PR multi-render). Returns a ReactNode — a VIEW, not a side
   * effect: … MUST be pure w.r.t. the context and MUST tolerate a null-resolving
   * anchor by rendering nothing (return null).
   */
  render(rect: Rect | null, ctx: RenderContext): ReactNode;
}
```

- `lane` (the named `WidgetLane` = `"left-gutter" | "right-gutter" | "inline-end"`,
  `types.ts:110`): widgets in **different lanes never collide**. Same-lane
  same-position widgets de-overlap by `weight` (higher = nearer the anchor; equal
  weights break by `id`, lexicographic). So placement is a pure function of
  `(lane, weight, id, resolved-rect)` — order-independent.
- `render(rect, ctx)`: `rect` is `Rect | null` (the layout-map may not have your
  anchor laid out — **you MUST tolerate `null` by returning `null`**). `ctx` is
  the **`RenderContext`** (§2 — no substrate field). Return a `ReactNode`; this is
  a VIEW, never a side effect.
- Build the view from React primitives — `import { createElement } from "react"`
  (no JSX, so no `.tsx`, so no extra import). QualityCue does this:
  `quality-cue.ts` imports only `react` + `../types`.

### 4c. The HEAVY-widget pattern — surface-injected components (don't import the component)

If your widget needs a genuinely heavy component (one with its own data reads,
callbacks, or non-allowlisted imports — the §9 accrual panel, the chase
launcher, a hover card), **do not import it** — that would blow the PR-8
allowlist. Instead the SURFACE injects it via `RenderContext.components`
(`types.ts:155-229`, the `AnchoredWidgetComponents` map: `AccrualPanel`,
`ChaseLauncher`, `SiteSeeHoverCard`, `MarginNote`). Your render returns the
surface-supplied component with substrate-derived props. From `accrual.ts:81-92`:

```ts
render(_rect: Rect | null, ctx: RenderContext): ReactNode {
  const Panel = ctx.components?.AccrualPanel;
  if (!Panel) return null;              // absent component ⇒ graceful no-op
  return createElement(Panel, { synthesisId });
},
```

You declare the VIEW you want placed; the surface owns the component, its
imports, and its behaviour (PR-1). The augmentation supplies only
substrate-derived data (PR-2 / PR-6), never the wiring. **If your idea needs a
component that isn't already in `AnchoredWidgetComponents`, that is a
finding/handoff item — the surface must add it (it owns that map); you may not
import the component to work around it.**

---

## 5. Anchors — semantic, never pixel (PR-4)

You name WHERE you contribute by **semantic identity**, never by pixel. The
layout-map resolves the pixel at read time. The frozen `Anchor` union
(`types.ts:54-63`):

```ts
export type Anchor =
  | { readonly kind: "chunk"; readonly chunkId: ChunkId }
  | { readonly kind: "claim"; readonly claimId: ClaimId }
  | {
      readonly kind: "passage";
      readonly chunkId: ChunkId;
      readonly start: number;   // char offsets INTO the chunk's text,
      readonly end: number;     // half-open [start, end)
    };
```

- **`chunk`** / **`document`** ids are substrate-minted and opaque. **`claim`** is
  a synthesis-scoped POSITIONAL index (`String(claim.index)`, 1-based) — stable
  for the lifetime of a rendered synthesis, reminted if claims reorder. Even the
  weakest of the three beats a pixel (stable across folds, themes, resizes,
  re-renders).
- The branded types (`ChunkId`, `ClaimId`, `DocumentId` — `string & { __brand }`)
  are opaque handles. The substrate-derived views you receive carry plain
  `string`s; cast at the anchor (`item.claimId as ClaimId`) exactly as the shipped
  augmentations do (`skim.ts:164`, `servability.ts:104`).
- A **shared anchor helper** lives at `reading-physics/anchors.ts` (NOT under
  `augmentations/`), e.g. `synthesisHeaderAnchor()`. Importing it is fine (it's a
  physics module, not a sibling augmentation). Use it for the synthesis-header
  anchor rather than re-deriving it.

> **Never** call `getBoundingClientRect`, read `offsetTop/offsetLeft/scrollTop`,
> or branch on `window.innerWidth`/`matchMedia`. Geometry is the layout-map's job
> (PR-4/PR-5). The guard flags all of these.

---

## 6. The composition contract (why this composes for free)

- **Declare into facets; the system combines; never import a sibling
  augmentation.** Every cross-augmentation concern is a named facet the surface
  owns (PR-3). The surface composes N augmentations in `O(facets)`, not `O(N²)`,
  precisely because no augmentation imports, measures, or reasons about another.
- Your augmentation must **not** know the roster of other augmentations. It
  declares into a facet; another augmentation declares into the same facet on the
  same range/anchor; the surface's combine rule de-conflicts them
  deterministically. That is the entire mechanism (Skim × SiteSee on the same
  claim range; QualityCue × Accrual on the same header anchor).
- The PR invariants you inherit by construction: PR-1 (declare, don't act), PR-2
  (substrate-owned data, no side store), PR-3 (named facets are the only
  coupling), PR-4/PR-5 (semantic anchors / what-vs-where separation), PR-6
  (substrate invariants are upstream — read verdicts, never recompute or write),
  PR-8 (authorable from the contract alone). Full statements:
  `docs/philosophy/physics-of-reading.md` §1.

---

## 7. THE SAFETY CONTRACT — the gates, up front (M2)

> **You are told the gates up front. An augmentation that fails the guard is
> REJECTED — automatically.** The guard is advisory now (the canon ships
> `status: draft`, so the guard warns but exits 0), and blocking once the canon
> is ratified AND CI runs it with `--enforce` (it needs BOTH). **The bar is the
> same as a hand-written augmentation — no relaxation for an agent.** If your
> output can't pass, that is a finding about the kit/your idea, never a reason to
> relax the guard.

Each prohibition below maps to the **exact** check in
`tools/lint/reading_physics_check.py`. These are the literal patterns the scan
matches — verified by running the guard against a probe that violated each one.

| Prohibition | Invariant | The guard check (literal patterns it matches) |
|---|---|---|
| **No surface / DOM mutation** | **PR-1** | `_DOM_MUTATION` (`reading_physics_check.py:273`). Flags `*.innerHTML =`, `.outerHTML =`, `.appendChild(`, `.insertBefore(`, `.removeChild(`, `.replaceChild(`, `.classList.add/remove/toggle(`, `document.querySelector` / `getElementById` / `getElementsBy*`, and `createPortal(`. You DECLARE; the surface enacts. **No escape.** |
| **No side store** | **PR-2** | `_PERSISTENCE` (`:258`) flags `localStorage` / `sessionStorage` / `indexedDB` / `window.localStorage`. `_STORE_IMPORT` (`:263`) flags a store-client import (`localforage`, `idb`, `dexie`, `zustand`, `jotai`, `redux`, `*store*`, `persist`, `pouchdb`, `lowdb`). `_NETWORK` (`:270`) flags a direct `fetch(` / `axios(` / `XMLHttpRequest(`. **Escape:** a line carrying a literal `// PR-2 escape:` comment is exempt — but ONLY for a bounded, **view-only, ephemeral, derivable-from-substrate** cache (no authored data, reconstructible from the substrate). A store of record is never exempt. |
| **No import of another augmentation PACKAGE** | **PR-3** | `_is_sibling_augmentation_import` (`:329`). Flags an import whose path resolves into `augmentations/` but to a DIFFERENT package. Your own package's internal modules are fine (a split augmentation = a folder, e.g. `marginalia/index.ts` + `marginalia/resolve-quote.ts` — same package, free to import each other). Crossing into a different augmentation is the violation. Couple through a named facet, never an import. |
| **Semantic, not pixel, anchors** | **PR-4 / PR-5** | `_PIXEL` (`:282`). Flags `getBoundingClientRect`, `offsetTop`, `offsetLeft`, `offsetWidth`, `offsetHeight`, `scrollTop`, `window.innerWidth`, `window.innerHeight`, `matchMedia`. Anchors are semantic; the layout-map resolves pixels. |
| **No substrate WRITE path** | **PR-6 (import half)** | `_WRITE_PATH` (`:290`). Flags an import from a path containing `db_lock`, `event_log` / `eventLog`, `append_event` / `appendEvent`, `writeEvent`, `mutation`, or `dispatch/write`. The physics reads; it never writes the substrate. *(The PR-6 "recompute a verdict locally" clause has no import signature and is review-owned, not mechanical — don't rely on the guard to catch it; just don't do it.)* |
| **PR-8 positive import-allowlist** | **PR-8** | `_is_allowed_import` (`:180`), the keystone. EVERY external import in an augmentation module must resolve to the allowed set: **`react` / `react/jsx-runtime`** (bare), OR a **relative import resolving into `reading-physics/`** (the facet API barrel `../types`, `../facet`, `../facets/*`, `../registry`, the shared `../anchors`), OR the **substrate read API** (`apps/reading/src/lib/api`). **Anything else fails** — `lodash`, `chart.js`, `date-fns`, a design-token module not yet allowlisted, etc. If it passes, the augmentation was authorable from the contract alone. |

> **The allowlist is held tight on purpose.** The canon names design-token / Lemon
> primitives as allowable, but the guard does NOT pre-allow them speculatively —
> no shipped augmentation imports them (they build views from React primitives +
> closed-vocabulary classes). If your widget genuinely needs a UI primitive,
> prefer the surface-injected-component pattern (§4c). If you truly must import
> one, that is a handoff item: the operator adds its exact name to
> `_ALLOWED_BARE_EXACT` (`:137`) and notes it in a decision doc — you do not
> work around the allowlist.

### What the guard CANNOT catch (so don't rely on it — but still obey it)

Honesty (the guard's own docstring says this): a static scan misses dynamic
`import(expr)`, a store hidden behind a shared util one hop away, a module-level
mutable singleton used as a store, a write through a React context/callback, and
the PR-6 §7-5b "recompute a substrate verdict locally" case. These are
**review-owned**. The contract still forbids them — the guard's silence is not
permission.

---

## 8. The gates you run (record the result)

```bash
# 1. Type-check (the template + your augmentation compile under strict tsconfig)
cd apps/reading && npx tsc -b            # → exit 0

# 2. The augmentation-boundary guard (PR-1/2/3/4/6 + PR-8 allowlist)
python3 tools/lint/reading_physics_check.py    # → "OK: no … violations"
```

Both must be green. (A composition test — your augmentation merging with
Skim/SiteSee/marginalia — and mounting into `MasterMdViewer` behind a toggle are
the next milestones, not part of authoring the module itself.)

`_template.ts` passes both as shipped — it is your known-green starting point.

---

## 9. Gotchas (the likely trip points — read before you author)

1. **ReadingContext vs RenderContext (§2).** The #1 trap. `contribute`'s `ctx` is
   the declare-time `ReadingContext` (has `substrate`); a widget render's `ctx` is
   the render-time `RenderContext` (no `substrate`). Read substrate at declare
   time, capture in the closure, render from the closure. Wanting `ctx.substrate`
   inside `render(...)` means you have the wrong `ctx`.

2. **`className` is a closed vocabulary, not CSS.** Declare a verdict WORD
   (`"foo--bar"`); the surface owns the paint. Passing a style string or raw CSS
   defeats the order-independent combine and is the wrong mental model (even
   though it won't always trip the guard — it'll just render wrong/un-composably).

3. **`noUnusedLocals` / `noUnusedParameters` are ON.** The strict tsconfig
   (`tsconfig.app.json`) rejects an unused import or an unused parameter. Prefix a
   deliberately-unused param with `_` (`_ctx`, `_rect`) — that's the shipped
   convention (`servability.ts`, `quality-cue.ts`). An unused `import` fails tsc.

4. **`react` is imported as a VALUE for widgets, a TYPE for the rest.** A widget
   that builds a view uses `import { createElement } from "react"` (a runtime
   value). A decorations-only augmentation imports only `../types` (all type-only)
   — it needs no React at all. Don't add a React import you don't use (gotcha #3).

5. **Tolerate `null`.** `LayoutMap.resolve(anchor)` returns `Rect | null`; a
   widget's `render(rect: Rect | null, ...)` receives `null` when the anchor isn't
   laid out. Return `null` from render in that case — don't assume a position.

6. **Heavy components are surface-injected, not imported (§4c).** Reaching for
   `import { AccrualView } from "../../modes/..."` blows the PR-8 allowlist. Use
   `ctx.components?.<Name>` and return it; the surface owns it.

7. **The substrate read API is on `ctx.substrate`, you rarely import it.** No
   shipped augmentation imports `lib/api` directly — the surface resolves the data
   and hands you a minimal substrate-derived view (the `*SourceView` /
   `*RoleView` shapes). The allowlist *permits* the relative `lib/api` import, but
   the idiomatic path is to receive resolved data via your factory + read
   `ctx.substrate` only when you genuinely need more.

8. **Don't declare a `SpatialTransform` (§3).** It's on the frozen sink but
   surface-reserved until SPR-05 (canon §9 OQ 2). Stick to decorations +
   anchored-widgets.

9. **OMIT `Decoration.title` when there's no label — never set it to
   `undefined`.** The §5.1 combine collects the SET of *declared* titles on a
   range and joins them sorted by `" · "`. The combine guards with `if (d.title)`
   (`facets/decorations.ts`), so an explicit `title: undefined` is filtered out
   today — but RELYING on that is brittle: spread the field in CONDITIONALLY so
   the title-join never even sees a phantom. The shipped idiom (see
   `review-due.ts`, the first agent-authored module):
   ```ts
   const decoration: Decoration = {
     anchor,
     className: MY_CLASS,
     ...(label !== undefined ? { title: label } : {}),  // omit, don't set undefined
   };
   ```
   Passing `title: someMaybeUndefined` directly invites a `"… · undefined · …"`
   bug the moment the combine (or a future surface) stops guarding — and it's the
   un-composable mental model regardless (a phantom title fragment that another
   augmentation's title would merge with). Omit the key; don't set it undefined.

---

## 10. Where each rule is enforced (defensibility — self-check map)

| You want to be sure… | Read | Enforced by |
|---|---|---|
| …you implement the right shape | `types.ts:459` (`ReadingAugmentation`) | tsc (`npx tsc -b`) |
| …you call the right sink methods | `types.ts:384` (`FacetRegistry`) | tsc |
| …you used the right `ctx` at render | `types.ts:118` (`RenderContext`) vs `:396` (`ReadingContext`) | tsc + §2 |
| …you didn't mutate the DOM | — | guard `_DOM_MUTATION` (`:273`) — PR-1 |
| …you kept no side store | — | guard `_PERSISTENCE`/`_STORE_IMPORT`/`_NETWORK` (`:258`–`:270`) — PR-2 |
| …you imported no sibling augmentation | — | guard `_is_sibling_augmentation_import` (`:329`) — PR-3 |
| …you used no pixel geometry | — | guard `_PIXEL` (`:282`) — PR-4/PR-5 |
| …you opened no write path | — | guard `_WRITE_PATH` (`:290`) — PR-6 |
| …you imported only the contract | — | guard `_is_allowed_import` (`:180`) — PR-8 |

If both gates in §8 are green, you have satisfied every mechanically-enforced
invariant. The two non-mechanical clauses (PR-6 verdict-recompute, PR-7
anti-purgatory) are review-owned — obey them anyway.

---

## 11. Run log (the kit's value, on record)

- **2026-05-27 (SPR-08 M3).** The first AUGMENTATION authored by an AGENT —
  `augmentations/review-due.ts` (a spaced-repetition "review-due" cue) — was
  written from this kit ALONE and passed both §8 gates **first try**: `npx tsc -b`
  exit 0 and `reading_physics_check.py` clean (contract-only: it imports only
  `../types`). It then composed with Skim + SiteSee + marginalia on one synthesis
  with **no** relaxation (`review-due.compose.test.ts` — `review-due`'s class and
  Skim's role class merge on the same claim range as one resolved decoration,
  order-independent) and mounted live behind a default-off toggle (SPR-08 M5).
  The agent's bar was the human's bar; the kit held. The one gap the agent
  surfaced is recorded as gotcha #9 (omit `Decoration.title`, don't set it
  `undefined`).

---

*Worked examples in this folder, in rough order of complexity:*
`_template.ts` (start here) → `skim.ts` / `servability.ts` / `ip-holder.ts`
(decorations, contract-only) → `quality-cue.ts` (anchored widget from React
primitives) → `accrual.ts` / `chase-launcher.ts` / `sitesee.ts` (anchored widget
via surface-injected `ctx.components`) → `marginalia/` (a split-package
augmentation). Read at least one decoration example and one widget example before
you author.
