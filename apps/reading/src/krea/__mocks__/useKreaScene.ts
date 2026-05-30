/**
 * Drop-in offline mock for `useKreaScene` (Mountain Shell SPR-02 M5).
 *
 * SPR-04 + CI use this so the living background renders with ZERO network and
 * NO Krea key. It returns the SAME `{status, art, error, isFallback}` contract
 * as the real hook, but ALWAYS the deterministic placeholder (isFallback:true)
 * — stable across runs, so SPR-04 snapshots don't flake.
 *
 * USAGE (vitest), in SPR-04's test or setup:
 *
 *   vi.mock("../krea/useKreaScene");   // auto-uses this file
 *
 * or import the fake directly:
 *
 *   import { useKreaScene } from "../krea/__mocks__/useKreaScene";
 *
 * To exercise the LIVE-art branch in a test, use `mockReadyScene(url)` to get a
 * fake that reports `status:"ready"` with a fixed image_url.
 */

import { deterministicPlaceholder, sceneKeyOf } from "../placeholder";
import type { SceneState } from "../../api/krea";
import type { KreaStatus, UseKreaScene } from "../useKreaScene";

export type { KreaArt, KreaStatus, UseKreaScene } from "../useKreaScene";

/** The default mock: always the deterministic fallback placeholder. */
export function useKreaScene(scene: SceneState): UseKreaScene {
  return {
    status: "fallback" as KreaStatus,
    isFallback: true,
    error: "mocked_offline",
    art: {
      image_url: deterministicPlaceholder(scene),
      scene_key: sceneKeyOf(scene),
      cached: false,
    },
  };
}

/** Factory: a fake hook reporting LIVE art with a fixed URL (for tests that
 *  want the ready branch). Still deterministic (no network). */
export function mockReadyScene(image_url: string) {
  return (scene: SceneState): UseKreaScene => ({
    status: "ready" as KreaStatus,
    isFallback: false,
    error: null,
    art: {
      image_url,
      scene_key: sceneKeyOf(scene),
      cached: false,
    },
  });
}
