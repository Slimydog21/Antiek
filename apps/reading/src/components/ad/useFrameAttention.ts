// Per-second in-frame IP-asset detection (SPR-07 M3).
//
// Once per second, compute which IP assets are visible in the WORKING REGION
// and produce one FrameSecond of FrameAttentionSamples (the M4 emitter buffers
// them). "In frame" is defined narrowly and testably (rigor #3, defensibility
// #5): a viewport-visible rendered/cited IP asset INSIDE the working region.
// The border's own creatives and the nav chrome are EXCLUDED — the border must
// not monetize attention to itself.
//
// DOM CONTRACT — how a rendered chunk exposes its asset_id:
//   Working-region content that is an IP asset carries `data-akb-asset-id`
//   (the document/asset id, the trace anchor) and optionally
//   `data-akb-chunk-id` (the specific chunk). Anything inside an element marked
//   `data-akb-ad-border` (the border) or `[data-akb-nav]` / role=navigation is
//   excluded. An element that looks like content but has no resolvable
//   asset id is EXCLUDED and COUNTED (the `unresolved` count) — never guessed
//   to inflate coverage (rigor #1).
//
// This is the seam SPR-06 left implicit: the four lenses render inside the
// shell's main slot, so the sampler scans `[data-akb-shell-frame]`'s working
// region. As lens surfaces adopt `data-akb-asset-id` on their rendered IP
// content (a one-line attribute, see handoff), they light up automatically —
// no per-lens fork.

import { useEffect, useRef } from "react";

import type { FrameAttentionSample, FrameSecond, Lens } from "./frameContract";

const ASSET_ATTR = "data-akb-asset-id";
const CHUNK_ATTR = "data-akb-chunk-id";
const SAMPLE_INTERVAL_MS = 1000;

export interface FrameAttentionResult {
  second: FrameSecond;
  /** Working-region elements that looked like content but had no resolvable
   *  asset id — excluded from the samples, counted here. Honesty over coverage. */
  unresolved: number;
}

export interface UseFrameAttentionOptions {
  lens: Lens;
  /** The current window's id. When it changes (a lens switch is a new window)
   *  the sampler restarts: ``second_index`` returns to 0 so the new window's
   *  batch is 0-based per the contract. Optional so a static story can omit it. */
  windowId?: string;
  /** Called once per second with the in-frame asset set for that second. */
  onSecond: (result: FrameAttentionResult) => void;
  /** The scroll/measurement root — the working region. Defaults to the
   *  shell frame. The border + nav inside it are excluded by marker. */
  rootSelector?: string;
  /** Off by default in non-browser/test envs unless a clock is injected. */
  enabled?: boolean;
}

/** Is `el` inside the ad border or the nav chrome (i.e. NOT working content)? */
function isChrome(el: Element): boolean {
  return Boolean(
    el.closest("[data-akb-ad-border]") ||
      el.closest("[data-akb-nav]") ||
      el.closest('[role="navigation"]'),
  );
}

/**
 * Geometry → the three per-asset features, for one element this second.
 *
 *  - viewport_area_fraction: the element's VISIBLE area (intersection with the
 *    viewport) as a fraction of the viewport area, clamped [0,1].
 *  - prominence: center-weighting — 1.0 when the element's visible centroid is
 *    at the viewport center, falling to 0 at the edges (Chebyshev distance to
 *    center, normalized). Mirrors reader_slots' position-categorical idea as a
 *    continuous signal, since the border wraps the frame.
 */
function measure(el: Element): { area: number; prominence: number } | null {
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vw <= 0 || vh <= 0) return null;

  const visLeft = Math.max(0, r.left);
  const visTop = Math.max(0, r.top);
  const visRight = Math.min(vw, r.right);
  const visBottom = Math.min(vh, r.bottom);
  const visW = visRight - visLeft;
  const visH = visBottom - visTop;
  if (visW <= 0 || visH <= 0) return null; // off-screen this second

  const area = Math.min(1, (visW * visH) / (vw * vh));

  const cx = (visLeft + visRight) / 2;
  const cy = (visTop + visBottom) / 2;
  // Normalized distance of the visible centroid from the viewport center, in
  // [0,1] per axis; prominence is 1 at center, 0 at the far edge.
  const dx = Math.abs(cx - vw / 2) / (vw / 2);
  const dy = Math.abs(cy - vh / 2) / (vh / 2);
  const prominence = Math.max(0, 1 - Math.max(dx, dy));

  return { area, prominence };
}

/**
 * Focused dwell for this second, in [0,1000] ms. Counts only when the tab is
 * foregrounded AND the page is "still" (no scroll since the last sample) OR a
 * selection/caret is active — mirroring reader_impressions' rule that dwell
 * while hidden/idle does not count. A scrolling-past second earns less dwell
 * than a paused-reading second; a hidden tab earns zero.
 */
function dwellMs(opts: { scrolledSinceLast: boolean; hasSelection: boolean }): number {
  if (typeof document !== "undefined" && document.visibilityState === "hidden") {
    return 0;
  }
  if (typeof document !== "undefined" && document.hasFocus && !document.hasFocus()) {
    return 0;
  }
  if (opts.hasSelection) return 1000;
  if (opts.scrolledSinceLast) return 250; // glancing past while scrolling
  return 1000; // paused on the content this whole second
}

export function useFrameAttention(opts: UseFrameAttentionOptions): void {
  const { lens, windowId, onSecond, rootSelector = "[data-akb-shell-frame]", enabled = true } = opts;
  // Keep the callback fresh without re-arming the 1Hz timer (rigor #3: no spin).
  const onSecondRef = useRef(onSecond);
  onSecondRef.current = onSecond;
  const lensRef = useRef<Lens>(lens);
  lensRef.current = lens;

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    let secondIndex = 0;
    let scrolledSinceLast = false;
    const onScroll = () => {
      scrolledSinceLast = true;
    };
    // Passive scroll listener only flips a boolean — no per-frame work, no rAF
    // loop. The sole periodic worker is the 1Hz interval below.
    window.addEventListener("scroll", onScroll, { passive: true, capture: true });

    const tick = () => {
      const root =
        document.querySelector(rootSelector) ?? document.body ?? document.documentElement;
      if (!root) return;

      const sel = window.getSelection();
      const hasSelection = Boolean(sel && !sel.isCollapsed && sel.toString().trim().length > 0);
      const dwell = dwellMs({ scrolledSinceLast, hasSelection });
      scrolledSinceLast = false;

      // One sample per resolvable asset; later in-frame chunks of the same
      // asset fold into the asset's max-visibility sample (the ASSET is the
      // monetized unit). Unresolved-looking content is counted, never guessed.
      const byAsset = new Map<string, FrameAttentionSample>();
      let unresolved = 0;

      const candidates = root.querySelectorAll<HTMLElement>(`[${ASSET_ATTR}]`);
      candidates.forEach((el) => {
        if (isChrome(el)) return;
        const assetId = el.getAttribute(ASSET_ATTR);
        if (!assetId) {
          unresolved += 1;
          return;
        }
        const m = measure(el);
        if (!m) return; // not visible this second
        const chunkId = el.getAttribute(CHUNK_ATTR);
        const prev = byAsset.get(assetId);
        // Per-asset, keep the most-visible chunk this second (max area) so an
        // asset shown across several chunks earns off its largest footprint.
        if (!prev || m.area > prev.viewport_area_fraction) {
          byAsset.set(assetId, {
            asset_id: assetId,
            viewport_area_fraction: m.area,
            prominence: m.prominence,
            focused_dwell_ms: dwell,
            chunk_id: chunkId ?? undefined,
          });
        }
      });

      const second: FrameSecond = {
        second_index: secondIndex,
        lens: lensRef.current,
        samples: Array.from(byAsset.values()),
      };
      secondIndex += 1;
      onSecondRef.current({ second, unresolved });
    };

    const timer = setInterval(tick, SAMPLE_INTERVAL_MS);
    return () => {
      clearInterval(timer);
      window.removeEventListener("scroll", onScroll, { capture: true } as EventListenerOptions);
    };
    // windowId in the deps so a lens switch (new window) re-arms the sampler
    // and restarts second_index at 0 — each window's batch is 0-based.
  }, [enabled, rootSelector, windowId]);
}
