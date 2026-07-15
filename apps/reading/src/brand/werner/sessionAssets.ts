/**
 * Session-refined Werner brand assets (Imagine + Codex image, 2026-07-12).
 *
 * Integrated into the brand tree so UI can import them — not loose one-offs.
 * Canonical four-mood product mark remains `Werner.tsx` (anchor transparent
 * poses). These session assets are cabinet key-art + optional emote polish.
 *
 * Alpha honesty (2026-07-15): ice-fishing + zombies product PNGs are residual-
 * fringe flood-cut so all four canvas corners are alpha=0 (see
 * cut_session_fringe.py + sessionAssets.integrity.test.ts). Opaque provenance
 * lives beside them as `*_opaque_provenance.png`.
 */

import celebrate from "./poses/session/werner_celebrate_session_v1.png";
import thinking from "./poses/session/werner_thinking_session_v1.png";
import iceFishing from "./poses/session/werner_ice_fishing_session_v1.png";
import zombies from "./poses/session/werner_zombies_session_v1.png";

export const SESSION_BRAND_ASSETS = {
  celebrate,
  thinking,
  iceFishing,
  zombies,
} as const;

export type SessionBrandAssetId = keyof typeof SESSION_BRAND_ASSETS;

export function sessionBrandAssetUrl(id: SessionBrandAssetId): string {
  return SESSION_BRAND_ASSETS[id];
}

/** Inventory for integrity / integration tests. */
export const SESSION_BRAND_ASSET_IDS: readonly SessionBrandAssetId[] = [
  "celebrate",
  "thinking",
  "iceFishing",
  "zombies",
] as const;
