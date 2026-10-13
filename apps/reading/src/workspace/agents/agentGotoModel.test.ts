/**
 * agentGotoModel.test.ts — SPR-10 M5: the pure picker model. Groups by the
 * registry root, cross-project rows in a trailing "Everywhere" group, rows
 * by attention rank then recency, b/w/i/d/a filters, and herdr B6's
 * movement (j/k clamp inside a group, Left/Right between groups, no wrap).
 */
import { describe, expect, it } from "vitest";

import type { Attention, RunEntry } from "./agentStatus";
import { applyFilter, buildGotoRows, moveSelection } from "./agentGotoModel";

function entry(runId: string, over: Partial<RunEntry> = {}): RunEntry {
  return { runId, viewId: `agent:thread:${runId}`, viewOpen: false, kind: "research-thread", investigationId: runId, title: `Title ${runId}`, projectId: "default", groupPath: ["default", runId], rootTitle: "Default project", ...over };
}

const ENTRIES: RunEntry[] = [
  entry("A", { treeSince: "2026-10-01T00:00:00Z" }),
  entry("B", { treeSince: "2026-10-03T00:00:00Z" }),
  entry("C", { treeSince: "2026-10-02T00:00:00Z" }),
  entry("D", { projectId: "p1", groupPath: ["p1", "D"], rootTitle: "Varda diligence" }),
  entry("agent:dialogue", { viewId: "agent:dialogue", viewOpen: true, kind: "dialogue", investigationId: undefined, projectId: null, groupPath: [], rootTitle: "" }),
];
const STATUS: Record<string, Attention> = {
  A: { state: "working" },
  B: { state: "idle", reason: "stopped" },
  C: { state: "idle" },
  D: { state: "done" },
  "agent:dialogue": { state: "unknown", reason: "no-run" },
};
const statusOf = (e: RunEntry) => STATUS[e.runId];

describe("buildGotoRows", () => {
  it("groups by the root, Everywhere last; rows by rank desc then since desc", () => {
    const groups = buildGotoRows(ENTRIES, statusOf);
    expect(groups.map((g) => g.title)).toEqual(["Default project", "Varda diligence", "Everywhere"]);
    expect(groups[0].rows.map((r) => r.runId)).toEqual(["A", "B", "C"]);
    expect(groups[0].rows[1]).toMatchObject({ runId: "B", status: "idle", reason: "stopped", viewOpen: false, investigationId: "B" });
    expect(groups[2].rows[0]).toMatchObject({ runId: "agent:dialogue", viewOpen: true, status: "unknown", reason: "no-run" });
    expect(groups[2].rows[0].investigationId).toBeUndefined();
  });

  it("an empty entry set yields no groups", () => {
    expect(buildGotoRows([], statusOf)).toEqual([]);
  });
});

describe("applyFilter", () => {
  const groups = buildGotoRows(ENTRIES, statusOf);
  it("b/w/i/d keep exactly that state; empty groups drop; all restores", () => {
    expect(applyFilter(groups, "working", "").flatMap((g) => g.rows.map((r) => r.runId))).toEqual(["A"]);
    expect(applyFilter(groups, "idle", "").flatMap((g) => g.rows.map((r) => r.runId))).toEqual(["B", "C"]);
    expect(applyFilter(groups, "done", "").map((g) => g.title)).toEqual(["Varda diligence"]);
    expect(applyFilter(groups, "blocked", "")).toEqual([]);
    expect(applyFilter(groups, "all", "")).toEqual(groups);
  });
  it("the query matches titles case-insensitively and composes with the state filter", () => {
    expect(applyFilter(groups, "all", "title b").flatMap((g) => g.rows.map((r) => r.runId))).toEqual(["B"]);
    expect(applyFilter(groups, "idle", "TITLE C").flatMap((g) => g.rows.map((r) => r.runId))).toEqual(["C"]);
    expect(applyFilter(groups, "all", "nothing")).toEqual([]);
  });
});

describe("moveSelection (herdr B6)", () => {
  const groups = buildGotoRows(ENTRIES, statusOf);
  it("j/k and the vertical arrows clamp inside a group", () => {
    let pos = { group: 0, row: 0 };
    pos = moveSelection(groups, pos, "j"); expect(pos).toEqual({ group: 0, row: 1 });
    pos = moveSelection(groups, pos, "ArrowDown"); expect(pos).toEqual({ group: 0, row: 2 });
    pos = moveSelection(groups, pos, "j"); expect(pos).toEqual({ group: 0, row: 2 });
    pos = moveSelection(groups, pos, "k"); expect(pos).toEqual({ group: 0, row: 1 });
    pos = moveSelection(groups, pos, "ArrowUp"); expect(pos).toEqual({ group: 0, row: 0 });
    pos = moveSelection(groups, pos, "k"); expect(pos).toEqual({ group: 0, row: 0 });
  });
  it("Left/Right move between groups without wrap, row clamped to the new group", () => {
    let pos = { group: 0, row: 2 };
    pos = moveSelection(groups, pos, "ArrowRight"); expect(pos).toEqual({ group: 1, row: 0 });
    pos = moveSelection(groups, pos, "ArrowRight"); expect(pos).toEqual({ group: 2, row: 0 });
    pos = moveSelection(groups, pos, "ArrowRight"); expect(pos).toEqual({ group: 2, row: 0 });
    pos = moveSelection(groups, pos, "ArrowLeft"); expect(pos).toEqual({ group: 1, row: 0 });
    pos = moveSelection(groups, pos, "ArrowLeft"); expect(pos).toEqual({ group: 0, row: 0 });
    pos = moveSelection(groups, pos, "ArrowLeft"); expect(pos).toEqual({ group: 0, row: 0 });
    expect(moveSelection(groups, pos, "x")).toEqual(pos);
    expect(moveSelection([], pos, "j")).toEqual({ group: 0, row: 0 });
  });
});
