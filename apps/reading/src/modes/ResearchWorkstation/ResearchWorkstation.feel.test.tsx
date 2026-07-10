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

  // Residual (afr): investigation centre wires multi-select collective panel.
  it("InvestigationCenter mounts CollectiveResearchPanel for multi-select (afr)", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "index.tsx"),
      "utf8",
    );
    expect(src).toMatch(/CollectiveResearchPanel/);
    expect(src).toMatch(/research-workstation-collective-mount/);
    expect(src).toMatch(/collectDeepResearchSpawnIds/);
    expect(src).toMatch(/openSpawnIds/);
    expect(src).toMatch(/data-seamless-workstation-collective/);
  });

  // Residual (afs): investigation centre wires recursive note-taker twins.
  it("InvestigationCenter mounts TwinNotesPanel recursive note-taker (afs)", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "index.tsx"),
      "utf8",
    );
    expect(src).toMatch(/TwinNotesPanel/);
    expect(src).toMatch(/research-workstation-twins-mount/);
    expect(src).toMatch(/autoSeedIfEmpty/);
    expect(src).toMatch(/data-seamless-workstation-twins/);
  });
});