import { describe, expect, it } from "vitest";

import {
  DEFAULT_OFFER_AFTER_MS,
  decideWaitHostMode,
  mustTeardownGame,
} from "./waitHostLogic";

describe("decideWaitHostMode", () => {
  const base = {
    waiting: true,
    ready: false,
    arcadeEnabled: true,
    reducedOrCalm: false,
    optedIn: false,
    waitedMs: 0,
    offerAfterMs: DEFAULT_OFFER_AFTER_MS,
  };

  it("hides when ready (readiness always wins)", () => {
    expect(decideWaitHostMode({ ...base, ready: true, optedIn: true })).toBe(
      "hidden",
    );
  });

  it("hides when not waiting", () => {
    expect(decideWaitHostMode({ ...base, waiting: false })).toBe("hidden");
  });

  it("plain loader when arcade flag off", () => {
    expect(
      decideWaitHostMode({ ...base, arcadeEnabled: false, waitedMs: 99999 }),
    ).toBe("plain-loader");
  });

  it("plain loader under reduced motion / calm", () => {
    expect(
      decideWaitHostMode({
        ...base,
        reducedOrCalm: true,
        waitedMs: 99999,
        optedIn: true,
      }),
    ).toBe("plain-loader");
  });

  it("offers after threshold without opt-in", () => {
    expect(
      decideWaitHostMode({
        ...base,
        waitedMs: DEFAULT_OFFER_AFTER_MS,
      }),
    ).toBe("offer");
  });

  it("plays only when opted in", () => {
    expect(decideWaitHostMode({ ...base, optedIn: true })).toBe("playing");
  });

  it("mustTeardownGame on ready transition", () => {
    expect(mustTeardownGame("playing", "hidden")).toBe(true);
    expect(mustTeardownGame("playing", "playing")).toBe(false);
    expect(mustTeardownGame("offer", "hidden")).toBe(false);
  });
});
