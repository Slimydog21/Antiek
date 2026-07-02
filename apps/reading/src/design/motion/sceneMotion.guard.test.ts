import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CROSSFADE,
  crossfadeOpacity,
  createCrossfadeTransition,
  sceneLayerTransform,
  type SceneMotionLayer,
} from "./sceneMotion";

const BASELINE = join(__dirname, "scene_motion_guard_baseline.json");
const SAMPLE_MS = [0, 250, 500, 1000, 1500, 2500, 5000, 10_000, 20_000, 40_000];
const LAYERS: SceneMotionLayer[] = ["peaks", "clouds", "snow", "krea"];

interface GuardBaseline {
  note: string;
  samplesMs: number[];
  layers: Record<SceneMotionLayer, Array<{ t: number; x: number; y: number; opacity: number }>>;
  reducedLayers: Record<SceneMotionLayer, { x: number; y: number; opacity: number }>;
  crossfade: Array<{ t: number; opacity: number }>;
  reducedCrossfade: { t: number; opacity: number };
}

function mintBaseline(): GuardBaseline {
  const fade = createCrossfadeTransition(0);
  return {
    note:
      "SPR-04 re-mint against adapted main Scene integration; deterministic sample grid, no Date.now/random.",
    samplesMs: SAMPLE_MS,
    layers: Object.fromEntries(
      LAYERS.map((layer) => [
        layer,
        SAMPLE_MS.map((t) => ({ t, ...roundTransform(sceneLayerTransform(layer, t)) })),
      ]),
    ) as GuardBaseline["layers"],
    reducedLayers: Object.fromEntries(
      LAYERS.map((layer) => [
        layer,
        roundTransform(sceneLayerTransform(layer, 12_345, { reducedMotion: true })),
      ]),
    ) as GuardBaseline["reducedLayers"],
    crossfade: SAMPLE_MS.slice(0, 7).map((t) => ({
      t,
      opacity: round(crossfadeOpacity(fade, t)),
    })),
    reducedCrossfade: {
      t: 500,
      opacity: round(
        crossfadeOpacity(createCrossfadeTransition(0, { reducedMotion: true }), 500),
      ),
    },
  };
}

function readBaseline(): GuardBaseline {
  return JSON.parse(readFileSync(BASELINE, "utf8")) as GuardBaseline;
}

function roundTransform(transform: { x: number; y: number; opacity: number }) {
  return {
    x: round(transform.x),
    y: round(transform.y),
    opacity: round(transform.opacity),
  };
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

describe("sceneMotion guard baseline", () => {
  it("matches deterministic sampled choreography curves", () => {
    const current = mintBaseline();

    if (process.env.SCENE_MOTION_GUARD_UPDATE) {
      writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
      // eslint-disable-next-line no-console
      console.log("sceneMotion guard baseline re-minted for adapted SPR-04 integration.");
      expect(existsSync(BASELINE)).toBe(true);
      return;
    }

    const expected = readBaseline();
    for (const layer of LAYERS) {
      expect(current.layers[layer], `${layer} drift curve changed`).toEqual(
        expected.layers[layer],
      );
      expect(current.reducedLayers[layer], `${layer} reduced-motion pose changed`).toEqual(
        expected.reducedLayers[layer],
      );
    }
    expect(current.crossfade, "krea crossfade envelope changed").toEqual(expected.crossfade);
    expect(current.reducedCrossfade, "reduced-motion crossfade changed").toEqual(
      expected.reducedCrossfade,
    );
    expect(current.crossfade.at(-1)?.opacity).toBe(CROSSFADE.paintedOpacity);
  });
});
