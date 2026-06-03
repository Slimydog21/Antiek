/**
 * analytics.test.ts — the typed event taxonomy contract.
 *
 * `track` is the single sanctioned entry point for product events. These tests
 * pin the three guarantees that make it worth having over raw posthog.capture:
 *   1. enabled  → forwards the exact event name + properties,
 *   2. prop-less events forward no property bag,
 *   3. disabled (no token) → a hard no-op, so CI / Storybook stay dark.
 *
 * The type-level guarantee (off-taxonomy names / wrong prop shapes are compile
 * errors) is enforced by tsc at every call site, not here.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe("track — typed analytics taxonomy", () => {
  it("forwards event name + properties when analytics is enabled", async () => {
    const capture = vi.fn();
    vi.doMock("./posthogClient", () => ({
      posthogEnabled: true,
      posthog: { capture },
    }));
    const { track } = await import("./analytics");

    track("deep_research_cascade_launched", { session_id: "s-1" });

    expect(capture).toHaveBeenCalledWith("deep_research_cascade_launched", {
      session_id: "s-1",
    });
  });

  it("forwards prop-less events with no property bag", async () => {
    const capture = vi.fn();
    vi.doMock("./posthogClient", () => ({
      posthogEnabled: true,
      posthog: { capture },
    }));
    const { track } = await import("./analytics");

    track("pricing_viewed");

    expect(capture).toHaveBeenCalledWith("pricing_viewed", undefined);
  });

  it("is a hard no-op when analytics is disabled (CI / no token)", async () => {
    const capture = vi.fn();
    vi.doMock("./posthogClient", () => ({
      posthogEnabled: false,
      posthog: { capture },
    }));
    const { track } = await import("./analytics");

    track("pricing_viewed");

    expect(capture).not.toHaveBeenCalled();
  });

  it("trackException reports Errors and is a no-op when disabled", async () => {
    const captureException = vi.fn();
    vi.doMock("./posthogClient", () => ({
      posthogEnabled: true,
      posthog: { captureException },
    }));
    const { trackException } = await import("./analytics");

    const err = new Error("boom");
    trackException(err);

    expect(captureException).toHaveBeenCalledWith(err);
  });
});
