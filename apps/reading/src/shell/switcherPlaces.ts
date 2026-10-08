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
 *   - Filters are QUERY SYNTAX, not bare letters: `in:open`, `in:agents`,
 *     `is:blocked` (the same shape as the palette's existing `state:`
 *     facet). herdr's bare b/w/i/d keys were rejected for this surface
 *     because the Switcher is type-to-search first and `r`, `d`, `s` begin
 *     "read", "documents", "speak" — a bare-letter filter would steal the
 *     first keystroke of the commonest queries (recorded in the SPR-02
 *     handoff). Tab/Shift+Tab cycle sections; chips click.
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

/** `in:<word>` section filter words (plural and singular both parse). */
export const SECTION_WORDS: Readonly<Record<string, PlaceSection>> = {
  door: "doors", doors: "doors",
  scene: "scenes", scenes: "scenes",
  open: "open", pane: "open", panes: "open", window: "open", windows: "open",
  tab: "tabs", tabs: "tabs",
  project: "projects", projects: "projects",
  agent: "agents", agents: "agents",
  arrangement: "arrangements", arrangements: "arrangements",
};

/** herdr's agent-status vocabulary (refs/omarchy-herdr.md R15), and its
 *  single-key filters inside the Agents section. */
export const AGENT_STATUSES = ["blocked", "working", "idle", "done", "unknown"] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];
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
  /** The core canvas as a pane target. OPTIONAL: on main there is no
   *  "focus the core" command (the pane-flow packet, SPR-01, adds one), and a
   *  row whose Enter does nothing would be a hidden non-consumption. Pass it
   *  only when the caller can actually focus it. */
  core?: { title: string };
}

export interface TabInput {
  mothership: string;
  /** Tabs of the focused pane's tree, pre-order; `path` is the hierarchical
   *  path of titles from the root (tabTree.pathTo). */
  tabs: readonly { id: string; title: string; path: readonly string[]; active: boolean }[];
}

/** The structural slice of workspace/tabTree.ts#TabTree this adapter reads
 *  (kept structural so the model imports nothing from workspace/). */
export interface TabTreeLike {
  nodes: Readonly<Record<string, { tab_id: string; parent_tab_id: string | null; hier_number: string; kind: string; ref: string; child_order: readonly string[]; pruned_at?: string }>>;
  root_order: readonly string[];
  active_tab_id: string | null;
}

/** Pre-order walk of a tab tree into TabInput rows. Pruned nodes are
 *  skipped. Titles are what the strip shows a user without a title
 *  field: the hierarchical number, the kind, and the ref's head. */
export function tabInputFromTree(mothership: string, tree: TabTreeLike): TabInput {
  const tabs: { id: string; title: string; path: readonly string[]; active: boolean }[] = [];
  const label = (id: string) => {
    const n = tree.nodes[id];
    return `${n.hier_number} ${n.kind} · ${n.ref.slice(0, 8)}`;
  };
  const walk = (id: string, path: readonly string[]) => {
    const n = tree.nodes[id];
    if (!n || n.pruned_at) return;
    const here = [...path, label(id)];
    tabs.push({ id, title: label(id), path: here, active: tree.active_tab_id === id });
    for (const c of n.child_order) walk(c, here);
  };
  for (const r of tree.root_order) walk(r, []);
  return { mothership, tabs };
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
  const rows: PlaceRow[] = [];
  if (open.core) {
    rows.push({
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
    });
  }
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
export function filterPlaceRows<R extends PlaceRow>(rows: readonly R[], filter: PlaceFilter): R[] {
  return rows.filter((r) => {
    if (filter.section !== "all" && r.section !== filter.section) return false;
    if (r.section === "agents" && filter.agentStatus !== "all") {
      return r.status === filter.agentStatus;
    }
    return true;
  });
}

/**
 * Parse the filter words off the front of a query: any leading run of
 * `in:<section>` / `is:<status>` words (either order, repeatable; the last
 * of each wins). Returns the filter and the remaining search text. Unknown
 * words after `in:`/`is:` are NOT filters — they stay in the text so the
 * user sees their typo rather than an empty list.
 */
export function parseFilterQuery(query: string): { filter: PlaceFilter; text: string } {
  let section: PlaceSection | "all" = "all";
  let agentStatus: AgentStatus | "all" = "all";
  const words = query.trim().split(/\s+/);
  let i = 0;
  while (i < words.length) {
    const w = words[i].toLowerCase();
    const m = w.match(/^(in|is):([a-z]*)$/);
    if (!m) break;
    if (m[1] === "in") {
      const s = SECTION_WORDS[m[2]];
      if (!s) break;
      section = s;
    } else {
      if (m[2] === "all") agentStatus = "all";
      else if ((AGENT_STATUSES as readonly string[]).includes(m[2])) agentStatus = m[2] as AgentStatus;
      else break;
    }
    i += 1;
  }
  return { filter: { section, agentStatus }, text: words.slice(i).join(" ") };
}

/** Rebuild a query from a filter and search text (chips write through this). */
export function formatFilterQuery(filter: PlaceFilter, text: string): string {
  const parts: string[] = [];
  if (filter.section !== "all") parts.push(`in:${filter.section}`);
  if (filter.agentStatus !== "all") parts.push(`is:${filter.agentStatus}`);
  if (text.trim()) parts.push(text.trim());
  return parts.join(" ");
}

/** The next section when cycling with Tab (direction 1) / Shift+Tab (-1)
 *  over "all" + the sections present. */
export function cycleSection(
  current: PlaceSection | "all",
  present: readonly PlaceSection[],
  direction: 1 | -1,
): PlaceSection | "all" {
  const ring: (PlaceSection | "all")[] = ["all", ...present];
  const idx = ring.indexOf(current);
  const next = (idx === -1 ? 0 : idx + direction + ring.length) % ring.length;
  return ring[next];
}

/**
 * Rank rows against a query WITHIN each section, keeping section order.
 * Empty query → original order (current/focused rows first within Open, so
 * the host you are on is one Enter away — the only recency signal on main).
 */
export function rankPlaceRows<R extends PlaceRow>(rows: readonly R[], query: string): R[] {
  const q = query.trim();
  const out: R[] = [];
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
export function groupBySection<R extends PlaceRow>(rows: readonly R[]): { section: PlaceSection; rows: R[] }[] {
  const groups: { section: PlaceSection; rows: R[] }[] = [];
  for (const section of PLACE_SECTIONS) {
    const inSection = rows.filter((r) => r.section === section);
    if (inSection.length) groups.push({ section, rows: inSection });
  }
  return groups;
}
