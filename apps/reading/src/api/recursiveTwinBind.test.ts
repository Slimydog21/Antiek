import { describe, expect, it } from "vitest";
import {
  evaluateRecursiveTwinBind,
  formatTwinBindSummary,
} from "./recursiveTwinBind";

describe("evaluateRecursiveTwinBind", () => {
  it("allows operator empty scaffold without inventing content", () => {
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "asset-1",
      source: "operator",
      llm_filled: false,
      gated: false,
    });
    expect(d.bind_allowed).toBe(true);
    expect(d.twin_created).toBe(false);
    expect(d.insights).toEqual([]);
    expect(d.questions).toEqual([]);
  });

  it("accepts operator-supplied lists", () => {
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "asset-1",
      source: "operator",
      llm_filled: false,
      gated: false,
      insights: ["claim X is load-bearing"],
      questions: ["what is the counterexample?"],
    });
    expect(d.bind_allowed).toBe(true);
    expect(d.insights).toEqual(["claim X is load-bearing"]);
    expect(d.questions).toHaveLength(1);
    expect(d.twin_created).toBe(false);
  });

  it("blocks gated assets", () => {
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "asset-1",
      source: "operator",
      llm_filled: false,
      gated: true,
      insights: ["should be dropped"],
    });
    expect(d.bind_allowed).toBe(false);
    expect(d.insights).toEqual([]);
    expect(d.twin_created).toBe(false);
  });

  it("requires explicit gated and llm_filled", () => {
    expect(() =>
      evaluateRecursiveTwinBind({
        parent_asset_id: "a",
        source: "operator",
        // @ts-expect-error intentional
        llm_filled: undefined,
        gated: false,
      }),
    ).toThrow(/llm_filled/);
    expect(() =>
      evaluateRecursiveTwinBind({
        parent_asset_id: "a",
        source: "operator",
        llm_filled: false,
        // @ts-expect-error intentional
        gated: undefined,
      }),
    ).toThrow(/gated/);
  });

  it("llm_note_taker requires llm_filled and non-empty lists", () => {
    expect(() =>
      evaluateRecursiveTwinBind({
        parent_asset_id: "a",
        source: "llm_note_taker",
        llm_filled: false,
        gated: false,
        insights: ["x"],
      }),
    ).toThrow(/llm_filled/);
    expect(() =>
      evaluateRecursiveTwinBind({
        parent_asset_id: "a",
        source: "llm_note_taker",
        llm_filled: true,
        gated: false,
      }),
    ).toThrow(/non-empty/);
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "a",
      source: "llm_note_taker",
      llm_filled: true,
      gated: false,
      questions: ["why?"],
    });
    expect(d.bind_allowed).toBe(true);
    expect(d.llm_filled).toBe(true);
  });

  it("unknown source denies bind", () => {
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "a",
      source: "unknown",
      llm_filled: false,
      gated: false,
    });
    expect(d.bind_allowed).toBe(false);
    expect(d.twin_created).toBe(false);
  });

  it("unknown + llm_filled=true is rejected (not silently rewritten)", () => {
    expect(() =>
      evaluateRecursiveTwinBind({
        parent_asset_id: "a",
        source: "unknown",
        llm_filled: true,
        gated: false,
        insights: ["should not mask"],
      }),
    ).toThrow(/llm_note_taker/);
  });

  it("rejects whitespace-only list entries as empty after trim", () => {
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "a",
      source: "operator",
      llm_filled: false,
      gated: false,
      insights: ["  ", "ok"],
    });
    expect(d.insights).toEqual(["ok"]);
  });
});

describe("formatTwinBindSummary", () => {
  it("summarizes honesty", () => {
    const d = evaluateRecursiveTwinBind({
      parent_asset_id: "a",
      source: "operator",
      llm_filled: false,
      gated: false,
    });
    expect(formatTwinBindSummary(d)).toMatch(/twin_created=false/);
  });
});
