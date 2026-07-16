import { describe, expect, it } from "vitest";

import {
  deriveResearchBroadcasts,
  researchStateBaseline,
  type ResearchBroadcastSnapshot,
} from "./researchBroadcast";

const running: ResearchBroadcastSnapshot[] = [
  { investigationId: "a", subQuestion: "Alpha?", state: "running" },
  { investigationId: "b", subQuestion: "Beta?", state: "paused" },
];

describe("research broadcast terminal edges", () => {
  it("treats initial terminal rows and identical polls as baseline, not arrivals", () => {
    const initial: ResearchBroadcastSnapshot[] = [
      { investigationId: "a", subQuestion: "Alpha?", state: "done" },
    ];
    expect(
      deriveResearchBroadcasts(researchStateBaseline(initial), initial),
    ).toEqual([]);
    expect(
      deriveResearchBroadcasts(researchStateBaseline(running), running),
    ).toEqual([]);
  });

  it("emits simultaneous terminal edges once in authoritative snapshot order", () => {
    const current: ResearchBroadcastSnapshot[] = [
      { investigationId: "b", subQuestion: "Beta?", state: "failed" },
      { investigationId: "a", subQuestion: "Alpha?", state: "done" },
    ];
    expect(
      deriveResearchBroadcasts(researchStateBaseline(running), current),
    ).toEqual([
      { ...current[0], kind: "failed" },
      { ...current[1], kind: "arrived" },
    ]);
    expect(
      deriveResearchBroadcasts(researchStateBaseline(current), current),
    ).toEqual([]);
  });

  it.each([
    ["stopped", "stopped"],
    ["budget_halted", "budget_halted"],
  ] as const)("maps %s to honest presentation copy", (state, kind) => {
    const current: ResearchBroadcastSnapshot[] = [
      { investigationId: "a", subQuestion: "Alpha?", state },
    ];
    expect(
      deriveResearchBroadcasts(researchStateBaseline(running), current),
    ).toEqual([{ ...current[0], kind }]);
  });

  it("allows a genuinely observed later nonterminal-to-terminal edge", () => {
    const restarted: ResearchBroadcastSnapshot[] = [
      {
        investigationId: "a",
        subQuestion: "Alpha redirected?",
        state: "running",
      },
    ];
    const redone: ResearchBroadcastSnapshot[] = [
      { investigationId: "a", subQuestion: "Alpha redirected?", state: "done" },
    ];
    expect(
      deriveResearchBroadcasts(researchStateBaseline(restarted), redone),
    ).toEqual([{ ...redone[0], kind: "arrived" }]);
  });
});
