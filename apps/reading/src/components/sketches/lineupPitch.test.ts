/**
 * lineupPitch — determinism + layout invariants for the generative field.
 * Plain vitest assertions (the repo does not install jest-dom matchers).
 */

import { describe, expect, it } from "vitest";

import {
  DEFAULT_LINEUP_PITCH_PARAMS,
  layoutLineupPitch,
  renderLineupPitch,
  TEAM_EDGES,
} from "./lineupPitch";

function stubCtx(): CanvasRenderingContext2D {
  // Minimal op-recording stub: the render must never throw and must only
  // touch ctx methods/properties (no DOM, no Math.random).
  const target: Record<string, unknown> = {};
  const proxy = new Proxy(target, {
    get(obj, prop) {
      if (prop === "canvas") return { width: 400, height: 500 };
      if (prop === "createLinearGradient" || prop === "createRadialGradient") {
        return () => ({ addColorStop: () => undefined });
      }
      if (prop === "measureText") return () => ({ width: 0 });
      if (typeof prop === "string") {
        if (!(prop in obj)) {
          // Methods become no-ops; properties default to 0/empty.
          return () => undefined;
        }
        return obj[prop];
      }
      return undefined;
    },
    set(obj, prop, value) {
      obj[String(prop)] = value;
      return true;
    },
  });
  return proxy as unknown as CanvasRenderingContext2D;
}

describe("layoutLineupPitch", () => {
  it("is deterministic — same call, same layout", () => {
    const a = layoutLineupPitch();
    const b = layoutLineupPitch();
    expect(a.nodes).toEqual(b.nodes);
    expect(a.edges).toEqual(b.edges);
  });

  it("covers all nine formation roles at their fixed positions", () => {
    const layout = layoutLineupPitch();
    const ids = layout.nodes.map((n) => n.roleId).sort();
    expect(ids).toEqual([
      "critic",
      "data_miner",
      "data_refinement",
      "data_verification",
      "indexer",
      "media_creator",
      "orchestrator",
      "voice",
      "writer",
    ]);
    // Formation coordinates live in [0, 100] — the layout normalises to [0, 1].
    for (const n of layout.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0.1);
      expect(n.x).toBeLessThanOrEqual(0.9);
      expect(n.y).toBeGreaterThanOrEqual(0.1);
      expect(n.y).toBeLessThanOrEqual(0.95);
    }
  });

  it("builds the full team graph — every edge references real roles", () => {
    const layout = layoutLineupPitch();
    expect(layout.edges).toHaveLength(TEAM_EDGES.length);
    for (const e of layout.edges) {
      expect(e.a).toBeGreaterThanOrEqual(0);
      expect(e.b).toBeLessThan(layout.nodes.length);
    }
  });

  it("flags the five discovered roles", () => {
    const layout = layoutLineupPitch();
    const discovered = layout.nodes.filter((n) => n.discovered).map((n) => n.roleId).sort();
    expect(discovered).toEqual([
      "critic",
      "indexer",
      "media_creator",
      "orchestrator",
      "voice",
    ]);
  });
});

describe("renderLineupPitch", () => {
  it("renders a static frame under reduced motion without throwing", () => {
    const ctx = stubCtx();
    renderLineupPitch(ctx, 400, 500, {
      ...DEFAULT_LINEUP_PITCH_PARAMS,
      reducedMotion: true,
      mode: "night",
    });
    renderLineupPitch(ctx, 400, 500, {
      ...DEFAULT_LINEUP_PITCH_PARAMS,
      reducedMotion: true,
      mode: "day",
    });
    expect(true).toBe(true);
  });

  it("renders the animated frame (t advanced) without throwing", () => {
    const ctx = stubCtx();
    renderLineupPitch(ctx, 400, 500, {
      ...DEFAULT_LINEUP_PITCH_PARAMS,
      reducedMotion: false,
      t: 1240,
      mode: "night",
    });
    expect(true).toBe(true);
  });

  it("renders highlight + substitution burst params without throwing", () => {
    const ctx = stubCtx();
    renderLineupPitch(ctx, 400, 500, {
      ...DEFAULT_LINEUP_PITCH_PARAMS,
      reducedMotion: false,
      t: 300,
      mode: "day",
      highlightRole: "writer",
      pulseRole: "writer",
      pulseSeed: "zai:glm-5.2",
      pulseT: 100,
      mountWall: 1000,
    });
    // Burst aged past its lifespan fades to nothing — still no throw.
    renderLineupPitch(ctx, 400, 500, {
      ...DEFAULT_LINEUP_PITCH_PARAMS,
      reducedMotion: false,
      t: 2000,
      mode: "day",
      highlightRole: "writer",
      pulseRole: "writer",
      pulseSeed: "zai:glm-5.2",
      pulseT: 100,
      mountWall: 1000,
    });
    expect(true).toBe(true);
  });

  it("never calls Math.random or Date.now (purity)", () => {
    const random = Math.random;
    const now = Date.now;
    let randomCalls = 0;
    let nowCalls = 0;
    Math.random = () => {
      randomCalls += 1;
      return 0.5;
    };
    Date.now = () => {
      nowCalls += 1;
      return 42;
    };
    try {
      renderLineupPitch(stubCtx(), 400, 500, {
        ...DEFAULT_LINEUP_PITCH_PARAMS,
        reducedMotion: true,
        mode: "night",
      });
    } finally {
      Math.random = random;
      Date.now = now;
    }
    expect(randomCalls).toBe(0);
    expect(nowCalls).toBe(0);
  });
});
