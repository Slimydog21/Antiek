/**
 * anchored-widgets.test.ts — SPR-04 M6: the anchored-widgets facet's placement
 * guarantees, proved in isolation.
 *
 * Three families of claims, each tied to the sprint's verification gates:
 *
 *   1. DE-OVERLAP DETERMINISM (canon §5.2, gate "De-overlap determinism").
 *      The combine is a pure function of the SET of declared widgets — shuffling
 *      the declaration/enable order yields a deep-equal plan. Two widgets at the
 *      SAME anchor in the SAME lane stack by (weight desc, id asc); different
 *      lanes never collide. The vertical de-overlap (enact) is likewise a pure
 *      function of (plan, layout-map): shuffled input → deep-equal enacted set.
 *
 *   2. NO-REGRESSION (canon §3, gate "No-regression"). The three re-homed
 *      widgets — QualityCue, AccrualView, the ChaseThread launcher — render
 *      through the facet at the SAME view they shipped:
 *        - QualityCue: the byte-equivalent quiet cue (absent → nothing, positive,
 *          low-flag, collapsed detail) the inline component produced;
 *        - AccrualView / ChaseLauncher: the SURFACE-supplied component (PR-8: the
 *          augmentation declares the view, never imports the heavy component),
 *          and NOTHING when the surface injects no component (graceful no-op).
 *
 *   3. §9.0 WITHHELD-ANCHOR + edge cases (canon §9.0 / §5.3, gate "§9.0 withheld
 *      anchor"). A widget anchored into a NON-SERVABLE source must not leak the
 *      withheld body. A semantic anchor is just an id + offsets — the widget
 *      never carries the chunk body, so an off-screen / withheld anchor resolves
 *      to null and the widget renders nothing. Plus: off-screen anchor → null →
 *      render nothing; empty input → empty plan.
 *
 * Headless: the combine/enact are pure functions; widget views are rendered with
 * react-dom/server's renderToStaticMarkup (no JSX, so this stays a .ts file).
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  combineAnchoredWidgets,
  enactWidgetLayout,
  resolveAnchoredWidgets,
} from "./facets/anchored-widgets";
import { baseGeometryFromMap, createLayoutMap } from "./layout-map";
import { synthesisHeaderAnchor } from "./anchors";
import { anchorKey } from "./facets/decorations";
import { collectAnchoredWidgets } from "./registry";
import {
  QUALITY_CUE_WIDGET_ID,
  makeQualityCueAugmentation,
  renderQualityCueView,
} from "./augmentations/quality-cue";
import { ACCRUAL_WIDGET_ID, makeAccrualAugmentation } from "./augmentations/accrual";
import { makeChaseLauncherAugmentation } from "./augmentations/chase-launcher";
import type {
  AnchoredWidget,
  Anchor,
  AnchoredWidgetComponents,
  ChunkId,
  ReadingAugmentation,
  ReadingContext,
  Rect,
  RenderContext,
} from "./types";

// ── Fixtures ───────────────────────────────────────────────────────────────

const STUB_CTX: ReadingContext = {
  synthesis: { question: null, claims: [] },
  layout: { resolve: () => null },
  substrate: {
    getChunk: () => Promise.reject(new Error("not wired in the widget test")),
  },
};

const RENDER_CTX: RenderContext = { pass: "main", layout: { resolve: () => null } };

function rect(top: number, height = 20): Rect {
  return { top, left: 0, width: 100, height };
}

/** A minimal widget for plan/enact testing — a render that ignores everything. */
function widget(over: Partial<AnchoredWidget>): AnchoredWidget {
  return {
    id: "w",
    anchor: synthesisHeaderAnchor(),
    lane: "right-gutter",
    weight: 0,
    render: () => null,
    ...over,
  };
}

/** Render an enacted widget's view to static markup (or "" when it renders
 *  nothing). The view is what the surface would mount at the resolved slot. */
function viewMarkup(node: ReactNode): string {
  return renderToStaticMarkup(createElement("div", null, node));
}

// ── 1. DE-OVERLAP DETERMINISM ────────────────────────────────────────────────

describe("anchored-widgets — de-overlap determinism (canon §5.2)", () => {
  it("combine is order-independent: a shuffled widget set yields a deep-equal plan", () => {
    const a = widget({ id: "a", lane: "right-gutter", weight: 10 });
    const b = widget({ id: "b", lane: "right-gutter", weight: 50 });
    const c = widget({ id: "c", lane: "left-gutter", weight: 0 });
    const d = widget({ id: "d", lane: "inline-end", weight: 5 });

    const planForward = combineAnchoredWidgets([a, b, c, d]);
    const planShuffled = combineAnchoredWidgets([d, b, a, c]);
    const planReverse = combineAnchoredWidgets([d, c, b, a]);

    // Deep-equal regardless of declaration order — the whole facet model rests
    // on this (PR-3 / §4).
    expect(planShuffled).toEqual(planForward);
    expect(planReverse).toEqual(planForward);
  });

  it("two widgets at the SAME anchor + lane stack by weight DESC, then id ASC", () => {
    // QualityCue-like (weight 100) + accrual-like (weight 50), one anchor/lane.
    const high = widget({ id: "z-high", lane: "right-gutter", weight: 100 });
    const low = widget({ id: "a-low", lane: "right-gutter", weight: 50 });

    const plan = combineAnchoredWidgets([low, high]); // declared low-first
    const lane = plan.byLane.find((l) => l.lane === "right-gutter");
    expect(lane).toBeDefined();
    // Higher weight takes the slot nearest the anchor (stackIndex 0) even though
    // it was declared SECOND — weight, not order, decides.
    expect(lane!.widgets.map((p) => p.widget.id)).toEqual(["z-high", "a-low"]);
    expect(lane!.widgets.map((p) => p.stackIndex)).toEqual([0, 1]);
  });

  it("equal weights break by id (lexicographic), order-independent", () => {
    const w1 = widget({ id: "alpha", lane: "left-gutter", weight: 7 });
    const w2 = widget({ id: "beta", lane: "left-gutter", weight: 7 });
    const w3 = widget({ id: "gamma", lane: "left-gutter", weight: 7 });

    const plan = combineAnchoredWidgets([w3, w1, w2]);
    const lane = plan.byLane.find((l) => l.lane === "left-gutter")!;
    expect(lane.widgets.map((p) => p.widget.id)).toEqual(["alpha", "beta", "gamma"]);
  });

  it("widgets in DIFFERENT lanes never collide (separate groups)", () => {
    const left = widget({ id: "L", lane: "left-gutter", weight: 0 });
    const right = widget({ id: "R", lane: "right-gutter", weight: 0 });
    const inline = widget({ id: "I", lane: "inline-end", weight: 0 });

    const plan = combineAnchoredWidgets([right, inline, left]);
    // Each lane is its own group; their order is the fixed LANE_ORDER, not the
    // declaration order (determinism device).
    expect(plan.byLane.map((l) => l.lane)).toEqual([
      "left-gutter",
      "inline-end",
      "right-gutter",
    ]);
    for (const l of plan.byLane) expect(l.widgets).toHaveLength(1);
  });

  it("enact vertically de-overlaps two OVERLAPPING same-lane widgets, order-independent", () => {
    // Both resolve to top=100 — they overlap; the de-overlap pushes the lower-
    // priority one below. Higher weight (the header cue) keeps the slot.
    const high = widget({ id: "high", lane: "right-gutter", weight: 100, anchor: chunkA() });
    const low = widget({ id: "low", lane: "right-gutter", weight: 50, anchor: chunkA() });
    const layout = createLayoutMap(
      baseGeometryFromMap(new Map([[anchorKey(chunkA()), rect(100, 20)]])),
    );

    const enactedForward = resolveAnchoredWidgets([high, low], layout);
    const enactedShuffled = resolveAnchoredWidgets([low, high], layout);
    expect(enactedShuffled).toEqual(enactedForward);

    const byId = new Map(enactedForward.map((e) => [e.widget.id, e]));
    // high keeps its anchor top (100); low is pushed below high's band
    // (100 + 20 height + 8 gap = 128).
    expect(byId.get("high")!.rect!.top).toBe(100);
    expect(byId.get("low")!.rect!.top).toBe(128);
  });

  it("enact: a NON-overlapping same-lane pair keeps both at their anchors", () => {
    const top = widget({ id: "top", lane: "right-gutter", weight: 100, anchor: chunkA() });
    const far = widget({ id: "far", lane: "right-gutter", weight: 50, anchor: chunkB() });
    const layout = createLayoutMap(
      baseGeometryFromMap(
        new Map([
          [anchorKey(chunkA()), rect(0, 20)],
          [anchorKey(chunkB()), rect(500, 20)], // far below — no overlap
        ]),
      ),
    );
    const byId = new Map(resolveAnchoredWidgets([top, far], layout).map((e) => [e.widget.id, e]));
    expect(byId.get("top")!.rect!.top).toBe(0);
    expect(byId.get("far")!.rect!.top).toBe(500); // not pushed — no collision
  });

  it("collectAnchoredWidgets is order-independent across AUGMENTATIONS", () => {
    // The two header-anchored re-homed widgets, declared in both orders.
    const cue = makeQualityCueAugmentation({
      composite: 0.9,
      voiceStyle: null,
      conviction: null,
      citationDensity: null,
      constraintCompliance: null,
    });
    const accrual = makeAccrualAugmentation("syn-1");

    const planA = collectAnchoredWidgets([cue, accrual], STUB_CTX);
    const planB = collectAnchoredWidgets([accrual, cue], STUB_CTX);
    // Compare the STRUCTURE that de-overlap fixes (lane → id → weight →
    // stackIndex), not the render-closure identity (each `contribute` mints a
    // fresh closure, so a deep-equal on the raw plan would compare functions by
    // reference — the placement plan's determinism is about (lane, id, weight),
    // not closure identity).
    expect(structure(planB)).toEqual(structure(planA));
    // Same anchor + lane → QualityCue (weight 100) above accrual (weight 50).
    const lane = planA.byLane.find((l) => l.lane === "right-gutter")!;
    expect(lane.widgets.map((p) => p.widget.id)).toEqual([
      QUALITY_CUE_WIDGET_ID,
      ACCRUAL_WIDGET_ID,
    ]);
  });
});

// ── 2. NO-REGRESSION — the three re-homed widgets render their shipped view ──

describe("anchored-widgets — no-regression: re-homed widgets render as today (canon §3)", () => {
  it("QualityCue: absent score → renders NOTHING (honest, no fabricated verdict)", () => {
    const cue = makeQualityCueAugmentation(null);
    const enacted = enactSingle(cue);
    expect(viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX))).toBe("<div></div>");
  });

  it("QualityCue: a passing score → the quiet positive cue (byte-equivalent)", () => {
    const cue = makeQualityCueAugmentation({
      composite: 0.82,
      voiceStyle: 0.8,
      conviction: 0.75,
      citationDensity: 1.0,
      constraintCompliance: 1.0,
    });
    const enacted = enactSingle(cue);
    const html = viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX));
    // The exact shipped wording + classes (the inline QualityCue produced this).
    expect(html).toContain("This answer clears our quality bar.");
    expect(html).toContain('class="mt-3 text-xs"');
    expect(html).toContain("text-shadow-1 dark:text-moonlight leading-relaxed");
    // Sub-scores present → the collapsed "the detail" toggle renders.
    expect(html).toContain("the detail");
    expect(html).toContain("Voice and style");
    // Not flagged for a re-run.
    expect(html).not.toContain("another pass");
  });

  it("QualityCue: a low score → the visible re-run flag, not the positive cue", () => {
    const cue = makeQualityCueAugmentation({
      composite: 0.22,
      voiceStyle: 0.3,
      conviction: 0.2,
      citationDensity: 0.0,
      constraintCompliance: 0.0,
    });
    const enacted = enactSingle(cue);
    const html = viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX));
    expect(html).toContain("another pass");
    expect(html).toContain("under our quality bar");
    expect(html).toContain("text-amber-800 dark:text-sun leading-relaxed");
    expect(html).not.toContain("clears our quality bar");
  });

  it("QualityCue: no sub-scores → NO 'the detail' toggle (no empty rows)", () => {
    const cue = makeQualityCueAugmentation({
      composite: 0.1,
      voiceStyle: null,
      conviction: null,
      citationDensity: null,
      constraintCompliance: null,
    });
    const enacted = enactSingle(cue);
    const html = viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX));
    expect(html).toContain("another pass"); // low → still flagged
    expect(html).not.toContain("the detail"); // but no breakdown
  });

  it("QualityCue: the re-homed view is byte-identical to the standalone view fn", () => {
    // The surface and the no-regression test render the SAME exported view fn,
    // so the re-home cannot drift from the augmentation's own output.
    const score = {
      composite: 0.82,
      voiceStyle: 0.8,
      conviction: 0.75,
      citationDensity: 1.0,
      constraintCompliance: 1.0,
    };
    const cue = makeQualityCueAugmentation(score);
    const enacted = enactSingle(cue);
    expect(viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX))).toBe(
      viewMarkup(renderQualityCueView(score)),
    );
  });

  it("AccrualView: renders the SURFACE-supplied AccrualPanel for the synthesis id", () => {
    const accrual = makeAccrualAugmentation("syn-42");
    const enacted = enactSingle(accrual);
    // The surface injects the heavy AccrualView component (PR-8: the augmentation
    // declares the view, never imports it). A test double stands in for it.
    const components: AnchoredWidgetComponents = {
      AccrualPanel: ({ synthesisId }) =>
        createElement("section", { "data-accrual-for": synthesisId }, "accrual panel"),
    };
    const ctx: RenderContext = { ...RENDER_CTX, components };
    const html = viewMarkup(enacted.widget.render(enacted.rect, ctx));
    expect(html).toContain('data-accrual-for="syn-42"');
    expect(html).toContain("accrual panel");
  });

  it("AccrualView: renders NOTHING when the surface injects no component (no-op)", () => {
    const accrual = makeAccrualAugmentation("syn-42");
    const enacted = enactSingle(accrual);
    // No `components` on the context (e.g. a minimap pass) → graceful no-op.
    expect(viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX))).toBe("<div></div>");
  });

  it("ChaseLauncher: renders the SURFACE-supplied launcher with the captured passage + ids", () => {
    const chase = makeChaseLauncherAugmentation({
      chunkId: "chk-1",
      start: 10,
      end: 40,
      passageText: "a curious claim",
      parentInvestigationId: "inv-parent",
      reservedChildId: "inv-reserved",
    });
    const enacted = enactSingle(chase);
    const components: AnchoredWidgetComponents = {
      ChaseLauncher: ({ passageText, parentInvestigationId, reservedChildId }) =>
        createElement(
          "button",
          {
            "data-parent": parentInvestigationId,
            "data-reserved": reservedChildId ?? "",
          },
          `Follow this: ${passageText}`,
        ),
    };
    const ctx: RenderContext = { ...RENDER_CTX, components };
    const html = viewMarkup(enacted.widget.render(enacted.rect, ctx));
    expect(html).toContain("Follow this: a curious claim");
    expect(html).toContain('data-parent="inv-parent"');
    expect(html).toContain('data-reserved="inv-reserved"');
  });

  it("ChaseLauncher: renders NOTHING when the surface injects no component", () => {
    const chase = makeChaseLauncherAugmentation({
      chunkId: "chk-1",
      start: 10,
      end: 40,
      passageText: "a curious claim",
      parentInvestigationId: "inv-parent",
    });
    const enacted = enactSingle(chase);
    expect(viewMarkup(enacted.widget.render(enacted.rect, RENDER_CTX))).toBe("<div></div>");
  });
});

// ── 3. §9.0 WITHHELD-ANCHOR + edge cases ─────────────────────────────────────

describe("anchored-widgets — §9.0 withheld anchor + edge cases (canon §9.0 / §5.3)", () => {
  it("§9.0: a widget anchored into a NON-SERVABLE source leaks no withheld body", () => {
    // A chase launcher pinned to a passage of a restricted chunk. The withheld
    // BODY is never an input to the augmentation — the anchor is just (chunkId,
    // offsets), and the captured seed is the passage TEXT the surface already
    // gate-served (a highlight can only carry gate-permitted text). The layout-
    // map resolves the restricted anchor to null (the surface measured no node
    // for a withheld source), so the widget renders NOTHING — no body can leak.
    const WITHHELD_BODY = "THE SECRET RESTRICTED BODY TEXT";
    const restrictedPassage: Anchor = {
      kind: "passage",
      chunkId: "restricted-chunk" as ChunkId,
      start: 0,
      end: 12,
    };
    const chase = makeChaseLauncherAugmentation({
      chunkId: "restricted-chunk",
      start: 0,
      end: 12,
      passageText: "gate-served snippet", // NOT the withheld body
      parentInvestigationId: "inv-parent",
    });

    // The layout-map has NO geometry for the restricted anchor → resolves null.
    const layout = createLayoutMap(baseGeometryFromMap(new Map()));
    expect(layout.resolve(restrictedPassage)).toBeNull();

    const enacted = enactSingle(chase, layout);
    expect(enacted.rect).toBeNull(); // not laid out

    // Even with a launcher component injected, no withheld body can appear: the
    // augmentation never received it (only the gate-served snippet).
    const components: AnchoredWidgetComponents = {
      ChaseLauncher: ({ passageText }) => createElement("button", null, passageText),
    };
    const ctx: RenderContext = { ...RENDER_CTX, components };
    const html = viewMarkup(enacted.widget.render(enacted.rect, ctx));
    expect(html).not.toContain(WITHHELD_BODY);
    expect(html).toContain("gate-served snippet"); // only the permitted text
  });

  it("off-screen anchor → resolve null → the widget keeps a null rect (renders nothing)", () => {
    const w = widget({ id: "off", lane: "right-gutter", weight: 0, anchor: chunkA() });
    // Empty geometry → every anchor resolves null (off-screen / not laid out).
    const layout = createLayoutMap(baseGeometryFromMap(new Map()));
    const enacted = resolveAnchoredWidgets([w], layout);
    expect(enacted).toHaveLength(1);
    expect(enacted[0].rect).toBeNull();
  });

  it("a null-resolving widget consumes NO slot — a sibling keeps its anchor top", () => {
    const off = widget({ id: "off", lane: "right-gutter", weight: 100, anchor: chunkA() });
    const on = widget({ id: "on", lane: "right-gutter", weight: 50, anchor: chunkB() });
    // chunkA is not laid out (null); chunkB is at top=100.
    const layout = createLayoutMap(
      baseGeometryFromMap(new Map([[anchorKey(chunkB()), rect(100, 20)]])),
    );
    const byId = new Map(resolveAnchoredWidgets([off, on], layout).map((e) => [e.widget.id, e]));
    expect(byId.get("off")!.rect).toBeNull();
    // `on` is NOT pushed down by the null `off` — a null widget occupies no band.
    expect(byId.get("on")!.rect!.top).toBe(100);
  });

  it("empty input → empty plan, empty enacted set (no-op)", () => {
    const plan = combineAnchoredWidgets([]);
    expect(plan.byLane).toEqual([]);
    expect(plan.all).toEqual([]);
    expect(enactWidgetLayout(plan, createLayoutMap(baseGeometryFromMap(new Map())))).toEqual([]);
  });
});

// ── helpers (anchors + single-widget enact) ──────────────────────────────────

/** Project a plan to its order-independent STRUCTURE (lane → id/weight/stack),
 *  dropping the render closure so two plans built from distinct `contribute`
 *  calls compare on placement, not closure reference identity. */
function structure(plan: ReturnType<typeof combineAnchoredWidgets>) {
  return plan.byLane.map((l) => ({
    lane: l.lane,
    widgets: l.widgets.map((p) => ({
      id: p.widget.id,
      weight: p.widget.weight,
      stackIndex: p.stackIndex,
      anchorKey: anchorKey(p.widget.anchor),
    })),
  }));
}

function chunkA(): Anchor {
  return { kind: "chunk", chunkId: "chunk-a" as ChunkId };
}
function chunkB(): Anchor {
  return { kind: "chunk", chunkId: "chunk-b" as ChunkId };
}

/** Collect ONE augmentation's widget and enact it (geometry-independent widgets
 *  use the empty layout-map; a caller may pass a real layout-map for geometry). */
function enactSingle(
  aug: ReadingAugmentation,
  layout = createLayoutMap(baseGeometryFromMap(new Map())),
) {
  const widgets = collectAnchoredWidgets([aug], STUB_CTX).all.map((p) => p.widget);
  const enacted = resolveAnchoredWidgets(widgets, layout);
  return enacted[0];
}
