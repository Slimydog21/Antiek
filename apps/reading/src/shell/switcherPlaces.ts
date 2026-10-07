/**
 * switcherPlaces.ts — the PURE "places" model behind the Switcher
 * (CommandPalette.tsx). Spec: specs/antiek-keyboard-panes-agents-20261007/
 * sprint-02-launcher.html (claim ffx-nav-SPR-02), milestone 1.
 *
 * Omarchy replaces every bar with a typed launcher (SUPER+Space); herdr's
 * goto picker (prefix+g) lists every pane on its own row, grouped, with
 * single-key filters. Antiek already binds prefix+g / ⌘K to ONE surface —
 * the Switcher — so places become SECTIONS of that surface rather than a
 * second modal (index.html decision D-06 / rejected alternative "separate
 * Launcher").
 *
 * Rules this module enforces (tested in switcherPlaces.test.ts):
 *   - Identity by reference. A place row carries the owning store's own id
 *     (window id, agent-tab id, panel id, tab id); never a copied payload.
 *     Choosing a row must FOCUS/REVEAL that host through the existing
 *     command, never open a second one (pane-flow contract S01/S09/S10).
 *   - Absent, not empty. A section whose input the caller did not supply
 *     (projects, agents, arrangements — owned by other lanes) is omitted
 *     entirely, so the UI never shows "no projects" for "no API".
 *   - Fixed section order; ranking happens WITHIN a section using the same
 *     facet ranker the rest of the palette uses (paletteFacet.rankEntries),
 *     so a query never interleaves sections.
 *   - Filter keys are only meaningful when the search box is EMPTY; the
 *     caller decides that (the input owns printable keys — contract S11's
 *     spirit). This module only maps key → section.
 *
 * No React, no store imports, no data layer: the caller (CommandPalette)
 * reads the stores and hands plain inputs in, exactly like paletteFacet.
 */
import { rankEntries, type FacetEntry } from "./paletteFacet";
import { WORKFLOWS, WORKFLOW_ORDER, type Workflow } from "./workflowTaxonomy";

/** Section order is fixed and is the order the Switcher renders. */
export const PLACE_SECTIONS = [
  "doors",
  "scenes",
  "open",
  "tabs",
  "projects",
  "agents",
  "arrangements",
] as const;
export type PlaceSection = (typeof PLACE_SECTIONS)[number];

/** Human labels for the section headers. */
export const SECTION_LABELS: Record<PlaceSection, string> = {
  doors: "Doors",
  scenes: "Scenes",
  open: "Open",
  tabs: "Tabs",
  projects: "Projects",
  agents: "Agents",
  arrangements: "Arrangements",
};

/**
 * Single-key section filters, active only while the query is empty.
 * `a` = all (herdr's "a: all"). `o` is Open (prefix+o is tab.visitChild in
 * keymap.ts, but inside the open Switcher the letter is free).
 */
export const SECTION_FILTER_KEYS: Readonly<Record<string, PlaceSection | "all">> = {
  d: "doors",
  s: "scenes",
  o: "open",
  t: "tabs",
  p: "projects",
  g: "agents",
  r: "arrangements",
  a: "all",
};

/** herdr's agent-status vocabulary (refs/omarchy-herdr.md R15), and its
 *  single-key filters inside the Agents section. */
export const AGENT_STATUSES = ["blocked", "working", "idle", "done", "unknown"] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];
export const AGENT_STATUS_FILTER_KEYS: Readonly<Record<string, AgentStatus | "all">> = {
  b: "blocked",
  w: "working",
  i: "idle",
  d: "done",
  a: "all",
};

/** The pane-flow contract's pane target union (horizontal-pane-flow-20261002
 *  contract.md "Presentation and lifetime model"). Identity = existing host. */
export type PaneTarget =
  | { kind: "core" }
  | { kind: "companion" }
  | { kind: "panel"; id: string }
  | { kind: "window"; id: string };

/** What choosing a row means. Every variant resolves to an EXISTING
 *  command in the caller; this module never performs the act. */
export type PlaceTarget =
  | { type: "door"; workflow: Exclude<Workflow, "shared">; route: string }
  | { type: "route"; path: string }
  | { type: "pane"; pane: PaneTarget }
  | { type: "agentTab"; id: string }
  | { type: "tab"; mothership: string; tabId: string }
  | { type: "project"; id: string }
  | { type: "agent"; id: string }
  | { type: "arrangement"; slot: number };

export interface PlaceRow extends FacetEntry {
  kind: "place";
  section: PlaceSection;
  /** Stable, section-prefixed; the owning store's id is embedded verbatim. */
  id: string;
  title: string;
  subtitle: string;
  target: PlaceTarget;
  /** True for the host that currently has focus/activation (rendered as a
   *  ring; also the "recency" signal — the only one we have on main). */
  current?: boolean;
  /** Agents only (herdr vocabulary). */
  status?: AgentStatus;
  /** Optional pending-reason for blocked agents (R15: blocked needs a why). */
  reason?: string;
  workflow?: Workflow;
}

/* ------------------------------------------------------------------ */
/* Inputs                                                              */
/* ------------------------------------------------------------------ */

export interface SceneInput {
  id: string;
  title: string;
  subtitle: string;
  path: string;
  workflow?: Workflow;
}

export interface OpenInput {
  /** Product windows in PRESENTATION order (windowsStore `order` is
   *  bottom-to-top z; the caller passes whatever order it renders). */
  windows: readonly { id: string; title: string; kind: string }[];
  focusedWindowId: string | null;
  /** Companion (agent) tabs in activation order. */
  companionTabs: readonly { id: string; title: string; kind: string }[];
  activeCompanionTabId: string | null;
  /** Generic workspace panels (PanelLayout). */
  panels: readonly { id: string; title: string }[];
  focusedPanelId: string | null;
  /** The core canvas — always present as a pane target. */
  core: { title: string };
}

export interface TabInput {
  mothership: string;
  /** Tabs of the focused pane's tree, pre-order; `path` is the hierarchical
   *  path of titles from the root (tabTree.pathTo). */
  tabs: readonly { id: string; title: string; path: readonly string[]; active: boolean }[];
}

export interface ProjectInput {
  id: string;
  title: string;
  parentId: string | null;
}

export interface AgentInput {
  id: string;
  title: string;
  projectId?: string;
  projectTitle?: string;
  status?: AgentStatus;
  reason?: string;
}

export interface ArrangementInput {
  /** 1–10, rendered as 1..9,0 (Omarchy SUPER+digit). */
  slot: number;
  label: string;
  occupied: boolean;
  current: boolean;
}

export interface PlaceContext {
  /** Doors come from workflowTaxonomy unless overridden (tests). */
  doors?: readonly Exclude<Workflow, "shared">[];
  scenes: readonly SceneInput[];
  open: OpenInput;
  /** Absent → section absent. */
  tabs?: TabInput;
  projects?: readonly ProjectInput[];
  agents?: readonly AgentInput[];
  arrangements?: readonly ArrangementInput[];
}

/* ------------------------------------------------------------------ */
/* Builders                                                            */
/* ------------------------------------------------------------------ */

function doorRows(doors: readonly Exclude<Workflow, "shared">[]): PlaceRow[] {
  return doors.map((wf) => ({
    kind: "place" as const,
    section: "doors" as const,
    id: `door:${wf}`,
    title: WORKFLOWS[wf].label,
    subtitle: WORKFLOWS[wf].tagline,
    workflow: wf,
    target: { type: "door" as const, workflow: wf, route: WORKFLOWS[wf].defaultRoute },
  }));
}

function sceneRows(scenes: readonly SceneInput[]): PlaceRow[] {
  return scenes.map((s) => ({
    kind: "place" as const,
    section: "scenes" as const,
    id: `scene:${s.id}`,
    title: s.title,
    subtitle: s.subtitle,
    workflow: s.workflow,
    target: { type: "route" as const, path: s.path },
  }));
}

function openRows(open: OpenInput): PlaceRow[] {
  const rows: PlaceRow[] = [
    {
      kind: "place",
      section: "open",
      id: "open:core",
      title: open.core.title,
      subtitle: "Core canvas",
      target: { type: "pane", pane: { kind: "core" } },
      current:
        open.focusedWindowId === null &&
        open.focusedPanelId === null &&
        open.activeCompanionTabId === null,
    },
  ];
  for (const w of open.windows) {
    rows.push({
      kind: "place",
      section: "open",
      id: `open:window:${w.id}`,
      title: w.title,
      subtitle: `Window · ${w.kind}`,
      target: { type: "pane", pane: { kind: "window", id: w.id } },
      current: open.focusedWindowId === w.id,
    });
  }
  for (const t of open.companionTabs) {
    rows.push({
      kind: "place",
      section: "open",
      id: `open:agent-tab:${t.id}`,
      title: t.title,
      subtitle: `Companion · ${t.kind}`,
      target: { type: "agentTab", id: t.id },
      current: open.activeCompanionTabId === t.id,
    });
  }
  for (const p of open.panels) {
    rows.push({
      kind: "place",
      section: "open",
      id: `open:panel:${p.id}`,
      title: p.title,
      subtitle: "Panel",
      target: { type: "pane", pane: { kind: "panel", id: p.id } },
      current: open.focusedPanelId === p.id,
    });
  }
  return rows;
}

function tabRows(tabs: TabInput): PlaceRow[] {
  return tabs.tabs.map((t) => ({
    kind: "place" as const,
    section: "tabs" as const,
    id: `tab:${tabs.mothership}:${t.id}`,
    title: t.title,
    subtitle: t.path.length > 1 ? t.path.slice(0, -1).join(" › ") : `Tab · ${tabs.mothership}`,
    target: { type: "tab" as const, mothership: tabs.mothership, tabId: t.id },
    current: t.active,
  }));
}

function projectRows(projects: readonly ProjectInput[]): PlaceRow[] {
  const byId = new Map(projects.map((p) => [p.id, p]));
  return projects.map((p) => {
    const parent = p.parentId ? byId.get(p.parentId) : undefined;
    return {
      kind: "place" as const,
      section: "projects" as const,
      id: `project:${p.id}`,
      title: p.title,
      subtitle: parent ? `in ${parent.title}` : "Project",
      target: { type: "project" as const, id: p.id },
    };
  });
}

function agentRows(agents: readonly AgentInput[]): PlaceRow[] {
  return agents.map((a) => ({
    kind: "place" as const,
    section: "agents" as const,
    id: `agent:${a.id}`,
    title: a.title,
    subtitle: a.projectTitle ? `Agent · ${a.projectTitle}` : "Agent",
    target: { type: "agent" as const, id: a.id },
    status: a.status ?? "unknown",
    reason: a.reason,
  }));
}

function arrangementRows(arrangements: readonly ArrangementInput[]): PlaceRow[] {
  return arrangements.map((a) => ({
    kind: "place" as const,
    section: "arrangements" as const,
    id: `arrangement:${a.slot}`,
    title: `${a.slot % 10} · ${a.label}`,
    subtitle: a.occupied ? "Arrangement" : "Arrangement · empty",
    target: { type: "arrangement" as const, slot: a.slot },
    current: a.current,
  }));
}

/**
 * Build every place row for the Switcher, in section order. Sections whose
 * input is absent are ABSENT from the result (no header, no rows).
 */
export function buildPlaceRows(ctx: PlaceContext): PlaceRow[] {
  const rows: PlaceRow[] = [];
  rows.push(...doorRows(ctx.doors ?? WORKFLOW_ORDER));
  rows.push(...sceneRows(ctx.scenes));
  rows.push(...openRows(ctx.open));
  if (ctx.tabs) rows.push(...tabRows(ctx.tabs));
  if (ctx.projects) rows.push(...projectRows(ctx.projects));
  if (ctx.agents) rows.push(...agentRows(ctx.agents));
  if (ctx.arrangements) rows.push(...arrangementRows(ctx.arrangements));
  return rows;
}

/** The sections present in a row set, in canonical order. */
export function presentSections(rows: readonly PlaceRow[]): PlaceSection[] {
  const seen = new Set(rows.map((r) => r.section));
  return PLACE_SECTIONS.filter((s) => seen.has(s));
}

export interface PlaceFilter {
  section: PlaceSection | "all";
  agentStatus: AgentStatus | "all";
}

export const NO_FILTER: PlaceFilter = { section: "all", agentStatus: "all" };

/** Apply the single-key filters. The agent-status filter only narrows the
 *  Agents section; other sections are untouched by it. */
export function filterPlaceRows(rows: readonly PlaceRow[], filter: PlaceFilter): PlaceRow[] {
  return rows.filter((r) => {
    if (filter.section !== "all" && r.section !== filter.section) return false;
    if (r.section === "agents" && filter.agentStatus !== "all") {
      return r.status === filter.agentStatus;
    }
    return true;
  });
}

/**
 * Interpret a key pressed while the query is EMPTY. Returns the next filter,
 * or null when the key is not a filter key (the caller then lets the input
 * have it). Inside the Agents section (or when the section filter is
 * "agents"), herdr's b/w/i/d/a narrow by status — `d` therefore means
 * "done" there and "doors" elsewhere; `a` always clears.
 */
export function nextFilterForKey(key: string, current: PlaceFilter): PlaceFilter | null {
  const k = key.length === 1 ? key.toLowerCase() : key;
  if (current.section === "agents") {
    const status = AGENT_STATUS_FILTER_KEYS[k];
    if (status === "all") return NO_FILTER;
    if (status) return { section: "agents", agentStatus: status };
  }
  const section = SECTION_FILTER_KEYS[k];
  if (section === undefined) return null;
  if (section === "all") return NO_FILTER;
  return { section, agentStatus: "all" };
}

/**
 * Rank rows against a query WITHIN each section, keeping section order.
 * Empty query → original order (current/focused rows first within Open, so
 * the host you are on is one Enter away — the only recency signal on main).
 */
export function rankPlaceRows(rows: readonly PlaceRow[], query: string): PlaceRow[] {
  const q = query.trim();
  const out: PlaceRow[] = [];
  for (const section of PLACE_SECTIONS) {
    const inSection = rows.filter((r) => r.section === section);
    if (inSection.length === 0) continue;
    if (!q) {
      // Stable: current first, then original order.
      const current = inSection.filter((r) => r.current);
      const rest = inSection.filter((r) => !r.current);
      out.push(...current, ...rest);
    } else {
      out.push(...rankEntries(inSection, q));
    }
  }
  return out;
}

/** Group ranked rows by section for rendering, preserving row order. */
export function groupBySection(rows: readonly PlaceRow[]): { section: PlaceSection; rows: PlaceRow[] }[] {
  const groups: { section: PlaceSection; rows: PlaceRow[] }[] = [];
  for (const section of PLACE_SECTIONS) {
    const inSection = rows.filter((r) => r.section === section);
    if (inSection.length) groups.push({ section, rows: inSection });
  }
  return groups;
}
