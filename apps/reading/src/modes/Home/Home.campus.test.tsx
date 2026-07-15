import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const runtimeAsset = resolve(
  "src/modes/Home/home_alpine_knowledge_campus_v1.webp",
);
const sourceAsset = resolve(
  "src/modes/Home/assets/home_alpine_knowledge_campus_v1_master.png",
);

describe("Home alpine campus asset contract", () => {
  it("keeps a compact runtime derivative and a larger source master", () => {
    const runtime = statSync(runtimeAsset);
    const source = statSync(sourceAsset);
    expect(runtime.size).toBeLessThanOrEqual(256 * 1024);
    expect(source.size).toBeGreaterThan(runtime.size);
  });

  it("does not introduce pixel-owned interaction machinery", () => {
    const source = readFileSync("src/modes/Home/Home.tsx", "utf8");
    expect(source).not.toMatch(/<map\b|<area\b|canvas|getImageData|pixel/i);
    expect(source).not.toMatch(/onPointer(?:Down|Move|Up)|client[XY]|offset[XY]/);
    expect(source.match(/data-workflow=/g)).toHaveLength(1);
  });

  it("does not add a runtime generation or network dependency", () => {
    const source = readFileSync("src/modes/Home/Home.tsx", "utf8");
    expect(source).not.toMatch(/\bfetch\s*\(|WebSocket|Krea|Modal|requestScene/);
  });
});
