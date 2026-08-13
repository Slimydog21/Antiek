/**
 * attention.test.ts — exhaustive coverage of the rollup ladder.
 * The priority order is the product contract: blocked > unseen-done >
 * working > done/stopped > unavailable; empty rolls up to null.
 */
import { describe, expect, it } from "vitest";

import {
  aggregateAttention,
  attentionScore,
  countSummoningGroups,
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
  it("blocked and unseen-done summon; working/seen-done do not", () => {
    expect(isSummoning({ state: "blocked" })).toBe(true);
    expect(isSummoning({ state: "done", unseen: true })).toBe(true);
    expect(isSummoning({ state: "working" })).toBe(false);
    expect(isSummoning({ state: "done" })).toBe(false);
    expect(isSummoning({ state: "stopped" })).toBe(false);
  });
});

describe("countSummoningGroups", () => {
  const fam = (id: string, parentId: string | null, state: "blocked" | "working" | "done", unseen = false) =>
    ({ id, parentId, state, unseen });

  it("two summoning members of one cascade count as ONE family", () => {
    const items = [
      fam("root", null, "working"),
      fam("child1", "root", "blocked"),
      fam("child2", "root", "blocked"),
    ];
    expect(countSummoningGroups(items)).toBe(1);
  });

  it("two summoning members of different families count as two", () => {
    const items = [
      fam("a", null, "blocked"),
      fam("b", null, "blocked"),
    ];
    expect(countSummoningGroups(items)).toBe(2);
  });

  it("an unseen-done leaf summons its family once", () => {
    const items = [
      fam("root", null, "working"),
      fam("leaf", "root", "done", true),
    ];
    expect(countSummoningGroups(items)).toBe(1);
  });

  it("non-summoning items never count", () => {
    expect(countSummoningGroups([fam("a", null, "working"), fam("b", null, "done")])).toBe(0);
    expect(countSummoningGroups([])).toBe(0);
  });

  it("a summoning orphan with unknown parent counts as its own family", () => {
    expect(countSummoningGroups([fam("x", "ghost", "blocked")])).toBe(1);
  });

  it("deep chains resolve to the topmost known root", () => {
    const items = [
      fam("top", null, "working"),
      fam("mid", "top", "working"),
      fam("leaf", "mid", "blocked"),
    ];
    expect(countSummoningGroups(items)).toBe(1);
  });
});

describe("hasUnseen", () => {
  it("detects at least one unseen completion", () => {
    expect(hasUnseen([{ state: "done", unseen: true }])).toBe(true);
    expect(hasUnseen([{ state: "done" }, { state: "working" }])).toBe(false);
    expect(hasUnseen([])).toBe(false);
  });
});
