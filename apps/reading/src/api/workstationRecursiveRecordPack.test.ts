import { describe, expect, it } from "vitest";
import {
  composeWorkstationRecursiveRecordPack,
  formatWorkstationRecursiveRecordPackSummary,
} from "./workstationRecursiveRecordPack";

describe("composeWorkstationRecursiveRecordPack", () => {
  it("packs without persist or inject", () => {
    const p = composeWorkstationRecursiveRecordPack({
      session_id: "sess-1",
      items: [
        {
          record_id: "r1",
          kind: "insight",
          text: "scaling holds under noise",
          weight: 0.9,
        },
        {
          record_id: "r2",
          kind: "question",
          text: "what about multimodal?",
          asset_id: "a1",
          weight: 0.5,
        },
      ],
    });
    expect(p.record_persisted).toBe(false);
    expect(p.prompts_injected).toBe(false);
    expect(p.pack_ready).toBe(true);
    expect(p.item_count).toBe(2);
    expect(p.by_kind.insight).toBe(1);
    expect(p.by_kind.question).toBe(1);
    expect(p.prompt_context_lines[0]).toMatch(/scaling holds/);
    expect(p.authority).toBe("workstation_recursive_record_pack_advisory");
    expect(formatWorkstationRecursiveRecordPackSummary(p)).toMatch(
      /record_persisted=false/,
    );
  });

  it("empty pack not ready, no invent", () => {
    const p = composeWorkstationRecursiveRecordPack({
      session_id: "s",
      items: [],
    });
    expect(p.pack_ready).toBe(false);
    expect(p.prompt_context_lines).toEqual([]);
    expect(p.record_persisted).toBe(false);
    expect(p.prompts_injected).toBe(false);
    expect(p.notes.some((n) => n.includes("no invent"))).toBe(true);
  });

  it("respects max_context_lines and rejects duplicates", () => {
    const p = composeWorkstationRecursiveRecordPack({
      session_id: "s",
      max_context_lines: 1,
      items: [
        { record_id: "a", kind: "insight", text: "first", weight: 0.2 },
        { record_id: "b", kind: "finding", text: "second", weight: 0.9 },
      ],
    });
    expect(p.prompt_context_lines).toHaveLength(1);
    expect(p.prompt_context_lines[0]).toMatch(/second/);
    expect(p.record_persisted).toBe(false);

    expect(() =>
      composeWorkstationRecursiveRecordPack({
        session_id: "s",
        items: [
          { record_id: "x", kind: "insight", text: "a" },
          { record_id: "x", kind: "question", text: "b" },
        ],
      }),
    ).toThrow(/duplicate/);
  });

  it("rejects invalid kind and blank text", () => {
    expect(() =>
      composeWorkstationRecursiveRecordPack({
        session_id: "s",
        items: [
          {
            record_id: "r",
            kind: "bogus" as "insight",
            text: "x",
          },
        ],
      }),
    ).toThrow(/kind/);
    expect(() =>
      composeWorkstationRecursiveRecordPack({
        session_id: "s",
        items: [{ record_id: "r", kind: "insight", text: "  " }],
      }),
    ).toThrow(/text/);
  });
});
