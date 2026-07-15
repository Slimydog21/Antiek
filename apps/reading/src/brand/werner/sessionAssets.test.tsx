import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import Werner from "../Werner";
import {
  SESSION_BRAND_ASSET_IDS,
  SESSION_BRAND_ASSETS,
  sessionBrandAssetUrl,
} from "./sessionAssets";

describe("session brand assets integration", () => {
  it("exports five session assets with non-empty module URLs", () => {
    expect(SESSION_BRAND_ASSET_IDS).toHaveLength(5);
    for (const id of SESSION_BRAND_ASSET_IDS) {
      const url = sessionBrandAssetUrl(id);
      expect(typeof url).toBe("string");
      expect(url.length).toBeGreaterThan(0);
      // Vite may return data URL or hashed path — must resolve to the asset.
      expect(SESSION_BRAND_ASSETS[id]).toBe(url);
    }
  });

  it("cabinet imports use ice fishing + zombies + clam catcher keys", () => {
    expect(SESSION_BRAND_ASSETS.iceFishing).toBeTruthy();
    expect(SESSION_BRAND_ASSETS.zombies).toBeTruthy();
    expect(SESSION_BRAND_ASSETS.clamCatcher).toBeTruthy();
  });

  it("Werner mark renders thinking + celebrate using session asset module URLs", () => {
    // Drive the shipped Werner component — mood poses must resolve to the
    // session asset module URLs (real UI consumption).
    const thinking = render(<Werner mood="thinking" size={48} label="t" />);
    const thinkingImg = thinking.container.querySelector("img");
    expect(thinkingImg?.getAttribute("src")).toBe(SESSION_BRAND_ASSETS.thinking);
    thinking.unmount();

    const celebrate = render(<Werner mood="celebrate" size={48} label="c" />);
    const celebrateImg = celebrate.container.querySelector("img");
    expect(celebrateImg?.getAttribute("src")).toBe(
      SESSION_BRAND_ASSETS.celebrate,
    );
    celebrate.unmount();
  });

  it("source tree wires session celebrate/thinking into product chrome", () => {
    const root = join(process.cwd(), "src");
    const wernerSrc = readFileSync(join(root, "brand/Werner.tsx"), "utf8");
    const cabinetSrc = readFileSync(
      join(root, "arcade/ArcadeCabinet.tsx"),
      "utf8",
    );
    expect(wernerSrc).toMatch(/werner_thinking_session_v1\.png/);
    expect(wernerSrc).toMatch(/werner_celebrate_session_v1\.png/);
    expect(cabinetSrc).toMatch(/cabinet-brand-thinking/);
    expect(cabinetSrc).toMatch(/cabinet-brand-celebrate/);
    expect(cabinetSrc).toMatch(/werner_clam_catcher_session_v1\.png/);
  });
});
