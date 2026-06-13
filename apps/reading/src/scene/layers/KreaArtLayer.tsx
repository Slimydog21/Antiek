import { useReducer, useRef } from "react";

import type { SceneArt } from "../useSceneArt";
import { SceneStatusBadge } from "../SceneStatusBadge";
import { CROSSFADE } from "../../design/motion/sceneMotion";
import {
  crossfadeReduce,
  initCrossfade,
  type CrossfadeState,
} from "../crossfadeMachine";

/**
 * KreaArtLayer (SPR-04 M4 — periodic Krea art; ALC SPR-06 M3 — choreographed,
 * INTERRUPTIBLE crossfade).
 *
 * Paints the LIVE Krea sky/peak art ABOVE the procedural sky, crossfading when
 * the mood changes. Renders NOTHING visual in fallback (no key / over-budget /
 * offline) — ProceduralSky shows through untouched, the seamless degradation
 * path. Purely presentational: the fetch cadence (useSceneArt) is mood-gated, so
 * this layer can never cause a fetch.
 *
 * ─── SPR-06 M3: from a key-remount keyframe to a two-slot transition ─────────
 *
 * The SPR-04 version keyed the incoming art on `fadeKey` and ran a keyframe
 * animation from opacity 0 — NOT interruptible (a mid-fade mood flip remounted
 * the element and restarted the keyframe from black: a jump-cut). M3 rebuilds it
 * as TWO PERSISTENT slots driven by `crossfadeMachine`: each swap changes a
 * slot's opacity TARGET, and a CSS `transition: opacity` interpolates from the
 * slot's CURRENT computed opacity. A flip mid-transition just retargets — the
 * browser glides from where the slot IS, never restarts. No `key` remount, no
 * keyframe here (the akb-krea-fade-in keyframe is retired from this layer; the
 * crossfade is a pure transition now). Opacity/transform only — GPU-cheap.
 *
 * INTERRUPTION INVARIANT: the machine never queues a swap; the latest art is
 * always made the front immediately. N rapid mood flips collapse to a single
 * smooth glide to the latest art, not a stutter of full fades. See
 * crossfadeMachine.ts for the contract a future edit must not break.
 *
 * Under reduced-motion (`frozen`) the transition collapses to the near-instant
 * CROSSFADE.reducedMs dissolve (opacity only — the one allowed animated property
 * under reduced-motion, per M5), so the art still swaps without a hard jump-cut
 * but effectively instantly. The static composition is the designed reduced state.
 */

export interface KreaArtLayerProps {
  art: SceneArt;
  /** When frozen, collapse the crossfade to a near-instant opacity dissolve. */
  frozen?: boolean;
}

/** Drive the persistent two-slot crossfade from the current art URL. We react to
 *  the LIVE imageUrl (and fadeKey, which useSceneArt bumps on every genuine swap
 *  incl. a re-show after fallback) — never per frame, never on the clock. */
function useCrossfade(art: SceneArt): CrossfadeState {
  const [state, dispatch] = useReducer(
    (s: CrossfadeState, url: string | null) =>
      crossfadeReduce(s, url, { paintedOpacity: CROSSFADE.paintedOpacity }),
    undefined,
    initCrossfade,
  );

  // The URL we last dispatched, so we only re-trigger on a genuine change (not
  // on unrelated re-renders). fadeKey is folded in so a fallback→same-URL re-show
  // (rare) still re-triggers; in practice the URL change is the trigger.
  const lastRef = useRef<string>("");
  const liveUrl = art.isFallback ? null : art.imageUrl;
  const signature = `${liveUrl ?? "∅"}#${art.fadeKey}`;
  if (signature !== lastRef.current) {
    lastRef.current = signature;
    dispatch(liveUrl);
  }

  return state;
}

export function KreaArtLayer({ art, frozen }: KreaArtLayerProps) {
  // The crossfade machine runs regardless of fallback so the slots can EASE OUT
  // (release cleanly) when art drops to fallback — rather than vanishing in a cut.
  const cf = useCrossfade(art);

  // The transition driving every slot's opacity. Under reduced-motion it
  // collapses to the near-instant dissolve (opacity only — never a transform).
  // The easing is the same calm "arriving element" curve either way; only the
  // duration changes (full crossfade vs near-instant reduced dissolve).
  const duration = frozen ? CROSSFADE.reducedMs : CROSSFADE.ms;
  const transition = `opacity ${duration} ${CROSSFADE.easeIn}`;

  // Fallback ⇒ the layer flags fallback + mounts the OPERATOR-ONLY badge (it
  // self-gates: renders only when authenticated AND fallback). The slots ARE
  // still rendered (easing to 0) so the release is a clean fade, not a cut — but
  // once both slots have released (target 0 and no url painted) the visible art
  // is gone and the procedural floor is the whole picture.
  const isFallback = art.isFallback || !art.imageUrl;

  // Render the two persistent slots. They never remount; only their
  // background-image + opacity target change. Order is fixed (A then B) so React
  // keeps both elements alive across swaps — the key to interruptibility.
  const slot = (id: "A" | "B") => {
    const s = cf[id];
    if (!s.url) return null;
    return (
      <div
        key={id}
        data-krea-slot={id}
        className="absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage: `url(${cssUrl(s.url)})`,
          opacity: s.target,
          transition,
          willChange: "opacity",
        }}
      />
    );
  };

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      data-testid="krea-art-layer"
      data-krea={isFallback ? "fallback" : "live"}
      aria-hidden="true"
    >
      {slot("A")}
      {slot("B")}
      {isFallback && <SceneStatusBadge isFallback reason={art.reason} />}
    </div>
  );
}

/** Sanitize a URL for use inside a CSS url() — strip the few chars that would
 *  break out of the url() token. Data-URIs and https URLs both pass through. */
function cssUrl(u: string): string {
  return u.replace(/[")]/g, encodeURIComponent);
}

export default KreaArtLayer;
