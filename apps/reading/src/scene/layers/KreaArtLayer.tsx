import type { SceneArt } from "../useSceneArt";

/**
 * KreaArtLayer (SPR-04, milestone 4 — periodic Krea art, crossfaded).
 *
 * Paints the LIVE Krea sky/peak art as a background image ABOVE the procedural
 * sky, crossfading when the mood changes. It renders NOTHING when in fallback
 * (no key / over-budget / offline) — the procedural ProceduralSky shows through
 * untouched, which is the seamless degradation path.
 *
 * CROSSFADE: two stacked image divs. The current art fades IN (keyed on
 * `fadeKey`), the previous art fades OUT beneath it — a CSS opacity transition,
 * NOT a per-frame redraw. The fetch cadence (useSceneArt) is mood-gated; this
 * layer is purely presentational, so it can never cause a fetch.
 *
 * Under reduced-motion the transition is removed (no animation), so the art
 * appears statically — consistent with the frozen scene.
 */

export interface KreaArtLayerProps {
  art: SceneArt;
  /** When frozen, drop the crossfade transition (static art). */
  frozen?: boolean;
}

export function KreaArtLayer({ art, frozen }: KreaArtLayerProps) {
  // Fallback ⇒ render nothing; the procedural sky is the whole picture.
  if (art.isFallback || !art.imageUrl) {
    return (
      <div
        className="absolute inset-0"
        data-testid="krea-art-layer"
        data-krea="fallback"
        aria-hidden="true"
      />
    );
  }

  const transition = frozen
    ? undefined
    : "opacity var(--motion-slow) var(--ease-standard)";

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      data-testid="krea-art-layer"
      data-krea="live"
      aria-hidden="true"
    >
      {art.prevImageUrl && art.prevImageUrl !== art.imageUrl && (
        <div
          // The outgoing art sits beneath, fading out.
          className="absolute inset-0 bg-cover bg-center opacity-0"
          style={{
            backgroundImage: `url(${cssUrl(art.prevImageUrl)})`,
            transition,
          }}
        />
      )}
      <div
        // The incoming art keyed on fadeKey so it remounts at opacity 0 then
        // transitions to the painted opacity — a crossfade, not a hard cut.
        key={art.fadeKey}
        className="absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage: `url(${cssUrl(art.imageUrl)})`,
          // A restrained opacity so the procedural motion (snow/clouds) still
          // reads ON TOP of the art rather than being buried — the art tints
          // and textures the sky, it does not replace the living layer.
          opacity: 0.82,
          transition,
          animation: frozen ? undefined : "akb-krea-fade-in var(--motion-slow) var(--ease-enter)",
        }}
      />
      {/* The akb-krea-fade-in crossfade animation + the reduced-motion guard
          live in src/scene/scene.css (the scene's consolidated motion home). */}
    </div>
  );
}

/** Sanitize a URL for use inside a CSS url() — strip the few chars that would
 *  break out of the url() token. Data-URIs and https URLs both pass through. */
function cssUrl(u: string): string {
  return u.replace(/[")]/g, encodeURIComponent);
}

export default KreaArtLayer;
