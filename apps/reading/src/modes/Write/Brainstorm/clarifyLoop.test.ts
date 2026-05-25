import { describe, it, expect } from "vitest";

import { canAskMore, initClarify, recordTurn, DEFAULT_TURN_CAP } from "./clarifyLoop";

/**
 * The turn cap (SPR-05 M3 mechanical gate): a long clarification is capped
 * and does not loop forever; the agent's own "done" signal also ends it.
 */

describe("clarify loop turn cap", () => {
  it("caps a runaway agent that never signals done", () => {
    let s = initClarify(3);
    for (let i = 0; i < 10; i++) {
      if (!canAskMore(s)) break;
      s = recordTurn(s, { shouldEnd: false }); // agent keeps wanting more
    }
    expect(s.done).toBe(true);
    expect(s.endReason).toBe("turn_cap"); // cap wins over the agent
    expect(s.turns).toBe(3); // never exceeded the cap
  });

  it("ends early when the agent signals completion", () => {
    let s = initClarify(5);
    s = recordTurn(s, { shouldEnd: false });
    s = recordTurn(s, { shouldEnd: true });
    expect(s.done).toBe(true);
    expect(s.endReason).toBe("agent_complete");
    expect(s.turns).toBe(2); // ended before the cap
  });

  it("canAskMore is false once done", () => {
    const s = recordTurn(initClarify(1), { shouldEnd: false });
    expect(s.done).toBe(true);
    expect(canAskMore(s)).toBe(false);
  });

  it("defaults to a sane cap and never allows < 1", () => {
    expect(initClarify().maxTurns).toBe(DEFAULT_TURN_CAP);
    expect(initClarify(0).maxTurns).toBe(1);
  });
});
