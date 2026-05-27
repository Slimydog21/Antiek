// ─────────────────────────────────────────────────────────────────────────
// Physics of Reading — FROZEN facet-API signature (SPR-01).
// Types-only. SPR-02 imports as-is. No runtime values.
// Verified: tsc --noEmit, strict, TS 5.9.3 — clean (see §10).
// ─────────────────────────────────────────────────────────────────────────
//
// This module is the verbatim transcription of `docs/philosophy/
// physics-of-reading.md` §6 — the ratified-draft frozen facet-API signature.
// SPR-02 transcribes the WHOLE signature (not just the decorations path it
// implements) so SPR-03+ import the real module as-is — the canon's intent:
// "SPR-02 imports it as-is" (§6). For the proving slice SPR-02 only USES the
// decorations path (Decoration / FacetRegistry.declareDecoration /
// ReadingAugmentation.contribute); the other declare* methods and facet
// shapes are present and frozen so SPR-04/05 add no new method to the sink.
//
// Additive widening is allowed in later sprints; renaming or narrowing a
// field is a canon change requiring re-ratification (§6).

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
  /**
   * SPR-04 — `positionOf` is the named, ergonomic read the canon §5.3 / the
   * sprint manual M2 names ("layoutMap.positionOf(location) → { top, side }").
   * It is a THIN derivation over `resolve`: it returns the resolved top edge
   * plus the lane the caller intends, or `null` when the anchor is not laid
   * out — so a widget can ask "where does my anchor sit, in my lane?" without
   * itself touching `resolve`'s full Rect. ADDITIVE widening of the frozen §6
   * `LayoutMap` (no field renamed/narrowed): SPR-02's `{ resolve: () => null }`
   * stubs stay valid because `positionOf` is OPTIONAL — a layout-map that only
   * implements `resolve` is still a layout-map. The de-overlap enact derives
   * everything it needs from `resolve` directly, so `positionOf` is a
   * convenience for augmentation/SPR-05 callers, never the load-bearing path.
   */
  positionOf?(anchor: Anchor, lane: WidgetLane): { top: number; side: WidgetLane } | null;
}

/**
 * The gutter/lane an anchored widget lives in (SPR-04). Hoisted to a named type
 * (was inline on `AnchoredWidget.lane`) so `LayoutMap.positionOf` and the
 * de-overlap enact can share the exact same closed vocabulary. Widening the
 * union later is additive; this is the §5.2 lane set verbatim.
 */
export type WidgetLane = "left-gutter" | "right-gutter" | "inline-end";

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
  /**
   * SPR-04 — the SURFACE-OWNED heavy-component map (PR-1 / PR-8). Some re-homed
   * widgets are genuinely heavy: AccrualView owns its own §9 attribution/consent
   * reads + a payout-refusal CALLBACK, and the ChaseThread launcher needs the
   * surface's "Follow this" launch callback. A `render(rect, ctx)` that imported
   * those directly would blow the PR-8 import allowlist (an augmentation may
   * import only the facet contract + React). Instead the SURFACE injects them
   * here as a `kind → component` map, and the augmentation's render returns the
   * surface-supplied component — declaring the VIEW it wants placed without
   * importing it (the canon §7 "named UI primitives" + the manual's PREFERRED
   * resolution: "the surface owns a kind → component map and the augmentation
   * declares a lightweight spec the §6 render returns"). OPTIONAL + ADDITIVE: a
   * context without it (every SPR-02/03 stub) is still a valid RenderContext;
   * a widget whose component is absent renders nothing (graceful no-op). The
   * surface owns BOTH the component and its behaviour (PR-1) — the augmentation
   * supplies only substrate-derived data (PR-2 / PR-6), never the wiring.
   */
  readonly components?: AnchoredWidgetComponents;
}

/**
 * The surface-owned components an anchored widget may ask the surface to place
 * (SPR-04). Each is a React component the SURFACE wires (its behaviour, its
 * heavy imports, its callbacks); the augmentation only chooses to render it with
 * substrate-derived props. Every member is OPTIONAL so a render pass that does
 * not provide a given component simply yields nothing for that widget (a widget
 * MUST tolerate an absent component, exactly as it tolerates a null rect).
 *
 * Typed as `ComponentType<…>`-shaped function props rather than concrete imports
 * so this contract module stays types-only and forks no surface component.
 */
export interface AnchoredWidgetComponents {
  /** The §9 accrual panel (modes/Economics/AccrualView). The augmentation
   *  supplies the synthesis id; the surface owns the reads + the payout gate. */
  readonly AccrualPanel?: (props: { readonly synthesisId: string }) => ReactNode;
  /** The "Follow this" chase launcher. The augmentation supplies the passage
   *  text + parent investigation id; the surface owns the one launch path. */
  readonly ChaseLauncher?: (props: {
    readonly passageText: string;
    readonly parentInvestigationId: string;
    readonly reservedChildId?: string | null;
  }) => ReactNode;
  /**
   * SPR-06 — SiteSee's citation hover card. The SURFACE owns the card chrome
   * (the popover, its styling, its dismiss behaviour); the augmentation supplies
   * only the substrate-derived, §9.0-GATED metadata to show. The props are a
   * CLOSED, bounded shape — there is no `body`/`text` field, so the augmentation
   * structurally CANNOT pass a withheld source body through the card. For a
   * non-servable cited source the augmentation supplies `servable: false` +
   * ONLY the title (no `ipHolderName` — the endpoint withholds it with the
   * body), and the surface renders the honest bounded state. The reading-history
   * `state` (read / saved / cited / unseen) is substrate-derived too. ADDITIVE +
   * OPTIONAL: a pass without it yields nothing for the card (graceful no-op),
   * exactly like AccrualPanel / ChaseLauncher.
   */
  readonly SiteSeeHoverCard?: (props: {
    /** The cited source's title (always shown — bounded metadata, never the
     *  body). Null when the substrate resolved no title. */
    readonly title: string | null;
    /** §9.0 verdict, READ from the substrate (never recomputed). Drives the
     *  card's bounded-vs-full metadata branch, mirroring the citation gate. */
    readonly servable: boolean;
    /** The IP-holder name — present ONLY for a servable source with a known
     *  owner (the endpoint withholds it for a non-servable source, so the
     *  augmentation never passes it there). Null/absent ⇒ the card shows no
     *  owner line (honest unknown OR §9.0-withheld). */
    readonly ipHolderName?: string | null;
    /** The reading-history state the marker was tinted by (substrate-derived).
     *  The card may echo it ("You've read this source"). */
    readonly state: CitationHistoryState;
  }) => ReactNode;
}

/**
 * The reading-history state of a cited source (SPR-06). Derived from the
 * substrate event log (per-source read / saved / cited signals); see
 * `augmentations/sitesee.ts` + reading-physics/README.md for where each lives.
 * "unseen" is the explicit HONEST default — a source with no history is unseen
 * and SiteSee tints it nothing (M5). The order is the precedence the surface
 * resolves to a single tint when a source carries more than one signal.
 */
export type CitationHistoryState = "cited" | "saved" | "read" | "unseen";

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
  /**
   * Optional WIDGET affordance painted ALONGSIDE this range (SPR-03 M2) — e.g.
   * the talk's quote-leap button next to a quoted passage. ADDITIVE widening of
   * the frozen §6 signature (allowed per §6: "additive widening is allowed in
   * later sprints; renaming or narrowing a field is a canon change"); no
   * existing field is renamed or narrowed, so SPR-02's decorations type-check
   * unchanged. It is DATA from a closed vocabulary (`WidgetSpec`), never a
   * render callback — the surface owns how the affordance looks and behaves, so
   * the augmentation cannot smuggle a DOM mutation through it (PR-1). Distinct
   * from the gutter-lane `AnchoredWidget` below (that is SPR-04's facet); this
   * widget is inline with the decorated range.
   */
  readonly widget?: WidgetDecorationSpec;
  /**
   * Optional ATTRIBUTION payload (SPR-03 M5) — the "whose work grounds this"
   * IP-holder name the surface paints inline (e.g. "published by MIT Press").
   * ADDITIVE widening of §6 (no field renamed/narrowed). It is structured DATA,
   * not free-form copy that competes with §5 voice (PR-6): the augmentation
   * supplies only the substrate-resolved owner NAME; the surface owns the
   * "published by …" phrasing. Kept off `title` (the tooltip) and off
   * `className` (the closed verdict vocabulary) deliberately, so the IP-holder
   * augmentation can declare attribution on the SAME range as the servability
   * augmentation's verdict class and the facet merges both WITHOUT either
   * augmentation knowing the other exists (PR-3 — the M5 composition).
   */
  readonly attribution?: AttributionSpec;
}

/**
 * The IP-holder attribution a `Decoration` may carry (SPR-03 M5). Read from the
 * substrate's `ip_holder_name` verdict (PR-6 — never invented), null-safe by
 * construction: an augmentation only declares this when the substrate resolved
 * a non-null owner, so the field's mere presence means "a known owner." The
 * surface owns the phrasing; the augmentation declares the name.
 */
export interface AttributionSpec {
  /** The IP-holder name the substrate resolved (e.g. "MIT Press"). Plain text,
   *  substrate-supplied; the augmentation never fabricates it. */
  readonly ipHolderName: string;
}

/**
 * The closed widget-affordance vocabulary a `Decoration` may carry (SPR-03 M2).
 * Kept here in the frozen-signature module (additively) so an augmentation that
 * declares a widget imports only `types.ts`. The surface maps each `kind` to a
 * concrete affordance; an augmentation declares WHAT (the kind + a label),
 * never HOW it is painted (PR-1 / PR-5).
 */
export interface WidgetDecorationSpec {
  /** Closed vocabulary — extend additively, never free-form CSS/DOM. */
  readonly kind: "quote-leap" | "preview" | "open-source";
  /** Accessible label/tooltip the surface paints. Plain text, no markup. */
  readonly label: string;
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
   * Typed via the named `WidgetLane` (SPR-04) — identical string literals to the
   * frozen inline union, shared with `LayoutMap.positionOf`; no narrowing. */
  readonly lane: WidgetLane;
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
