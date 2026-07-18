/**
 * densify: Flipbook-feel HTML streaming ladder remains cost-intelligent and NO-GO pure sole UI.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const NOTE = join(
  process.cwd(),
  "docs/design-assets/FLIPBOOK-FEEL-HTML-STREAMING-NOTE.md",
);

describe("Flipbook stream ladder densify", () => {
  it("documents cost-intelligent ladder + pure Flipbook sole UI NO-GO", () => {
    const text = readFileSync(NOTE, "utf8");
    expect(text).toMatch(/NO-GO/);
    expect(text).toMatch(/HTML-first|HTML remains/i);
    expect(text).toMatch(/CSS invent reframe|sessionLivingTv/i);
    expect(text).toMatch(/Pre-rendered|webm|mp4|CDN/i);
    expect(text).toMatch(/Krea|Imagine/i);
    expect(text).toMatch(/Modal/i);
    expect(text).toMatch(/Budget projection|price ceiling|budget/i);
    expect(text).toMatch(/37 files \/ 298 tests|test:branding-densify/);
  });
});
