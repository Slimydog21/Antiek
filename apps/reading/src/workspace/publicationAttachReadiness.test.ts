import { describe, expect, it } from "vitest";
import { publicationAttachReadiness } from "./publicationAttachReadiness";

describe("publicationAttachReadiness residual (asb)", () => {
  it("is not ready without spawn or refs", () => {
    const r = publicationAttachReadiness({});
    expect(r.attach_ready).toBe(false);
    expect(r.spawn_bound).toBe(false);
    expect(r.ref_count).toBe(0);
    expect(r.html_first).toBe(true);
    expect(r.view_format).toBe("html");
    expect(r.live_hydrate_deferred).toBe(true);
    expect(r.never_auto_hydrate).toBe(true);
    expect(r.summary).toMatch(/bind spawn/i);
  });

  it("requires spawn bound and ≥1 ref", () => {
    expect(
      publicationAttachReadiness({ spawnId: "spn_1", refCount: 0 }).attach_ready,
    ).toBe(false);
    expect(
      publicationAttachReadiness({ spawnId: "", refCount: 2 }).attach_ready,
    ).toBe(false);
    const ready = publicationAttachReadiness({
      spawnId: "spn_1",
      refCount: 2,
    });
    expect(ready.attach_ready).toBe(true);
    expect(ready.spawn_bound).toBe(true);
    expect(ready.ref_count).toBe(2);
    expect(ready.summary).toMatch(/attach ready/i);
    expect(ready.summary).toMatch(/L1\/L2 deferred/i);
  });

  it("floors negative ref counts and trims spawn", () => {
    expect(
      publicationAttachReadiness({ spawnId: "  ", refCount: -3 }).ref_count,
    ).toBe(0);
    expect(
      publicationAttachReadiness({ spawnId: "  spn  ", refCount: 1 }).spawn_bound,
    ).toBe(true);
  });
});
