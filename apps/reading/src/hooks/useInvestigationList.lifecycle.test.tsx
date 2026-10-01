import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useInvestigationList } from "./useInvestigationList";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const response = (id: string) => new Response(JSON.stringify({ count: 1, investigations: [{ investigation_id: id }] }), { headers: { "Content-Type": "application/json" } });

it("ignores an old scope's late success after the replacement scope failed", async () => {
  let release = (_reply: Response) => {};
  const pending = new Promise<Response>((resolve) => { release = resolve; });
  vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockReturnValueOnce(pending).mockRejectedValueOnce(new Error("B unavailable")));
  const { result, rerender } = renderHook(({ scopeKey }) => useInvestigationList({ scopeKey, pollIntervalMs: 0 }), { initialProps: { scopeKey: "A" } });
  await act(async () => { rerender({ scopeKey: "B" }); });
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { release(response("old-A")); });
  expect(result.current.investigations).toEqual([]);
  expect(result.current.error).toBe("B unavailable");
});

it("ignores an old scope's late failure after the replacement scope succeeded", async () => {
  let reject = (_error: Error) => {};
  const pending = new Promise<Response>((_resolve, rejectRequest) => { reject = rejectRequest; });
  vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockReturnValueOnce(pending).mockResolvedValueOnce(response("current-B")));
  const { result, rerender } = renderHook(({ scopeKey }) => useInvestigationList({ scopeKey, pollIntervalMs: 0 }), { initialProps: { scopeKey: "A" } });
  await act(async () => { rerender({ scopeKey: "B" }); });
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { reject(new Error("Old A unavailable")); });
  expect(result.current.investigations.map((row) => row.investigation_id)).toEqual(["current-B"]);
  expect(result.current.error).toBeNull();
});

it("retains only the current scope's rows during a failed refresh and clears its error on retry", async () => {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValueOnce(response("current-A")).mockRejectedValueOnce(new Error("Refresh unavailable")).mockResolvedValueOnce(response("refreshed-A")));
  const { result } = renderHook(() => useInvestigationList({ scopeKey: "A", pollIntervalMs: 0 }));
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { result.current.refetch(); });
  await waitFor(() => expect(result.current.error).toBe("Refresh unavailable"));
  expect(result.current.loading).toBe(false);
  expect(result.current.investigations.map((row) => row.investigation_id)).toEqual(["current-A"]);
  await act(async () => { result.current.refetch(); });
  await waitFor(() => expect(result.current.investigations[0]?.investigation_id).toBe("refreshed-A"));
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBeNull();
});
