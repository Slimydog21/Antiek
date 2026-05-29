/**
 * useFrameAttention.test.ts — SPR-07 M3 acceptance.
 *
 * Load-bearing claims (each ASSERTED, not eyeballed):
 *  - samples at ~1 Hz (one FrameSecond per second, second_index increments
 *    0,1,2…) and does NOT spin between samples (the only periodic worker is
 *    the 1 Hz interval — a passive scroll listener that flips a boolean is the
 *    only other handler);
 *  - computes per-asset viewport_area_fraction ∈ [0,1] and prominence ∈ [0,1]
 *    from element geometry, and focused_dwell_ms ∈ [0,1000];
 *  - EXCLUDES the ad-border's own creatives and the nav chrome (it must not
 *    monetize attention to itself);
 *  - an element carrying the asset marker but no resolvable id is EXCLUDED and
 *    COUNTED in `unresolved` — never guessed to inflate coverage;
 *  - folds multiple in-frame chunks of one asset into the asset's
 *    largest-footprint sample (the ASSET is the monetized unit).
 *
 * jsdom has no layout, so getBoundingClientRect returns 0×0 by default. Each
 * test stamps a rect via a data attribute and a getBoundingClientRect stub so
 * geometry is deterministic — the SAME approach the repo's other geometry
 * tests use, not a real browser.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { useFrameAttention, type FrameAttentionResult } from "./useFrameAttention";

const VW = 1000;
const VH = 800;

/** Give an element a deterministic rect for getBoundingClientRect. */
function stampRect(
  el: HTMLElement,
  rect: { left: number; top: number; width: number; height: number },
): void {
  el.getBoundingClientRect = () =>
    ({
      left: rect.left,
      top: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      width: rect.width,
      height: rect.height,
      x: rect.left,
      y: rect.top,
      toJSON: () => ({}),
    }) as DOMRect;
}

function assetEl(
  assetId: string | null,
  rect: { left: number; top: number; width: number; height: number },
  opts?: { chunkId?: string; chrome?: "border" | "nav" },
): HTMLElement {
  const el = document.createElement("div");
  if (assetId !== null) el.setAttribute("data-akb-asset-id", assetId);
  else el.setAttribute("data-akb-asset-id", ""); // present but unresolvable
  if (opts?.chunkId) el.setAttribute("data-akb-chunk-id", opts.chunkId);
  stampRect(el, rect);
  if (opts?.chrome === "border") {
    const wrap = document.createElement("div");
    wrap.setAttribute("data-akb-ad-border", "");
    wrap.appendChild(el);
    document.body.appendChild(wrap);
  } else if (opts?.chrome === "nav") {
    const wrap = document.createElement("nav");
    wrap.setAttribute("role", "navigation");
    wrap.appendChild(el);
    document.body.appendChild(wrap);
  } else {
    document.body.appendChild(el);
  }
  return el;
}

beforeEach(() => {
  vi.useFakeTimers();
  Object.defineProperty(window, "innerWidth", { value: VW, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: VH, configurable: true });
  Object.defineProperty(document, "visibilityState", {
    value: "visible",
    configurable: true,
  });
  document.hasFocus = () => true;
  // The sampler scans [data-akb-shell-frame]; in these tests body IS the root
  // (the selector falls back to document.body when the frame is absent).
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("useFrameAttention — 1 Hz sampling (M3)", () => {
  it("emits one FrameSecond per second with an incrementing 0-based index", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl("doc-1", { left: 0, top: 0, width: VW, height: VH });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );

    vi.advanceTimersByTime(1000);
    vi.advanceTimersByTime(1000);
    vi.advanceTimersByTime(1000);

    expect(seconds).toHaveLength(3);
    expect(seconds.map((s) => s.second.second_index)).toEqual([0, 1, 2]);
    expect(seconds[0]!.second.lens).toBe("read");
  });

  it("does not emit before a full second elapses (no spin)", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl("doc-1", { left: 0, top: 0, width: VW, height: VH });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(999);
    expect(seconds).toHaveLength(0);
    vi.advanceTimersByTime(1);
    expect(seconds).toHaveLength(1);
  });

  it("is disabled when enabled=false", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl("doc-1", { left: 0, top: 0, width: VW, height: VH });
    renderHook(() =>
      useFrameAttention({ lens: "read", enabled: false, onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(3000);
    expect(seconds).toHaveLength(0);
  });
});

describe("useFrameAttention — geometry features (M3)", () => {
  it("computes area∈[0,1] and prominence∈[0,1] for a centered full-viewport asset", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl("doc-1", { left: 0, top: 0, width: VW, height: VH });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);

    const s = seconds[0]!.second.samples;
    expect(s).toHaveLength(1);
    expect(s[0]!.asset_id).toBe("doc-1");
    expect(s[0]!.viewport_area_fraction).toBeCloseTo(1, 5); // fills the viewport
    expect(s[0]!.prominence).toBeCloseTo(1, 5); // centered → max prominence
    expect(s[0]!.focused_dwell_ms).toBeGreaterThanOrEqual(0);
    expect(s[0]!.focused_dwell_ms).toBeLessThanOrEqual(1000);
  });

  it("clamps area to the VISIBLE intersection for a half-off-screen asset", () => {
    const seconds: FrameAttentionResult[] = [];
    // Half above the top edge: only the bottom half is visible.
    assetEl("doc-1", { left: 0, top: -VH / 2, width: VW, height: VH });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);
    expect(seconds[0]!.second.samples[0]!.viewport_area_fraction).toBeCloseTo(0.5, 2);
  });

  it("drops a fully off-screen asset (no sample)", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl("doc-1", { left: 0, top: -VH - 100, width: VW, height: VH });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);
    expect(seconds[0]!.second.samples).toHaveLength(0);
  });
});

describe("useFrameAttention — exclusions + honesty (M3)", () => {
  it("excludes the ad-border's own creatives and the nav chrome", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl("border-creative", { left: 0, top: 0, width: VW, height: 40 }, { chrome: "border" });
    assetEl("nav-thing", { left: 0, top: 0, width: VW, height: 40 }, { chrome: "nav" });
    assetEl("doc-content", { left: 0, top: 100, width: VW, height: 400 });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);
    const ids = seconds[0]!.second.samples.map((s) => s.asset_id);
    expect(ids).toEqual(["doc-content"]);
  });

  it("excludes AND counts an asset-marked element with no resolvable id", () => {
    const seconds: FrameAttentionResult[] = [];
    assetEl(null, { left: 0, top: 0, width: VW, height: VH }); // empty asset id
    assetEl("doc-1", { left: 0, top: 0, width: VW, height: 200 });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);
    expect(seconds[0]!.unresolved).toBe(1);
    expect(seconds[0]!.second.samples.map((s) => s.asset_id)).toEqual(["doc-1"]);
  });

  it("folds multiple chunks of one asset into its largest-footprint sample", () => {
    const seconds: FrameAttentionResult[] = [];
    // Two chunks of the SAME asset; the larger one wins the per-asset sample.
    assetEl("doc-1", { left: 0, top: 0, width: VW, height: 100 }, { chunkId: "c-small" });
    assetEl("doc-1", { left: 0, top: 100, width: VW, height: 400 }, { chunkId: "c-big" });
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);
    const samples = seconds[0]!.second.samples;
    expect(samples).toHaveLength(1);
    expect(samples[0]!.chunk_id).toBe("c-big");
  });
});
