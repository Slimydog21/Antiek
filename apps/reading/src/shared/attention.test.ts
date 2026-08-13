/**
 * attention.test.ts — exhaustive coverage of the rollup ladder.
 * The priority order is the product contract: blocked > unseen-done >
 * working > done/stopped > unavailable; empty rolls up to null.
 */
import { describe, expect, it } from "vitest";

import {
  aggregateAttention,
  attentionScore,
  hasUnseen,
  isSummoning,
  type AttentionInput,
} from "./attention";

describe("attentionScore", () => {
  it("ladders blocked above everything", () => {
    expect(attentionScore({ state: "blocked" })).toBe(4);
    expect(attentionScore({ state: "done", unseen: true })).toBe(3);
    expect(attentionScore({ state: "working" })).toBe(2);
    expect(attentionScore({ state: "done" })).toBe(1);
    expect(attentionScore({ state: "stopped" })).toBe(1);
    expect(attentionScore({ state: "unavailable" })).toBe(0);
  });

  it("unseen boosts done above working (unread completion is a to-do)", () => {
    expect(attentionScore({ state: "done", unseen: true })).toBeGreaterThan(
      attentionScore({ state: "working" }),
    );
  });

  it("seen done does not outrank working", () => {
    expect(attentionScore({ state: "done" })).toBeLessThan(
      attentionScore({ state: "working" }),
    );
  });
});

describe("aggregateAttention", () => {
  it("empty input rolls up to null — no phantom attention", () => {
    expect(aggregateAttention([])).toBeNull();
  });

  it("one blocked child reddens the whole group", () => {
    const items: AttentionInput[] = [
      { state: "working" },
      { state: "done", unseen: true },
      { state: "blocked" },
    ];
    expect(aggregateAttention(items)).toBe("blocked");
  });

  it("unseen-done outranks a running sibling", () => {
    const items: AttentionInput[] = [
      { state: "working" },
      { state: "done", unseen: true },
    ];
    expect(aggregateAttention(items)).toBe("done");
  });

  it("working outranks seen completions", () => {
    expect(aggregateAttention([{ state: "done" }, { state: "working" }])).toBe(
      "working",
    );
  });

  it("the highest-priority state wins ties deterministically (first wins)", () => {
    expect(aggregateAttention([{ state: "done" }, { state: "stopped" }])).toBe(
      "done",
    );
  });

  it("a lone done rolls up to done", () => {
    expect(aggregateAttention([{ state: "done" }])).toBe("done");
  });
});

describe("isSummoning", () => {
  it("only blocked summons the operator", () => {
    expect(isSummoning("blocked")).toBe(true);
    expect(isSummoning("working")).toBe(false);
    expect(isSummoning("done")).toBe(false);
    expect(isSummoning(null)).toBe(false);
  });
});

describe("hasUnseen", () => {
  it("detects at least one unseen completion", () => {
    expect(hasUnseen([{ state: "done", unseen: true }])).toBe(true);
    expect(hasUnseen([{ state: "done" }, { state: "working" }])).toBe(false);
    expect(hasUnseen([])).toBe(false);
  });
});
