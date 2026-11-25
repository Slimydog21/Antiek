/**
 * debounce.test.ts — SPR-10 M2: herdr's status debounce as a pure reducer
 * with explicit `at` timestamps (refs/omarchy-herdr.md R19): working→idle
 * needs 3 confirmations 100 ms apart, capped at 700 ms; 3 s startup grace.
 */
import { describe, expect, it } from "vitest";

import { DEBOUNCE, debounceStep, inStartupGrace, type DebounceState } from "./debounce";

const t0 = 10_000;

describe("DEBOUNCE constants are herdr's", () => {
  it("3 × 100 ms, 700 ms cap, 3 s grace, 2 s poll, 30 s idle poll", () => {
    expect(DEBOUNCE).toEqual({ confirmations: 3, intervalMs: 100, capMs: 700, startupGraceMs: 3000, pollMs: 2000, idlePollMs: 30000 });
    expect(Object.isFrozen(DEBOUNCE)).toBe(true);
  });
});

describe("debounceStep", () => {
  it("first observation commits at once, whatever the phase", () => {
    for (const phase of ["working", "finished", "unknown"] as const) {
      const r = debounceStep(undefined, { phase, at: t0, source: "poll" });
      expect(r.commit).toBe(phase);
      expect(r.confirmAt).toBeNull();
      expect(r.next).toEqual({ kind: "settled", phase });
    }
  });

  it("working→finished: not committed at t0+299, committed at t0+300 after three agreeing confirms", () => {
    let s: DebounceState = { kind: "settled", phase: "working" };
    let r = debounceStep(s, { phase: "finished", at: t0, source: "poll" });
    expect(r.commit).toBeNull();
    expect(r.confirmAt).toBe(t0 + 100);
    s = r.next;
    r = debounceStep(s, { phase: "finished", at: t0 + 100, source: "confirm" });
    expect(r.commit).toBeNull();
    expect(r.confirmAt).toBe(t0 + 200);
    s = r.next;
    r = debounceStep(s, { phase: "finished", at: t0 + 200, source: "confirm" });
    expect(r.commit).toBeNull();
    expect(r.confirmAt).toBe(t0 + 300);
    s = r.next;
    // An early third confirm (t0+299) does not commit.
    const early = debounceStep(s, { phase: "finished", at: t0 + 299, source: "confirm" });
    expect(early.commit).toBeNull();
    expect(early.confirmAt).toBe(t0 + 300);
    r = debounceStep(s, { phase: "finished", at: t0 + 300, source: "confirm" });
    expect(r.commit).toBe("finished");
    expect(r.confirmAt).toBeNull();
    expect(r.next).toEqual({ kind: "settled", phase: "finished" });
  });

  it("a disagreeing confirm (working again) at +200 returns to settled working, no commit", () => {
    let s: DebounceState = { kind: "settled", phase: "working" };
    s = debounceStep(s, { phase: "finished", at: t0, source: "poll" }).next;
    s = debounceStep(s, { phase: "finished", at: t0 + 100, source: "confirm" }).next;
    const r = debounceStep(s, { phase: "working", at: t0 + 200, source: "confirm" });
    expect(r.commit).toBeNull();
    expect(r.confirmAt).toBeNull();
    expect(r.next).toEqual({ kind: "settled", phase: "working" });
  });

  it("samples that keep disagreeing commit the latest at exactly t0+700 and never later", () => {
    let s: DebounceState = { kind: "settled", phase: "working" };
    s = debounceStep(s, { phase: "finished", at: t0, source: "poll" }).next;
    const phases = ["unknown", "finished", "unknown", "finished", "unknown", "finished"] as const;
    for (let i = 0; i < phases.length; i++) {
      const r = debounceStep(s, { phase: phases[i], at: t0 + 100 * (i + 1), source: "confirm" });
      expect(r.commit, `at +${100 * (i + 1)}`).toBeNull();
      expect(r.confirmAt).not.toBeNull();
      expect(r.confirmAt!).toBeLessThanOrEqual(t0 + 700);
      s = r.next;
    }
    // At +699 still nothing; at +700 the latest sample commits regardless.
    expect(debounceStep(s, { phase: "unknown", at: t0 + 699, source: "confirm" }).commit).toBeNull();
    const r = debounceStep(s, { phase: "unknown", at: t0 + 700, source: "confirm" });
    expect(r.commit).toBe("unknown");
    expect(r.next).toEqual({ kind: "settled", phase: "unknown" });
    // Never later: a sample past the cap also commits at once.
    const late = debounceStep(debounceStep({ kind: "settled", phase: "working" }, { phase: "finished", at: t0, source: "poll" }).next, { phase: "finished", at: t0 + 900, source: "poll" });
    expect(late.commit).toBe("finished");
  });

  it("→working and first observations commit at t=0; finished↔unknown (no working side) commit at once", () => {
    expect(debounceStep({ kind: "settled", phase: "finished" }, { phase: "working", at: t0, source: "poll" }).commit).toBe("working");
    expect(debounceStep({ kind: "settled", phase: "unknown" }, { phase: "working", at: t0, source: "poll" }).commit).toBe("working");
    expect(debounceStep({ kind: "settled", phase: "finished" }, { phase: "unknown", at: t0, source: "poll" }).commit).toBe("unknown");
    expect(debounceStep({ kind: "settled", phase: "unknown" }, { phase: "finished", at: t0, source: "poll" }).commit).toBe("finished");
    const same = debounceStep({ kind: "settled", phase: "working" }, { phase: "working", at: t0, source: "poll" });
    expect(same.commit).toBeNull();
    expect(same.next).toEqual({ kind: "settled", phase: "working" });
  });

  it("inStartupGrace is true at 2999 and false at 3000", () => {
    expect(inStartupGrace(t0, t0 + 2999)).toBe(true);
    expect(inStartupGrace(t0, t0 + 3000)).toBe(false);
  });
});
