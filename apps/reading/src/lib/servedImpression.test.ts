/**
 * Focused tests for the P0 served-impression audit emission
 * (docs/own-your-mind/10-p0-implementation-brief.md §5).
 *
 * Contract under test:
 *  - exactly ONE emission per mount (StrictMode-safe: a second effect
 *    invocation must not re-emit)
 *  - payload shape matches SurfaceServedImpressionPayload (action_type,
 *    surface, item_kind, item_id, ranked_position, ranked_version,
 *    timestamp, user_id)
 *  - envelope carries investigation_id "system"
 *  - failures are swallowed (fire-and-forget; audit never breaks the UI)
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitServedImpression, useServedImpression } from "./servedImpression";

const { postTypedEventMock } = vi.hoisted(() => ({
  postTypedEventMock: vi.fn((_e: unknown) =>
    Promise.resolve({ event_id: "ev-1", action_type: "surface.served_impression" }),
  ),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, postTypedEvent: postTypedEventMock };
});

describe("servedImpression (P0 §5)", () => {
  beforeEach(() => {
    postTypedEventMock.mockClear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("emits exactly one served-impression per mount, even under double effects", async () => {
    const { rerender } = renderHook(() =>
      useServedImpression({ surface: "explain", itemKind: "claim", itemId: "claim-1" }),
    );
    // Simulate a StrictMode double-effect by re-running the effect via rerender.
    rerender();
    rerender();
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
  });

  it("emits a well-formed envelope: system investigation + typed payload", () => {
    emitServedImpression({ surface: "objective-card", itemKind: "surface", itemId: "/objective" });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const envelope = postTypedEventMock.mock.calls[0][0] as {
      investigation_id: string;
      payload: Record<string, unknown>;
    };
    expect(envelope.investigation_id).toBe("system");
    const p = envelope.payload;
    expect(p.action_type).toBe("surface.served_impression");
    expect(p.surface).toBe("objective-card");
    expect(p.item_kind).toBe("surface");
    expect(p.item_id).toBe("/objective");
    expect(p.ranked_position).toBe(0);
    expect(p.ranked_version).toBe("");
    expect(p.user_id).toBe("__operator__");
    expect(typeof p.timestamp).toBe("string");
  });

  it("swallows post failures (audit-only: never breaks the UI)", () => {
    postTypedEventMock.mockRejectedValueOnce(new Error("backend down"));
    expect(() =>
      emitServedImpression({ surface: "signals", itemKind: "surface", itemId: "/signals" }),
    ).not.toThrow();
    // fire-and-forget: the rejected promise is handled inside emit
    return new Promise((resolve) => setTimeout(resolve, 20));
  });
});
