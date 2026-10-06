import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

const { notified } = vi.hoisted(() => ({ notified: vi.fn() }));
vi.mock("react", async (original) => {
  const actual = await original<typeof import("react")>();
  const subscriptions = new WeakMap<Parameters<typeof actual.useSyncExternalStore>[0], Parameters<typeof actual.useSyncExternalStore>[0]>();
  return {
    ...actual,
    useSyncExternalStore: <T,>(subscribe: Parameters<typeof actual.useSyncExternalStore>[0], snapshot: () => T, serverSnapshot?: () => T) => {
      let observed = subscriptions.get(subscribe);
      if (!observed) {
        observed = (listener) => subscribe(() => { notified(); listener(); });
        subscriptions.set(subscribe, observed);
      }
      return actual.useSyncExternalStore(observed, snapshot, serverSnapshot);
    },
  };
});

import {
  notifyReadingPositionOwner,
  readingPositionOwnerEpoch,
  setReadingPositionOwner,
  usePositionOwner,
  usePositionOwnerEpoch,
} from "./usePosition";

afterEach(() => {
  cleanup();
  setReadingPositionOwner(null);
  notified.mockClear();
});

describe("owner epoch, client lifetime observation only", () => {
  it("keeps same-owner verification stable", () => {
    setReadingPositionOwner("control-a");
    const epoch = readingPositionOwnerEpoch();
    const { result } = renderHook(usePositionOwnerEpoch);
    act(() => setReadingPositionOwner("control-a"));
    expect(readingPositionOwnerEpoch()).toBe(epoch);
    expect(result.current).toBe(epoch);
    expect(notified).not.toHaveBeenCalled();
  });

  it("advances twice for silent A-B-A before a render or notification", () => {
    setReadingPositionOwner("control-a");
    const { result } = renderHook(usePositionOwnerEpoch);
    const epoch = result.current;
    act(() => {
      setReadingPositionOwner("control-b", false);
      expect(readingPositionOwnerEpoch()).toBe(epoch + 1);
      setReadingPositionOwner("control-a", false);
      expect(readingPositionOwnerEpoch()).toBe(epoch + 2);
    });
    expect(result.current).toBe(epoch);
    expect(notified).not.toHaveBeenCalled();
    act(notifyReadingPositionOwner);
    expect(result.current).toBe(epoch + 2);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it("uses the existing notification path for both owner and epoch", () => {
    setReadingPositionOwner("control-a");
    const { result } = renderHook(() => ({ owner: usePositionOwner(), epoch: usePositionOwnerEpoch() }));
    const epoch = result.current.epoch;
    act(() => setReadingPositionOwner("control-b"));
    expect(result.current).toEqual({ owner: "control-b", epoch: epoch + 1 });
    expect(notified).toHaveBeenCalledTimes(2);
  });

  it("removes the observer subscription on unmount", () => {
    const { unmount } = renderHook(usePositionOwnerEpoch);
    unmount();
    act(() => setReadingPositionOwner("control-a"));
    act(notifyReadingPositionOwner);
    expect(notified).not.toHaveBeenCalled();
  });
});
