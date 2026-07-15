import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * A deliberately small architecture gate for activity implementations.
 *
 * StationActivity's type withholds movement authority from callers, but React
 * components remain ordinary code and can import whatever the module graph
 * exposes. This test makes the fixed-station boundary mechanical for direct
 * dependencies and APIs. It is not a JavaScript sandbox; it is an honest,
 * reviewable tripwire against accidentally rebuilding the reel inside a new
 * activity.
 */
const activityDirectory = dirname(fileURLToPath(import.meta.url));
const implementationFiles = readdirSync(activityDirectory)
  .filter((name) => name.endsWith(".tsx") && !name.endsWith(".test.tsx"))
  .sort();

const forbidden = [
  /from\s+["'][^"']*WernerStage["']/,
  /from\s+["'][^"']*PenguinMascot["']/,
  /import\s*\{[^}]*useMouseFollow[^}]*\}\s*from/s,
  /\b(?:fetch|XMLHttpRequest|WebSocket)\b/,
  /\b(?:navigate|useNavigate|location\.assign|location\.replace)\b/,
  /\b(?:left|top|translate[XY]?)\s*:/,
];

describe("station activity source boundary", () => {
  it("has at least one implementation to audit", () => {
    expect(implementationFiles).not.toHaveLength(0);
  });

  for (const filename of implementationFiles) {
    it(`${filename} does not claim movement, navigation, or network authority`, () => {
      const source = readFileSync(join(activityDirectory, filename), "utf8");
      for (const pattern of forbidden) {
        expect(source, `${filename} matched forbidden ${pattern}`).not.toMatch(pattern);
      }
    });
  }
});
