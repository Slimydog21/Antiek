/** interviewMode.test.ts — SPR-07 M8 (patterns 18/20): the option card parser and the seed hand-off. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVIEW_FIRST_TURN, INTERVIEW_SYSTEM_PROMPT, dispatchProjectSeed, parseOptionCard, resetProjectSeedSeam, seedFromActions, subscribeProjectSeed, type ProjectSeed } from "./interviewMode";

// The seam is module state: every test starts with no consumer and no held
// seed, so a dispatch left unconsumed by one test cannot leak into the next.
beforeEach(() => { resetProjectSeedSeam(); });
afterEach(() => { vi.restoreAllMocks(); });

describe("interviewMode", () => {
  it("the hidden first turn and the prompt exist", () => {
    expect(INTERVIEW_FIRST_TURN).toBe("Begin the interview.");
    expect(INTERVIEW_SYSTEM_PROMPT).toMatch(/one question at a time/i);
  });

  it("parses a fenced @@options JSON block into a card and strips it from the prose", () => {
    const text = "Which era?\n\n@@options\n{\"question\":\"Which era?\",\"options\":[\"1830s\",\"1970s\"],\"allowCustom\":true}\n@@end";
    expect(parseOptionCard(text)).toEqual({ prose: "Which era?", card: { question: "Which era?", options: ["1830s", "1970s"], allowCustom: true } });
    expect(parseOptionCard("plain")).toEqual({ prose: "plain", card: null });
    expect(parseOptionCard("x\n\n@@options\n{not json}\n@@end").card).toBeNull();
    expect(parseOptionCard("x\n\n@@options\n{\"options\":\"nope\"}\n@@end").card).toBeNull();
  });

  it("seedFromActions picks the first project_seed", () => {
    expect(seedFromActions([{ kind: "toast", level: "info", message: "m" }])).toBeNull();
    const seed = seedFromActions([{ kind: "project_seed", title: "T", prompt: "P", sources: ["doc-1"] }]);
    expect(seed).toEqual({ title: "T", prompt: "P", sources: ["doc-1"] });
  });

  describe("the seed seam (repair C2): subscribeProjectSeed is the intake's ONE consumer path", () => {
    const seed: ProjectSeed = { title: "T", prompt: "P", sources: ["doc-1"] };

    it("a dispatched seed reaches a registered consumer exactly once, and the consumer is told it was delivered", () => {
      const seen: ProjectSeed[] = [];
      const off = subscribeProjectSeed((s) => { seen.push(s); });
      try {
        expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 });
        expect(seen).toEqual([seed]);
        expect(dispatchProjectSeed({ ...seed, title: "U" })).toEqual({ delivered: 1, failed: 0 });
        expect(seen.map((s) => s.title)).toEqual(["T", "U"]);
      } finally {
        off();
      }
      // Unsubscribed: nothing reaches it, and the dispatcher says so.
      expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0, failed: 0 });
      expect(seen).toHaveLength(2);
    });

    it("exactly once across intake remounts: a seed delivered to a mounted intake is NOT also held for the next one (second repair, finding 4)", () => {
      const first: ProjectSeed[] = [];
      const off = subscribeProjectSeed((s) => { first.push(s); });
      dispatchProjectSeed(seed);
      off();
      expect(first).toEqual([seed]);
      const remounted: ProjectSeed[] = [];
      subscribeProjectSeed((s) => { remounted.push(s); })();
      expect(remounted).toEqual([]);
    });

    it("a seed dispatched before the intake mounts is held and handed to the FIRST consumer once, never twice", () => {
      expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0, failed: 0 });
      const a: ProjectSeed[] = [];
      const b: ProjectSeed[] = [];
      const offA = subscribeProjectSeed((s) => { a.push(s); });
      const offB = subscribeProjectSeed((s) => { b.push(s); });
      try {
        expect(a).toEqual([seed]);
        expect(b).toEqual([]);
        expect(dispatchProjectSeed({ ...seed, title: "V" })).toEqual({ delivered: 2, failed: 0 });
        expect(a.map((s) => s.title)).toEqual(["T", "V"]);
        expect(b.map((s) => s.title)).toEqual(["V"]);
      } finally {
        offA(); offB();
      }
    });

    it("two confirms before any intake mounts are BOTH held, in confirmation order: the pane told the user each was held (second repair, finding 3)", () => {
      dispatchProjectSeed(seed);
      dispatchProjectSeed({ ...seed, title: "second" });
      const got: ProjectSeed[] = [];
      subscribeProjectSeed((s) => { got.push(s); })();
      expect(got.map((s) => s.title)).toEqual(["T", "second"]);
      const later: ProjectSeed[] = [];
      subscribeProjectSeed((s) => { later.push(s); })();
      expect(later).toEqual([]);
    });

    it("a throwing consumer neither stops delivery to the others nor escapes dispatch; it is counted as failed (second repair, finding 3)", () => {
      const error = vi.spyOn(console, "error").mockImplementation(() => {});
      const b: ProjectSeed[] = [];
      const offA = subscribeProjectSeed(() => { throw new Error("boom"); });
      const offB = subscribeProjectSeed((s) => { b.push(s); });
      try {
        expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 1 });
        expect(b).toEqual([seed]);
        expect(error).toHaveBeenCalledTimes(1);
      } finally {
        offA(); offB();
      }
      // Delivered to one: not held for the next intake.
      const later: ProjectSeed[] = [];
      subscribeProjectSeed((s) => { later.push(s); })();
      expect(later).toEqual([]);
    });

    it("a seed NO consumer took (the only intake threw) is held for the next one, not lost; a held seed a subscriber throws on stays held (second repair, finding 3)", () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const offBroken = subscribeProjectSeed(() => { throw new Error("boom"); });
      expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0, failed: 1 });
      offBroken();
      // The next intake to mount throws on the held seed too: still held.
      subscribeProjectSeed(() => { throw new Error("boom again"); })();
      const healthy: ProjectSeed[] = [];
      subscribeProjectSeed((s) => { healthy.push(s); })();
      expect(healthy).toEqual([seed]);
      const after: ProjectSeed[] = [];
      subscribeProjectSeed((s) => { after.push(s); })();
      expect(after).toEqual([]);
    });

    it("the seed is a value copy: a consumer mutating it never changes what the next consumer sees", () => {
      const offA = subscribeProjectSeed((s) => { s.title = "mutated"; });
      const b: ProjectSeed[] = [];
      const offB = subscribeProjectSeed((s) => { b.push(s); });
      try {
        dispatchProjectSeed(seed);
        expect(b[0].title).toBe("T");
        expect(seed.title).toBe("T");
      } finally {
        offA(); offB();
      }
    });
  });
});
