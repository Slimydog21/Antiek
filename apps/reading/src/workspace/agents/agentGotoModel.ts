/**
 * agents/agentGotoModel.ts — SPR-10 M5: the goto picker's PURE model.
 * Groups by the registry root (the first id of an entry's groupPath),
 * cross-project entries in a trailing "Everywhere" group; rows by attention
 * rank desc then recency desc; b/w/i/d/a filters; herdr B6 movement.
 */
import { rankOf, type AgentStatus, type Attention, type RunEntry } from "./agentStatus";

export interface GotoRow {
  runId: string;
  viewId: string;
  viewOpen: boolean;
  investigationId?: string;
  title: string;
  kind: RunEntry["kind"];
  status: AgentStatus;
  reason?: string;
  since: string;
}

export interface GotoGroup {
  key: string;
  title: string;
  rows: GotoRow[];
}

export type GotoFilter = "all" | "blocked" | "working" | "idle" | "done";

export const FILTER_KEYS: Readonly<Record<string, GotoFilter>> = Object.freeze({
  b: "blocked",
  w: "working",
  i: "idle",
  d: "done",
  a: "all",
});

export const EVERYWHERE_KEY = "";
export const EVERYWHERE_TITLE = "Everywhere";

export function buildGotoRows(entries: Iterable<RunEntry>, statusOf: (e: RunEntry) => Attention): GotoGroup[] {
  const groups = new Map<string, GotoGroup>();
  let everywhere: GotoGroup | null = null;
  for (const e of entries) {
    const a = statusOf(e);
    const row: GotoRow = {
      runId: e.runId,
      viewId: e.viewId,
      viewOpen: e.viewOpen,
      ...(e.investigationId !== undefined ? { investigationId: e.investigationId } : {}),
      title: e.title,
      kind: e.kind,
      status: a.state,
      ...(a.reason ? { reason: a.reason } : {}),
      since: e.treeSince ?? "",
    };
    const key = e.groupPath[0] ?? EVERYWHERE_KEY;
    if (key === EVERYWHERE_KEY) {
      everywhere ??= { key: EVERYWHERE_KEY, title: EVERYWHERE_TITLE, rows: [] };
      everywhere.rows.push(row);
      continue;
    }
    const g = groups.get(key) ?? { key, title: e.rootTitle || key, rows: [] };
    g.rows.push(row);
    groups.set(key, g);
  }
  const out = [...groups.values()];
  if (everywhere) out.push(everywhere);
  for (const g of out) g.rows.sort((x, y) => rankOf(y.status) - rankOf(x.status) || y.since.localeCompare(x.since));
  return out;
}

export function applyFilter(groups: readonly GotoGroup[], filter: GotoFilter, query: string): GotoGroup[] {
  const needle = query.trim().toLowerCase();
  if (filter === "all" && !needle) return [...groups];
  const out: GotoGroup[] = [];
  for (const g of groups) {
    const rows = g.rows.filter((r) => (filter === "all" || r.status === filter) && (!needle || r.title.toLowerCase().includes(needle)));
    if (rows.length) out.push({ ...g, rows });
  }
  return out;
}

export interface GotoPos {
  group: number;
  row: number;
}

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

/** j/k/ArrowDown/ArrowUp inside a group (clamped); ArrowLeft/ArrowRight
 *  between groups, no wrap (herdr B6). Any other key: unchanged. */
export function moveSelection(groups: readonly GotoGroup[], pos: GotoPos, key: string): GotoPos {
  if (groups.length === 0) return { group: 0, row: 0 };
  const group = clamp(pos.group, 0, groups.length - 1);
  const row = clamp(pos.row, 0, groups[group].rows.length - 1);
  switch (key) {
    case "j":
    case "ArrowDown":
      return { group, row: clamp(row + 1, 0, groups[group].rows.length - 1) };
    case "k":
    case "ArrowUp":
      return { group, row: clamp(row - 1, 0, groups[group].rows.length - 1) };
    case "ArrowRight": {
      const g = clamp(group + 1, 0, groups.length - 1);
      return { group: g, row: clamp(row, 0, groups[g].rows.length - 1) };
    }
    case "ArrowLeft": {
      const g = clamp(group - 1, 0, groups.length - 1);
      return { group: g, row: clamp(row, 0, groups[g].rows.length - 1) };
    }
    default:
      return { group, row };
  }
}
