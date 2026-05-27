/**
 * readingGeometryPass.test.ts — Living-Roadmap SPR-02: the surface
 * geometry-measurement pass that closes the D13 gap
 * (docs/decisions/spr-05-geometry-pass-gap.md).
 *
 * Pins the milestones:
 *   M1 — a populated DOM measured through baseGeometryFromMap → createLayoutMap
 *        resolves a KNOWN anchor to a NON-NULL rect (the happy-path proof), and
 *        the mounted map is NO LONGER EMPTY_LAYOUT_MAP (a known anchor that
 *        EMPTY_LAYOUT_MAP would resolve to null now resolves to a real rect).
 *   M1 failure modes (rigor #3) — a ZERO-HEIGHT anchor (not yet laid out) is
 *        DROPPED → resolves null (the widget renders nothing, not pinned at the
 *        origin); an OFF-SCREEN anchor keeps its real rect (scope, not measure,
 *        decides viewport membership).
 *   M2 — minimap / collapse / marginalia all resolve a real rect through the
 *        LIVE map built from the populated DOM (wiring-only liveness, no
 *        augmentation logic touched).
 *   M3 — the viewport-scoped pass short-circuits an off-band anchor to null.
 *
 * jsdom's getBoundingClientRect returns all-zeros by default (nothing is "laid
 * out"), so we install a per-element rect via a data attribute + a spy — which
 * ALSO exercises the zero-height failure mode for free (an element with no
 * installed rect reads 0×0).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CLAIM_ID_ATTR,
  buildLayoutMap,
  buildViewportBand,
  buildViewportScopedLayoutMap,
  measureClaimGeometry,
} from "./readingGeometryPass";
import { EMPTY_LAYOUT_MAP, baseGeometryFromMap, createLayoutMap } from "../../reading-physics/layout-map";
import { anchorKey } from "../../reading-physics/facets/decorations";
import type { ResolvedDecoration } from "../../reading-physics/facets/decorations";
import type { Anchor, ClaimId } from "../../reading-physics/types";
import {
  minimapLayoutFrom,
  projectDecorationsToMinimap,
} from "../../reading-physics/minimap";
import {
  CollapseState,
  fingerprintPlan,
} from "../../reading-physics/augmentations/collapse";
import { resolveAnchoredWidgets } from "../../reading-physics/facets/anchored-widgets";
import { makeChaseLauncherAugmentation } from "../../reading-physics/augmentations/chase-launcher";
import { collectAnchoredWidgets } from "../../reading-physics/registry";

// ── A populated-DOM fixture (jsdom) ──────────────────────────────────────────
//
// jsdom does no layout, so getBoundingClientRect is all-zeros. We stamp each
// element's intended rect on a data attribute and spy getBoundingClientRect to
// read it back — a real DOM tree the measure pass walks, with installed geometry.

interface FakeRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function installRect(el: HTMLElement, rect: FakeRect): void {
  el.setAttribute("data-test-rect", JSON.stringify(rect));
}

let geomSpy: ReturnType<typeof vi.spyOn> | null = null;

beforeEach(() => {
  geomSpy = vi
    .spyOn(HTMLElement.prototype, "getBoundingClientRect")
    .mockImplementation(function (this: HTMLElement) {
      const raw = this.getAttribute("data-test-rect");
      const r: FakeRect = raw
        ? (JSON.parse(raw) as FakeRect)
        : { top: 0, left: 0, width: 0, height: 0 };
      return {
        top: r.top,
        left: r.left,
        width: r.width,
        height: r.height,
        right: r.left + r.width,
        bottom: r.top + r.height,
        x: r.left,
        y: r.top,
        toJSON() {
          return r;
        },
      } as DOMRect;
    });
});

afterEach(() => {
  geomSpy?.mockRestore();
  document.body.innerHTML = "";
});

/** Build an article root with claim spans at the given rects; the root itself is
 *  pinned at the origin so root-relative == absolute for simple assertions. */
function makeArticle(
  claims: { claimId: string; rect: FakeRect }[],
  rootRect: FakeRect = { top: 0, left: 0, width: 800, height: 4000 },
): HTMLElement {
  const root = document.createElement("article");
  installRect(root, rootRect);
  for (const c of claims) {
    const span = document.createElement("span");
    span.setAttribute(CLAIM_ID_ATTR, c.claimId);
    installRect(span, c.rect);
    root.appendChild(span);
  }
  document.body.appendChild(root);
  return root;
}

function claimAnchor(id: string): Anchor {
  return { kind: "claim", claimId: id as ClaimId };
}

describe("readingGeometryPass — M1: measured DOM → non-null rect through createLayoutMap", () => {
  it("resolves a KNOWN claim anchor to a NON-NULL rect (the happy-path proof)", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 100, left: 20, width: 600, height: 40 } },
      { claimId: "2", rect: { top: 200, left: 20, width: 600, height: 60 } },
    ]);
    const map = buildLayoutMap(root);

    const r1 = map.resolve(claimAnchor("1"));
    expect(r1).not.toBeNull();
    expect(r1).toEqual({ top: 100, left: 20, width: 600, height: 40 });

    const r2 = map.resolve(claimAnchor("2"));
    expect(r2).not.toBeNull();
    expect(r2!.height).toBe(60);
  });

  it("the mounted map is NOT EMPTY_LAYOUT_MAP — an anchor EMPTY resolves null now resolves real", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 50, left: 10, width: 400, height: 30 } },
    ]);
    // EMPTY_LAYOUT_MAP (the pre-measurement mount) resolves the anchor to null …
    expect(EMPTY_LAYOUT_MAP.resolve(claimAnchor("1"))).toBeNull();
    // … the LIVE map resolves it to a real rect. So replacing EMPTY with the live
    // map genuinely changes the resolved geometry (not a no-op rename).
    expect(buildLayoutMap(root).resolve(claimAnchor("1"))).not.toBeNull();
  });

  it("goes through baseGeometryFromMap → createLayoutMap (the designed seam, not a parallel build)", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 100, left: 20, width: 600, height: 40 } },
    ]);
    // Re-derive the SAME map by hand through the documented constructors and
    // assert the surface pass produced an identical resolution — proving it uses
    // baseGeometryFromMap + createLayoutMap, not a re-implementation.
    const rects = measureClaimGeometry(root);
    const handBuilt = createLayoutMap(baseGeometryFromMap(rects));
    expect(buildLayoutMap(root).resolve(claimAnchor("1"))).toEqual(
      handBuilt.resolve(claimAnchor("1")),
    );
  });
});

describe("readingGeometryPass — M1 failure modes (rigor #3)", () => {
  it("ZERO-HEIGHT anchor (not yet laid out) is DROPPED → resolves null (renders nothing)", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 0, left: 0, width: 0, height: 0 } }, // not laid out
      { claimId: "2", rect: { top: 120, left: 20, width: 600, height: 40 } }, // laid out
    ]);
    const map = buildLayoutMap(root);
    // The unlaid anchor is null (the layout-map "not laid out" contract) — NOT a
    // 0×0 rect pinning a widget at the document origin.
    expect(map.resolve(claimAnchor("1"))).toBeNull();
    // A genuinely laid-out anchor still resolves.
    expect(map.resolve(claimAnchor("2"))).not.toBeNull();
  });

  it("OFF-SCREEN anchor keeps its real rect at MEASURE time (scope, not measure, drops it)", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 9000, left: 20, width: 600, height: 40 } }, // far below fold
    ]);
    // measureClaimGeometry keeps it (it is laid out, just off-screen). The
    // UNSCOPED map resolves it — viewport-scoping (M3) is what would drop it.
    expect(buildLayoutMap(root).resolve(claimAnchor("1"))).not.toBeNull();
  });
});

describe("readingGeometryPass — M3: viewport-scoped recompute discipline", () => {
  it("short-circuits an OFF-BAND anchor to null while keeping an in-band one", () => {
    const root = makeArticle(
      [
        { claimId: "1", rect: { top: 100, left: 20, width: 600, height: 40 } }, // in view
        { claimId: "2", rect: { top: 9000, left: 20, width: 600, height: 40 } }, // off view
      ],
      // Root is the scroll reference; band = root box ± overscan, root-relative.
      { top: 0, left: 0, width: 800, height: 600 },
    );
    const band = buildViewportBand(root, root);
    const map = buildViewportScopedLayoutMap(root, band);
    expect(map.resolve(claimAnchor("1"))).not.toBeNull(); // in band → resolves
    expect(map.resolve(claimAnchor("2"))).toBeNull(); // off band → short-circuit null
  });
});

// ── M2 — minimap / collapse / marginalia against the LIVE map ────────────────

function resolvedClaimDecoration(claimId: string): ResolvedDecoration {
  const anchor = claimAnchor(claimId);
  return {
    anchor,
    key: anchorKey(anchor),
    classNames: ["review-due"],
    title: "Due today",
    widgets: [],
    ipHolderNames: [],
  };
}

describe("readingGeometryPass — M2: facets light up against the live map (wiring only)", () => {
  it("MINIMAP: a claim-anchored decoration projects to a NON-NULL minimap rect", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 400, left: 20, width: 600, height: 40 } },
    ]);
    const live = buildLayoutMap(root);
    const minimapLayout = minimapLayoutFrom(live, 0.1, 6);
    const marks = projectDecorationsToMinimap([resolvedClaimDecoration("1")], minimapLayout);
    expect(marks).toHaveLength(1);
    expect(marks[0].rect).not.toBeNull();
    // Compressed: minimap top = main top * scale, width = the minimap column.
    expect(marks[0].rect!.top).toBeCloseTo(40, 5);
    expect(marks[0].rect!.width).toBe(6);
    // The SAME resolved decoration the main view would paint (shared reference).
    expect(marks[0].decoration.classNames).toContain("review-due");
  });

  it("COLLAPSE: fingerprintPlan resolves a claim anchor through the live map (inside a band)", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 300, left: 20, width: 600, height: 40 } },
    ]);
    const live = buildLayoutMap(root);
    // A collapsed band covering the claim's measured top — the surface mints this
    // from the same measured geometry. The plan must see the anchor IN the band.
    const state = new CollapseState([
      { id: "sec-1", range: { topPx: 250, bottomPx: 400 } },
    ]);
    const plan = fingerprintPlan(
      [{ key: anchorKey(claimAnchor("1")), anchor: claimAnchor("1") }],
      live, // the LIVE pre-transform map (this sprint's pipeline is empty)
      state,
    );
    expect(plan).toHaveLength(1);
    expect(plan[0].inFingerprint).toBe(true);
    expect(plan[0].bandId).toBe("sec-1");
  });

  it("COLLAPSE: a claim OUTSIDE every band is not in any fingerprint (real rect, honest miss)", () => {
    const root = makeArticle([
      { claimId: "1", rect: { top: 1000, left: 20, width: 600, height: 40 } },
    ]);
    const live = buildLayoutMap(root);
    const state = new CollapseState([
      { id: "sec-1", range: { topPx: 0, bottomPx: 200 } },
    ]);
    const plan = fingerprintPlan(
      [{ key: anchorKey(claimAnchor("1")), anchor: claimAnchor("1") }],
      live,
      state,
    );
    expect(plan[0].inFingerprint).toBe(false);
    expect(plan[0].bandId).toBeNull();
  });

  it("MARGINALIA/ANCHORED-WIDGET: a widget anchored to a measured claim enacts to a real rect", () => {
    // Marginalia is the same anchored-widgets facet path; we prove a declared
    // anchored widget RESOLVES (non-null rect) against the live map. (Marginalia
    // itself anchors to PASSAGE anchors, which this claim-only DOM does not carry
    // — see the handoff: marginalia is genuinely dormant for passage targets until
    // the surface stamps passage markers. The facet PATH it shares is proved live.)
    const root = makeArticle([
      { claimId: "1", rect: { top: 500, left: 20, width: 600, height: 40 } },
    ]);
    const live = buildLayoutMap(root);
    // Use the chase-launcher (anchored-widgets facet) but pin it to a CLAIM anchor
    // we measured, to prove the facet enacts a non-null rect through the live map.
    const aug = makeChaseLauncherAugmentation({
      chunkId: "c1",
      start: 0,
      end: 5,
      passageText: "hello",
      parentInvestigationId: "inv-1",
    });
    const widgets = collectAnchoredWidgets([aug], {
      synthesis: { question: null, claims: [] },
      layout: live,
      substrate: {
        getChunk: () => Promise.reject(new Error("unused")),
      },
    }).all.map((p) => p.widget);
    // Re-pin the declared widget to a measured claim anchor (wiring proof: the
    // facet resolves whatever anchor it is handed against the live map).
    const repinned = widgets.map((w) => ({ ...w, anchor: claimAnchor("1") }));
    const enacted = resolveAnchoredWidgets(repinned, live);
    expect(enacted).toHaveLength(1);
    expect(enacted[0].rect).not.toBeNull();
    expect(enacted[0].rect!.top).toBe(500);
  });
});
