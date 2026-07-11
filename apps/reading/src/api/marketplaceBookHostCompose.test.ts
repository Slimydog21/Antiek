import { describe, expect, it } from "vitest";
import {
  composeMarketplaceBookHost,
  formatMarketplaceComposeSummary,
} from "./marketplaceBookHostCompose";

describe("composeMarketplaceBookHost", () => {
  it("free hit blocks purchase and may host with sha", () => {
    const d = composeMarketplaceBookHost({
      title: "Walden",
      free_copy_available: true,
      html_projection_sha: "sha:ready",
      host_requested: true,
    });
    expect(d.purchase_intent_allowed).toBe(false);
    expect(d.purchase_executed).toBe(false);
    expect(d.hosted).toBe(false);
    expect(d.path).toBe("html_host");
    expect(d.hostable).toBe(true);
  });

  it("free miss allows purchase intent", () => {
    const d = composeMarketplaceBookHost({
      title: "Unknown Book",
      free_copy_available: false,
    });
    expect(d.path).toBe("purchase_intent");
    expect(d.purchase_intent_allowed).toBe(true);
    expect(d.purchase_executed).toBe(false);
    expect(d.hosted).toBe(false);
  });

  it("unknown free copy is incomplete (no invent miss)", () => {
    const d = composeMarketplaceBookHost({
      title: "Maybe Free",
      free_copy_available: null,
    });
    expect(d.path).toBe("incomplete");
    expect(d.purchase_intent_allowed).toBe(false);
  });

  it("skip free without ack blocks", () => {
    const d = composeMarketplaceBookHost({
      title: "X",
      free_copy_available: false,
      skip_free_copy: true,
      operator_skip_acknowledged: false,
    });
    expect(d.path).toBe("blocked");
  });

  it("free miss + sha + host → html_host still not purchased/hosted", () => {
    const d = composeMarketplaceBookHost({
      title: "Bought Book",
      free_copy_available: false,
      html_projection_sha: "sha:html",
      host_requested: true,
    });
    expect(d.path).toBe("html_host");
    expect(d.purchase_executed).toBe(false);
    expect(d.hosted).toBe(false);
    expect(d.hostable).toBe(true);
  });

  it("rejects empty title", () => {
    expect(() =>
      composeMarketplaceBookHost({
        title: "  ",
        free_copy_available: false,
      }),
    ).toThrow(/title/);
  });
});

describe("formatMarketplaceComposeSummary", () => {
  it("summarizes honesty", () => {
    const d = composeMarketplaceBookHost({
      title: "T",
      free_copy_available: false,
    });
    expect(formatMarketplaceComposeSummary(d)).toMatch(/purchase_executed=false/);
    expect(formatMarketplaceComposeSummary(d)).toMatch(/hosted=false/);
  });
});
