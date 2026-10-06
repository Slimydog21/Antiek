import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

import { recordAdImpressions } from "../../api/books";
import type { AdFillView } from "./AdBorder";
import { useReaderImpressions } from "./useReaderImpressions";

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
  vi.spyOn(performance, "now").mockImplementation(() => clock);
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.mocked(recordAdImpressions).mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
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
});
