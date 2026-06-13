/**
 * useKreaScene — the React hook SPR-04's living mountain background consumes.
 * (Mountain Shell SPR-02, milestone 5.)
 *
 * CONTRACT (the seam SPR-04 builds against — DO NOT change without updating
 * src/krea/README.md):
 *
 *   const { status, art, error, isFallback } = useKreaScene(scene);
 *
 *   - status: "idle" | "loading" | "ready" | "fallback"
 *   - art:    KreaArt | null         (image_url + scene_key + cached; the
 *                                      DETERMINISTIC PLACEHOLDER when isFallback)
 *   - error:  string | null          (a human reason when fallback; never thrown)
 *   - isFallback: boolean            (true ⇒ art is the deterministic placeholder)
 *
 * GUARANTEES:
 *   1. NEVER throws. Disabled (no key / kill-switch / over-budget) / offline /
 *      any upstream failure → isFallback: true + a deterministic placeholder.
 *   2. The placeholder is DETERMINISTIC: the same scene-state always yields the
 *      same data-URI, so SPR-04 snapshots are stable across runs (no Date.now,
 *      no Math.random).
 *   3. `art` is ALWAYS non-null after the first resolve — on fallback it is the
 *      placeholder — so the background always has something to paint.
 *
 * TESTING: the pure resolver `resolveScene(scene, fetchScene)` is exported and
 * is the unit-test seam (success / disabled / error→fallback) with `fetchScene`
 * mocked — no network, no React renderer required. A drop-in fake hook lives at
 * `src/krea/__mocks__/useKreaScene.ts` so SPR-04 + CI run fully offline.
 */

import { useEffect, useRef, useState } from "react";

import { requestScene } from "../api/krea";
import type { SceneResult, SceneState } from "../api/krea";
import { isSceneArt } from "../api/krea";
import { deterministicPlaceholder, sceneKeyOf } from "./placeholder";

export type KreaStatus = "idle" | "loading" | "ready" | "fallback";

export interface KreaArt {
  /** A live generated URL when ready; a deterministic data-URI when fallback. */
  image_url: string;
  /** Normalized scene-state key (matches the server's cache key). */
  scene_key: string;
  /** True when served from the server warm cache (false for live + placeholder). */
  cached: boolean;
}

export interface UseKreaScene {
  status: KreaStatus;
  art: KreaArt | null;
  error: string | null;
  isFallback: boolean;
}

/** The fetch seam — the hook calls this; tests inject a fake. Defaults to the
 *  real `/krea/scene` client. */
export type SceneFetcher = (scene: SceneState) => Promise<SceneResult>;

/**
 * PURE resolver — the unit-test seam. Given a scene-state and a fetcher,
 * resolves to the hook's `{status, art, error, isFallback}` shape. NEVER
 * throws: any rejection from the fetcher, any disabled/over-budget response,
 * or a missing image collapses to the deterministic placeholder.
 */
export async function resolveScene(
  scene: SceneState,
  fetchScene: SceneFetcher = requestScene,
): Promise<UseKreaScene> {
  let result: SceneResult;
  try {
    result = await fetchScene(scene);
  } catch (e) {
    // Defensive: the client already turns network failures into a typed
    // fallback, but if anything escapes we STILL never throw.
    return fallback(scene, reasonOf(e) ?? "offline");
  }
  if (isSceneArt(result)) {
    return {
      status: "ready",
      isFallback: false,
      error: null,
      art: {
        image_url: result.image_url,
        scene_key: result.scene_key,
        cached: result.cached,
      },
    };
  }
  // Disabled / over-budget / upstream-failure → deterministic placeholder.
  return fallback(scene, result.reason);
}

/** Build the deterministic-placeholder fallback state for a scene + reason. */
function fallback(scene: SceneState, reason: string): UseKreaScene {
  const scene_key = sceneKeyOf(scene);
  return {
    status: "fallback",
    isFallback: true,
    error: reason,
    art: {
      image_url: deterministicPlaceholder(scene),
      scene_key,
      cached: false,
    },
  };
}

function reasonOf(e: unknown): string | null {
  if (e instanceof Error && e.message) return e.message;
  return null;
}

/**
 * The React hook. Resolves art for `scene` on mount + whenever the
 * scene-state changes. While in flight, `status` is "loading" but `art` is
 * already the deterministic placeholder, so the background paints the
 * placeholder immediately and swaps to live art when it arrives. A stale
 * resolution (the scene changed mid-flight) is discarded.
 *
 * `fetchScene` is injectable for tests; production uses the real client.
 */
export function useKreaScene(
  scene: SceneState,
  fetchScene: SceneFetcher = requestScene,
): UseKreaScene {
  // Seed with the deterministic placeholder so `art` is never null and the
  // first paint is stable (no flash of nothing).
  const [state, setState] = useState<UseKreaScene>(() => ({
    status: "loading",
    isFallback: true,
    error: null,
    art: {
      image_url: deterministicPlaceholder(scene),
      scene_key: sceneKeyOf(scene),
      cached: false,
    },
  }));

  const key = sceneKeyOf(scene);
  const reqId = useRef(0);

  useEffect(() => {
    // IN-FLIGHT DEDUP is delegated to the server cache BY DESIGN: re-entering a
    // key whose fetch is still pending fires a second request, but the server's
    // warm-cache answers it cheaply and the reqId stale-discard below drops any
    // out-of-order resolution. From the binary OS-theme mood this is unreachable
    // at a meaningful rate, so a client-side in-flight registry is not worth its
    // complexity — the server cache + reqId are the dedup layer.
    const myId = ++reqId.current;
    let cancelled = false;
    // Show the placeholder for THIS scene while loading.
    setState((prev) => ({
      ...prev,
      status: "loading",
      art: prev.art && prev.art.scene_key === key
        ? prev.art
        : {
            image_url: deterministicPlaceholder(scene),
            scene_key: key,
            cached: false,
          },
    }));
    resolveScene(scene, fetchScene)
      .then((resolved) => {
        if (cancelled || myId !== reqId.current) return; // stale — discard
        setState(resolved);
      })
      .catch(() => {
        // resolveScene never rejects, but belt-and-braces: never throw.
        if (cancelled || myId !== reqId.current) return;
        setState(fallback(scene, "offline"));
      });
    return () => {
      cancelled = true;
    };
    // Re-run only when the normalized scene-state key changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}
