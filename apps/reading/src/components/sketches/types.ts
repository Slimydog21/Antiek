/**
 * Processing-style generative sketch contract (v1-sharpen §12).
 *
 * Sketches are pure Canvas2D renderers — no p5.js dependency. Same seed +
 * params + size → identical pixels (auditable / provenance-friendly).
 * Reduced-motion is a param: render a static frame, never spin an rAF loop.
 */

/** Deterministic random source. `next()` returns a float in [0, 1). */
export interface SketchRng {
  next(): number;
  /** Float in [min, max). */
  range(min: number, max: number): number;
  /** Integer in [min, max] inclusive. */
  int(min: number, max: number): number;
}

/**
 * Common params every sketch accepts. Sketch-specific knobs extend this.
 * `seed` may be a string (artifact id) or a numeric seed.
 */
export interface SketchBaseParams {
  /** Artifact id or free-form seed string; hashed to u32 for the PRNG. */
  seed: string | number;
  /**
   * Logical animation time in ms. Callers pass a frozen value under
   * prefers-reduced-motion; animated wrappers advance it via rAF.
   */
  t?: number;
  /** When true, sketches MUST ignore continuous animation and draw a still. */
  reducedMotion?: boolean;
  /** Colour mode. Defaults to "night" — sketches sit on dark glass. */
  mode?: "day" | "night";
}

/**
 * Pure render function. Mutates only the canvas context; no DOM, no rAF,
 * no Math.random / Date.now. Deterministic given (width, height, params).
 */
export type SketchRender<P extends SketchBaseParams = SketchBaseParams> = (
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  params: P,
) => void;

export interface SketchDefinition<
  P extends SketchBaseParams = SketchBaseParams,
> {
  /** Stable registry key (e.g. "constellation"). */
  name: string;
  /** Human label for style-wheel / picker UI. */
  label: string;
  /** Pure canvas renderer. */
  render: SketchRender<P>;
  /** Default params (must include a seed). */
  defaultParams: P;
}
