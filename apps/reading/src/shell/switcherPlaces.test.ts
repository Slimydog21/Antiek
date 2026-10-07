/**
 * switcherPlaces.test.ts — SPR-02 M1 (specs/antiek-keyboard-panes-agents-20261007/
 * sprint-02-launcher.html). Pure logic, no React, no data layer.
 */
import { describe, expect, it } from "vitest";

import {
  buildPlaceRows,
  filterPlaceRows,
  groupBySection,
  cycleSection,
  formatFilterQuery,
  NO_FILTER,
  parseFilterQuery,
  PLACE_SECTIONS,
  presentSections,
  rankPlaceRows,
  tabInputFromTree,
  type OpenInput,
  type PlaceContext,
} from "./switcherPlaces";

const open: OpenInput = {
  windows: [
    { id: "win-reader-doc-1", title: "Ocean iron fertilisation (PDF)", kind: "reader" },
    { id: "win-notes-2", title: "Notes", kind: "notebook" },
  ],
  focusedWindowId: "win-notes-2",
  companionTabs: [{ id: "agent-tab-7", title: "Thread: iron limits", kind: "research-thread" }],
  activeCompanionTabId: null,
  panels: [{ id: "panel-tree", title: "Project tree" }],
  focusedPanelId: null,
  core: { title: "Research canvas" },
};

const base: PlaceContext = {
  scenes: [
    { id: "library", title: "Library", subtitle: "Read · all documents", path: "/library", workflow: "read" },
    { id: "brainstorm", title: "Brainstorm", subtitle: "Research · parked questions", path: "/brainstorm", workflow: "research" },
  ],
  open,
};

describe("buildPlaceRows — absent, not empty", () => {
  it("omits projects, agents, tabs and arrangements when their inputs are absent", () => {
    const rows = buildPlaceRows(base);
    expect(presentSections(rows)).toEqual(["doors", "scenes", "open"]);
    expect(rows.some((r) => r.section === "projects")).toBe(false);
    expect(rows.some((r) => r.section === "agents")).toBe(false);
  });

  it("includes a section when its input is present but empty? — no: an empty list is still 'present'", () => {
    // The caller decides presence by passing the array; an API that answered
    // with zero projects IS a real answer and renders a header with no rows.
    const rows = buildPlaceRows({ ...base, projects: [] });
    // presentSections derives from rows, so an empty projects list yields no
    // rows — the UI must read `ctx.projects !== undefined` for the header.
    expect(rows.some((r) => r.section === "projects")).toBe(false);
  });

  it("renders the four doors from the taxonomy in rail order", () => {
    const doors = buildPlaceRows(base).filter((r) => r.section === "doors");
    expect(doors.map((d) => d.target)).toEqual([
      { type: "door", workflow: "research", route: expect.any(String) },
      { type: "door", workflow: "read", route: expect.any(String) },
      { type: "door", workflow: "write", route: expect.any(String) },
      { type: "door", workflow: "speak", route: expect.any(String) },
    ]);
  });
});

describe("Open rows — identity by reference", () => {
  it("carries the stores' ids verbatim and never a copied payload", () => {
    const rows = buildPlaceRows(base).filter((r) => r.section === "open");
    const targets = rows.map((r) => r.target);
    expect(targets).toContainEqual({ type: "pane", pane: { kind: "core" } });
    expect(targets).toContainEqual({ type: "pane", pane: { kind: "window", id: "win-reader-doc-1" } });
    expect(targets).toContainEqual({ type: "pane", pane: { kind: "window", id: "win-notes-2" } });
    expect(targets).toContainEqual({ type: "agentTab", id: "agent-tab-7" });
    expect(targets).toContainEqual({ type: "pane", pane: { kind: "panel", id: "panel-tree" } });
    for (const r of rows) {
      expect(Object.keys(r)).not.toContain("payload");
      expect(Object.keys(r)).not.toContain("html");
    }
  });

  it("marks exactly the focused host as current", () => {
    const rows = buildPlaceRows(base).filter((r) => r.section === "open");
    expect(rows.filter((r) => r.current).map((r) => r.id)).toEqual(["open:window:win-notes-2"]);
  });

  it("emits no core row when the caller cannot focus the core (main today)", () => {
    const { core: _omit, ...noCore } = open;
    const rows = buildPlaceRows({ ...base, open: { ...noCore, focusedWindowId: null } }).filter((r) => r.section === "open");
    expect(rows.some((r) => r.id === "open:core")).toBe(false);
    expect(rows.some((r) => r.current)).toBe(false);
  });

  it("marks the core canvas current when nothing else holds focus", () => {
    const rows = buildPlaceRows({
      ...base,
      open: { ...open, focusedWindowId: null },
    }).filter((r) => r.section === "open");
    expect(rows.filter((r) => r.current).map((r) => r.id)).toEqual(["open:core"]);
  });
});

describe("rankPlaceRows — section order is never interleaved", () => {
  it("keeps sections in canonical order and puts the current host first inside Open on an empty query", () => {
    const ranked = rankPlaceRows(buildPlaceRows(base), "");
    const order = ranked.map((r) => r.section);
    const firstIndex = (s: (typeof order)[number]) => order.indexOf(s);
    expect(firstIndex("doors")).toBeLessThan(firstIndex("scenes"));
    expect(firstIndex("scenes")).toBeLessThan(firstIndex("open"));
    const openRows = ranked.filter((r) => r.section === "open");
    expect(openRows[0].id).toBe("open:window:win-notes-2");
  });

  it("'read' ranks the Read door above the Library scene (door section first), both above Open", () => {
    const ranked = rankPlaceRows(buildPlaceRows(base), "read");
    const ids = ranked.map((r) => r.id);
    expect(ids.indexOf("door:read")).toBeGreaterThanOrEqual(0);
    expect(ids.indexOf("door:read")).toBeLessThan(ids.indexOf("scene:library"));
    expect(ids).not.toContain("open:window:win-notes-2");
  });

  it("'rea' matches by text in every section and drops the rest ('research' does not contain 'rea')", () => {
    const ranked = rankPlaceRows(buildPlaceRows(base), "rea");
    const ids = ranked.map((r) => r.id);
    // "research-th[rea]d" — the companion tab matches on its kind, too.
    expect(ids).toEqual(["door:read", "scene:library", "open:agent-tab:agent-tab-7", "open:window:win-reader-doc-1"]);
  });

  it("'notes' lists the Write door (its tagline says notes) before the open Notes window — sections, not scores, order the list", () => {
    const ranked = rankPlaceRows(buildPlaceRows(base), "notes");
    expect(ranked.map((r) => r.id)).toEqual(["door:write", "open:window:win-notes-2"]);
  });
});

describe("filters — query syntax, never bare letters", () => {
  it("parses in:<section> and is:<status> off the front and leaves the search text", () => {
    expect(parseFilterQuery("in:open notes")).toEqual({ filter: { section: "open", agentStatus: "all" }, text: "notes" });
    expect(parseFilterQuery("in:agents is:blocked")).toEqual({ filter: { section: "agents", agentStatus: "blocked" }, text: "" });
    expect(parseFilterQuery("is:done in:agent plan")).toEqual({ filter: { section: "agents", agentStatus: "done" }, text: "plan" });
    expect(parseFilterQuery("read")).toEqual({ filter: NO_FILTER, text: "read" });
  });

  it("a bare first letter is search text, not a filter — r/d/s/o/a all search", () => {
    for (const k of ["r", "d", "s", "o", "a", "b"]) {
      expect(parseFilterQuery(k)).toEqual({ filter: NO_FILTER, text: k });
    }
  });

  it("an unknown word after in:/is: stays visible as text instead of silently filtering", () => {
    expect(parseFilterQuery("in:nowhere x")).toEqual({ filter: NO_FILTER, text: "in:nowhere x" });
    expect(parseFilterQuery("is:sleepy")).toEqual({ filter: NO_FILTER, text: "is:sleepy" });
  });

  it("formatFilterQuery round-trips what parseFilterQuery reads", () => {
    const q = formatFilterQuery({ section: "agents", agentStatus: "blocked" }, "plan");
    expect(q).toBe("in:agents is:blocked plan");
    expect(parseFilterQuery(q)).toEqual({ filter: { section: "agents", agentStatus: "blocked" }, text: "plan" });
    expect(formatFilterQuery(NO_FILTER, "  ")).toBe("");
  });

  it("Tab cycles all → each present section → all, and Shift+Tab reverses", () => {
    const present = ["doors", "open"] as const;
    expect(cycleSection("all", present, 1)).toBe("doors");
    expect(cycleSection("doors", present, 1)).toBe("open");
    expect(cycleSection("open", present, 1)).toBe("all");
    expect(cycleSection("all", present, -1)).toBe("open");
    expect(cycleSection("tabs", present, 1)).toBe("all"); // a section no longer present resets
  });

  it("filterPlaceRows narrows Agents by status and leaves other sections alone", () => {
    const rows = buildPlaceRows({
      ...base,
      agents: [
        { id: "a1", title: "Planner", status: "blocked", reason: "needs a yes" },
        { id: "a2", title: "Reader", status: "working" },
        { id: "a3", title: "Summariser" },
      ],
    });
    const blocked = filterPlaceRows(rows, { section: "agents", agentStatus: "blocked" });
    expect(blocked.map((r) => r.id)).toEqual(["agent:a1"]);
    expect(blocked[0].reason).toBe("needs a yes");
    const unknown = rows.find((r) => r.id === "agent:a3");
    expect(unknown?.status).toBe("unknown");
    const onlyOpen = filterPlaceRows(rows, { section: "open", agentStatus: "blocked" });
    expect(onlyOpen.every((r) => r.section === "open")).toBe(true);
    expect(onlyOpen.length).toBe(5);
  });
});

describe("tabs, projects, arrangements", () => {
  it("tab rows carry mothership + tabId and a path subtitle", () => {
    const rows = buildPlaceRows({
      ...base,
      tabs: {
        mothership: "reading",
        tabs: [
          { id: "t1", title: "Chapter 1", path: ["Chapter 1"], active: false },
          { id: "t2", title: "Footnote 3", path: ["Chapter 1", "Footnote 3"], active: true },
        ],
      },
    }).filter((r) => r.section === "tabs");
    expect(rows.map((r) => r.target)).toEqual([
      { type: "tab", mothership: "reading", tabId: "t1" },
      { type: "tab", mothership: "reading", tabId: "t2" },
    ]);
    expect(rows[1].subtitle).toBe("Chapter 1");
    expect(rows[1].current).toBe(true);
  });

  it("tabInputFromTree walks pre-order, skips pruned nodes, and marks the active tab", () => {
    const node = (tab_id: string, parent_tab_id: string | null, hier_number: string, child_order: string[] = [], pruned_at?: string) =>
      ({ tab_id, parent_tab_id, hier_number, kind: "reader", ref: `${tab_id}-ref-0123456789`, child_order, pruned_at });
    const input = tabInputFromTree("reading", {
      nodes: { r1: node("r1", null, "1", ["c1", "c2"]), c1: node("c1", "r1", "1.1"), c2: node("c2", "r1", "1.2", [], "2026-10-07"), r2: node("r2", null, "2") },
      root_order: ["r1", "r2"],
      active_tab_id: "c1",
    });
    expect(input.tabs.map((t) => t.id)).toEqual(["r1", "c1", "r2"]);
    expect(input.tabs[1]).toMatchObject({ active: true, path: ["1 reader · r1-ref-0", "1.1 reader · c1-ref-0"] });
    const rows = buildPlaceRows({ ...base, tabs: input }).filter((r) => r.section === "tabs");
    expect(rows[1].subtitle).toBe("1 reader · r1-ref-0");
  });

  it("project rows name their parent; arrangements render slot 10 as 0", () => {
    const rows = buildPlaceRows({
      ...base,
      projects: [
        { id: "p", title: "Ocean", parentId: null },
        { id: "c", title: "Iron", parentId: "p" },
      ],
      arrangements: [
        { slot: 1, label: "Reading", occupied: true, current: true },
        { slot: 10, label: "Scratch", occupied: false, current: false },
      ],
    });
    expect(rows.find((r) => r.id === "project:c")?.subtitle).toBe("in Ocean");
    expect(rows.find((r) => r.id === "arrangement:10")?.title).toBe("0 · Scratch");
    expect(groupBySection(rows).map((g) => g.section)).toEqual(["doors", "scenes", "open", "projects", "arrangements"]);
  });

  it("PLACE_SECTIONS is the only order groupBySection ever emits", () => {
    const groups = groupBySection(buildPlaceRows(base));
    const idx = groups.map((g) => PLACE_SECTIONS.indexOf(g.section));
    expect([...idx].sort((a, b) => a - b)).toEqual(idx);
  });
});
