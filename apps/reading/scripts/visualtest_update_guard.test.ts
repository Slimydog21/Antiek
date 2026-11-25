/**
 * Guard contract: macOS refuses, Linux passes, the ack override passes with a
 * warning, and the refusal text names the CI-artifact flow (the 2026-10-08
 * lesson must stay actionable, not just negative).
 */
import { describe, expect, it } from "vitest";

import { decide, REMINT_ACK_ENV } from "./visualtest_update_guard";

describe("visualtest update guard", () => {
  it("passes silently on Linux (the baseline host's rasterizer)", () => {
    expect(decide("linux", undefined)).toEqual({ ok: true, message: "" });
  });

  it("refuses a bare macOS run and names the CI-artifact flow", () => {
    const d = decide("darwin", undefined);
    expect(d.ok).toBe(false);
    expect(d.message).toContain("refused on macOS");
    expect(d.message).toContain("lostpixel-diffs");
    expect(d.message).toContain(".lostpixel/baseline/");
    expect(d.message).toContain(REMINT_ACK_ENV);
  });

  it("honors the deliberate-remint ack with a warning, not silence", () => {
    const d = decide("darwin", "1");
    expect(d.ok).toBe(true);
    expect(d.message).toContain("override acknowledged");
  });

  it("treats an empty ack as absent", () => {
    expect(decide("darwin", "").ok).toBe(false);
  });
});
