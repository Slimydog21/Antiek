/**
 * densify: every product UI file importing session invent webps must stamp
 * Flipbook-feel invent reframe class. Inventory-only invents may remain unstamped.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function walkTsx(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, name.name);
    if (name.isDirectory()) {
      if (name.name === "node_modules" || name.name === "dist") continue;
      walkTsx(p, out);
    } else if (
      name.name.endsWith(".tsx") &&
      !name.name.includes(".test.") &&
      !name.name.includes(".stories.")
    ) {
      out.push(p);
    }
  }
  return out;
}

describe("invent class product-map densify", () => {
  it("all product UI invent webp imports stamp antiek-living-tv-invent", () => {
    const files = walkTsx(SRC);
    const offenders: string[] = [];
    for (const abs of files) {
      const src = readFileSync(abs, "utf8");
      if (
        src.includes("poses/session/werner_") &&
        src.includes("session_v1.webp") &&
        !src.includes("antiek-living-tv-invent")
      ) {
        offenders.push(abs.replace(SRC + "/", ""));
      }
    }
    expect(offenders, offenders.join(", ")).toEqual([]);
  });

  it("invent polish wave complete note pins densify gate + Flipbook NO-GO honesty", () => {
    const summary = readFileSync(
      join(process.cwd(), "docs/design-assets/BRANDING-DENSIFY-SUMMARY.md"),
      "utf8",
    );
    const flipbook = readFileSync(
      join(process.cwd(), "docs/design-assets/FLIPBOOK-FEEL-HTML-STREAMING-NOTE.md"),
      "utf8",
    );
    expect(summary).toMatch(/Invent polish v2d wave complete/i);
    expect(summary).toMatch(/Invent polish v2e wave complete/i);
    expect(summary).toMatch(/Invent polish v2f wave complete/i);
    expect(summary).toMatch(/Invent polish v2g wave complete/i);
    expect(summary).toMatch(/Invent polish v2h wave complete/i);
    expect(summary).toMatch(/Invent polish v2i wave complete/i);
    expect(summary).toMatch(/Invent polish v2j wave complete/i);
    // densify pack progression through invent polish honesty densify
    expect(summary).toMatch(
      /29\/25[01]|32\/268|36\/297|37\/298|38\/299|39\/30[23]/,
    );
    expect(flipbook).toMatch(
      /39 files \/ 30[23] tests|38 files \/ 299 tests/,
    );
    expect(flipbook).toMatch(/Invent polish v2i/);
    expect(flipbook).toMatch(/NO-GO/);
    expect(flipbook).toMatch(/ice-bait|IceBait|ice-cursor/i);
  });
});
