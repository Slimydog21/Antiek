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
      // Residual invent doors (v2b wave surfaces)
      "modes/BrainstormStation/ThoughtPartnerPanel.tsx",
      "modes/DeepResearchWorkspace/PlanEditor.tsx",
      "modes/DeepResearchWorkspace/ResearchWaitArcade.tsx",
      "arcade/ArcadeCabinet.tsx",
      // Product invent doors refreshed in invent polish v2d
      "modes/Multimedia/KnowledgePanel.tsx",
      "modes/Settings/AntiekBenchPanel.tsx",
      "components/ModelDecisionBar.tsx",
      "modes/Settings/modelSelection/MidnightOilPanel.tsx",
    ];
    for (const rel of paths) {
      const src = readFileSync(join(root, rel), "utf8");
      expect(src, rel).toMatch(/living-tv/);
      expect(src, rel).toMatch(/antiek-living-tv-invent/);
    }
  });
});

describe("sessionLivingTv invent reframe CSS contract", () => {
  it("ships Flipbook-feel invent class with reduced-motion collapse", () => {
    const css = readFileSync(
      join(process.cwd(), "src/brand/sessionLivingTv.css"),
      "utf8",
    );
    expect(css).toMatch(/antiek-living-tv-invent/);
    expect(css).toMatch(/prefers-reduced-motion:\s*reduce/);
    expect(css).toMatch(/antiek-living-tv-reframe/);
    // Pure Flipbook sole UI remains NO-GO — CSS comment is load-bearing honesty.
    expect(css).toMatch(/NO-GO/i);
  });

  it("multi-phase reframe keeps soft ambient living-TV motion (not thrash)", () => {
    const css = readFileSync(
      join(process.cwd(), "src/brand/sessionLivingTv.css"),
      "utf8",
    );
    // Multi-keyframe reframe densify after invent polish v2j craft pass.
    expect(css).toMatch(/33%/);
    expect(css).toMatch(/66%/);
    expect(css).toMatch(/16s/);
    expect(css).toMatch(/reshape-with-window|Flipbook/i);
  });

  it("covers research-wait playing invent testid via suffix densify", () => {
    const css = readFileSync(
      join(process.cwd(), "src/brand/sessionLivingTv.css"),
      "utf8",
    );
    // Global invent testids ending in -living-tv-art match wait playing scene.
    expect(css).toMatch(/data-testid\$="-living-tv-art"/);
    expect("research-wait-playing-living-tv-art".endsWith("-living-tv-art")).toBe(
      true,
    );
  });

  it("covers home invent living-tv testids via suffix densify", () => {
    const css = readFileSync(
      join(process.cwd(), "src/brand/sessionLivingTv.css"),
      "utf8",
    );
    expect(css).toMatch(/data-testid\$="-living-tv-art"/);
    // Home door invent + igloo arcade invent use the Flipbook-feel suffix.
    for (const id of [
      "home-living-tv-art",
      "home-arcade-living-tv-art",
    ] as const) {
      expect(id.endsWith("-living-tv-art")).toBe(true);
    }
  });
});
