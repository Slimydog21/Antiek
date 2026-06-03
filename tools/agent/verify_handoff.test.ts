import { describe, expect, it } from "vitest";

import {
  REQUIRED_HEADINGS,
  isPytestTailSoleVerify,
  parseGateResultsTable,
  parseHandoffSections,
  sectionHasContent,
  splitTableRow,
  verifyHandoff,
} from "./verify_handoff";

const GOOD_HANDOFF = `## Sprint SPR-03 — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-02 |
| Repo root (\`pwd\`) | \`/Users/slimydog/Desktop/Antiek\` |
| Branch | \`caffen/ant-exec-spr03\` |
| Commit SHA | \`abc1234\` |

### Not proved
- Live LLM on all decompose paths (operator card not run)

### Status
\`done\` — handoff linter shipped

### Files touched
- \`tools/agent/verify_handoff.ts\` — schema linter

### Milestones (checkboxes)
- [x] M1: verify_handoff.ts

### Gate results

| gate | command | exit | log path |
|------|---------|------|----------|
| handoff lint | \`cd apps/reading && npm run test:handoff\` | 0 | (stdout) |

### Steelman rejected alternative
**Fast path:** skip vitest, narrate green
**Why it loses:** R-03 theater

### Open questions
- none
`;

const PYTEST_TAIL_HANDOFF = `## Sprint SPR-03 — Handoff

### Env Card
| Field | Value |
|-------|-------|
| Branch | \`caffen/ant-exec-spr03\` |

### Not proved
- none

### Status
\`done\`

### Files touched
- tools/agent/verify_handoff.ts

### Milestones (checkboxes)
- [x] M1

### Gate results
| gate | command | exit | log path |
|------|---------|------|----------|
| verify | \`.venv/bin/python -m pytest -q | tail\` | 0 | (stdout) |

### Steelman rejected alternative
N/A — test fixture

### Open questions
- none
`;

describe("REQUIRED_HEADINGS", () => {
  it("lists the eight TEMPLATES.md handoff headings", () => {
    expect(REQUIRED_HEADINGS).toHaveLength(8);
    expect(REQUIRED_HEADINGS[0]).toBe("### Env Card");
    expect(REQUIRED_HEADINGS[1]).toBe("### Not proved");
  });
});

describe("sectionHasContent", () => {
  it("accepts N/A — reason waivers", () => {
    expect(sectionHasContent("N/A — docs-only sprint")).toBe(true);
  });
  it("rejects blank bodies", () => {
    expect(sectionHasContent("   \n  ")).toBe(false);
  });
});

describe("splitTableRow", () => {
  it("does not split on pipes inside backticks", () => {
    const cells = splitTableRow(
      "| verify | `.venv/bin/python -m pytest -q | tail` | 0 | (stdout) |",
    );
    expect(cells[1]).toContain("pytest -q | tail");
  });
});

describe("parseGateResultsTable", () => {
  it("extracts gate rows from a markdown table", () => {
    const rows = parseGateResultsTable(`
| gate | command | exit | log path |
|------|---------|------|----------|
| lint | \`npm test\` | 0 | out.log |
`);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.gate).toBe("lint");
    expect(rows[0]?.command).toContain("npm test");
  });
});

describe("isPytestTailSoleVerify", () => {
  it("flags when every command is pytest piped to tail", () => {
    expect(
      isPytestTailSoleVerify([
        { gate: "x", command: ".venv/bin/python -m pytest -q | tail", exit: "0", logPath: "" },
      ]),
    ).toBe(true);
  });
  it("does not flag mixed real verify commands", () => {
    expect(
      isPytestTailSoleVerify([
        { gate: "a", command: "pytest -q | tail", exit: "0", logPath: "" },
        { gate: "b", command: "npm run test:handoff", exit: "0", logPath: "" },
      ]),
    ).toBe(false);
  });
});

describe("verifyHandoff", () => {
  it("PASSes a complete handoff fixture", () => {
    const r = verifyHandoff(GOOD_HANDOFF);
    expect(r.ok).toBe(true);
    expect(r.issues).toHaveLength(0);
  });

  it("FAILs when ### Env Card is missing (R-01)", () => {
    const bad = GOOD_HANDOFF.replace("### Env Card\n\n| Field", "### Status\n\n| Field");
    const r = verifyHandoff(bad);
    expect(r.ok).toBe(false);
    expect(r.issues.some((i) => i.code === "missing_heading" && i.heading === "### Env Card")).toBe(
      true,
    );
  });

  it("FAILs when ### Not proved is missing", () => {
    const bad = GOOD_HANDOFF.replace(/### Not proved[\s\S]*?### Status/, "### Status");
    const r = verifyHandoff(bad);
    expect(r.ok).toBe(false);
    expect(r.issues.some((i) => i.heading === "### Not proved")).toBe(true);
  });

  it("FAILs on empty ### Gate results table (R-04)", () => {
    const bad = GOOD_HANDOFF.replace(
      /\| handoff lint[\s\S]*?\| \(stdout\) \|/,
      "",
    ).replace(
      "| gate | command | exit | log path |\n|------|---------|------|----------|",
      "| gate | command | exit | log path |\n|------|---------|------|----------|",
    );
    const r = verifyHandoff(bad);
    expect(r.ok).toBe(false);
    expect(r.issues.some((i) => i.code === "empty_gate_table")).toBe(true);
  });

  it("FAILs when pytest|tail is the sole gate command (R-03)", () => {
    const r = verifyHandoff(PYTEST_TAIL_HANDOFF);
    expect(r.ok).toBe(false);
    expect(r.issues.some((i) => i.code === "pytest_tail_theater")).toBe(true);
  });

  it("FAILs when ### Not proved appears after ### Status (R-06)", () => {
    const bad = GOOD_HANDOFF.replace(
      /### Not proved[\s\S]*?### Status[\s\S]*?`done`/,
      "### Status\n`done`\n\n### Not proved\n- deferred",
    );
    const r = verifyHandoff(bad);
    expect(r.ok).toBe(false);
    expect(r.issues.some((i) => i.code === "not_proved_after_status")).toBe(true);
  });

  it("FAILs on empty ### Env Card section", () => {
    const bad = GOOD_HANDOFF.replace(
      /### Env Card[\s\S]*?### Not proved/,
      "### Env Card\n\n### Not proved",
    );
    const r = verifyHandoff(bad);
    expect(r.ok).toBe(false);
    expect(r.issues.some((i) => i.code === "empty_section" && i.heading === "### Env Card")).toBe(
      true,
    );
  });
});

describe("parseHandoffSections", () => {
  it("indexes headings for order checks", () => {
    const sections = parseHandoffSections(GOOD_HANDOFF);
    const headings = sections.map((s) => s.heading);
    expect(headings.indexOf("### Not proved")).toBeLessThan(headings.indexOf("### Status"));
  });
});