import { useEffect, useRef, useState } from "react";

import { useKreaScene, type UseKreaScene } from "../krea/useKreaScene";
import type { SceneFetcher } from "../krea/useKreaScene";
import { moodKey, sceneStateFromMood, type SceneMood } from "./mood";

/**
 * useSceneArt — periodic Krea art refresh for the sky/peak layers (SPR-04
 * milestone 4).
 *
 * THE CADENCE INVARIANT (the thing the cadence test guards):
 *   Krea is asked for new art ONLY when the MOOD changes — never per frame,
 *   never on the rAF clock. The living motion (clouds/snow/parallax) runs at
 *   60fps off `useSceneClock`; the ART underneath it changes at most a handful
 *   of times a session (dawn→day→dusk→night, or a weather shift). We achieve
 *   this structurally: `useKreaScene` re-fetches only when its scene-state KEY
 *   changes (see its `[key]` effect dep), and we feed it a scene-state derived
 *   purely from the mood. The clock is NOT a dependency here, so no amount of
 *   ticking can trigger a fetch. A test asserts the underlying fetcher is
 *   called once per mood, not once per frame.
 *
 * CROSSFADE: when the mood changes and new art resolves, we keep the PREVIOUS
 * art around as `prevImageUrl` and bump `fadeKey` so the Scene can crossfade
 * the old sky into the new one (a CSS opacity transition on the art layer),
 * rather than hard-cutting. The crossfade is presentational; the fetch cadence
 * is unaffected.
 *
 * DEGRADATION: `useKreaScene` NEVER throws and ALWAYS returns non-null `art`
 * (the deterministic placeholder when `isFallback`). So over-budget /
 * kill-switch / offline / no-key all collapse to `isFallback: true` and the
 * Scene simply renders procedural-only (it ignores the placeholder data-URI as
 * a sky source and leans on ProceduralSky). We surface `isFallback` so the
 * Scene can make that choice seamlessly.
 */

export interface SceneArt {
  /** A live Krea image URL to paint into the sky/peak layers, or null when in
   *  fallback (procedural-only). NEVER the placeholder data-URI — the Scene
   *  owns a richer hand-authored fallback than a 16×16 gradient. */
  imageUrl: string | null;
  /** The previous live image URL during a crossfade (null otherwise). */
  prevImageUrl: string | null;
  /** Bumped each time live art swaps — the Scene keys its crossfade on this. */
  fadeKey: number;
  /** True ⇒ no live art; render procedural-only. */
  isFallback: boolean;
  /** The raw hook status, for debugging / future UI. */
  status: UseKreaScene["status"];
  /** Honest fallback reason (e.g. "no_key", "over_daily_budget"), or null. */
  reason: string | null;
}

/**
 * Wrap `useKreaScene` to drive periodic, mood-gated art refresh + crossfade.
 *
 * @param mood        the current scene mood (from the theme); changing it is
 *                    the ONLY thing that triggers a new Krea fetch.
 * @param fetchScene  injectable fetcher for tests (defaults to the real
 *                    client inside `useKreaScene`).
 */
export function useSceneArt(
  mood: SceneMood,
  fetchScene?: SceneFetcher,
): SceneArt {
  const sceneState = sceneStateFromMood(mood);
  // `useKreaScene` re-fetches only when the normalized scene-state key changes
  // — which, because `sceneState` is a pure function of `mood`, means only on
  // mood change. The clock is intentionally NOT involved.
  // One unconditional hook call (Rules of Hooks): useKreaScene defaults its
  // fetcher to the real client, so an undefined `fetchScene` (production)
  // resolves to it while tests inject their own — same hook, every render.
  const krea = useKreaScene(sceneState, fetchScene);

  const [fadeKey, setFadeKey] = useState(0);
  const prevUrlRef = useRef<string | null>(null);
  const curUrlRef = useRef<string | null>(null);
  const moodRef = useRef<string>(moodKey(mood));

  // Live art = the hook's image_url only when NOT fallback. On fallback we use
  // null so the Scene renders ProceduralSky rather than the 16×16 placeholder.
  const liveUrl = !krea.isFallback && krea.art ? krea.art.image_url : null;

  useEffect(() => {
    const mk = moodKey(mood);
    const moodChanged = mk !== moodRef.current;
    const urlChanged = liveUrl !== curUrlRef.current;
    if (urlChanged) {
      // Promote current → prev for the crossfade (only when we have a real
      // outgoing URL to fade from).
      prevUrlRef.current = curUrlRef.current;
      curUrlRef.current = liveUrl;
      // Bump the fade key so the Scene re-triggers its opacity transition.
      setFadeKey((k) => k + 1);
    }
    if (moodChanged) moodRef.current = mk;
    // Depend on the live URL + the mood key — NOT on any clock value.
  }, [liveUrl, mood]);

  return {
    imageUrl: curUrlRef.current,
    prevImageUrl: prevUrlRef.current,
    fadeKey,
    isFallback: krea.isFallback,
    status: krea.status,
    reason: krea.error,
  };
}
