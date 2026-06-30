import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  readReviewDuePolicy,
  useReviewDuePolicy,
  writeReviewDuePolicy,
} from "./reviewDuePolicy";

const originalLocalStorage = window.localStorage;

function installLocalStorageStub(overrides: Partial<Storage> = {}) {
  const values = new Map<string, string>();
  const storage = {
    get length() {
      return values.size;
    },
    clear: vi.fn(() => values.clear()),
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    key: vi.fn((index: number) => Array.from(values.keys())[index] ?? null),
    removeItem: vi.fn((key: string) => {
      values.delete(key);
    }),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
    ...overrides,
  } as Storage;
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: storage,
  });
  return storage;
}

beforeEach(() => {
  installLocalStorageStub();
});

afterEach(() => {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: originalLocalStorage,
  });
  vi.restoreAllMocks();
});

describe("reviewDuePolicy", () => {
  it("defaults review cues on when no operator preference exists", () => {
    expect(readReviewDuePolicy()).toBe(true);

    const { result } = renderHook(() => useReviewDuePolicy());

    expect(result.current[0]).toBe(true);
  });

  it("persists an explicit off policy and restores default-on by removing it", () => {
    writeReviewDuePolicy(false);
    expect(readReviewDuePolicy()).toBe(false);

    writeReviewDuePolicy(true);
    expect(readReviewDuePolicy()).toBe(true);
  });

  it("updates hook state and localStorage together", () => {
    const { result } = renderHook(() => useReviewDuePolicy());

    act(() => result.current[1](false));
    expect(result.current[0]).toBe(false);
    expect(readReviewDuePolicy()).toBe(false);

    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(readReviewDuePolicy()).toBe(true);
  });

  it("falls back to default-on when localStorage cannot be read", () => {
    installLocalStorageStub({
      getItem: vi.fn(() => {
        throw new Error("blocked");
      }),
    });

    expect(readReviewDuePolicy()).toBe(true);
  });
});
