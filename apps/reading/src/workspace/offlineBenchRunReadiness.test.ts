import { describe, expect, it } from "vitest";
import { offlineBenchRunReadiness } from "./offlineBenchRunReadiness";

describe("offlineBenchRunReadiness (ava)", () => {
  it("is not run_ready without week id", () => {
    const r = offlineBenchRunReadiness({});
    expect(r.run_ready).toBe(false);
    expect(r.block_reason).toBe("no_week_id");
    expect(r.offline_only).toBe(true);
    expect(r.never_auto_promote).toBe(true);
    expect(r.propose_neq_promote).toBe(true);
    expect(r.html_first).toBe(true);
    expect(r.run_title).toMatch(/Enter a week id/i);
  });

  it("is run_ready with week id", () => {
    const r = offlineBenchRunReadiness({ week_id: "  2026-W28  " });
    expect(r.run_ready).toBe(true);
    expect(r.week_id).toBe("2026-W28");
    expect(r.block_reason).toBe("ok");
    expect(r.summary).toMatch(/never auto-promote/);
    expect(r.run_title).toMatch(/propose≠promote|propose=not promote|never auto-promote/i);
  });
});
