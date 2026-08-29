/**
 * releaseNotes.test.ts — the seen-once contract.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  hasSeenRelease,
  latestReleaseNote,
  markReleaseSeen,
  RELEASE_NOTES,
} from "./releaseNotes";

describe("release notes", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("the latest note exists and is staged with items", () => {
    const latest = latestReleaseNote();
    expect(RELEASE_NOTES[0]).toBe(latest);
    expect(latest.version).toBeTruthy();
    expect(latest.items.length).toBeGreaterThan(0);
  });

  it("unseen by default, seen after markReleaseSeen", () => {
    const v = latestReleaseNote().version;
    expect(hasSeenRelease(v)).toBe(false);
    markReleaseSeen(v);
    expect(hasSeenRelease(v)).toBe(true);
  });

  it("different versions are tracked independently", () => {
    markReleaseSeen("v1");
    expect(hasSeenRelease("v1")).toBe(true);
    expect(hasSeenRelease("v2")).toBe(false);
  });
});
