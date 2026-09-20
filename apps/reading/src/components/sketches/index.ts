/**
 * Processing-style sketch registry (v1-sharpen §12).
 *
 * name → { render, defaultParams, label }. Style-wheel / artifact HTML can
 * look up a sketch by name and mount it via <SketchCanvas>.
 */

import {
  DEFAULT_CONSTELLATION_PARAMS,
  renderConstellation,
  type ConstellationParams,
} from "./constellation";
import {
  DEFAULT_HEAT_TRAIL_PARAMS,
  renderHeatTrail,
  type HeatTrailParams,
} from "./heatTrail";
import {
  DEFAULT_SYNTHESIS_WAVE_PARAMS,
  renderSynthesisWave,
  type SynthesisWaveParams,
} from "./synthesisWave";
import type { SketchBaseParams, SketchDefinition, SketchRender } from "./types";

export type { SketchBaseParams, SketchDefinition, SketchRender, SketchRng } from "./types";
export { coerceSeed, makeRng, rngFromSeed, seedFromString } from "./seed";
export {
  DEFAULT_CONSTELLATION_PARAMS,
  layoutConstellation,
  renderConstellation,
  type ConstellationParams,
} from "./constellation";
export {
  DEFAULT_HEAT_TRAIL_PARAMS,
  layoutHeatTrail,
  renderHeatTrail,
  type HeatTrailParams,
} from "./heatTrail";
export {
  DEFAULT_SYNTHESIS_WAVE_PARAMS,
  layoutSynthesisWave,
  renderSynthesisWave,
  sampleWave,
  type SynthesisWaveParams,
} from "./synthesisWave";
export { SketchCanvas, type SketchCanvasProps } from "./SketchCanvas";

/** Union of all v1 sketch param types. */
export type AnySketchParams =
  | ConstellationParams
  | HeatTrailParams
  | SynthesisWaveParams;

/** Stable registry keys for the three v1 seed sketches. */
export type SketchName = "constellation" | "heatTrail" | "synthesisWave";

type AnyDefinition = SketchDefinition<SketchBaseParams>;

/**
 * name → definition. Values are widened to SketchBaseParams so consumers can
 * iterate without a param-type switch; call sites that need knobs should
 * import the typed defaults directly.
 */
export const SKETCH_REGISTRY: Record<SketchName, AnyDefinition> = {
  constellation: {
    name: "constellation",
    label: "Knowledge-graph constellation",
    render: renderConstellation as SketchRender<SketchBaseParams>,
    defaultParams: DEFAULT_CONSTELLATION_PARAMS,
  },
  heatTrail: {
    name: "heatTrail",
    label: "Attention heat trail",
    render: renderHeatTrail as SketchRender<SketchBaseParams>,
    defaultParams: DEFAULT_HEAT_TRAIL_PARAMS,
  },
  synthesisWave: {
    name: "synthesisWave",
    label: "Synthesis wave",
    render: renderSynthesisWave as SketchRender<SketchBaseParams>,
    defaultParams: DEFAULT_SYNTHESIS_WAVE_PARAMS,
  },
};

export const SKETCH_NAMES: readonly SketchName[] = [
  "constellation",
  "heatTrail",
  "synthesisWave",
] as const;

export function getSketch(name: SketchName): AnyDefinition {
  return SKETCH_REGISTRY[name];
}

export function isSketchName(value: string): value is SketchName {
  return Object.prototype.hasOwnProperty.call(SKETCH_REGISTRY, value);
}
