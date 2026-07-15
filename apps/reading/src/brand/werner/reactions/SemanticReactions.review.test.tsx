import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const storyPath = path.join(__dirname, "SemanticReactions.review.stories.tsx");
const cssPath = path.join(__dirname, "semantic-reactions.review.css");
const storySource = fs.readFileSync(storyPath, "utf8");
const cssSource = fs.readFileSync(cssPath, "utf8");

describe("semantic motion proof sheet", () => {
  it("covers all five reactions and all four named review frames", () => {
    for (const reaction of ["curious", "happy", "composed", "dizzy", "hit"]) {
      expect(storySource).toContain(`${reaction}: Werner`);
    }
    for (const frame of ["start", "semantic-beat", "settle", "reduced"]) {
      expect(storySource).toContain(`name: \"${frame}\"`);
    }
  });

  it("derives settle frames from the canonical duration table", () => {
    expect(storySource).toContain("WERNER_SEMANTIC_DURATION_MS[reaction]");
    expect(storySource).toContain("SEMANTIC_BEAT_MS[reaction]");
    expect(storySource).toContain(
      '"--werner-review-delay": `-${frame.elapsedMs}ms`',
    );
  });

  it("freezes every animated descendant and retains explicit reduced stills", () => {
    expect(cssSource).toContain("animation-play-state: paused !important");
    expect(cssSource).toContain(
      "animation-delay: var(--werner-review-delay) !important",
    );
    expect(storySource).toContain("reduced={frame.reduced}");
    expect(storySource).toContain(
      'name: "reduced", elapsedMs: 0, reduced: true',
    );
    for (const animation of [
      "werner-curious-beat",
      "werner-evidence-arrive",
      "werner-proud-lift",
      "werner-verified-beat",
      "werner-folio-bind",
      "werner-slip-one-bind",
      "werner-slip-two-bind",
      "werner-slip-three-bind",
      "werner-bind-settle",
      "werner-paperclip-orbit",
      "werner-hit-rebound",
      "werner-tab-impact",
    ]) {
      expect(cssSource).toContain(`animation: ${animation}`);
    }
    expect(cssSource).toContain('[data-reduced="false"]');
    expect(cssSource).not.toContain('[data-reduced="true"]');
  });

  it("is story-only and introduces no animation or raw color vocabulary", () => {
    const productionSources = ["SemanticReactions.tsx", "index.ts"]
      .map((file) => fs.readFileSync(path.join(__dirname, file), "utf8"))
      .join("\n");
    expect(productionSources).not.toContain("semantic-reactions.review.css");
    expect(cssSource).not.toMatch(/@keyframes|\binfinite\b/);
    expect(cssSource).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(storySource).not.toMatch(/export\s*\{[^}]*REACTIONS/);
    expect(storySource).not.toMatch(/export\s*\{[^}]*SEMANTIC_BEAT_MS/);
  });
});
