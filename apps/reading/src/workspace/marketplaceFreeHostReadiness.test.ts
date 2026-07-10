import { describe, expect, it } from "vitest";

import { marketplaceFreeHostReadiness } from "./marketplaceFreeHostReadiness";

describe("marketplaceFreeHostReadiness residual (aru)", () => {
  it("is not host_ready when no free books visible", () => {
    const r = marketplaceFreeHostReadiness({});
    expect(r.host_ready).toBe(false);
    expect(r.receipt_required).toBe(false);
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
    expect(r.live_payment).toBe(false);
    expect(r.summary).toMatch(/no free books visible/i);
  });

  it("is host_ready when free catalog has rows", () => {
    const r = marketplaceFreeHostReadiness({
      freeCatalogVisible: 3,
      freePdOnlyFilter: false,
    });
    expect(r.host_ready).toBe(true);
    expect(r.free_catalog_visible).toBe(3);
    expect(r.summary).toMatch(/3 free book/i);
    expect(r.summary).toMatch(/never PDF/i);
    expect(r.summary).toMatch(/no receipt required/i);
  });

  it("stamps free-only filter honesty", () => {
    const empty = marketplaceFreeHostReadiness({
      freeCatalogVisible: 0,
      freePdOnlyFilter: true,
    });
    expect(empty.free_pd_only_filter).toBe(true);
    expect(empty.summary).toMatch(/free-only filter/i);

    const ready = marketplaceFreeHostReadiness({
      freeCatalogVisible: 2,
      freePdOnlyFilter: true,
    });
    expect(ready.summary).toMatch(/free-only filter on/i);
  });

  it("never invents free counts from negatives", () => {
    const r = marketplaceFreeHostReadiness({ freeCatalogVisible: -5 });
    expect(r.free_catalog_visible).toBe(0);
    expect(r.host_ready).toBe(false);
  });
});
