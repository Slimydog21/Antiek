/** agentThread.test.ts — SPR-07 invariant 8: failed turns never enter the wire history; at most the last 8 done turns. */
import { beforeEach, describe, expect, it } from "vitest";

import { HISTORY_CAP, historyFor, useAgentThreads } from "./agentThreadStore";

const key = "agent:pane:p:proj-1";
const store = () => useAgentThreads.getState();

beforeEach(() => store().reset());

describe("agentThread", () => {
  it("startTurn → completeTurn records the answer; failTurn keeps the answer null", () => {
    const a = store().startTurn(key, "q1");
    store().completeTurn(key, a, { answer: "a1", shape: "SYNTHESIS", actions: [] });
    const b = store().startTurn(key, "q2");
    store().failTurn(key, b, "HTTP 500");
    const turns = store().threads[key];
    expect(turns.map((t) => [t.status, t.answer])).toEqual([["done", "a1"], ["failed", null]]);
    expect(turns[1].error).toBe("HTTP 500");
    expect(turns[0].statusWord).toBe("reading");
    expect(turns[1].statusWord).toBe("weighing");
  });

  it("history carries only done turns, capped at the last 8", () => {
    expect(HISTORY_CAP).toBe(8);
    for (let i = 0; i < 10; i++) {
      const id = store().startTurn(key, `q${i}`);
      if (i % 3 === 2) store().failTurn(key, id, "x");
      else store().completeTurn(key, id, { answer: `a${i}`, shape: "SYNTHESIS", actions: [] });
    }
    const history = historyFor(store().threads[key]);
    expect(history.every((h) => h.answer.startsWith("a"))).toBe(true);
    expect(history).toHaveLength(7); // 10 turns, 3 failed
    for (let i = 10; i < 14; i++) {
      const id = store().startTurn(key, `q${i}`);
      store().completeTurn(key, id, { answer: `a${i}`, shape: "SYNTHESIS", actions: [] });
    }
    const capped = historyFor(store().threads[key]);
    expect(capped).toHaveLength(8);
    expect(capped[0].question).toBe("q4");
    expect(capped.at(-1)!.question).toBe("q13");
  });

  it("hidden turns (the interview's first) stay out of the rendered list but in history once done", () => {
    const id = store().startTurn(key, "Begin the interview.", { hidden: true });
    store().completeTurn(key, id, { answer: "What is this project about?", shape: "EXTENSION", actions: [] });
    expect(store().threads[key][0].hidden).toBe(true);
    expect(historyFor(store().threads[key])).toEqual([{ question: "Begin the interview.", answer: "What is this project about?" }]);
  });

  it("streamTurn updates the partial answer without finishing the turn", () => {
    const id = store().startTurn(key, "q");
    store().streamTurn(key, id, "par");
    expect(store().threads[key][0]).toMatchObject({ status: "streaming", answer: "par" });
    expect(historyFor(store().threads[key])).toEqual([]);
  });

  it("a late reply healing the 8 s fallback: streamTurn on a failed turn clears endedAt and error, so the turn runs again (second repair, finding 5)", () => {
    const id = store().startTurn(key, "q");
    store().failTurn(key, id, null);
    expect(store().threads[key][0]).toMatchObject({ status: "failed", answer: null, error: null });
    expect(store().threads[key][0].endedAt).toEqual(expect.any(Number));
    store().streamTurn(key, id, "par");
    expect(store().threads[key][0]).toMatchObject({ status: "streaming", answer: "par", error: null });
    expect(store().threads[key][0].endedAt).toBeUndefined();
    store().completeTurn(key, id, { answer: "whole", shape: "SYNTHESIS", actions: [] });
    expect(store().threads[key][0].endedAt).toEqual(expect.any(Number));
    expect(historyFor(store().threads[key])).toEqual([{ question: "q", answer: "whole" }]);
  });
});
