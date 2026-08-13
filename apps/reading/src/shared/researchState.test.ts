/**
 * researchState.test.ts — exhaustive coverage of the single state registry.
 * Every backend status must map, every style must be total, and the
 * unseen axis must follow herdr's done = Idle ∧ ¬seen rule.
 */
import { describe, expect, it } from "vitest";

import {
  isUnseen,
  researchStateDotClass,
  researchStateFor,
  researchStateLabel,
  researchStateStyle,
  type ResearchState,
} from "./researchState";

const ALL_STATUSES = [
  "in_progress",
  "completed",
  "failed",
  "stopped",
  "not_found",
] as const;

describe("researchStateFor", () => {
  it("maps every backend status to exactly one state", () => {
    expect(researchStateFor("in_progress")).toBe("working");
    expect(researchStateFor("completed")).toBe("done");
    expect(researchStateFor("failed")).toBe("blocked");
    expect(researchStateFor("stopped")).toBe("stopped");
    expect(researchStateFor("not_found")).toBe("unavailable");
  });

  it("covers the whole status union (compile-time exhaustiveness)", () => {
    const seen: ResearchState[] = ALL_STATUSES.map((s) => researchStateFor(s));
    expect(new Set(seen).size).toBe(5);
  });
});

describe("researchStateStyle", () => {
  it("is total over the status union — every status yields a full style", () => {
    for (const status of ALL_STATUSES) {
      const style = researchStateStyle(status);
      expect(style.state).toBe(researchStateFor(status));
      expect(style.colour).toBeTruthy();
      expect(style.token).toMatch(/^state-/);
      expect(style.label).toBeTruthy();
    }
  });

  it("keeps the pre-registry visual contract (no regression)", () => {
    expect(researchStateStyle("in_progress")).toMatchObject({
      label: "working",
      colour: "sun",
      running: true,
    });
    expect(researchStateStyle("completed")).toMatchObject({
      label: "done",
      colour: "aurora",
      running: false,
    });
    expect(researchStateStyle("failed")).toMatchObject({
      label: "needs attention",
      colour: "danger",
      running: false,
    });
    expect(researchStateStyle("stopped")).toMatchObject({
      label: "stopped",
      colour: "muted",
      running: false,
    });
    expect(researchStateStyle("not_found")).toMatchObject({
      label: "unavailable",
      colour: "muted",
      running: false,
    });
  });

  it("only 'working' is running", () => {
    for (const status of ALL_STATUSES) {
      expect(researchStateStyle(status).running).toBe(status === "in_progress");
    }
  });
});

describe("researchStateLabel", () => {
  it("renders blocked as the plain-language 'needs attention'", () => {
    expect(researchStateLabel("blocked")).toBe("needs attention");
    expect(researchStateLabel("working")).toBe("working");
    expect(researchStateLabel("done")).toBe("done");
    expect(researchStateLabel("stopped")).toBe("stopped");
    expect(researchStateLabel("unavailable")).toBe("unavailable");
  });
});

describe("isUnseen", () => {
  const done = { status: "completed" as const, completed_at: "2026-08-13T10:00:00Z" };

  it("a completed research is unseen when never opened", () => {
    expect(isUnseen(done, null)).toBe(true);
  });

  it("a completed research is unseen when it finished after the last open", () => {
    expect(isUnseen(done, "2026-08-13T09:00:00Z")).toBe(true);
  });

  it("a completed research is seen when opened after it finished", () => {
    expect(isUnseen(done, "2026-08-13T11:00:00Z")).toBe(false);
  });

  it("only completed research carries the unseen axis", () => {
    expect(isUnseen({ status: "in_progress", completed_at: null }, null)).toBe(false);
    expect(isUnseen({ status: "failed", completed_at: "2026-08-13T10:00:00Z" }, null)).toBe(false);
    expect(isUnseen({ status: "stopped", completed_at: "2026-08-13T10:00:00Z" }, null)).toBe(false);
    expect(isUnseen({ status: "not_found", completed_at: null }, null)).toBe(false);
  });

  it("a completed research without a completion timestamp is never unread", () => {
    expect(isUnseen({ status: "completed", completed_at: null }, null)).toBe(false);
  });

  it("unparsable completion timestamps fail toward unread", () => {
    expect(isUnseen({ status: "completed", completed_at: "not-a-date" }, null)).toBe(true);
    expect(isUnseen({ status: "completed", completed_at: "not-a-date" }, "2026-08-13T11:00:00Z")).toBe(true);
  });

  it("a corrupt last-seen timestamp fails toward unread, not false-read", () => {
    expect(isUnseen({ status: "completed", completed_at: "2026-08-13T10:00:00Z" }, "garbage")).toBe(true);
  });
});

describe("researchStateDotClass", () => {
  it("every state resolves through the --state-* token family", () => {
    for (const state of ["working", "blocked", "done", "stopped", "unavailable"] as const) {
      expect(researchStateDotClass(state, false)).toMatch(/var\(--state-/);
    }
  });

  it("unseen-done renders a halo ring, seen-done does not", () => {
    expect(researchStateDotClass("done", true)).toContain("ring-2");
    expect(researchStateDotClass("done", false)).not.toContain("ring");
  });

  it("the unseen halo is full-opacity (3:1 non-text contrast)", () => {
    const cls = researchStateDotClass("done", true);
    expect(cls).toContain("ring-[var(--state-done)]");
    expect(cls).not.toContain("/50");
  });

  it("working keeps the ambient pulse, disabled under reduced motion", () => {
    const cls = researchStateDotClass("working", false);
    expect(cls).toContain("animate-pulse");
    expect(cls).toContain("motion-reduce:animate-none");
  });

  it("no dot uses a translucent fill (contrast floor)", () => {
    for (const state of ["working", "blocked", "done", "stopped", "unavailable"] as const) {
      expect(researchStateDotClass(state, false)).not.toContain("/50");
    }
  });
});
