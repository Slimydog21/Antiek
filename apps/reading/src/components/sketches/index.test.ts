import { describe, expect, it } from "vitest";

import {
  SKETCH_NAMES,
  SKETCH_REGISTRY,
  getSketch,
  isSketchName,
} from "./index";
import { recordingContext } from "./testUtils";

describe("sketch registry", () => {
  it("exposes exactly the three v1 seed sketches", () => {
    expect([...SKETCH_NAMES].sort()).toEqual(
      ["constellation", "heatTrail", "synthesisWave"].sort(),
    );
    for (const name of SKETCH_NAMES) {
      const def = getSketch(name);
      expect(def.name).toBe(name);
      expect(def.label.length).toBeGreaterThan(0);
      expect(typeof def.render).toBe("function");
      expect(def.defaultParams.seed).toBeTruthy();
    }
  });

  it("isSketchName narrows correctly", () => {
    expect(isSketchName("constellation")).toBe(true);
    expect(isSketchName("nope")).toBe(false);
  });

  it("every registered sketch paints deterministically from defaults", () => {
    for (const name of SKETCH_NAMES) {
      const def = SKETCH_REGISTRY[name];
      const a = recordingContext();
      const b = recordingContext();
      const params = { ...def.defaultParams, reducedMotion: true, t: 0 };
      def.render(a.context, 200, 120, params);
      def.render(b.context, 200, 120, params);
      expect(a.hash()).toBe(b.hash());
    }
  });
});
