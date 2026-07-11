import { describe, expect, it } from "vitest";
import {
  composeRecursiveTwinSessionPack,
  formatRecursiveTwinSessionPackSummary,
} from "./recursiveTwinSessionPackCompose";

describe("composeRecursiveTwinSessionPack", () => {
  it("packs ready without store mutation", () => {
    const p = composeRecursiveTwinSessionPack({
      session_id: "sess-1",
      members: [
        {
          asset_id: "a1",
          twin_bound: true,
          insights: ["scaling holds under noise"],
          questions: ["what about multimodal?"],
        },
        {
          asset_id: "a2",
          twin_bound: false,
          insights: [],
          questions: [],
        },
      ],
    });
    expect(p.twin_store_mutated).toBe(false);
    expect(p.pack_ready).toBe(true);
    expect(p.insight_count).toBe(1);
    expect(p.question_count).toBe(1);
    expect(p.bound_count).toBe(1);
    expect(p.unbound_count).toBe(1);
    expect(p.authority).toBe("recursive_twin_session_pack_compose_advisory");
    expect(formatRecursiveTwinSessionPackSummary(p)).toMatch(
      /twin_store_mutated=false/,
    );
  });

  it("pack not ready without bound or content", () => {
    const unbound = composeRecursiveTwinSessionPack({
      session_id: "s",
      members: [
        {
          asset_id: "a1",
          twin_bound: false,
          insights: ["x"],
          questions: [],
        },
      ],
    });
    expect(unbound.pack_ready).toBe(false);
    expect(unbound.twin_store_mutated).toBe(false);

    const empty = composeRecursiveTwinSessionPack({
      session_id: "s",
      members: [
        {
          asset_id: "a1",
          twin_bound: true,
          insights: [],
          questions: [],
        },
      ],
    });
    expect(empty.pack_ready).toBe(false);
    expect(empty.notes.some((n) => n.includes("no invent"))).toBe(true);
  });

  it("rejects duplicates and blank content", () => {
    expect(() =>
      composeRecursiveTwinSessionPack({
        session_id: "s",
        members: [
          {
            asset_id: "a1",
            twin_bound: true,
            insights: [],
            questions: [],
          },
          {
            asset_id: "a1",
            twin_bound: true,
            insights: [],
            questions: [],
          },
        ],
      }),
    ).toThrow(/duplicate/);
    expect(() =>
      composeRecursiveTwinSessionPack({
        session_id: "s",
        members: [
          {
            asset_id: "a1",
            twin_bound: true,
            insights: ["  "],
            questions: [],
          },
        ],
      }),
    ).toThrow(/insights/);
  });
});
