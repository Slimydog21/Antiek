/**
 * projectTabs.ts — the tab-tree wire module (THREAD-CONTRACT §1.6, lane B).
 *
 * Types and a thin client for GET/PUT /projects/{id}/tabs/{mothership},
 * POST …/allocate and GET …/retired. It holds no state and does no retry or
 * rebase: lane A's TabTreeAdapter builds those on top (agreed 2026-09-26).
 *
 * `tree` is `{nodes: {[tab_id]: TabNode}, root_order: tab_id[]}`. There is
 * no in-tree history or counter: the server's `retired[]` holds closed tabs
 * with their whole node, and `next_child_index` (root tabs under `"root"`)
 * holds the per-parent counters. Numbers are addresses and never reused.
 *
 * A PUT answers one of three outcomes, discriminated so the caller narrows
 * without parsing strings: saved (the new snapshot), conflict (409
 * `version_stale` | `number_conflict`, with `current` to rebase on), or
 * invalid (422 `tab_origin_invalid` | `tab_tree_invalid`, a lane-A bug to
 * log, never to show the operator). Anything else throws ApiError.
 */
import { API_BASE, ApiError, apiFetch } from "../api";

export type Mothership = "research" | "writing" | "reading";
export type TabSide = "left" | "right";
/** `research` is on both sides: left, a deep research spawned from a document
 *  (R3, core material); right, a research as an agent you talk to (R6, R18). */
export type LeftTabKind = "reader" | "document" | "research";
export type RightTabKind =
  | "research"
  | "dialogue"
  | "reformat"
  | "diligence"
  | "island"
  | "findings"
  | "flags"
  | "block";
export type TabKind = LeftTabKind | RightTabKind;
/** `branch_origin.kind` on the wire. The UI's "island" is `selection`. */
export type BranchOriginKind =
  | "footnote"
  | "reference"
  | "citation"
  | "selection"
  | "research"
  | "manual"
  | "agent"
  | "derivation";
export type CloseMode = "close" | "prune" | "lift_children";

export interface TextLocator {
  start: number;
  end: number;
  text_sha256: string;
  block_id?: string | null;
}

/** Contract §1.4. `source_locator` is the durable key. */
export interface BranchAnchor {
  document_id: string;
  source_locator?: TextLocator | null;
  region_id?: string | null;
  anchor_id?: string | null;
  quote?: string | null;
  prefix?: string | null;
  suffix?: string | null;
  page_index?: number | null;
}

export interface BranchOrigin {
  document_id: string;
  anchor?: BranchAnchor | null;
  kind: BranchOriginKind;
}

/** Required when `branch_origin.kind` is `agent` (422 tab_origin_invalid otherwise). */
export interface OpenedBy {
  thread_id: string;
  agent_kind: string;
}

export interface PaneDock {
  docked_kind?: string | null;
  docked_ref?: string | null;
}

/** A node in the tab tree (contract Part 2 §2.2). The server refuses any other field. */
export interface TabNode {
  tab_id: string;
  parent_tab_id: string | null;
  side: TabSide;
  kind: TabKind;
  ref: string;
  title: string;
  mothership: Mothership;
  pane?: PaneDock | null;
  /** null while `numbering`: the server fills in a number allocate registered. */
  public_number: number | null;
  hier_number: string;
  branch_origin?: BranchOrigin | null;
  opened_by?: OpenedBy | null;
  child_order: string[];
  last_visited_child_id?: string | null;
  /** Set only on a retired node that left by prune; never on an open tab. */
  pruned_at?: string | null;
}

export interface TabTreeWire {
  nodes: Record<string, TabNode>;
  root_order: string[];
}

export interface ActiveBySide {
  left: string | null;
  right: string | null;
}

export interface RetiredEntry {
  closed_at: string;
  close_mode: CloseMode;
  node: TabNode;
}

/** The GET shape, the PUT's saved answer, and every 409's `current`. */
export interface TabsSnapshot {
  tree: TabTreeWire;
  active: ActiveBySide;
  version: number;
  /** Per-parent counters; root tabs count under `"root"`. Absent means 1. */
  next_child_index: Record<string, number>;
  /** The 200 most recent unrestored retirements, newest first. */
  retired: RetiredEntry[];
}

export interface PutTabsRequest {
  tree: TabTreeWire;
  active: ActiveBySide;
  expected_version: number;
}

export interface AllocateResponse {
  public_number: number;
}

export type TabsConflict =
  | { reason: "version_stale"; current: TabsSnapshot }
  | { reason: "number_conflict"; tab_id: string; detail: string; current: TabsSnapshot };

export interface TabsInvalid {
  reason: "tab_origin_invalid" | "tab_tree_invalid";
  tab_id: string | null;
  detail: string;
}

export type PutTabsResult =
  | { status: "saved"; snapshot: TabsSnapshot }
  | { status: "conflict"; conflict: TabsConflict }
  | { status: "invalid"; invalid: TabsInvalid };

export interface RetiredPage {
  retired: RetiredEntry[];
  /** Pass as `before` for the next page; null when this was the last. */
  next_before: string | null;
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isCount = (v: unknown, min = 0): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= min;
const isNullableString = (v: unknown): boolean => v === null || typeof v === "string";

function isTabNode(v: unknown): v is TabNode {
  return (
    isObject(v) &&
    typeof v.tab_id === "string" &&
    isNullableString(v.parent_tab_id) &&
    (v.side === "left" || v.side === "right") &&
    typeof v.kind === "string" &&
    typeof v.ref === "string" &&
    typeof v.title === "string" &&
    typeof v.mothership === "string" &&
    (v.public_number === null || isCount(v.public_number, 1)) &&
    typeof v.hier_number === "string" &&
    Array.isArray(v.child_order) &&
    v.child_order.every((c) => typeof c === "string")
  );
}

function isRetiredEntry(v: unknown): v is RetiredEntry {
  return (
    isObject(v) &&
    typeof v.closed_at === "string" &&
    (v.close_mode === "close" || v.close_mode === "prune" || v.close_mode === "lift_children") &&
    isTabNode(v.node)
  );
}

function isSnapshot(v: unknown): v is TabsSnapshot {
  if (!isObject(v) || !isObject(v.tree) || !isObject(v.active) || !isObject(v.next_child_index)) return false;
  const { nodes, root_order } = v.tree;
  return (
    isObject(nodes) &&
    Object.entries(nodes).every(([id, n]) => isTabNode(n) && n.tab_id === id) &&
    Array.isArray(root_order) &&
    root_order.every((id) => typeof id === "string") &&
    isNullableString(v.active.left) &&
    isNullableString(v.active.right) &&
    isCount(v.version) &&
    Object.values(v.next_child_index).every((n) => isCount(n, 1)) &&
    Array.isArray(v.retired) &&
    v.retired.every(isRetiredEntry)
  );
}

/** Parse a snapshot at the boundary; a malformed body throws, never half-parses. */
export function parseTabsSnapshot(raw: unknown): TabsSnapshot {
  if (!isSnapshot(raw)) {
    throw new ApiError("project tabs: malformed snapshot", 0, JSON.stringify(raw));
  }
  return raw;
}

function tabsUrl(projectId: string, mothership: Mothership, suffix = ""): string {
  return `${API_BASE}/projects/${encodeURIComponent(projectId)}/tabs/${mothership}${suffix}`;
}

async function fail(what: string, resp: Response): Promise<never> {
  throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
}

/** GET the tree; a project never written answers version 0 and an empty tree. */
export async function getTabs(projectId: string, mothership: Mothership, signal?: AbortSignal): Promise<TabsSnapshot> {
  const resp = await apiFetch(tabsUrl(projectId, mothership), { signal });
  if (!resp.ok) return fail("GET /projects/{id}/tabs/{mothership}", resp);
  return parseTabsSnapshot(await resp.json());
}

/** PUT a whole-tree snapshot with the version it descends from. */
export async function putTabs(
  projectId: string,
  mothership: Mothership,
  body: PutTabsRequest,
  signal?: AbortSignal,
): Promise<PutTabsResult> {
  const resp = await apiFetch(tabsUrl(projectId, mothership), {
    signal,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.ok) return { status: "saved", snapshot: parseTabsSnapshot(await resp.json()) };
  if (resp.status === 409) {
    const raw: unknown = await resp.json();
    if (isObject(raw) && raw.reason === "version_stale") {
      return { status: "conflict", conflict: { reason: "version_stale", current: parseTabsSnapshot(raw.current) } };
    }
    if (isObject(raw) && raw.reason === "number_conflict" && typeof raw.tab_id === "string") {
      return {
        status: "conflict",
        conflict: {
          reason: "number_conflict",
          tab_id: raw.tab_id,
          detail: typeof raw.detail === "string" ? raw.detail : "",
          current: parseTabsSnapshot(raw.current),
        },
      };
    }
    throw new ApiError("PUT /projects/{id}/tabs: malformed 409", 409, JSON.stringify(raw));
  }
  if (resp.status === 422) {
    const raw: unknown = await resp.json();
    if (isObject(raw) && (raw.reason === "tab_origin_invalid" || raw.reason === "tab_tree_invalid")) {
      return {
        status: "invalid",
        invalid: {
          reason: raw.reason,
          tab_id: typeof raw.tab_id === "string" ? raw.tab_id : null,
          detail: typeof raw.detail === "string" ? raw.detail : "",
        },
      };
    }
    throw new ApiError("PUT /projects/{id}/tabs: malformed 422", 422, JSON.stringify(raw));
  }
  return fail("PUT /projects/{id}/tabs/{mothership}", resp);
}

/** The tab's public number: idempotent per tab_id, project-wide, never reused. */
export async function allocateTab(
  projectId: string,
  mothership: Mothership,
  tabId: string,
  signal?: AbortSignal,
): Promise<AllocateResponse> {
  const resp = await apiFetch(tabsUrl(projectId, mothership, "/allocate"), {
    signal,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tab_id: tabId }),
  });
  if (!resp.ok) return fail("POST /projects/{id}/tabs/{mothership}/allocate", resp);
  const raw: unknown = await resp.json();
  if (!isObject(raw) || !isCount(raw.public_number, 1)) {
    throw new ApiError("allocate: malformed response body", 0, JSON.stringify(raw));
  }
  return { public_number: raw.public_number };
}

/** Older unrestored retirements, newest first. */
export async function getRetired(
  projectId: string,
  mothership: Mothership,
  page: { before?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<RetiredPage> {
  const params = new URLSearchParams();
  if (page.before !== undefined) params.set("before", page.before);
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  const query = params.toString();
  const resp = await apiFetch(tabsUrl(projectId, mothership, `/retired${query ? `?${query}` : ""}`), { signal });
  if (!resp.ok) return fail("GET /projects/{id}/tabs/{mothership}/retired", resp);
  const raw: unknown = await resp.json();
  if (!isObject(raw) || !Array.isArray(raw.retired) || !raw.retired.every(isRetiredEntry) || !isNullableString(raw.next_before)) {
    throw new ApiError("retired: malformed response body", 0, JSON.stringify(raw));
  }
  return { retired: raw.retired, next_before: raw.next_before as string | null };
}
