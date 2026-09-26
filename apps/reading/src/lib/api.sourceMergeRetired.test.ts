import { describe, expect, it } from "vitest";

import * as api from "./api";

/**
 * Nothing writes into a source (T6, DECISIONS.md 2026-09-26). Lane B retires
 * /research/artifacts/source-merge/{preview,apply,commit} with a 410 (LB-33),
 * and the client keeps no caller of any source-merge route. Restore stays live
 * on the server for merges prod may already hold, but no surface can reach it
 * without a receipts read, so the client does not carry it either.
 */
describe("retired source merge", () => {
  it("exports no source-merge client", () => {
    for (const name of ["applySourceMerge", "previewSourceMerge", "commitSourceMerge", "restoreSourceMerge"]) {
      expect(name in api, name).toBe(false);
    }
  });
});
