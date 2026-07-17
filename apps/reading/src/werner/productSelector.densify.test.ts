/**
 * densify: productSelector pins invent product doors to the documented
 * [data-product-id] contract so living-TV choreography can resolve the same
 * surfaces Home / ArcadeCabinet / ResearchWaitArcade stamp.
 */
import { describe, expect, it } from "vitest";

import { productSelector } from "./choreography";

describe("productSelector densify", () => {
  it("pins invent product doors to the data-product-id selector contract", () => {
    for (const id of [
      "research",
      "read",
      "write",
      "arcade",
      "home-arcade",
      "book-marketplace",
      "wait-arcade",
      "ice-fishing",
      "clam-catcher",
      "zombies",
      "midnight-oil",
      "antiek-bench",
      "settings",
    ]) {
      expect(productSelector({ productId: id, source: "click" })).toBe(
        `[data-product-id="${id}"]`,
      );
      expect(productSelector({ productId: id, source: "hotkey" })).toBe(
        `[data-product-id="${id}"]`,
      );
    }
  });

  it("click and hotkey share the identical selector densify (parity)", () => {
    const click = productSelector({ productId: "research", source: "click" });
    const hotkey = productSelector({ productId: "research", source: "hotkey" });
    expect(click).toBe(hotkey);
    expect(click).toBe('[data-product-id="research"]');
  });
});
