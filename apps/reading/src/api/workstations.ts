/**
 * workstations.ts — the workstation + tab-tree API client
 * (workstation-tabs SPR-01).
 *
 * The CONTAINER's persistence stands as specced (the reconciliation note,
 * PR #3431); the CHROME is the corpus's (D2 keymap, D6 tabTree, the cockpit
 * panels). This module ships the API + the wire TYPES ONLY — the corpus's
 * tabTreeStore/workstationStore wire it up; this PR does NOT reimplement
 * their client stores.
 *
 * The wire types mirror the corpus tabTree's snapshot shape
 * (tabTree.ts:748-773 — {tree, active_tab_id, retired_numbers} + the
 * server's version); the adapter contract (load / save(expected_version)
 * / allocate) maps onto the routes directly.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

// ── The container types ─────────────────────────────────────────────────

export interface WorkstationTab {
  tab_id: string;
  surface_kind: string;
  /** Refs-only: ids and small locators, never content (422 server-side). */
  surface_payload: Record<string, unknown>;
}

export interface Workstation {
  workstation_id: string;
  name: string;
  color_token: string;
  position: number;
  revision: number;
  tabs: WorkstationTab[];
}

// ── The corpus wire shape (tabTree.ts — mirrored, never imported: the
// corpus's stack owns the model; the wire shape is the contract) ─────────

export interface WireTabNode {
  tab_id: string;
  hier_number: string;
  child_order: string[];
  branch_origin?: { kind: string; [k: string]: unknown } | null;
  public_number: number | null;
  [k: string]: unknown;
}

export interface WireTabTree {
  mothership: string;
  nodes: Record<string, WireTabNode>;
  root_order: string[];
  history: Record<string, { node: WireTabNode; [k: string]: unknown }>;
  next_root_index: number;
  next_child_index: Record<string, number>;
}

export interface RetiredNumber {
  tab_id: string;
  hier_number: string;
  public_number: number;
}

/** The corpus's TabTreeSnapshot on the wire (the adapter's load shape). */
export interface TabTreeSnapshotWire {
  tree: WireTabTree;
  active_tab_id: string | null;
  retired_numbers: RetiredNumber[];
  version: number;
}

export interface TabTreeEnvelope {
  workstation_id: string;
  /** Empty ({}) at version 0 — no tree yet, honestly absent. */
  snapshot: TabTreeSnapshotWire | Record<string, never>;
  version: number;
}

// ── The calls ───────────────────────────────────────────────────────────

async function throwIfNotOk(resp: Response, what: string): Promise<void> {
  if (!resp.ok) {
    throw new ApiError(
      `${what} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
}

export async function listWorkstations(): Promise<{
  workstations: Workstation[];
  count: number;
}> {
  const resp = await apiFetch(`${API_BASE}/workstations`);
  await throwIfNotOk(resp, "GET /workstations");
  return (await resp.json()) as { workstations: Workstation[]; count: number };
}

export async function createWorkstation(body: {
  name: string;
  color_token?: string;
}): Promise<Workstation> {
  const resp = await apiFetch(`${API_BASE}/workstations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await throwIfNotOk(resp, "POST /workstations");
  return (await resp.json()) as Workstation;
}

/** Full-replace with optimistic concurrency — a stale revision throws
 *  ApiError 409 (never a silent clobber; the client rebases). */
export async function replaceWorkstation(
  workstationId: string,
  body: {
    name: string;
    color_token?: string;
    tabs: { tab_id?: string; surface_kind: string; surface_payload: Record<string, unknown> }[];
    revision: number;
  },
): Promise<Workstation> {
  const resp = await apiFetch(
    `${API_BASE}/workstations/${encodeURIComponent(workstationId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  await throwIfNotOk(resp, "PUT /workstations/{id}");
  return (await resp.json()) as Workstation;
}

export async function deleteWorkstation(workstationId: string): Promise<void> {
  const resp = await apiFetch(
    `${API_BASE}/workstations/${encodeURIComponent(workstationId)}`,
    { method: "DELETE" },
  );
  await throwIfNotOk(resp, "DELETE /workstations/{id}");
}

/** The TabTreeAdapter's load. */
export async function loadTabTree(workstationId: string): Promise<TabTreeEnvelope> {
  const resp = await apiFetch(
    `${API_BASE}/workstations/${encodeURIComponent(workstationId)}/tab-tree`,
  );
  await throwIfNotOk(resp, "GET /workstations/{id}/tab-tree");
  return (await resp.json()) as TabTreeEnvelope;
}

/** The TabTreeAdapter's save — snapshot.version is the expected_version;
 *  409 on conflict (the client rebases); a snapshot failing the model's
 *  invariants is a 422. */
export async function saveTabTree(
  workstationId: string,
  snapshot: TabTreeSnapshotWire,
): Promise<TabTreeEnvelope> {
  const resp = await apiFetch(
    `${API_BASE}/workstations/${encodeURIComponent(workstationId)}/tab-tree`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot, expected_version: snapshot.version }),
    },
  );
  await throwIfNotOk(resp, "PUT /workstations/{id}/tab-tree");
  return (await resp.json()) as TabTreeEnvelope;
}

/** The TabTreeAdapter's allocate — server-allocated, monotonic, never
 *  reused. */
export async function allocatePublicNumber(
  workstationId: string,
): Promise<{ public_number: number }> {
  const resp = await apiFetch(
    `${API_BASE}/workstations/${encodeURIComponent(workstationId)}/tab-tree/allocate`,
    { method: "POST" },
  );
  await throwIfNotOk(resp, "POST /workstations/{id}/tab-tree/allocate");
  return (await resp.json()) as { public_number: number };
}
