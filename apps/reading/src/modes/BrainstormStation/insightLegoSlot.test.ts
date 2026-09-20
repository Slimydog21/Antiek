import { describe, expect, it } from "vitest";

import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import {
  mergeSlottedSystemContext,
  slotInsight,
  slottedToContextItems,
  unslotInsight,
} from "./insightLegoSlot";

const a: PaletteDragPayload = {
  from: "palette",
  block_kind: "insight",
  block_id: "n-1",
  label: "First insight",
};
const b: PaletteDragPayload = {
  from: "palette",
  block_kind: "claim",
  block_id: "n-2",
  label: "Second claim",
};

describe("insightLegoSlot", () => {
  it("dedupes and caps slots", () => {
    expect(slotInsight([], a)).toEqual([a]);
    expect(slotInsight([a], a)).toEqual([a]);
    expect(slotInsight([a], b)).toEqual([a, b]);
    const many = Array.from({ length: 12 }, (_, i) => ({
      ...a,
      block_id: `n-${i}`,
      label: `L${i}`,
    }));
    expect(slotInsight(many, b)).toEqual(many);
  });

  it("unslots by id", () => {
    expect(unslotInsight([a, b], "n-1")).toEqual([b]);
  });

  it("maps to compose-context @insight items", () => {
    expect(slottedToContextItems([a, b])).toEqual([
      { kind: "insight", id: "n-1" },
      { kind: "insight", id: "n-2" },
    ]);
  });

  it("merges insight context ahead of base", () => {
    expect(mergeSlottedSystemContext("@insight A", "picker B")).toBe(
      "@insight A\n\npicker B",
    );
    expect(mergeSlottedSystemContext("", "only base")).toBe("only base");
    expect(mergeSlottedSystemContext("only insight", null)).toBe("only insight");
  });
});
