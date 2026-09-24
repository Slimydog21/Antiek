import { describe, expect, it } from "vitest";

import {
  STORIES,
  parseArgs,
  raceTimeout,
  planAudit,
  readIndex,
  renderReport,
  verdict,
  type AuditResult,
} from "./a11y_audit";

const INDEX = {
  v: 5,
  entries: {
    "lemon-card--default": { id: "lemon-card--default", type: "story", tags: ["story"] },
    "navigation-topbar--research": {
      id: "navigation-topbar--research",
      type: "story",
      tags: ["story", "a11y-audit"],
    },
    "lemon-card--docs": { id: "lemon-card--docs", type: "docs", tags: ["a11y-audit"] },
  },
};

const clean = (story: string, theme: "light" | "dark"): AuditResult => ({
  story,
  theme,
  violations: [],
  error: null,
});

describe("parseArgs", () => {
  it("audits both themes by default", () => {
    expect(parseArgs([]).themes).toEqual(["light", "dark"]);
  });

  it("narrows to the themes asked for and rejects unknown ones", () => {
    expect(parseArgs(["--themes", "dark"]).themes).toEqual(["dark"]);
    expect(() => parseArgs(["--themes", "sepia"])).toThrow(/unknown theme/);
  });
});

describe("readIndex", () => {
  it("reads story ids and the a11y-audit tag, ignoring docs entries", () => {
    const { ids, tagged } = readIndex(INDEX);
    expect([...ids].sort()).toEqual(["lemon-card--default", "navigation-topbar--research"]);
    expect(tagged).toEqual(["navigation-topbar--research"]);
  });
});

describe("planAudit", () => {
  it("plans every present story once per theme", () => {
    const { ids } = readIndex(INDEX);
    const { jobs, missing } = planAudit(
      ["lemon-card--default", "navigation-topbar--research", "lemon-card--default"],
      ids,
      ["light", "dark"],
    );
    expect(missing).toEqual([]);
    expect(jobs).toEqual([
      { story: "lemon-card--default", theme: "light" },
      { story: "lemon-card--default", theme: "dark" },
      { story: "navigation-topbar--research", theme: "light" },
      { story: "navigation-topbar--research", theme: "dark" },
    ]);
  });

  it("reports an id the build does not contain instead of auditing a blank page", () => {
    const { ids } = readIndex(INDEX);
    const { jobs, missing } = planAudit(["design-moodboard--palette-day-off-whites-glacials"], ids, [
      "light",
    ]);
    expect(jobs).toEqual([]);
    expect(missing).toEqual(["design-moodboard--palette-day-off-whites-glacials"]);
  });
});

describe("verdict", () => {
  it("passes only when every planned audit ran clean in every theme", () => {
    expect(verdict([clean("a--b", "light"), clean("a--b", "dark")], []).pass).toBe(true);
  });

  it("fails on a serious violation that exists only at night", () => {
    const night: AuditResult = {
      ...clean("a--b", "dark"),
      violations: [{ id: "color-contrast", impact: "serious", help: "", helpUrl: "", nodes: 3 }],
    };
    const v = verdict([clean("a--b", "light"), night], []);
    expect(v.pass).toBe(false);
    expect(v.blocking).toEqual([{ story: "a--b", theme: "dark", v: night.violations[0] }]);
  });

  it("does not fail on minor or moderate violations", () => {
    const r: AuditResult = {
      ...clean("a--b", "dark"),
      violations: [{ id: "x", impact: "moderate", help: "", helpUrl: "", nodes: 1 }],
    };
    expect(verdict([r], []).pass).toBe(true);
  });

  it("fails when a story was not audited or is missing from the build", () => {
    const broken: AuditResult = { ...clean("a--b", "dark"), error: "theme did not apply" };
    expect(verdict([broken], []).pass).toBe(false);
    expect(verdict([clean("a--b", "light")], ["gone--story"]).pass).toBe(false);
  });
});

describe("renderReport", () => {
  it("shows each theme as its own column and totals row", () => {
    const night: AuditResult = {
      ...clean("a--b", "dark"),
      violations: [{ id: "color-contrast", impact: "serious", help: "", helpUrl: "u", nodes: 4 }],
    };
    const md = renderReport([clean("a--b", "light"), night], [], ["light", "dark"], "T");
    expect(md).toContain("| Story | light | dark |");
    expect(md).toContain("| `a--b` | 0 | 1 (serious · color-contrast) |");
    expect(md).toContain("| dark | 1 | 1 | 1 | 4 | 4 | 0 |");
    expect(md).toContain("| `a--b` | dark | `color-contrast` | serious | 4 | [docs](u) |");
  });
});

describe("raceTimeout", () => {
  it("names a hung audit instead of waiting for it forever", async () => {
    await expect(raceTimeout(new Promise(() => {}), 10)).rejects.toThrow(/timed out after 0.01s/);
  });

  it("returns the audit when it settles in time", async () => {
    await expect(raceTimeout(Promise.resolve(3), 1000)).resolves.toBe(3);
  });
});

describe("STORIES", () => {
  it("lists each curated story once", () => {
    expect(new Set(STORIES).size).toBe(STORIES.length);
  });
});
