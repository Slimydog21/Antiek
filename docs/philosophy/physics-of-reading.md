---
title: A Physics of Reading
status: draft
date: 2026-05-27
sprint: SPR-01 (physics-of-reading)
ratified_by: null
supersedes: null
---

> **Front-matter convention (new).** No `docs/philosophy/` directory existed
> before this sprint, and no existing Antiek doc uses YAML front-matter (the
> `docs/decisions/*.md` files use a `**Status:**` markdown line instead). This
> sprint *establishes* a minimal front-matter convention for `docs/philosophy/`:
> a leading `--- … ---` block carrying `title`, `status` (`draft` | `ratified`),
> `date` (ISO, the last substantive edit), `sprint`, and `ratified_by` (null
> until an operator ratifies). The convention is deliberately small — five keys,
> all human-readable — so a future philosophy doc copies it without ceremony.
>
> **RATIFICATION (operator-only).** This document ships at `status: draft`.
> **SPR-02 … SPR-08 MUST NOT treat PR-1 … PR-8 as binding canon until the
> front-matter reads `status: ratified`.** Until then they are a precise
> *proposal*: implementable as-is, but reversible by the operator. Setting
> `status: ratified` is an operator act; the builder of this sprint did not (and
> may not) set it. The CI guard SPR-03 builds (§7) reads this flag and runs
> **advisory** (warn-only) while `status: draft`, then **blocking** once ratified
> — so the guard never blocks a PR against unratified canon.

# A Physics of Reading

*Antiek's read-side composition layer, stated as binding canon.*

## 0. Why this document exists

Antiek's Read surface — `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx`
plus the reading companion (`apps/reading/src/modes/Reading/ReadingCompanion.tsx`)
— is in production at antiek.ai. It already carries several reading
augmentations, each hand-wired into the surface:

- **§9.0 servability gating** — a cited source either opens or shows an honest
  "not available to open" state, decided by the retrieval-time gate
  (`MasterMdViewer.tsx`, `SourceCitation`).
- **Named-source / IP-holder inline annotation** — "from *Title*, p.12,
  published by MIT Press", resolved through the provenance chain
  (`MasterMdViewer.tsx`, `NamedSources` / `SourceCitation`).
- **QualityCue** — a quiet read of the §14.4 inline rubric score
  (`MasterMdViewer.tsx`, `QualityCue`).
- **AccrualView** — the §9 provenance-economics panel
  (`apps/reading/src/modes/Economics/AccrualView.tsx`).
- **ChaseThread** — "Follow this" launchers off a highlighted passage
  (`apps/reading/src/modes/ResearchWorkstation/ChaseThread.tsx`).

Each was added by editing the surface directly. The cost compounds: the next
augmentation means editing the same regions again, and two augmentations that
touch the same region (a citation chip and a chase launcher on the same claim)
race for the same DOM. This is the org-mode failure mode — every feature pokes
the same buffer, and the interactions between features become the dominant
source of bugs.

Matuschak's "a physics of reading" (early 2026) names the escape, drawn from
CodeMirror: an editor built entirely of plugins that **never mutate the
document**. A plugin *declares* a contribution into a named **facet**; the
editor's "physics" combines all contributions and enacts the result. Plugins
compose for free because they never touch each other or the buffer — they only
ever declare into facets, and the editor owns the combine.

This document writes Antiek's version of that physics, scoped to **reading**.
It is precise enough that **SPR-02 implements the `decorations` facet from the
frozen signature in §6 alone**, and **SPR-03 implements the CI guard from the
contract in §7 alone**. It does **not** legislate the Write/notes surface's edit
algebra (the `transaction-filter` facet) — that is named as future (§5.6) and
out of scope here.

A load-bearing distinction inherited from CodeMirror and re-grounded in Antiek:
**this is a read-side *composition* layer, not a second source of truth.** The
substrate (DuckDB single-writer event log; claim → chunk → document → IP-holder
provenance; §9.0 servability; §5 voice) is upstream of the physics and is never
violated by it (PR-6). The physics composes a *view* of substrate-owned data;
it never owns data.

---

## 1. The eight invariants (PR-1 … PR-8)

Each invariant states **the rule**, **why it exists** (tied both to the talk and
to the specific Antiek substrate invariant it sits above), **a concrete Antiek
example** (preferably an existing shipped augmentation re-expressed), and **how a
violation looks in code** (so SPR-03's guard has a concrete pattern to detect).

### PR-1 — Declare, don't act

**Rule.** An augmentation never mutates the reading surface directly. It
*declares* contributions into a named facet (§5); the system composes all
declarations and enacts them.

**Why.** This is the central move from the talk: CodeMirror plugins never poke
the buffer, so they compose. In Antiek it sits above the **§5 voice/style
discipline** — the surface, not a scattering of augmentations, owns how the
reading column looks and reads, so voice stays coherent no matter how many
augmentations contribute. It also makes PR-7 (anti-purgatory) affordable: adding
an augmentation is declaring into an existing facet, not surgery on a shared
component.

**Concrete Antiek example.** Today `QualityCue` is JSX hand-placed inside
`MasterMdViewer`'s `<header>`. Under PR-1 it instead declares an
`AnchoredWidget` pinned to the synthesis header anchor; the surface places it.
The surface — not QualityCue — decides it sits in the right gutter and how it
stacks against any other header-anchored widget.

**Violation in code (SPR-03 detects).** An augmentation module writes to the DOM
or a sibling directly: `ref.current.innerHTML = …`, `el.appendChild(…)`,
`document.querySelector(…).classList.add(…)`, or a direct
`ReactDOM.createPortal` into a node it does not own. Any DOM-mutating call inside
a module under the augmentations directory is a PR-1 violation.

### PR-2 — Substrate-owned data, no side store

**Rule.** An augmentation's data lives in the substrate (chunk / claim / doc /
event), visible to every other augmentation — never in a private store. CI-guarded.

**Bounded escape clause.** A *view-only, ephemeral, derivable-from-substrate
cache* is permitted (e.g. memoizing a resolved chunk → title for the duration of
a render). It MUST: (a) hold no authored reading data — nothing a user or agent
created that isn't already in the substrate; (b) be reconstructible from the
substrate alone (losing it loses nothing); (c) carry a `// PR-2 escape:`
rationale comment at its declaration. Anything else — a store that persists
across reloads, or that holds the only copy of any datum — is a PR-2 violation.

**Why.** Above the **substrate-as-source-of-truth** invariant (CLAUDE.md §3:
every claim → chunk → document → `ip_holder_id`). A private augmentation store
forks the truth: a second augmentation can't see it, so composition breaks (you
can't combine facets over data one augmentation hides), and the provenance chain
develops a branch the §9 attribution math can't account for. In the talk this is
"the document is the single shared model"; in Antiek the shared model is the
substrate.

**Concrete Antiek example.** `NamedSources` resolves chunks through `getChunk`
(the substrate read API) every render and holds nothing authoritative — exactly
PR-2-clean. A counterexample to reject: a "my highlights" augmentation that
stashes highlights in `localStorage`. Highlights are authored reading data;
they belong in the substrate event log so the chase augmentation and the notes
augmentation can both see them.

**Violation in code (SPR-03 detects).** An augmentation module imports a
persistence client other than the substrate read API: `localStorage` /
`sessionStorage` / `indexedDB`, a SQL/KV client, `fetch`/`axios` to a non-
substrate origin, or any state library used as a store of record. A `// PR-2
escape:` comment on the line suppresses the flag for the bounded cache case.

### PR-3 — Named facets are the only coupling

**Rule.** Every cross-augmentation concern is a named facet (§5) with an explicit
combine rule (§6). No augmentation imports or depends on another.

**Why.** The talk's free-composition guarantee comes from this: plugins interact
*only* through facets the editor owns, so there is no plugin-to-plugin graph to
reason about. In Antiek it bounds the blast radius of every future augmentation
— the surface composes N augmentations in `O(facets)`, not `O(N²)` pairwise
interactions. It also makes PR-8 (agent-authorable) true: an agent can write an
augmentation knowing only the facet API, never the roster of siblings.

**Concrete Antiek example.** Today `ChaseThread` and `NamedSources` can both want
to render on the same claim. Under PR-3 neither imports the other: ChaseThread
declares an `AnchoredWidget` on the claim anchor; the citation declares a
`Decoration` + widget on the same anchor; the surface's combine rules (§6)
de-overlap them. Adding a third claim-level augmentation tomorrow requires
editing neither.

**Violation in code (SPR-03 detects).** An augmentation module imports a
*different* augmentation (an import path that resolves into the augmentations
directory, other than the facet API barrel). An augmentation's identity is its
**package** — a flat module file, OR a subdirectory when one augmentation is
split across several files (`marginalia/index.ts` + `marginalia/resolve-quote.ts`);
same-package internal imports are that augmentation's own structure, not a
sibling import. Crossing into a *different* package is the violation — a direct
dependency PR-3 forbids; coupling must go through a named facet, not an import.

### PR-4 — Anchors are semantic, not pixel

**Rule.** Widgets declare a *location* — a chunk id, a passage within a chunk, a
claim — not a pixel. The layout-map (§5.3) resolves the pixel at read time,
accounting for any spatial transform (§5.4).

**Why.** In the talk, anchoring to document positions (not screen coordinates) is
what lets folding, soft-wrap, and multiple views all work without each plugin
re-deriving geometry. In Antiek the semantic unit tracks the substrate unit —
**claim → chunk → document** is the provenance chain (CLAUDE.md §3). The chunk
and document anchors *are* substrate-minted identities; the claim anchor is one
notch weaker — a **synthesis-scoped positional index** (`data-claim-id =
String(claim.index)`, MasterMdViewer.tsx:153 / synthesisParser.ts:30), stable for
the lifetime of a rendered synthesis but reminted if the claims reorder. Even the
weakest of the three is far better than a pixel: a pixel is not stable across a
fold, a theme change, a window resize, or a second render; a chunk id is, and a
claim index is stable for as long as the synthesis it indexes does.

**Concrete Antiek example.** `MasterMdViewer` already stamps
`data-claim-id={String(claim.index)}` on the claim span — a semantic (if
positional) handle. PR-4 makes that the *only* handle an augmentation gets:
ChaseThread anchors to `{ kind: "claim", claimId }`, never to a measured
`getBoundingClientRect()` it captured at mount.

**Violation in code (SPR-03 detects).** An augmentation reads pixel geometry to
position itself: `getBoundingClientRect`, `offsetTop` / `offsetLeft` /
`scrollTop`, or a hardcoded `top:`/`left:` style derived from a measurement.
Geometry is the layout-map's job; an augmentation that measures it has pinned to
pixels.

### PR-5 — What-to-show is separate from where-to-show

**Rule.** An augmentation declares *what* to show (a decoration, a widget) and
its *semantic where* (an anchor). The *pixel where* is computed by the
layout-map. This separation enables multi-render and spatial transforms without
augmentations knowing the geometry changed.

**Why.** This is the structural payoff of PR-4. In the talk it's the reason one
plugin's decorations show correctly in both the main editor and the minimap: the
plugin declared *what*, the view computed *where*, twice. In Antiek it sits above
the same substrate provenance chain as PR-4: because *what* is keyed by substrate
identity and *where* is derived, the surface can fold a section (§5.4), render a
minimap (§5.5), or reflow into columns and every augmentation follows for free.

**Concrete Antiek example.** A "reading minimap" (a future second render of the
synthesis) wants the servability decorations and the QualityCue widget to appear
in it too. Because each augmentation declared *what* + *semantic where* (PR-4),
the surface runs the same `contribute()` against a minimap `RenderContext`; the
layout-map resolves minimap pixels; no augmentation changes.

**Violation in code (SPR-03 detects).** Same surface as PR-4 (pixel reads) plus:
an augmentation branches on viewport/window dimensions (`window.innerWidth`,
`matchMedia`, a resize listener) to decide *what* to show. Deciding *what* by
geometry collapses the two concerns PR-5 separates.

### PR-6 — Substrate invariants are upstream

**Rule.** The physics never violates a substrate invariant. It is a read-side
composition layer, not a second source of truth. Concretely, the physics must
never:
- **(single-writer)** write to the substrate. Augmentations declare and read;
  the *only* writer to the graph is the serialized host funnel through
  `runtime/db_lock` (CLAUDE.md §1, `--workers 1`). A reading augmentation that
  needs to record something (e.g. a chase launch) does it through an existing
  substrate write endpoint the surface already calls — never by the augmentation
  opening its own writer.
- **(provenance)** invent or sever a claim → chunk → document link. An
  augmentation reads the chain; it never fabricates a title, a chunk, or an
  owner (CLAUDE.md §3).
- **(§9.0 servability)** show a restricted source's body. The servability
  verdict comes from the substrate read API and is honored, not recomputed.
- **(§5 voice)** emit prose in its own voice. Composition serves the surface's
  voice; an augmentation contributes structure (decorations/widgets), not
  free-form copy that competes with §5.

**Why.** Without this, "compose freely" would license the physics to become a
parallel truth — exactly what CLAUDE.md's invariants forbid. The talk treats the
document as sacred and immutable-by-plugins; Antiek treats the *substrate* as
sacred. PR-6 is the bridge: the physics composes over the substrate, strictly
downstream of it.

**Concrete Antiek example.** `SourceCitation` reads `servable` from `getChunk`
and renders "not available to open" when false — it never second-guesses the
gate. Under the physics this becomes a `Decoration` whose treatment is chosen by
the substrate-supplied verdict; the augmentation still has no power to override
§9.0.

**Violation in code (SPR-03 detects).** An augmentation imports a substrate
*write* path (anything from the dispatch/write side, e.g. `db_lock`, an
event-append helper, a `POST` mutation client) rather than the read API; or
recomputes a servability verdict / rubric score / attribution share locally
instead of reading the substrate's. (The DOM-write and non-substrate-store
checks of PR-1/PR-2 cover the rest of PR-6's surface.)

### PR-7 — Anti-purgatory

**Rule.** Every augmentation ships into the *production* reading surface
(`MasterMdViewer` and the reading companion) — never only into a prototype
reader that lives forever in a branch.

**Why.** The talk's prototypes are a research tool, but a reading *product* dies
in research purgatory if each idea gets its own throwaway reader and none reach
users. PR-1's declare-don't-act is what makes shipping cheap enough to keep this
promise: because an augmentation is a declaration into an existing facet, landing
it in production is adding an augmentation to the registry, not forking the
surface. This sits above no single substrate invariant — it is the product
discipline that keeps the physics honest (and it is the reason CodeMirror's
"editor of plugins" beats a pile of bespoke editors).

**Concrete Antiek example.** A new "show me the rhetorical structure" idea is
prototyped as a `decorations` augmentation against the same `MasterMdViewer`
behind a flag, then enabled — not as a separate `ReadingPrototype.tsx` that never
merges. ChaseThread is the model: it replaced ChaseSlideOver *in the production
surface*, it did not spawn a second reader.

**Violation (review-detectable; SPR-03 advisory).** A new augmentation imports or
mounts a non-production reader component, or is gated to a `*Prototype*` /
`*Playground*` surface with no path into `MasterMdViewer`. This is harder to make
purely mechanical than PR-1…PR-6; SPR-03 treats it as an advisory grep for
prototype-reader entry points, and code review owns the final call. (Recorded as
an open question, §9.)

### PR-8 — Agent-authorable

**Rule.** The facet API (§6) is small and safe enough that a coding agent can
author a new composable augmentation without rewriting the surface.

**Why.** Antiek's roadmap is agent-built augmentations. The talk's facet API is
small *because* the editor owns the hard parts (combine, layout, enact); the same
smallness is what lets an agent write a correct augmentation from the contract
alone. It sits above the same §16 / agent-failure discipline the rest of the
codebase uses: a small, typed, write-incapable surface is one an agent can't use
to violate single-writer, provenance, or §9.0 by accident — PR-6's guarantees
hold *because* the contract is narrow.

**Concrete Antiek example.** An agent asked to "highlight every claim whose only
source is tier-3" writes a `ReadingAugmentation` (§6) that reads
`ctx.synthesis.claims`, resolves tiers via `ctx.substrate`, and calls
`registry.declareDecoration(...)`. It imports the facet API and nothing else,
type-checks against the frozen signature, and composes with every existing
augmentation — no surface edit.

**Violation in code (SPR-03 detects).** Largely the union of PR-1…PR-3 + PR-6:
an augmentation that reaches outside the facet API (DOM, a non-substrate store,
another augmentation, a write path) is by definition not author-able from the
contract alone. PR-8 has no *additional* detector beyond "the augmentation
imports only the facet API barrel and the substrate read API"; SPR-03 enforces
that import-allowlist directly (§7).

---

## 2. The augmentation, defined

An **augmentation** is a `ReadingAugmentation` (§6): a stable id plus a pure
`contribute(ctx, registry)` method. It reads a **read-only** `ReadingContext`
(the parsed synthesis, the layout-map, and the substrate read API) and emits
**declarations** into a `FacetRegistry`. It returns nothing. It mutates nothing.
The surface calls `contribute()` once per `RenderContext` (§5.5), collects every
augmentation's declarations per facet, applies each facet's combine rule (§6),
and enacts the composed result.

That single shape is what PR-1…PR-8 protect. Everything below specifies the
facets it declares into and the contract it is held to.

---

## 3. Shipped-augmentation → facet map (diligence)

Before legislating, the canon must describe a physics the *real shipped*
augmentations can be re-expressed in. If any can't be, the canon is wrong. Each
maps cleanly:

| Shipped augmentation | File | Facet | How it re-expresses |
|---|---|---|---|
| **§9.0 servability gating** | `MasterMdViewer.tsx` `SourceCitation` | **decorations** | Declares a `Decoration` on the cited-source range whose treatment (openable vs "not available to open") is chosen by the substrate-supplied `servable` verdict. Range-keyed, order-independent. |
| **Named-source / IP-holder annotation** | `MasterMdViewer.tsx` `NamedSources` / `SourceCitation` | **decorations** (+ optional **anchored-widget** for the hover/preview affordance) | The "from *Title*, p.12, published by …" treatment is a decoration on the claim's citation range; the click-to-preview / ⌘-open affordance is an `inline-end` anchored widget. Both keyed to the claim/chunk anchor. |
| **QualityCue** | `MasterMdViewer.tsx` `QualityCue` | **anchored-widget** | Pins a quiet widget to the synthesis header anchor (`left-gutter` or header lane). Reads the persisted rubric score from the substrate; never recomputes (PR-6). |
| **AccrualView** | `modes/Economics/AccrualView.tsx` | **anchored-widget** | The §9 accrual panel pins to the synthesis (header/aside lane) as a widget. Its no-money-path / opt-in honesty (PR-6 over §9.0/§9.10) is unchanged — the physics governs *placement*, not the panel's substrate-honesty logic. |
| **ChaseThread** | `modes/ResearchWorkstation/ChaseThread.tsx` | **anchored-widget** (the "Follow this" launcher) **+ decorations** (the highlightable passage) | The passage the chase descends from is a `passage` decoration; the launcher is an anchored widget pinned to that passage. It still launches through the one shipped launch path (PR-6 single-writer: the surface's existing write endpoint, not a writer the augmentation opens). |

**Result:** all five shipped augmentations are representable; **none is
unrepresentable** in PR-1…PR-8 + the five facets. The two that today emit prose
into the surface (QualityCue, AccrualView) become widgets that the surface
*places* — their substrate-honesty logic is untouched; only the hand-wiring into
JSX is replaced by a declaration. (An earlier draft kept a separate "augmentation
data shape" section between this map and the facet definitions; its content folded
into this map above and into the per-facet `Declares` clauses of §5, so there is
no standalone section before §5.)

---

## 4. Why composition is cheap (the O(facets) claim)

The whole point of the physics — the reason it is worth the facet indirection — is
a cost claim, stated here so the rest of the canon can lean on it: **with PR-1
(declare, don't act) and PR-3 (named facets are the only coupling), the surface
composes N augmentations in `O(facets)`, not `O(N²)` pairwise interactions.** No
augmentation imports, measures, or reasons about another; each only declares into
one of the five named facets (§5), and the surface owns the combine. So the cost
of adding the Nth augmentation is "declare into an existing facet," independent of
the prior N−1 — which is exactly what makes PR-7 (anti-purgatory) affordable and
PR-8 (agent-authorable) true. This is the property the org-mode failure mode
lacks: there, every feature pokes the shared buffer, so interactions are
`O(N²)` and the Nth feature must be reasoned against all prior ones (§0, §11.1).

---

## 5. The five named facets

Each facet definition states: **what an augmentation declares**, **the combine
rule**, and **the enact step** (what the surface does with the combined result).
Combine rules are **deterministic and order-independent** where the spec requires
it (decorations), and an **explicit, justified ordering** where order is
semantically load-bearing (the spatial-transform pipeline). A facet whose combine
rule cannot be stated precisely is not ready to be canon; §9 records the cases
that aren't fully closed.

### 5.1 `decorations` — *(SPR-02 builds; SPR-03 guards)*

- **Declares:** a `Decoration` — a semantic `anchor` (range) + a closed-vocabulary
  `className` + an optional `title`.
- **Combine rule:** **range union, deterministic, order-independent.** All
  declared decorations apply; the surface paints the union of their ranges. Two
  decorations on overlapping ranges *both* apply (see §8, case 1). When two
  decorations resolve to the *same* range and both carry a `title`, the surface
  joins the titles deterministically (the set of titles, sorted lexicographically,
  joined by `" · "`) so the result does not depend on declaration order.
- **Enact:** for each resolved range, the surface wraps the range with the
  combined class set and the joined title. No augmentation paints; the surface
  does.

### 5.2 `anchored-widgets` — *(SPR-04 builds)*

- **Declares:** an `AnchoredWidget` — a stable `id`, a semantic `anchor`, a `lane`
  (`left-gutter` | `right-gutter` | `inline-end`), a `weight`, and a pure
  `render(rect, ctx)`.
- **Combine rule:** **de-overlap, deterministic.** Widgets in *different* lanes
  never collide. Widgets in the *same* lane whose resolved rects overlap
  vertically are stacked: the higher `weight` takes the slot nearest its anchor;
  the loser stacks just below; equal weights break by `id` (lexicographic). So the
  outcome is a pure function of `(lane, weight, id, resolved-rect)` — independent
  of declaration order (see §8, case 2).
- **Enact:** the surface resolves each widget's anchor via the layout-map (§5.3),
  runs the de-overlap to assign final rects, and calls each `render(rect, ctx)`.
  A widget whose anchor resolves to `null` renders nothing.

### 5.3 `layout-map` — *(SPR-04 builds)*

- **Declares:** nothing. The layout-map is **read by** augmentations, **owned by**
  the surface. It is the read-time resolver — `resolve(anchor): Rect | null` —
  that answers "where is anchor X *now*?", after every spatial transform (§5.4)
  has been folded in.
- **Combine rule:** not a contributed facet, so no augmentation-combine. Its
  *internal* rule: the map composes the spatial-transform pipeline (§5.4) over the
  base geometry, and reports the **final** rect. It is the single point that knows
  geometry, which is what makes PR-4/PR-5 possible.
- **Enact:** queried on demand by anchored-widget rendering and by any
  augmentation that legitimately needs a position. Returns `null` for anchors not
  currently laid out (off-screen, folded, excluded by the render pass) — and
  callers MUST tolerate `null`.

### 5.4 `spatial-transform` — *(SPR-05 builds)*

- **Declares:** a `SpatialTransform` — a stable `id`, an explicit pipeline
  `order`, and `apply(anchor, rect): Rect | null` that remaps a pre-transform rect
  to a post-transform rect (or `null` to remove the anchor from this pass, e.g. a
  folded section).
- **Combine rule:** **an explicit ordered pipeline — NOT order-independent.**
  Transforms compose left-to-right by ascending `order` (ties broken by `id`,
  lexicographic, for determinism). Order is load-bearing: fold-then-zoom differs
  from zoom-then-fold, so the spec makes ordering explicit and justified rather
  than pretending it commutes. The metaphor from the talk: a spatial transform
  composes with decorations like a **fragment shader over a vertex shader** — the
  transform moves *where* content appears (the vertices); decorations paint *what*
  appears (the fragments) and follow the moved geometry automatically because they
  query the layout-map's final rect (§5.3), never a pre-transform pixel.
- **Enact:** the layout-map (§5.3) applies the pipeline in order when resolving any
  anchor, so decorations and widgets see only the final geometry (see §8, case 3).

### 5.5 `multi-render` — *(SPR-05 builds)*

- **Declares:** nothing new. Multi-render is the surface rendering the *same*
  facets more than once — the main reading column plus, e.g., a minimap or a
  second pass — each as its own `RenderContext` (`pass: "main" | "minimap" | …`).
- **Combine rule:** **per-context determinism.** Each augmentation's
  `contribute()` is run once per `RenderContext` and MUST be a *pure function of
  that context* — it may legitimately contribute differently to the minimap than
  to the main view, but with no hidden cross-pass state, so re-reading the same
  facet in a second pass is reproducible (see §8, case 4). Widget `id`s are stable
  across passes so a pass can reconcile (the same QualityCue is "the same widget"
  in main and minimap).
- **Enact:** the surface runs the full collect-combine-enact cycle once per
  context, each with its own layout-map instance (a minimap has different
  geometry). No augmentation knows there is more than one pass.

### 5.6 `transaction-filter` — *(FUTURE; out of scope this sprint)*

The **edit algebra** — how concurrent edits to a writable document compose,
validate, and reconcile (CodeMirror's transaction filters / the OT-like layer) —
is the **Write/notes surface's** concern, **not reading's**. Reading composes a
*view* of an immutable substrate-derived synthesis; it does not edit a buffer, so
it needs no transaction algebra. This facet is **named and deferred**: when the
Write/notes surface adopts the physics, `transaction-filter` is the facet it adds,
and it will get its own canon. Legislating it here would be speculative; this
sprint deliberately does not.

### Build ownership summary

| Facet | Built by | Status |
|---|---|---|
| `decorations` | **SPR-02** (impl) / **SPR-03** (CI guard) | this sprint freezes the signature |
| `anchored-widgets` | **SPR-04** | signature frozen here |
| `layout-map` | **SPR-04** | signature frozen here |
| `spatial-transform` | **SPR-05** | signature frozen here |
| `multi-render` | **SPR-05** | no new declaration; render-cycle behavior frozen here |
| `transaction-filter` | **future (Write/notes)** | named, deferred, out of scope |

---

## 6. The frozen facet-API signature

This is a **types-only** TypeScript module (one `import type { ReactNode }` from
react; no runtime values). **SPR-02 imports it as-is** — and that is now literally
true on both ends: the `SubstrateReadApi.getChunk` return type is the shipped
`ChunkResponse` shape verbatim (snake_case, §6 below + `api.ts:456-480`), so SPR-02
wires `ctx.substrate.getChunk` straight to the shipped `api.ts:getChunk` with no
adapter. It was type-checked in isolation with `tsc --noEmit` under `strict`
(TS 5.9.3, matching `apps/reading/tsconfig.app.json`'s `strict` + `noUnusedLocals`
+ `noUnusedParameters` + `moduleResolution bundler`), with react's `ReactNode`
resolving against the shipped `@types/react` — result recorded in §10. SPR-02
should place it at `apps/reading/src/modes/Reading/facets/physics.ts` (or the path
SPR-02's plan fixes) and treat the shapes below as frozen — additive widening is
allowed in later sprints; renaming or narrowing a field is a canon change
requiring re-ratification.

```ts
// ─────────────────────────────────────────────────────────────────────────
// Physics of Reading — FROZEN facet-API signature (SPR-01).
// Types-only. SPR-02 imports as-is. No runtime values.
// Verified: tsc --noEmit, strict, TS 5.9.3 — clean (see §10).
// ─────────────────────────────────────────────────────────────────────────

// The reading surface is React; a widget's render returns a view node, never a
// side effect. Typing the return as ReactNode (not `unknown`) is what makes
// "a view, not a side effect" a TYPE constraint, not just a PR-1 grep.
import type { ReactNode } from "react";

// ── Semantic identity (PR-2 / PR-4) ──────────────────────────────────────
// Augmentations name WHERE they contribute by semantic identity, never by
// pixel. ChunkId and DocumentId are opaque ids the SUBSTRATE mints; ClaimId
// is a synthesis-scoped POSITIONAL index (see its note). The reading surface
// is the only place that resolves any of these to geometry (PR-5).

/** A chunk id — the engine's retrieval unit. Opaque; substrate-minted. */
export type ChunkId = string & { readonly __brand: "ChunkId" };

/**
 * A claim's identity WITHIN one rendered synthesis. NOT substrate-minted:
 * the real handle is `data-claim-id = String(claim.index)`
 * (MasterMdViewer.tsx:153), the 1-based positional `ParsedClaim.index`
 * (synthesisParser.ts:30). It is synthesis-scoped and positional — vastly
 * more stable than a pixel and fixed for the lifetime of a rendered
 * synthesis, but it SHIFTS if the claims reorder (a re-parse that reorders
 * components remints the index). Branded so the type system still treats it
 * as an opaque handle, not a free-form string.
 */
export type ClaimId = string & { readonly __brand: "ClaimId" };

/** A document id. Opaque; substrate-minted. */
export type DocumentId = string & { readonly __brand: "DocumentId" };

/**
 * A semantic anchor (PR-4). An augmentation declares one of these to say
 * WHERE it contributes; the layout-map (PR-5) resolves it to pixels at read
 * time. A passage offset is expressed relative to a chunk, never to the
 * rendered DOM, so it survives a spatial transform.
 */
export type Anchor =
  | { readonly kind: "chunk"; readonly chunkId: ChunkId }
  | { readonly kind: "claim"; readonly claimId: ClaimId }
  | {
      readonly kind: "passage";
      readonly chunkId: ChunkId;
      /** Char offsets INTO the chunk's text, half-open [start, end). */
      readonly start: number;
      readonly end: number;
    };

/**
 * A resolved pixel rectangle in the reading surface's coordinate space, AFTER
 * any spatial transform has been applied (PR-5). Augmentations never
 * construct these; the layout-map returns them.
 */
export interface Rect {
  readonly top: number;
  readonly left: number;
  readonly width: number;
  readonly height: number;
}

// ── The read-time resolver every widget queries (PR-5 / layout-map) ──────

/**
 * The layout-map facet (PR-5): the read-time answer to "where is anchor X
 * now?". The surface owns it; augmentations only query it. Returns null when
 * the anchor is not currently laid out (off-screen, collapsed, in a render
 * pass that excludes it — see RenderContext). An augmentation MUST tolerate
 * null rather than assume a position.
 */
export interface LayoutMap {
  resolve(anchor: Anchor): Rect | null;
}

/**
 * Which render pass is asking (PR / multi-render). The same facets are read
 * once per context; an augmentation may legitimately contribute differently
 * to the minimap than to the main view, but it MUST be a pure function of the
 * context — no hidden cross-pass state.
 */
export interface RenderContext {
  /** "main" is the primary reading column; others are secondary passes.
   *  `string & {}` keeps the "main"/"minimap" autocomplete hints while staying
   *  open to future pass names (a bare `string` union would discard them). */
  readonly pass: "main" | "minimap" | (string & {});
  readonly layout: LayoutMap;
}

// ── Decoration facet (PR-1 / decorations) ───────────────────────────────

/**
 * A visual treatment applied to a semantic RANGE. Combine rule: range UNION,
 * deterministic and order-independent (PR / decorations). Two decorations on
 * overlapping ranges both apply; the surface paints their union; neither wins
 * by being declared first.
 */
export interface Decoration {
  /** What range receives the treatment. */
  readonly anchor: Anchor;
  /**
   * The class(es) the surface paints onto the resolved range. A closed
   * vocabulary the surface understands — NOT arbitrary CSS, NOT inline DOM,
   * so the combine stays order-independent (PR-1: declare, don't act).
   */
  readonly className: string;
  /**
   * Optional title/aria text. When two decorations on the same range both
   * carry a title, the surface joins them deterministically (sorted, joined
   * by " · ") — see the doc's overlapping-decorations case.
   */
  readonly title?: string;
}

// ── Anchored-widget facet (PR-1 / anchored-widgets) ──────────────────────

/**
 * A widget pinned to a semantic anchor (PR-4). The surface resolves the pixel
 * via the layout-map and places the widget; the augmentation never positions
 * itself. Combine rule: de-overlap by `lane` then `weight` (see doc).
 */
export interface AnchoredWidget {
  /** Stable id so multi-render (PR / multi-render) can reconcile passes. */
  readonly id: string;
  /** WHERE it pins (PR-4 semantic, resolved by layout-map at read time). */
  readonly anchor: Anchor;
  /**
   * Which gutter/lane the widget lives in. Widgets in different lanes never
   * collide; widgets in the SAME lane at the same vertical position de-overlap
   * by `weight` (higher wins the slot; the loser stacks below). Deterministic.
   */
  readonly lane: "left-gutter" | "right-gutter" | "inline-end";
  /** Tie-break weight for same-lane same-position collisions. Higher = nearer
   *  the anchor; equal weights break by `id` (lexicographic) for determinism. */
  readonly weight: number;
  /**
   * The render function. Receives the resolved rect (post-transform, PR-5) and
   * the context (PR multi-render). Returns a ReactNode — a VIEW, not a side
   * effect: the type forbids returning junk and pairs with PR-1 (declare,
   * don't act) at the type level, not just at the grep level. MUST be pure
   * w.r.t. the context and MUST tolerate a null-resolving anchor by rendering
   * nothing (return null).
   */
  render(rect: Rect | null, ctx: RenderContext): ReactNode;
}

// ── Spatial-transform facet (PR-5 / spatial-transform) ───────────────────

/**
 * A read-side remap of where content appears (e.g. fold a section, zoom a
 * passage, reflow into columns). Composes with decorations like a fragment
 * shader over a vertex shader (PR-5): the transform changes the geometry the
 * layout-map reports, so decorations and widgets follow automatically without
 * knowing the geometry moved. Combine rule: an ORDERED pipeline (see doc) —
 * transforms are explicitly composed left-to-right; order is justified, not
 * order-independent, because folding-then-zooming differs from zoom-then-fold.
 */
export interface SpatialTransform {
  /** Stable id; also the pipeline-ordering key when two transforms tie. */
  readonly id: string;
  /** Explicit pipeline position. Lower runs first. Equal ⇒ break by `id`. */
  readonly order: number;
  /**
   * Remap an anchor's pre-transform rect to its post-transform rect, or null
   * to remove it from this pass (e.g. a folded section). The layout-map folds
   * the whole pipeline so widgets/decorations query the FINAL geometry only.
   */
  apply(anchor: Anchor, rect: Rect | null): Rect | null;
}

// ── The augmentation contract (PR-1 / PR-3 / PR-8) ────────────────────────

/**
 * The sink an augmentation declares INTO. The surface provides it; the
 * augmentation never holds a ref to the DOM and never mutates a sibling.
 * Every method is "declare", never "act" (PR-1). This is the entire surface
 * area an augmentation may touch (PR-8: small + safe enough for an agent).
 */
export interface FacetRegistry {
  declareDecoration(d: Decoration): void;
  declareAnchoredWidget(w: AnchoredWidget): void;
  declareSpatialTransform(t: SpatialTransform): void;
}

/**
 * What every augmentation reads FROM. A narrow, read-only window onto the
 * substrate (PR-2): the augmentation sees chunks/claims/docs the substrate
 * already owns, plus the layout-map (PR-5). It has NO write capability and NO
 * persistence client — that is the CI-guarded boundary (PR-2 / SPR-03).
 */
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

/** A read-only view of the parsed synthesis. (Shape owned by synthesisParser;
 *  declared opaque here so the facet API does not fork the parser's types.) */
export interface ReadonlySynthesis {
  readonly question: string | null;
  readonly claims: readonly { readonly claimId: ClaimId; readonly chunkIds: readonly ChunkId[] }[];
}

/** The substrate read API surface an augmentation is allowed to call (PR-2).
 *  Read-only by construction. The RETURN type IS the shipped `ChunkResponse`
 *  shape verbatim (apps/reading/src/lib/api.ts:456-480) — snake_case, same
 *  field names — so SPR-02 wires `ctx.substrate.getChunk` straight to the
 *  shipped `api.ts:getChunk` (api.ts:952) with ZERO adapter. The branded
 *  `ChunkId` input is the augmentation-facing identity (PR-4); only the input
 *  is augmentation-shaped, the return mirrors the substrate exactly. Widened
 *  in later sprints additively, never with writes. */
export interface SubstrateReadApi {
  getChunk(id: ChunkId): Promise<{
    readonly chunk_id: string;
    readonly text: string;
    readonly section_path: string | null;
    readonly token_count: number;
    readonly document_id: string;
    readonly document_title: string | null;
    readonly source_tier: number;
    /** §9.0: when false, the endpoint withholds the body (`text`) and the
     *  surface must show "not available to open", never the content. The
     *  §9.0 gate is carried entirely by `servable` + `servability` here —
     *  the augmentation reads the verdict, it never recomputes it (PR-6). */
    readonly servable: boolean;
    /** SPR-10 M1 "whose work grounds this": the IP-holder name, or null when
     *  the owner is unknown OR the source is non-servable (the endpoint
     *  withholds the owner with the body). */
    readonly ip_holder_name?: string | null;
    /** The IP-holder lifecycle word (pre_onboarded … claimed); null when no
     *  owner or non-servable. */
    readonly ip_holder_status?: string | null;
    /** Why a source is withheld ("restricted" | "taken_down"); null when
     *  servable. The second half of the §9.0 gate. */
    readonly servability: string | null;
  }>;
}

/**
 * THE augmentation contract (PR-1 / PR-8). An augmentation is a pure function
 * from a read-only ReadingContext to a set of DECLARATIONS into the registry.
 * It returns nothing; it does not mutate the surface, a sibling, or the
 * substrate. SPR-02's decorations augmentation, and every augmentation after
 * it, implements exactly this shape.
 */
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

**Note on the `declareDecoration` shape SPR-02 builds first.** SPR-02 implements
exactly the `decorations` path: it consumes `Decoration` declarations made via
`FacetRegistry.declareDecoration`, applies the §5.1 range-union/order-independent
combine, and enacts onto the production `MasterMdViewer`. The other `declare*`
methods are present in the frozen registry so SPR-04/05 add no new method to the
sink — they only start producing declarations the registry already accepts.

---

## 7. The CI-guard contract (SPR-03 implements this from the contract alone)

SPR-03 builds an **augmentation-boundary lint**, modeled on the existing
`tools/lint/boundary_check.py` (which forbids vendor-SDK imports in `substrate/`).
It runs as a **new step in `.github/workflows/ci.yml`'s `tsc` job, alongside the
existing token-lint / bundle-budget steps** (the augmentation surface is
TypeScript, so it lives in the JS CI job, not the pytest job). It is a static
import/AST check over the augmentations directory — sub-second, no build needed.

**Scope.** The guard runs over modules under the augmentations directory SPR-02
establishes (proposed `apps/reading/src/modes/Reading/augmentations/**` and
`.../facets/**`). A module is "an augmentation module" if it lives under that
directory (excluding the facet API barrel and `*.test.*` / `*.stories.*`).

**Detectable violation patterns (each maps to an invariant):**

1. **DOM / sibling mutation (PR-1).** Any of: `*.innerHTML =`, `.appendChild(`,
   `.insertBefore(`, `.removeChild(`, `.classList.add(` / `.remove(`,
   `document.querySelector`/`getElementById`, `createPortal` into a foreign node.
   *An augmentation declares; it must not act on the DOM.*
2. **Non-substrate persistence (PR-2).** Any import/reference of `localStorage`,
   `sessionStorage`, `indexedDB`, a SQL/KV client, or `fetch`/`axios`/`XMLHttpRequest`
   to a non-substrate origin; or a state library used as a store of record.
   **Escape:** a line carrying a `// PR-2 escape:` comment is exempt (the bounded
   view-only/ephemeral/derivable cache of §PR-2); the comment is required, so the
   exemption is auditable.
3. **Augmentation-to-augmentation import (PR-3).** An import whose resolved path
   is inside the augmentations directory but is *not* the facet API barrel.
   *Coupling must go through a named facet, never an import.*
4. **Pixel anchoring (PR-4 / PR-5).** Any of: `getBoundingClientRect`, `offsetTop`,
   `offsetLeft`, `offsetWidth`/`offsetHeight` used for positioning, `scrollTop`,
   or a `window.innerWidth`/`matchMedia`/resize-listener used to decide *what* to
   show. *Geometry is the layout-map's job.*
5. **Substrate write (PR-6) — BLOCKING, detectable.** An import of a substrate
   *write* path (`db_lock`, an event-append/POST-mutation helper, the dispatch
   write side) or a persistence client from an augmentation. This half has a
   concrete import/call signature to match, so the guard blocks on it. *The
   physics reads; it does not write to the substrate.*
5b. **Substrate-verdict recompute (PR-6) — ADVISORY, review-owned.** A local
   re-implementation of a servability verdict / rubric score / attribution share
   instead of reading the substrate's. This is *arbitrary arithmetic* — there is
   no import or call signature to match, so it is **not statically detectable**.
   The guard cannot mechanically catch it; like PR-7, it is **advisory /
   review-owned** (recorded as an open question, §9). *The physics must not
   second-guess a substrate verdict — but the boundary lint can't prove it
   didn't; a reviewer must.*
6. **Import allowlist (PR-8, the positive form of 1–3 + 5).** Beyond the negative
   patterns, the guard asserts the *positive*: an augmentation module's external
   imports are a subset of { the facet API barrel, the substrate read API, React,
   the design-token/Lemon primitives, pure util modules }. Anything outside the
   allowlist fails. (This covers the import-detectable patterns — 1–3 and the
   write half 5 — but cannot cover 5b's local recompute, which has no import to
   gate.) This is the single check that makes PR-8 true — if it passes, the
   augmentation was authorable from the contract alone.

**Anti-purgatory (PR-7) is advisory-only in this guard.** SPR-03 greps for an
augmentation mounting/importing a `*Prototype*`/`*Playground*` reader with no path
into `MasterMdViewer`, and **warns**; it does not block. PR-7 is a product
discipline that code review owns (see §9, open question).

**Rollout.** Per the standing CI discipline (informational-then-blocking, as the
latency check and the boundary check were introduced), the guard runs
**advisory (warn-only) in its first PR**, so the team sees its findings on the
real tree without a surprise red gate; it flips to **blocking** in a follow-up PR
once the augmentations directory is clean. **Additionally**, while this canon's
front-matter reads `status: draft`, the guard stays advisory regardless — it only
ever blocks against *ratified* canon (the guard reads the front-matter `status`).

**Honesty constraint (rigor #1).** Every BLOCKING pattern above is something a
static import/AST scan can actually detect. Two things are deliberately **not**
mechanically enforced and are not dressed up as if they were: **PR-7**
(anti-purgatory — partly a product/review judgment) and the **5b
substrate-verdict-recompute clause of PR-6** (arbitrary arithmetic with no import
or call signature to match). Both are explicitly advisory / review-owned and
recorded as open questions (§9). No invariant in §1 is claimed as mechanically
enforced when it isn't.

---

## 8. Hard composition cases, enumerated (rigor #3)

Each is a case the combine rules must handle; each combine rule's behavior is
stated, and any case that can't be made deterministic is moved to §9 rather than
papered over.

1. **Two decorations on overlapping ranges.** Both apply. The surface paints the
   **union** of the two ranges with the **union** of their class sets; on the
   overlap the classes stack. When both carry a `title`, the titles are combined
   as the sorted set joined by `" · "`. **Order-independent** — swapping which
   decoration was declared first yields byte-identical output. (E.g. a
   servability decoration and a "tier-3-only" decoration on the same citation
   range both show.)
2. **Two anchored widgets at the same vertical position (same lane).** De-overlap
   by `weight` (higher takes the slot nearest the anchor), then the loser stacks
   just below; **equal weights break by `id`** (lexicographic). Different lanes
   never collide. **Deterministic** and order-independent. (E.g. QualityCue and a
   future "freshness" widget both in the header `left-gutter`.)
3. **A spatial transform under an anchored widget.** The widget anchored
   semantically (PR-4); the transform remaps the anchor's rect via the layout-map
   pipeline (§5.4). The widget's `render(rect, …)` receives the **post-transform**
   rect and follows automatically. If the transform returns `null` for the anchor
   (e.g. the widget's anchor is in a folded section), the widget renders nothing.
   The widget never learns the geometry moved (PR-5). **Behavior fully specified.**
4. **The same facet read twice (multi-render).** `contribute()` runs once per
   `RenderContext`; each pass has its own layout-map. The augmentation may produce
   different declarations per pass (main vs minimap) but MUST be a pure function of
   the context — **no hidden cross-pass state** — so the second read is
   reproducible. Widget `id`s are stable across passes so a pass can reconcile
   "the same widget". **Deterministic per context.**

A fifth case worth stating because it is *not* order-independent and the spec is
honest about it: **two spatial transforms in the pipeline.** These compose by
ascending `order` (ties by `id`); the result depends on order *by design*
(fold-then-zoom ≠ zoom-then-fold), so the canon makes ordering explicit and
justified rather than claiming commutativity it doesn't have (§5.4). See §9 for
the open question on cross-augmentation transform ordering.

---

## 9. Open questions (intellectual honesty)

These are unresolved or only-partly-resolved; each names who should answer.

1. **PR-7 mechanical enforcement.** PR-7 (anti-purgatory) lacks a clean static
   detector — "did this ship into the production surface, not a prototype
   reader?" is partly a product/review judgment. The guard treats it as an
   advisory grep for prototype-reader entry points. *Resolve in SPR-03:* either
   find a sharper signal (e.g. an augmentation registry that the production
   surface and only the production surface reads from, so "registered ⇒ shipped"
   becomes mechanical) or accept it as review-owned and drop the advisory grep.
   *Owner: SPR-03 + operator.*
1b. **PR-6 substrate-verdict-recompute detection (§7 pattern 5b).** The other
   non-mechanical clause: an augmentation that *recomputes* a servability verdict
   / rubric score / attribution share locally — instead of reading the
   substrate's — is arbitrary arithmetic with no import or call signature to
   match, so the boundary lint cannot catch it (the import-write half, pattern 5,
   it catches fine). It is advisory / review-owned, exactly like PR-7. *Resolve in
   SPR-03:* decide whether a sharper signal exists (e.g. the substrate read API is
   the *only* sanctioned source of these verdicts, so the absence of a verdict
   read where one is rendered is a smell a reviewer checks) or accept it as
   permanently review-owned. *Owner: SPR-03 + operator.*
2. **Cross-augmentation spatial-transform ordering.** Within one augmentation,
   transform `order` is the author's to set. *Across* augmentations, if two
   augmentations each declare a transform with the same `order`, the `id`
   tie-break is deterministic but arbitrary — and a genuinely conflicting pair
   (fold a section + zoom a passage inside it) may have no "right" order. *Resolve
   in SPR-05:* decide whether spatial transforms are surface-reserved (only the
   surface declares them, augmentations never do — which sidesteps the conflict
   entirely) or augmentation-declarable with a documented conflict policy.
   *Owner: SPR-05.* (Until resolved, treat `spatial-transform` as
   surface-declared-only — the safe default — and SPR-04/05 must not assume an
   augmentation can declare one.)
3. **`passage` anchor offset stability.** A `passage` anchor uses char offsets
   *into a chunk's text* (PR-4-clean: relative to substrate identity, not DOM). If
   a chunk's text is ever re-derived (a re-ingest changes tokenization), the
   offsets could drift. *Resolve in SPR-04:* confirm chunk text is immutable once
   minted (the substrate's tokenization doctrine suggests it is), or add a chunk
   text-version to the anchor. *Owner: SPR-04 + substrate.*
4. **`ReadonlySynthesis` vs the parser's types.** The frozen signature declares a
   minimal read-only synthesis shape rather than importing `synthesisParser`'s
   `ParsedSynthesis`, to avoid the facet API forking the parser. SPR-02 must
   either adapt `ParsedSynthesis` → `ReadonlySynthesis` at the surface boundary or
   widen `ReadonlySynthesis`. Additive widening is allowed without re-ratification;
   a structural conflict is a canon change. *Owner: SPR-02.*

---

## 10. Verification record (what was VERIFIED vs ASSUMED)

**Verified (ran):**
- Read `MasterMdViewer.tsx` in full (567 lines) — confirmed servability gating,
  named-source/IP-holder annotation, and QualityCue are hand-wired into the
  surface; mapped each to a facet (§3).
- Read `ChaseThread.tsx` (header + props) and `AccrualView.tsx` (header + props)
  and `ReadingCompanion.tsx` (header + props) — confirmed ChaseThread's launch
  path is the one shipped path (single-writer) and AccrualView's no-money/opt-in
  honesty is substrate-logic the physics governs only placement of; mapped both
  to facets (§3).
- Read `ChunkResponse` in `apps/reading/src/lib/api.ts` (lines 456-480) and
  `QualityScore` in `synthesisParser.ts` — `SubstrateReadApi.getChunk`'s return
  type IS the shipped `ChunkResponse` shape verbatim (snake_case, identical
  field names), so SPR-02 imports the read API as-is with no adapter; the
  read-only synthesis shape is likewise grounded in the real shipped surface.
- Read `getChunk` in `apps/reading/src/lib/api.ts` (line 952,
  `Promise<ChunkResponse>`) — confirmed the frozen `SubstrateReadApi.getChunk`
  return mirrors it field-for-field.
- Read `tools/lint/boundary_check.py` and `.github/workflows/ci.yml` — modeled
  the CI-guard contract (§7) on the existing AST/import lint and placed it in the
  existing `tsc` CI job alongside token-lint/bundle-budget.
- Confirmed **no existing YAML front-matter convention** in `docs/` (decisions use
  a `**Status:**` line) — established the new `docs/philosophy/` convention and
  said so (front-matter note at top).
- **Type-checked the §6 frozen signature in isolation** with `tsc --noEmit`,
  TypeScript **5.9.3**, under `strict` + `isolatedModules` + `verbatimModuleSyntax`
  + `noUnusedLocals` + `noUnusedParameters` + `moduleResolution bundler` (the repo
  `tsconfig.app.json` settings), with the `import type { ReactNode } from "react"`
  resolving against the shipped `@types/react`. **Result: clean, exit 0**
  (`TSC_CLEAN_EXIT_0`). A deliberate-break probe (assigning a non-node to a
  `ReactNode` slot) was rejected by `tsc`, confirming the react types are really
  resolved and `render(): ReactNode` genuinely constrains "a view, not a side
  effect" rather than waving the import through. The block SPR-02 imports is the
  identical text (the `import type` line + the types).

**Assumed (not verified — flagged for the implementing sprint):**
- The exact augmentations directory path (`apps/reading/src/modes/Reading/
  augmentations/**` + `.../facets/**`) is a *proposal*; SPR-02 fixes the real path
  and SPR-03's guard scopes to it. The guard's *logic* does not depend on the
  path.
- That chunk text is immutable once minted (used by the `passage` anchor) — see
  §9 open question 3; SPR-04 confirms.
- That `ParsedSynthesis` can be adapted to `ReadonlySynthesis` without a
  structural conflict — see §9 open question 4; SPR-02 confirms.

---

## 11. Rejected alternatives

Each carries a **reconsider-if** so the rejection is defensible, not dogmatic.

### 11.1 Direct-mutation plugins (the Emacs / org-mode model)

**What.** Let each augmentation reach into the reading surface and mutate it
directly — poke the buffer, the way an Emacs minor mode pokes the buffer.

**Rejected because.** This is exactly the org-mode folding nightmare the talk
diagnoses: every feature mutates the shared buffer, so the *interactions between
features* become the dominant bug source, and adding the Nth feature means
reasoning about its collisions with the prior N−1. It directly violates PR-1
(declare, don't act) and PR-3 (no augmentation-to-augmentation coupling). Antiek
already feels the early form of this — two augmentations on one claim race for the
same DOM region.

**Reconsider if.** A future surface has exactly one augmentation that owns the
whole surface and no composition is ever needed — in which case the facet
indirection is pure overhead. (Antiek's roadmap is the opposite: many composable,
agent-authored augmentations, so this is unlikely.)

### 11.2 Plugin-in-a-box (the Photoshop modal/sidebar model)

**What.** Augmentations live in their own modal or sidebar panel and may *not*
touch the primary reading surface — a safe sandbox.

**Rejected because.** It is safe precisely by being unable to do the thing that
matters: a reading augmentation's whole value is annotating the *reading column
itself* (a servability badge on a citation, a chase launcher on a passage). A
sidebar-only augmentation can't put a decoration inline where the reader is
looking. The physics gets the safety of a sandbox (PR-1/PR-2/PR-6 keep
augmentations from breaking the surface) *without* the box, because declare-don't-
act means an augmentation can contribute inline without being able to corrupt the
surface.

**Reconsider if.** A specific augmentation genuinely belongs in a panel (a heavy
analytics view) — then it's an `anchored-widget` in an aside lane, which is the
box *as a facet*, not the whole model.

### 11.3 Per-augmentation private store

**What.** Each augmentation keeps its own data store (localStorage, an in-memory
cache of record, a per-feature table).

**Rejected because.** It breaks PR-2 and therefore composition: a second
augmentation can't combine facets over data the first one hides, and the
provenance chain (claim → chunk → doc → IP-holder) develops a branch the §9
attribution math can't see. The shared substrate *is* the composition substrate —
the moment data goes private, "facets compose freely" becomes false.

**Reconsider if.** A datum is provably view-only, ephemeral, and reconstructible
from the substrate — which is the **bounded PR-2 escape clause** (a memoized
resolve cache), not a private store of record. Anything holding the only copy of a
datum is never reconsiderable here; it belongs in the substrate.

### 11.4 A separate prototype reader per idea

**What.** Each new reading idea gets its own throwaway reader component
(`ReadingPrototypeX.tsx`), iterated in isolation, maybe merged later.

**Rejected because.** This is research purgatory (PR-7): ideas accumulate in
branches and never reach users, and the production surface ossifies because
nobody wants to touch it. The physics makes the prototype reader unnecessary —
because an augmentation is a declaration into an existing facet, you can prototype
*against the production surface* behind a flag and ship by flipping it.

**Reconsider if.** A change is so structural it isn't an augmentation at all (a
new rendering engine, a different document model) — then a prototype surface is
the honest way to de-risk it, and PR-7 doesn't apply because it isn't an
augmentation.

### 11.5 Adopt wholesale CodeMirror / ProseMirror for reading

**Steelman (fair, genuine strength — rigor #2).** CodeMirror and ProseMirror have
*already solved* exactly the problem this document legislates: battle-tested
facet systems, decorations, view plugins, and transaction algebras refined over a
decade across thousands of production editors. Adopting one would give Antiek free
composition, a mature decoration/widget layer, accessibility and IME handling we'd
otherwise reinvent, and a large community of plugins and patterns — we would
inherit a *correct* physics instead of writing our own and discovering its edge
cases in production. This is a serious option and the strongest alternative on
this list.

**Rejected because.** The data flow is inverted. CodeMirror/ProseMirror are built
around a **text buffer the user edits** as the source of truth — transactions
mutate that buffer, and everything composes around buffer state. Antiek's reading
surface renders a **substrate-derived synthesis** (claim → chunk → document, an
immutable view the user does *not* edit). Adopting an editor framework would make
*its* document model the source of truth, which collides head-on with PR-2/PR-6:
the substrate must stay upstream, and a reader is not an editor. We'd spend our
effort fighting the framework's buffer-centric assumptions and constantly syncing
its model back to the substrate — paying the framework's full weight to use a
sliver of it (decorations + facets) while disabling its core (editing). The
physics borrows CodeMirror's *idea* (declare into named facets; the system
combines) without inheriting its *data model* (a mutable text buffer). That is the
defensible line: take the architecture lesson, not the buffer.

**Reconsider if.** The Write/notes surface (where the user *does* edit a buffer)
needs the `transaction-filter` edit algebra (§5.6) — there, a ProseMirror/
CodeMirror core is a genuinely strong candidate *for that surface*, because the
data flow finally matches (the buffer *is* what's edited). This rejection is
scoped to **reading**, not to all of Antiek.

### 11.6 Pixel-anchored widgets

**What.** Widgets store and position by pixel coordinates measured at mount
(`getBoundingClientRect`, absolute `top`/`left`).

**Rejected because.** Pixels break under everything the physics is built to
support: a spatial transform (fold/zoom/reflow), a theme or font change, a window
resize, or a second render (minimap) all move the geometry, and a pixel-anchored
widget is left pointing at empty space. It violates PR-4 (anchors are semantic)
and defeats PR-5 (what/where separation). A chunk id is stable across all of
these; a pixel is stable across none.

**Reconsider if.** A widget is genuinely tied to a viewport position, not to
content — a fixed "scroll to top" affordance, say. That isn't an *anchored*
widget at all (it has no content anchor); it's surface chrome the surface owns
directly, outside the facet system. So even this case doesn't reopen pixel
anchoring *for augmentations*.

---

*End of canon. Ships at `status: draft`. Awaiting operator ratification
(`status: draft` → `ratified`). SPR-02 … SPR-08 must not treat PR-1 … PR-8 as
binding until then.*
