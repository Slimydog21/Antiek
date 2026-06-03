/**
 * ResearchWorkstation.feel.test.tsx — FEEL-S4 exempt-surface guard.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("ResearchWorkstation — dense IDE exempt from floating stack chrome", () => {
  it("investigation centre uses GlassSurface solid, not floating shadow-z3", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "index.tsx"),
      "utf8",
    );
    expect(src).toMatch(/GlassSurface[\s\S]*variant="solid"/);
    expect(src).not.toMatch(/shadow-z3/);
  });

  it("StartResearch example prompts use shared cardLift motion helper", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "StartResearch.tsx"),
      "utf8",
    );
    expect(src).toMatch(/cardLift/);
    expect(src).toMatch(/from ["'].*design\/motion["']/);
  });
});