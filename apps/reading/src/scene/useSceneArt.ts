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
 *
 * ─── THE §4 FRAME-SOURCE SEAM (AMS-v2 SPR-05, M1 — HONEST NO-GO) ───────────
 * SPR-02's feasibility spike (docs/ams-v2/stream-spike.md) returned a **NO-GO**
 * on a near-real-time *generative* stream: the doc-derived ceiling is ~0.25 gen
 * fps (Flux ~4s/image) against a ≥10 fps requirement, at ~$0.60/min that
 * exhausts the 50-unit cap in ~3.3 min. So there is NO live stream, and SPR-05
 * adds NO streaming endpoint (no SSE / WebSocket / EventSource on krea_routes.py
 * — verified zero on origin/main). The shipped path is this one: a 60fps
 * procedural floor (useSceneClock → Clouds/Snow canvases) with PERIODIC,
 * mood-gated Krea art crossfaded over it.
 *
 * The §4 "frame-source seam" the spike specifies is therefore the EXISTING
 * `SceneFetcher` type (`../krea/useKreaScene` L58:
 *   `export type SceneFetcher = (scene: SceneState) => Promise<SceneResult>`).
 * It is the single, typed swap point: `useSceneArt` injects a `fetchScene` into
 * `useKreaScene`, which re-fetches ONLY when `sceneKeyOf(scene)` changes — never
 * per frame, never on the clock. A FUTURE "GO" (a benchmarked sub-second turbo
 * model, or an L411 server-side pump) would swap the concrete `SceneFetcher`
 * here; every consumer (useSceneArt → KreaArtLayer → Scene) is untouched.
 *
 * DECISION (M1): we did NOT create a `useSceneStream.ts`. On a NO-GO it would
 * be a hook wrapping a hook with no behavioural content, and naming it "stream"
 * would misdescribe a non-stream — both worse engineering than naming the seam
 * that already exists. `SceneFetcher` IS the §4 frame-source seam; it fully
 * serves, so `useSceneStream.ts` is unnecessary. See the handoff for the
 * fairness/rigor steelman behind this call.
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

  // Live art = the hook's image_url only when the fetch has RESOLVED to live
  // art (status "ready"). On fallback we use null so the Scene renders
  // ProceduralSky rather than the 16×16 placeholder.
  //
  // Why gate on status === "ready" and not just !isFallback (SPR-05 M2 fix): on
  // a MOOD CHANGE, useKreaScene re-enters "loading" and seeds `art` with the new
  // scene-state's deterministic PLACEHOLDER while it spreads the PREVIOUS
  // resolve's `isFallback:false`. With a bare `!isFallback` guard that transient
  // leaks the placeholder data-URI in as a "live" URL, so the crossfade would
  // briefly promote the 16×16 gradient placeholder into prevImageUrl/imageUrl —
  // a momentary flash of the placeholder BETWEEN two real arts (a hard-cut-ish
  // blip, not the from-old-art-to-new-art crossfade the contract promises).
  // "ready" is the only status whose `art.image_url` is a genuine live URL, so
  // gating on it makes the crossfade fade old-live → new-live cleanly.
  const liveUrl =
    krea.status === "ready" && !krea.isFallback && krea.art
      ? krea.art.image_url
      : null;

  const fallback = krea.isFallback;

  useEffect(() => {
    const mk = moodKey(mood);
    const moodChanged = mk !== moodRef.current;

    if (liveUrl != null) {
      // A genuine NEW live URL resolved → crossfade old-live → new-live.
      // Promote current → prev so KreaArtLayer fades the OUTGOING real art out
      // (prev stays null on the very first art) and bump fadeKey to re-trigger
      // the opacity transition. (liveUrl is only ever the "ready" URL — never
      // the loading placeholder — so this never fades from the 16×16 gradient.)
      if (liveUrl !== curUrlRef.current) {
        prevUrlRef.current = curUrlRef.current;
        curUrlRef.current = liveUrl;
        setFadeKey((k) => k + 1);
      }
    } else if (fallback) {
      // A genuine fallback (no key / over-budget / kill-switch / offline) → no
      // live art at all; drop to procedural-only. Clear refs so imageUrl is
      // null and the Scene flags data-scene-fallback.
      if (curUrlRef.current !== null || prevUrlRef.current !== null) {
        prevUrlRef.current = null;
        curUrlRef.current = null;
        setFadeKey((k) => k + 1);
      }
    }
    // else: status is "loading" mid-reload (liveUrl null, not yet fallback) —
    // KEEP the last live art on screen so a mood change does not flash to the
    // procedural floor before the new art arrives. No promote, no bump.

    if (moodChanged) moodRef.current = mk;
    // Depend on the live URL, the fallback flag, + the mood key — NOT any clock.
  }, [liveUrl, fallback, mood]);

  return {
    imageUrl: curUrlRef.current,
    prevImageUrl: prevUrlRef.current,
    fadeKey,
    isFallback: krea.isFallback,
    status: krea.status,
    reason: krea.error,
  };
}
