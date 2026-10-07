import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

import { recordAdImpressions } from "../../api/books";
import type { AdFillView } from "./AdBorder";
import { useReaderImpressions } from "./useReaderImpressions";
import {
  beforeWorkspaceOwnerChange,
  setWorkspaceOwner,
  workspaceOwnerSession,
} from "../../lib/accountWorkspaceOwner";

vi.mock("../../api/books", async (original) => ({
  ...await original<typeof import("../../api/books")>(),
  recordAdImpressions: vi.fn().mockResolvedValue(undefined),
}));

let clock = 0;
let hidden = false;
const houseFill = { kind: "house", house: null } satisfies AdFillView;
const slots = [{ slotId: "top", fill: houseFill }];

beforeEach(() => {
  clock = 0;
  hidden = false;
  setWorkspaceOwner("unit-reader-a");
  vi.spyOn(performance, "now").mockImplementation(() => clock);
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.mocked(recordAdImpressions).mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  vi.restoreAllMocks();
});

describe("focused reader dwell", () => {
  it("does not report loading or visibility events before a readable page exists", () => {
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useReaderImpressions("a", "session", callback));
    clock = 60_000;
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      result.current.flush();
    });
    unmount();
    expect(callback).not.toHaveBeenCalled();
    expect(recordAdImpressions).not.toHaveBeenCalled();
  });

  it("reports reading evidence without ad slots and excludes time before a page exists", () => {
    const onDwell = vi.fn();
    const { result } = renderHook(() => useReaderImpressions("a", "session", onDwell));
    clock = 90_000;
    act(() => result.current.observePage(0, []));
    clock = 110_000;
    act(() => result.current.observePage(1, []));
    clock = 120_000;
    act(() => result.current.flush());

    expect(onDwell).toHaveBeenLastCalledWith({ totalDwellMs: 30_000, pagesSeen: 2 });
    expect(recordAdImpressions).not.toHaveBeenCalled();
  });

  it("flushes the old document to its own callback, then starts the new document at zero", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { result, rerender } = renderHook(
      ({ id, callback }) => useReaderImpressions(id, "session", callback),
      { initialProps: { id: "a", callback: first } },
    );
    act(() => result.current.observePage(0, slots));
    clock = 20_000;
    act(() => result.current.observePage(1, slots));
    clock = 30_000;
    rerender({ id: "b", callback: second });

    expect(first).toHaveBeenLastCalledWith({ totalDwellMs: 30_000, pagesSeen: 2 });
    expect(second).not.toHaveBeenCalled();
    expect(recordAdImpressions).toHaveBeenLastCalledWith("a", "session", [
      expect.objectContaining({ page_index: 1, focused_dwell_ms: 10_000 }),
    ]);
    act(() => result.current.observePage(0, slots));
    clock = 35_000;
    act(() => result.current.flush());
    expect(second).toHaveBeenLastCalledWith({ totalDwellMs: 5_000, pagesSeen: 1 });
    expect(recordAdImpressions).toHaveBeenLastCalledWith("b", "session", [
      expect.objectContaining({ page_index: 0, focused_dwell_ms: 5_000 }),
    ]);
  });

  it("refuses retired document callbacks", () => {
    const callback = vi.fn();
    const { result, rerender } = renderHook(
      ({ id }) => useReaderImpressions(id, "session", callback),
      { initialProps: { id: "a" } },
    );
    act(() => result.current.observePage(0, slots));
    const retired = result.current;
    clock = 10_000;
    rerender({ id: "b" });
    callback.mockClear();
    vi.mocked(recordAdImpressions).mockClear();
    clock = 20_000;
    act(() => {
      retired.observePage(8, slots);
      retired.flush();
    });
    expect(callback).not.toHaveBeenCalled();
    expect(recordAdImpressions).not.toHaveBeenCalled();
    act(() => {
      result.current.observePage(0, []);
      result.current.flush();
    });
    expect(callback).toHaveBeenLastCalledWith({ totalDwellMs: 0, pagesSeen: 1 });
  });

  it("excludes hidden intervals including a flush and page turn while hidden", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    clock = 10_000;
    hidden = true;
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    clock = 40_000;
    act(() => result.current.observePage(1, slots));
    clock = 70_000;
    act(() => result.current.flush());
    expect(callback).toHaveBeenLastCalledWith({ totalDwellMs: 10_000, pagesSeen: 2 });
    hidden = false;
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    clock = 75_000;
    act(() => result.current.flush());
    expect(callback).toHaveBeenLastCalledWith({ totalDwellMs: 15_000, pagesSeen: 2 });
  });

  it("keeps dwell on a same-document render and uses the current callback", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { result, rerender } = renderHook(
      ({ callback }) => useReaderImpressions("a", "session", callback),
      { initialProps: { callback: first } },
    );
    act(() => result.current.observePage(0, []));
    clock = 10_000;
    rerender({ callback: second });
    clock = 15_000;
    act(() => result.current.flush());
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenLastCalledWith({ totalDwellMs: 15_000, pagesSeen: 1 });
  });

  it("retires a changed reading session even for the same document", () => {
    const callback = vi.fn();
    const { result, rerender } = renderHook(
      ({ session }) => useReaderImpressions("a", session, callback),
      { initialProps: { session: "first" } },
    );
    act(() => result.current.observePage(4, []));
    clock = 20_000;
    rerender({ session: "second" });
    act(() => result.current.observePage(0, []));
    clock = 25_000;
    act(() => result.current.flush());
    expect(callback).toHaveBeenLastCalledWith({ totalDwellMs: 5_000, pagesSeen: 1 });
  });

  it("reports the final page on unmount despite failed ad bookkeeping and refuses later callbacks", async () => {
    vi.mocked(recordAdImpressions).mockRejectedValue(new TypeError("controlled ad outage"));
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    clock = 10_000;
    unmount();
    await act(async () => {});
    expect(callback).toHaveBeenCalledExactlyOnceWith({ totalDwellMs: 10_000, pagesSeen: 1 });
    expect(recordAdImpressions).toHaveBeenCalledTimes(1);
    clock = 20_000;
    act(() => result.current.flush());
    expect(callback).toHaveBeenCalledTimes(1);
    expect(recordAdImpressions).toHaveBeenCalledTimes(1);
  });

  it("refuses account-retired cleanup and deferred callbacks before React can render", async () => {
    let finishImpression: (() => void) | undefined;
    vi.mocked(recordAdImpressions).mockReturnValue(new Promise<void>((resolve) => {
      finishImpression = resolve;
    }));
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    clock = 20_000;
    act(() => result.current.observePage(1, slots));
    expect(recordAdImpressions).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenLastCalledWith({ totalDwellMs: 20_000, pagesSeen: 1 });
    const retired = result.current;
    callback.mockClear();
    clock = 30_000;

    act(() => {
      setWorkspaceOwner("unit-reader-b");
      retired.flush();
      retired.observePage(9, slots);
      unmount();
    });
    await act(async () => {
      if (!finishImpression) throw new Error("The admitted impression did not start");
      finishImpression();
    });

    expect(recordAdImpressions).toHaveBeenCalledTimes(1);
    expect(callback).not.toHaveBeenCalled();
  });

  it("refuses an A-B-A account replacement and starts the new owner at zero", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    const retired = result.current;
    const firstOwner = workspaceOwnerSession();
    clock = 30_000;
    act(() => {
      setWorkspaceOwner("unit-reader-b");
      setWorkspaceOwner("unit-reader-a");
      retired.flush();
    });
    expect(workspaceOwnerSession()).not.toBe(firstOwner);
    expect(recordAdImpressions).not.toHaveBeenCalled();
    expect(callback).not.toHaveBeenCalled();
    act(() => result.current.observePage(0, []));
    clock = 35_000;
    act(() => result.current.flush());
    expect(callback).toHaveBeenCalledExactlyOnceWith({ totalDwellMs: 5_000, pagesSeen: 1 });
  });

  it("preserves the two-page leave flush when the same owner is verified again", () => {
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useReaderImpressions("a", "session", callback));
    const owner = workspaceOwnerSession();
    act(() => result.current.observePage(0, slots));
    clock = 20_000;
    act(() => result.current.observePage(1, slots));
    clock = 30_000;
    act(() => setWorkspaceOwner("unit-reader-a"));
    unmount();
    expect(workspaceOwnerSession()).toBe(owner);
    expect(callback).toHaveBeenLastCalledWith({ totalDwellMs: 30_000, pagesSeen: 2 });
    expect(recordAdImpressions).toHaveBeenLastCalledWith("a", "session", [
      expect.objectContaining({ page_index: 1, focused_dwell_ms: 10_000 }),
    ]);
  });

  it("retires before another retirement listener can flush under the old identity", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    const owner = workspaceOwnerSession();
    const retired = result.current;
    const duringRetirement = vi.fn(() => {
      expect(workspaceOwnerSession()).toBe(owner);
      retired.flush();
    });
    const unsubscribe = beforeWorkspaceOwnerChange(duringRetirement);
    clock = 30_000;
    try {
      act(() => setWorkspaceOwner("unit-reader-b"));
    } finally {
      unsubscribe();
    }
    expect(duringRetirement).toHaveBeenCalledTimes(1);
    expect(recordAdImpressions).not.toHaveBeenCalled();
    expect(callback).not.toHaveBeenCalled();
  });

  it("refuses logged-out measurement and cleanup", () => {
    setWorkspaceOwner(null);
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    clock = 30_000;
    act(() => result.current.flush());
    unmount();
    expect(recordAdImpressions).not.toHaveBeenCalled();
    expect(callback).not.toHaveBeenCalled();
  });

  it("rechecks the owner before onDwell when impression dispatch retires it", () => {
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useReaderImpressions("a", "session", callback));
    act(() => result.current.observePage(0, slots));
    vi.mocked(recordAdImpressions).mockImplementation(async () => {
      setWorkspaceOwner(null);
    });
    clock = 30_000;
    act(() => result.current.flush());
    unmount();
    expect(recordAdImpressions).toHaveBeenCalledTimes(1);
    expect(callback).not.toHaveBeenCalled();
  });
});
