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
});
