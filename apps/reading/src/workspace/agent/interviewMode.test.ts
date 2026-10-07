/** interviewMode.test.ts — SPR-07 M8 (patterns 18/20): the option card parser and the seed hand-off. */
import { describe, expect, it, vi } from "vitest";

import { INTERVIEW_FIRST_TURN, INTERVIEW_SYSTEM_PROMPT, PROJECT_INTAKE_SEED_EVENT, dispatchProjectSeed, parseOptionCard, seedFromActions } from "./interviewMode";

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

  it("seedFromActions picks the first project_seed; dispatchProjectSeed emits exactly one window event", () => {
    expect(seedFromActions([{ kind: "toast", level: "info", message: "m" }])).toBeNull();
    const seed = seedFromActions([{ kind: "project_seed", title: "T", prompt: "P", sources: ["doc-1"] }]);
    expect(seed).toEqual({ title: "T", prompt: "P", sources: ["doc-1"] });
    const seen: unknown[] = [];
    const onSeed = (e: Event) => seen.push((e as CustomEvent).detail);
    window.addEventListener(PROJECT_INTAKE_SEED_EVENT, onSeed);
    dispatchProjectSeed(seed!);
    window.removeEventListener(PROJECT_INTAKE_SEED_EVENT, onSeed);
    expect(PROJECT_INTAKE_SEED_EVENT).toBe("antiek:project-intake:seed");
    expect(seen).toEqual([{ title: "T", prompt: "P", sources: ["doc-1"] }]);
    vi.restoreAllMocks();
  });
});
