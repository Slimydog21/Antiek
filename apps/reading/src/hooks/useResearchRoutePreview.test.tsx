import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { previewMock } = vi.hoisted(() => ({ previewMock: vi.fn() }));
vi.mock("../lib/api", async (original) => {
  const actual = await original<typeof import("../lib/api")>();
  return { ...actual, previewResearchRoutes: previewMock };
});

import { useResearchRoutePreview } from "./useResearchRoutePreview";

afterEach(() => {
  vi.useRealTimers();
  previewMock.mockReset();
});

describe("useResearchRoutePreview", () => {
  it("debounces and ignores a superseded response", async () => {
    vi.useFakeTimers();
    let resolveFirst!: (value: unknown) => void;
    previewMock
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({
        policy_version: "research-route.v1",
        prompt_fingerprint: "new",
        candidates: [],
        budget: {
          authority: "advisory",
          daily_cap_usd: null,
          spent_usd: null,
          spent_status: "unknown",
          cap_source: null,
          notes: [],
          projection_status: "unavailable",
          projection_note: "Trajectory cost is unavailable.",
        },
      });
    const { result, rerender } = renderHook(
      ({ question }) => useResearchRoutePreview(question),
      { initialProps: { question: "first question" } },
    );
    await act(() => vi.advanceTimersByTimeAsync(300));
    rerender({ question: "new question" });
    await act(() => vi.advanceTimersByTimeAsync(300));
    await act(async () => { await Promise.resolve(); });
    expect(result.current.preview?.prompt_fingerprint).toBe("new");
    await act(async () => resolveFirst({ prompt_fingerprint: "old" }));
    expect(result.current.preview?.prompt_fingerprint).toBe("new");
  });

  it("surfaces an honest retryable error", async () => {
    vi.useFakeTimers();
    previewMock.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useResearchRoutePreview("valid question"));
    await act(() => vi.advanceTimersByTimeAsync(300));
    await act(async () => { await Promise.resolve(); });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("offline");
    expect(result.current.preview).toBeNull();
  });
});
