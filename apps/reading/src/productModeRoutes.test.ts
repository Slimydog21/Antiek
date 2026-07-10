/**
 * Structural tests for shell registration of Midnight Oil + Marketplace Host.
 * Drives the shipped PRODUCT_MODE_ROUTES registry (and App import binding).
 */

import { describe, expect, it } from "vitest";
import {
  PRODUCT_MODE_ROUTES,
  productModeByPath,
  productModePaths,
  productModeRegistrySnapshot,
} from "./productModeRoutes";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import MarketplaceHost from "./modes/MarketplaceHost";
import MidnightOil from "./modes/MidnightOil";
import { modeById } from "./shell/workflowTaxonomy";

const __dirname = dirname(fileURLToPath(import.meta.url));

describe("productModeRoutes shell registration", () => {
  it("registers midnight-oil and marketplace/host paths", () => {
    const paths = productModePaths();
    expect(paths).toContain("/midnight-oil");
    expect(paths).toContain("/marketplace/host");
    expect(paths.length).toBe(2);
  });

  it("binds paths to the shipped mode components", () => {
    const moil = productModeByPath("/midnight-oil");
    const mkt = productModeByPath("/marketplace/host");
    expect(moil).toBeDefined();
    expect(mkt).toBeDefined();
    expect(moil!.Component).toBe(MidnightOil);
    expect(mkt!.Component).toBe(MarketplaceHost);
    expect(moil!.modeId).toBe("MidnightOil");
    expect(mkt!.modeId).toBe("MarketplaceHost");
  });

  it("declares HTML-first viewFormat for every product mode", () => {
    for (const r of PRODUCT_MODE_ROUTES) {
      expect(r.viewFormat).toBe("html");
    }
  });

  it("double-run registry snapshot is stable", () => {
    const a = productModeRegistrySnapshot();
    const b = productModeRegistrySnapshot();
    expect(a).toEqual(b);
    expect(a.map((x) => x.path).sort()).toEqual(
      ["/marketplace/host", "/midnight-oil"].sort(),
    );
    expect(a.every((x) => x.viewFormat === "html")).toBe(true);
  });

  it("workflow taxonomy points at the same routes", () => {
    const moil = modeById("MidnightOil");
    const mkt = modeById("MarketplaceHost");
    expect(moil?.built).toBe(true);
    expect(mkt?.built).toBe(true);
    expect(moil?.route).toBe("/midnight-oil");
    expect(mkt?.route).toBe("/marketplace/host");
  });

  it("Midnight Oil blurb stamps multi-goal swarm honesty (aoj)", () => {
    const moil = productModeByPath("/midnight-oil");
    expect(moil?.blurb || "").toMatch(/multi-goal/i);
    expect(moil?.blurb || "").toMatch(/templates|one per line/i);
    expect(moil?.blurb || "").toMatch(/price ceiling/i);
    expect(moil?.viewFormat).toBe("html");
    const tax = modeById("MidnightOil");
    expect(tax?.description || tax?.blurb || "").toMatch(/multi-goal/i);
  });

  it("Marketplace host blurb stamps domain-aware HTML research land (aon)", () => {
    const mkt = productModeByPath("/marketplace/host");
    expect(mkt?.blurb || "").toMatch(/HTML/i);
    expect(mkt?.blurb || "").toMatch(/domain-aware|twin|DR/i);
    expect(mkt?.viewFormat).toBe("html");
  });

  it("App.tsx consumes PRODUCT_MODE_ROUTES for shell wiring", () => {
    const appSrc = readFileSync(join(__dirname, "App.tsx"), "utf-8");
    expect(appSrc).toContain("PRODUCT_MODE_ROUTES");
    expect(appSrc).toContain("productModeRoutes");
    // Modes are not inlined as separate hard-coded Route paths (registry owns them).
    expect(appSrc).not.toMatch(/path="\/midnight-oil"/);
    expect(appSrc).not.toMatch(/path="\/marketplace\/host"/);
  });

  it("mode sources retain data-view-format html", () => {
    const moil = readFileSync(
      join(__dirname, "modes/MidnightOil/index.tsx"),
      "utf-8",
    );
    const mkt = readFileSync(
      join(__dirname, "modes/MarketplaceHost/index.tsx"),
      "utf-8",
    );
    expect(moil).toContain('data-view-format="html"');
    expect(mkt).toContain('data-view-format="html"');
  });
});
