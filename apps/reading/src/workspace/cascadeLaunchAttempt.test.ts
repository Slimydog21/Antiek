import { beforeEach, describe, expect, it } from "vitest";

import { acquireCascadeLaunchAttempt, clearCascadeLaunchAttempt } from "./cascadeLaunchAttempt";

describe("cascade launch attempt browser recovery", () => {
  beforeEach(() => sessionStorage.clear());

  it("survives remount for identical reviewed inputs", () => {
    const inputs = { planVersion: 3, gatherMode: "exa_reasoning", allowContractStub: false };
    const first = acquireCascadeLaunchAttempt("plan-1", inputs);
    const afterRemount = acquireCascadeLaunchAttempt("plan-1", inputs);
    expect(afterRemount).toBe(first);
  });

  it("rotates on reviewed-input drift and clears after acceptance", () => {
    const first = acquireCascadeLaunchAttempt("plan-1", { planVersion: 3 });
    const changed = acquireCascadeLaunchAttempt("plan-1", { planVersion: 4 });
    expect(changed).not.toBe(first);
    clearCascadeLaunchAttempt("plan-1");
    expect(acquireCascadeLaunchAttempt("plan-1", { planVersion: 4 })).not.toBe(changed);
  });

  it("rotates when the reviewed research driver tier changes", () => {
    const deep = acquireCascadeLaunchAttempt("plan-tier", { researchTier: "deep" });
    const wrestle = acquireCascadeLaunchAttempt("plan-tier", { researchTier: "wrestle" });
    expect(wrestle).not.toBe(deep);
  });
});
