import { describe, expect, it, vi } from "vitest";
import {
  loadCitationEvidencePosition,
  storeCitationEvidencePosition,
} from "./citationEvidencePosition";

describe("citation evidence position", () => {
  it("stores only closed ordinal metadata under the exact receipt", () => {
    const rows = new Map<string, string>();
    const storage = {
      getItem: (key: string) => rows.get(key) ?? null,
      setItem: (key: string, value: string) => { rows.set(key, value); },
    };
    const receipt = "a".repeat(64);
    expect(storeCitationEvidencePosition(receipt, 3, 2, storage)).toBe(true);
    expect(loadCitationEvidencePosition(receipt, 3, storage)).toBe(2);
    const serialized = [...rows.values()][0];
    expect(serialized).toBe(JSON.stringify({ version: 1, receipt_sha256: receipt, index: 2, anchor_count: 3 }));
    expect(serialized).not.toMatch(/chunk|document|claim|html|source/i);
  });

  it("fails closed on receipt/count/schema/range drift and storage errors", () => {
    const receipt = "b".repeat(64);
    const malformed = { getItem: vi.fn(() => JSON.stringify({ version: 1, receipt_sha256: receipt, index: 9, anchor_count: 2 })) };
    expect(loadCitationEvidencePosition(receipt, 2, malformed)).toBe(0);
    expect(loadCitationEvidencePosition("bad", 2, malformed)).toBe(0);
    expect(storeCitationEvidencePosition(receipt, 2, 2, { setItem: vi.fn() })).toBe(false);
    expect(loadCitationEvidencePosition(receipt, 2, { getItem: () => { throw new Error("denied"); } })).toBe(0);
  });
});
