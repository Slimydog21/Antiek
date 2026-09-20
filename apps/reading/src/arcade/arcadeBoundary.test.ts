import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));

function productionFiles(directory: string): string[] {
  return readdirSync(directory)
    .flatMap((name) => {
      const path = join(directory, name);
      if (statSync(path).isDirectory()) return productionFiles(path);
      if (!/\.(ts|tsx)$/.test(name) || name.includes(".test.")) return [];
      return [path];
    })
    .sort();
}

const forbidden = [
  /from\s+["'][^"']*(?:AppShell|\/App|DeepResearch|WernerStage|reactionBus)["']/,
  /from\s+["']react-router/,
  /from\s+["'][^"']*(?:navigation|content|provider|persistence|mascot|PenguinMascot|sessionAssets|SceneHotspots)["']/i,
  /\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon)\b/,
  /\b(?:localStorage|sessionStorage|indexedDB)\b/,
  /\b(?:useNavigate|location\.(?:assign|replace)|document\.cookie|navigator\.credentials)\b/,
  /\b(?:posthog|analytics|telemetry|budget|spend)\b/i,
];

describe("arcade core source boundary", () => {
  const files = productionFiles(root);

  it("audits the recovered production core", () => {
    expect(files.length).toBeGreaterThanOrEqual(12);
  });

  for (const file of files) {
    it(`${relative(root, file)} withholds product and persistence authority`, () => {
      const source = readFileSync(file, "utf8");
      for (const pattern of forbidden) {
        expect(
          source,
          `${relative(root, file)} matched ${pattern}`,
        ).not.toMatch(pattern);
      }
    });
  }
});
