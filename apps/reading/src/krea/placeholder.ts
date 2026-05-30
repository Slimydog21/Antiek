/**
 * Deterministic offline placeholder for the living background (SPR-02 M5).
 *
 * When Krea is disabled (no key / kill-switch / over-budget) or unreachable
 * (offline / upstream failure), the hook returns THIS as the art so the
 * background always has something to paint. It is DETERMINISTIC: the same
 * scene-state always produces the byte-identical data-URI — no Date.now, no
 * Math.random — so SPR-04's snapshot tests are stable across runs.
 *
 * This is a lightweight gradient SVG, NOT a rendered scene: SPR-04 owns the
 * actual visuals (this sprint is OOS for rendering). It just guarantees a
 * stable, scene-tinted backdrop the moment the page loads, before/without any
 * generation.
 */

import type { SceneState } from "../api/krea";

/** Normalize one scene axis the SAME way the server does (lowercase,
 *  alphanumeric-only, "any" when empty) so the client key matches the
 *  server's `scene_key`. */
function norm(s: string): string {
  const cleaned = (s ?? "").trim().toLowerCase().replace(/[^a-z0-9]/g, "");
  return cleaned || "any";
}

/**
 * The scene-state key. Mirrors `scene_key()` in krea_routes.py so the client
 * placeholder key and the server cache key never disagree. DETERMINISTIC.
 */
export function sceneKeyOf(scene: SceneState): string {
  return `${norm(scene.mood)}|${norm(scene.dayNight)}|${norm(scene.season)}`;
}

/** Stable 32-bit hash of a string (FNV-1a). Pure + deterministic — used only
 *  to pick stable gradient hues from the scene-state. */
function hash32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  // To unsigned.
  return h >>> 0;
}

/**
 * Build a deterministic gradient-SVG data-URI for a scene-state. The two
 * stop hues are derived from the scene key's hash, so distinct scene-states
 * get distinct (but stable) tints, and night scenes are darkened. Returns a
 * `data:image/svg+xml,...` URI usable directly as a CSS background or <img>
 * src.
 */
export function deterministicPlaceholder(scene: SceneState): string {
  const key = sceneKeyOf(scene);
  const h = hash32(key);
  const hueTop = h % 360;
  const hueBottom = (hueTop + 40) % 360;
  const isNight = norm(scene.dayNight) === "night";
  const lTop = isNight ? 18 : 72;
  const lBottom = isNight ? 8 : 54;
  // No quotes in the SVG so the data-URI needs no extra escaping beyond the
  // few reserved chars we encode below; keeps the output byte-stable.
  const svg = [
    "<svg xmlns=http://www.w3.org/2000/svg width=16 height=16",
    " viewBox=0 0 16 16 preserveAspectRatio=none>",
    "<defs><linearGradient id=g x1=0 y1=0 x2=0 y2=1>",
    `<stop offset=0 stop-color=hsl(${hueTop},45%,${lTop}%)/>`,
    `<stop offset=1 stop-color=hsl(${hueBottom},50%,${lBottom}%)/>`,
    "</linearGradient></defs>",
    "<rect width=16 height=16 fill=url(#g)/>",
    "</svg>",
  ].join("");
  // Encode the handful of chars that are unsafe in a data-URI. Deterministic.
  const encoded = svg
    .replace(/%/g, "%25")
    .replace(/</g, "%3C")
    .replace(/>/g, "%3E")
    .replace(/#/g, "%23")
    .replace(/"/g, "%22");
  return `data:image/svg+xml,${encoded}`;
}
