import { describe, expect, it } from "vitest";

import { twinSubstrateReadiness } from "./twinSubstrateReadiness";

describe("twinSubstrateReadiness residual (arq)", () => {
  it("reports empty when no notes or counts", () => {
    const r = twinSubstrateReadiness({});
    expect(r.empty).toBe(true);
    expect(r.substrate_ready).toBe(false);
    expect(r.has_insights).toBe(false);
    expect(r.has_questions).toBe(false);
    expect(r.summary).toMatch(/empty twin substrate/i);
  });

  it("is substrate_ready only when both insights and questions present", () => {
    expect(
      twinSubstrateReadiness({
        insight_count: 2,
        question_count: 0,
      }).substrate_ready,
    ).toBe(false);
    expect(
      twinSubstrateReadiness({
        insight_count: 0,
        question_count: 3,
      }).substrate_ready,
    ).toBe(false);
    const ready = twinSubstrateReadiness({
      insight_count: 1,
      question_count: 2,
      note_count: 3,
    });
    expect(ready.substrate_ready).toBe(true);
    expect(ready.empty).toBe(false);
    expect(ready.summary).toMatch(/substrate ready/i);
    expect(ready.summary).toMatch(/insights=1/);
    expect(ready.summary).toMatch(/questions=2/);
  });

  it("counts kinds from notes without inventing", () => {
    const r = twinSubstrateReadiness({
      notes: [
        { kind: "insight" },
        { kind: "question" },
        { kind: "question" },
        { kind: "scratch" },
      ],
    });
    expect(r.insight_count).toBe(1);
    expect(r.question_count).toBe(2);
    expect(r.other_count).toBe(1);
    expect(r.note_count).toBe(4);
    expect(r.substrate_ready).toBe(true);
  });

  it("prefers larger explicit counts over derived (server aggregate honesty)", () => {
    const r = twinSubstrateReadiness({
      notes: [{ kind: "insight" }],
      insight_count: 5,
      question_count: 2,
      note_count: 10,
    });
    expect(r.insight_count).toBe(5);
    expect(r.question_count).toBe(2);
    expect(r.note_count).toBe(10);
    expect(r.substrate_ready).toBe(true);
  });

  it("summarizes missing legs honestly", () => {
    expect(
      twinSubstrateReadiness({ insight_count: 3 }).summary,
    ).toMatch(/missing questions/i);
    expect(
      twinSubstrateReadiness({ question_count: 2 }).summary,
    ).toMatch(/missing insights/i);
  });
});
