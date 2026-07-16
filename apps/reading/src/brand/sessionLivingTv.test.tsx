/**
 * Flipbook-feel invent strip class is load-bearing on product invent doors.
 * Global CSS also keys on living-tv testids; explicit class keeps densify honest.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import SessionBrandChrome from "./SessionBrandChrome";

afterEach(cleanup);

describe("sessionLivingTv Flipbook-feel invent motion", () => {
  it("applies antiek-living-tv-invent class to the invent strip", () => {
    render(
      <SessionBrandChrome title="Test door" testIdPrefix="test-door" />,
    );
    const art = screen.getByTestId("test-door-living-tv-art");
    expect(art.className).toMatch(/antiek-living-tv-invent/);
  });

  it("key product invent sources stamp antiek-living-tv-invent next to living-tv testids", () => {
    const root = join(process.cwd(), "src");
    const paths = [
      "modes/Home/Home.tsx",
      "modes/Write/WriteHome.tsx",
      "modes/Library/index.tsx",
      "modes/DeepResearchWorkspace/index.tsx",
      "modes/Login/index.tsx",
      "arcade/host/LoadingGameHost.tsx",
    ];
    for (const rel of paths) {
      const src = readFileSync(join(root, rel), "utf8");
      expect(src, rel).toMatch(/living-tv/);
      expect(src, rel).toMatch(/antiek-living-tv-invent/);
    }
  });
});
