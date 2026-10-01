import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useInvestigationList } from "./useInvestigationList";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("reports an initial list failure without pretending the request is pending", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("list unavailable"); }));
  const { result } = renderHook(() => useInvestigationList({ scopeKey: "confirmed-owner:project-A", pollIntervalMs: 0 }));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBeTruthy();
  expect(result.current.investigations).toEqual([]);
});

it("settles an authorized same-owner project-scope list failure without exposing the previous scope", async () => {
  const fetcher = vi.fn<typeof fetch>()
    .mockResolvedValueOnce(new Response(JSON.stringify({ count: 1, investigations: [{ investigation_id: "old-project-thread" }] }), { headers: { "Content-Type": "application/json" } }))
    .mockRejectedValueOnce(new Error("list unavailable"));
  vi.stubGlobal("fetch", fetcher);
  const { result, rerender } = renderHook(({ scopeKey }) => useInvestigationList({ scopeKey, pollIntervalMs: 0 }), {
    initialProps: { scopeKey: "confirmed-owner:project-A" },
  });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.investigations).toHaveLength(1);
  await act(async () => { rerender({ scopeKey: "confirmed-owner:project-B" }); });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(result.current.investigations).toEqual([]);
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBeTruthy();
});
