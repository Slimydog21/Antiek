import { describe, expect, it } from "vitest";

import * as api from "./api";

/**
 * Nothing writes into a source (T6, DECISIONS.md 2026-09-26). Lane B retires
 * /research/artifacts/source-merge/{preview,apply,commit} with a 410 (LB-33),
 * and the client keeps no caller of any source-merge route. Restore stays live
 * on the server for merges prod may already hold, but no surface can reach it
 * without a receipts read, so the client does not carry it either.
 */
/** Every non-test source file in apps/reading/src, as text. */
const sources = import.meta.glob(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}", "!../**/*.stories.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("retired source merge", () => {
  it("exports no source-merge client", () => {
    for (const name of ["applySourceMerge", "previewSourceMerge", "commitSourceMerge", "restoreSourceMerge"]) {
      expect(name in api, name).toBe(false);
    }
    expect(Object.keys(api).filter((key) => /SourceMerge/.test(key))).toEqual([]);
  });

  it("no source file calls a source-merge route, exported or not", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(100);
    const callers = Object.entries(sources)
      .filter(([, text]) => text.includes("artifacts/source-merge"))
      .map(([path]) => path);
    expect(callers).toEqual([]);
  });
});
