import { useEffect, useRef, useState } from "react";

import {
  CROSSFADE,
  crossfadeOpacity,
  createCrossfadeTransition,
  retargetCrossfade,
  sceneLayerTransform,
  type CrossfadeTransition,
} from "../../design/motion/sceneMotion";
import type { SceneArt } from "../useSceneArt";

/**
 * KreaArtLayer (SPR-04, milestone 4 — periodic Krea art, crossfaded).
 *
 * Paints the LIVE Krea sky/peak art as a background image ABOVE the procedural
 * sky, crossfading when the mood changes. It renders NOTHING when in fallback
 * (no key / over-budget / offline) — the procedural ProceduralSky shows through
 * untouched, which is the seamless degradation path.
 *
 * CROSSFADE: two stacked image divs. The current art fades IN and the previous
 * art fades OUT beneath it from a scene-clock envelope. If a new image arrives
 * mid-fade, the envelope retargets from the current opacity instead of
 * remounting at 0. The fetch cadence (useSceneArt) is mood-gated; this layer is
 * purely presentational, so it can never cause a fetch.
 *
 * Under reduced-motion the envelope collapses to an instant cut, so the art
 * appears statically — consistent with the frozen scene.
 */

export interface KreaArtLayerProps {
  art: SceneArt;
  /** When frozen, collapse the crossfade to an instant static cut. */
  frozen?: boolean;
  /** Scene-clock timestamp used for interruptible crossfade envelopes. */
  clockMs?: number;
}

interface PresentationState {
  currentUrl: string | null;
  previousUrl: string | null;
  transition: CrossfadeTransition;
}

export function KreaArtLayer({ art, frozen = false, clockMs = 0 }: KreaArtLayerProps) {
  const clockRef = useRef(clockMs);
  clockRef.current = clockMs;
  const [presentation, setPresentation] = useState<PresentationState>(() => ({
    currentUrl: art.imageUrl,
    previousUrl: art.prevImageUrl,
    transition: createCrossfadeTransition(0, {
      fromOpacity: art.imageUrl ? (frozen ? CROSSFADE.paintedOpacity : 0) : 0,
      reducedMotion: frozen,
    }),
  }));

  useEffect(() => {
    const startedAtMs = clockRef.current;
    if (art.isFallback || !art.imageUrl) {
      setPresentation((prev) =>
        prev.currentUrl || prev.previousUrl
          ? {
              currentUrl: null,
              previousUrl: null,
              transition: createCrossfadeTransition(startedAtMs, {
                fromOpacity: 0,
                toOpacity: 0,
                reducedMotion: frozen,
              }),
            }
          : prev,
      );
      return;
    }

    setPresentation((prev) => {
      if (prev.currentUrl === art.imageUrl) return prev;
      const seed = prev.currentUrl
        ? retargetCrossfade(prev.transition, startedAtMs, CROSSFADE.paintedOpacity, {
            reducedMotion: frozen,
          })
        : createCrossfadeTransition(startedAtMs, {
            fromOpacity: 0,
            toOpacity: CROSSFADE.paintedOpacity,
            reducedMotion: frozen,
          });
      return {
        currentUrl: art.imageUrl,
        previousUrl: prev.currentUrl ?? art.prevImageUrl,
        transition: seed,
      };
    });
  }, [art.fadeKey, art.imageUrl, art.isFallback, art.prevImageUrl, frozen]);

  // Fallback ⇒ render nothing; the procedural sky is the whole picture.
  if (art.isFallback || !presentation.currentUrl) {
    return (
      <div
        className="absolute inset-0"
        data-testid="krea-art-layer"
        data-krea="fallback"
        aria-hidden="true"
      />
    );
  }

  const drift = sceneLayerTransform("krea", clockMs, { reducedMotion: frozen });
  const incomingOpacity = crossfadeOpacity(presentation.transition, clockMs);
  const outgoingOpacity = frozen
    ? 0
    : Math.max(0, CROSSFADE.paintedOpacity - incomingOpacity);

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      data-testid="krea-art-layer"
      data-krea="live"
      data-crossfade-opacity={incomingOpacity.toFixed(4)}
      data-drift-x={drift.x}
      data-drift-y={drift.y}
      style={{ transform: `translate3d(${drift.x}px, ${drift.y}px, 0)` }}
      aria-hidden="true"
    >
      {presentation.previousUrl && presentation.previousUrl !== presentation.currentUrl && (
        <div
          // The outgoing art sits beneath, fading out.
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage: `url(${cssUrl(presentation.previousUrl)})`,
            opacity: outgoingOpacity,
          }}
        />
      )}
      <div
        // Opacity is calculated from the scene clock so an interrupted fade can
        // retarget from its current value instead of remounting at 0.
        className="absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage: `url(${cssUrl(presentation.currentUrl)})`,
          // A restrained opacity so the procedural motion (snow/clouds) still
          // reads ON TOP of the art rather than being buried — the art tints
          // and textures the sky, it does not replace the living layer.
          opacity: incomingOpacity,
        }}
      />
    </div>
  );
}

/** Sanitize a URL for use inside a CSS url() — strip the few chars that would
 *  break out of the url() token. Data-URIs and https URLs both pass through. */
function cssUrl(u: string): string {
  return u.replace(/[")]/g, encodeURIComponent);
}

export default KreaArtLayer;
