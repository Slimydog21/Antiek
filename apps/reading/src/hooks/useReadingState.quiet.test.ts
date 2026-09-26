/**
 * FFX SPR-04 M8 (A-16, client half): the first open of a book has no reading
 * position yet. The backend answers 404 `reading_state_not_found`; that is
 * the designed empty state, so the hook must not log an error and must keep
 * the bus reachable (a later page turn is written, not held as "offline").
 *
 * Honest scope note: at main this path already logged nothing from JS (the
 * console line A-16 saw is Chromium's own network log for any 4xx fetch,
 * which page code cannot suppress). This test pins that contract so a future
 * change cannot start logging it; the network-log half needs the backend to
 * answer 204/200 (Astra).
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: (input: unknown, init?: unknown) => apiFetchMock(input, init),
}));

import {
  READING_STATE_DEBOUNCE_MS,
  resetReadingStateBus,
  setReadingStateOwner,
  useReadingState,
  useReadingStateBus,
} from "./useReadingState";

const DOC = "doc-first-open";

beforeEach(() => {
  apiFetchMock.mockReset();
  sessionStorage.clear();
  resetReadingStateBus();
  setReadingStateOwner("reader-quiet");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useReadingState first open (A-16)", () => {
  it("a 404 reading_state_not_found logs no error and keeps the bus reachable", async () => {
    const errorSpy = vi.spyOn(console, "error");
    const warnSpy = vi.spyOn(console, "warn");
    apiFetchMock.mockImplementation(async (_url: unknown, init?: { method?: string }) => {
      if (init?.method === "PUT") {
        return new Response(
          JSON.stringify({
            document_id: DOC,
            page_index: 3,
            anchor_ref: null,
            prefs: {},
            revision: 1,
            updated_at: "2026-09-27T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ detail: "reading_state_not_found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    });

    const { result } = renderHook(() => useReadingState(DOC, 10));
    await waitFor(() => expect(useReadingStateBus.getState().byDocument[DOC]?.loaded).toBe(true));
    const entry = useReadingStateBus.getState().byDocument[DOC];
    expect(entry.reachable).toBe(true);
    expect(entry.revision).toBe(0);

    act(() => result.current.setPageIndex(3));
    await waitFor(
      () => expect(apiFetchMock.mock.calls.some(([, init]) => (init as { method?: string } | undefined)?.method === "PUT")).toBe(true),
      { timeout: READING_STATE_DEBOUNCE_MS + 2000 },
    );

    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
