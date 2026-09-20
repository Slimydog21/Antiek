/**
 * seen.test.ts — last-seen storage contract.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { allSeen, getSeenVersion, lastSeenAt, markSeen, subscribeSeen } from "./seen";

const KEY = "antiek:last_seen:v1";

describe("seen store", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts with nothing seen", () => {
    expect(lastSeenAt("inv-1")).toBeNull();
    expect(allSeen()).toEqual({});
  });

  it("markSeen records an ISO timestamp", () => {
    markSeen("inv-1");
    const at = lastSeenAt("inv-1");
    expect(at).not.toBeNull();
    expect(() => new Date(at as string).toISOString()).not.toThrow();
  });

  it("markSeen is idempotent per id and independent across ids", () => {
    markSeen("inv-1");
    markSeen("inv-1");
    markSeen("inv-2");
    expect(Object.keys(allSeen()).sort()).toEqual(["inv-1", "inv-2"]);
  });

  it("ignores empty ids", () => {
    markSeen("");
    expect(allSeen()).toEqual({});
  });

  it("survives a reload (same storage key)", () => {
    markSeen("inv-9");
    const raw = window.localStorage.getItem(KEY);
    expect(raw).toContain("inv-9");
  });

  it("tolerates corrupt storage (returns empty, does not throw)", () => {
    window.localStorage.setItem(KEY, "{not json");
    expect(lastSeenAt("inv-1")).toBeNull();
    expect(allSeen()).toEqual({});
  });

  it("tolerates non-object storage (returns empty, does not throw)", () => {
    window.localStorage.setItem(KEY, '"just a string"');
    expect(allSeen()).toEqual({});
  });
});

describe("seen store — reactivity", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("subscribeSeen fires on markSeen and unsubscribes cleanly", () => {
    const spy = vi.fn();
    const unsub = subscribeSeen(spy);
    markSeen("inv-1");
    expect(spy).toHaveBeenCalledTimes(1);
    unsub();
    markSeen("inv-2");
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("getSeenVersion advances on markSeen", () => {
    const v0 = getSeenVersion();
    markSeen("inv-1");
    expect(getSeenVersion()).toBeGreaterThan(v0);
  });
});