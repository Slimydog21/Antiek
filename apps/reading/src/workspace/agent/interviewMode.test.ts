/** interviewMode.test.ts — SPR-07 M8 (patterns 18/20): the option card parser and the seed hand-off. */
import { describe, expect, it, vi } from "vitest";

import { INTERVIEW_FIRST_TURN, INTERVIEW_SYSTEM_PROMPT, dispatchProjectSeed, parseOptionCard, seedFromActions, subscribeProjectSeed, type ProjectSeed } from "./interviewMode";

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
    vi.restoreAllMocks();
  });

  describe("the seed seam (repair C2): subscribeProjectSeed is the intake's ONE consumer path", () => {
    const seed: ProjectSeed = { title: "T", prompt: "P", sources: ["doc-1"] };

    it("a dispatched seed reaches a registered consumer exactly once, and the consumer is told it was delivered", () => {
      const seen: ProjectSeed[] = [];
      const off = subscribeProjectSeed((s) => { seen.push(s); });
      try {
        expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1 });
        expect(seen).toEqual([seed]);
        expect(dispatchProjectSeed({ ...seed, title: "U" })).toEqual({ delivered: 1 });
        expect(seen.map((s) => s.title)).toEqual(["T", "U"]);
      } finally {
        off();
      }
      // Unsubscribed: nothing reaches it, and the dispatcher says so.
      expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0 });
      expect(seen).toHaveLength(2);
    });

    it("a seed dispatched before the intake mounts is held and handed to the FIRST consumer once, never twice", () => {
      expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0 });
      const a: ProjectSeed[] = [];
      const b: ProjectSeed[] = [];
      const offA = subscribeProjectSeed((s) => { a.push(s); });
      const offB = subscribeProjectSeed((s) => { b.push(s); });
      try {
        expect(a).toEqual([seed]);
        expect(b).toEqual([]);
        expect(dispatchProjectSeed({ ...seed, title: "V" })).toEqual({ delivered: 2 });
        expect(a.map((s) => s.title)).toEqual(["T", "V"]);
        expect(b.map((s) => s.title)).toEqual(["V"]);
      } finally {
        offA(); offB();
      }
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
