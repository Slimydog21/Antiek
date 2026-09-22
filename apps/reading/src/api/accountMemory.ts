// Typed client for the owner-private account-memory surface
// (interfaces/research/api/account_memory_routes.py, prefix /account/memory).
//
// The two route shapes are AccountMemoryListResponse (GET) and
// AccountMemoryWriteResponse (POST); the interfaces below mirror them field
// for field. Every call goes through `apiFetch`, which carries the Antiek
// session cookie cross-origin — a bare `fetch` here would 401 in production
// and resolve against the Pages origin instead of the API host.
//
// WHAT THE GET ROUTE ACTUALLY RETURNS. `get_account_memory` calls
// `recall_memory`, which calls `list_memory` with its default
// `include_invalidated=False`, so the response carries ONLY the currently
// valid head of each (subject, predicate) key. Superseded versions are
// retained forever in the graph (substrate/memory/store.py closes the prior
// edge with `valid_until` + `superseded_by` rather than deleting it) but there
// is no query parameter that exposes them. Verified against a running backend:
// after a correction, `GET /account/memory` returns one row, the new object.
//
// That is why `supersededLocally` exists. When a correction comes back as
// SUPERSEDE, the panel already holds the row that was just closed, and it
// stamps that row with the closure the substrate performed so the version
// stays on screen under its replacement instead of vanishing. `foldMemoryVersions`
// is deliberately agnostic about where a superseded row came from: the day the
// GET route grows an `include_invalidated` parameter, history arrives in the
// list and the fold needs no change.

import { apiFetch } from "../lib/api";

/** One memory row. Mirrors `AccountMemoryItem` in account_memory_routes.py. */
export interface AccountMemoryItem {
  memory_id: string;
  edge_id: string;
  subject: string;
  predicate: string;
  object: string;
  /** Free-form, but the server-side validator refuses provenance with no
   *  source reference, and stamps `authority` itself. Rendered, never hidden. */
  provenance: Record<string, unknown>;
  valid_from: string;
  valid_to: string | null;
  superseded_by: string | null;
}

/** GET /account/memory. */
export interface AccountMemoryListResponse {
  items: AccountMemoryItem[];
}

/** The reconciler's verdict — substrate/memory/router.py:route_memory_update. */
export type AccountMemoryAction = "ADD" | "UPDATE" | "SUPERSEDE" | "NOOP";

/** POST /account/memory. */
export interface AccountMemoryWriteResponse {
  action: AccountMemoryAction;
  item: AccountMemoryItem;
}

/** The POST body. `valid_from` must be later than the current version's and no
 *  more than five minutes in the future; both are server-enforced. */
export interface AccountMemoryWrite {
  subject: string;
  predicate: string;
  object: string;
  provenance: Record<string, unknown>;
  valid_from: string;
}

/** Route-level ceiling: `get_account_memory` rejects limit > 50 with a 422. */
export const ACCOUNT_MEMORY_MAX_LIMIT = 50;

/** Provenance key the server owns. A client that sends `authority_*` is
 *  rejected outright, so the panel's writes never carry one. */
const SERVER_OWNED_PROVENANCE_PREFIX = "authority_";

export class AccountMemoryError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AccountMemoryError";
  }
}

async function describeFailure(response: Response, verb: string): Promise<AccountMemoryError> {
  // The route deliberately returns opaque details (it must not echo private
  // values back), so there is rarely more than a short string to show.
  let detail = "";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // non-JSON body — the status alone is the message
  }
  const suffix = detail ? ` — ${detail}` : "";
  return new AccountMemoryError(`${verb} /account/memory: HTTP ${response.status}${suffix}`, response.status);
}

export async function fetchAccountMemory(
  options: { limit?: number; query?: string } = {},
): Promise<AccountMemoryListResponse> {
  const limit = Math.min(options.limit ?? ACCOUNT_MEMORY_MAX_LIMIT, ACCOUNT_MEMORY_MAX_LIMIT);
  const params = new URLSearchParams({ limit: String(limit) });
  if (options.query) params.set("q", options.query);
  const response = await apiFetch(`/account/memory?${params.toString()}`);
  if (!response.ok) throw await describeFailure(response, "GET");
  return (await response.json()) as AccountMemoryListResponse;
}

export async function writeAccountMemory(
  payload: AccountMemoryWrite,
): Promise<AccountMemoryWriteResponse> {
  const response = await apiFetch("/account/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await describeFailure(response, "POST");
  return (await response.json()) as AccountMemoryWriteResponse;
}

/** The identity of a memory KEY — one fact, however many versions it has had. */
export function memoryKey(item: Pick<AccountMemoryItem, "subject" | "predicate">): string {
  return `${item.subject}\u0000${item.predicate}`;
}

/** One fact: its current value, plus every earlier value we know about. */
export interface MemoryVersionGroup {
  key: string;
  subject: string;
  predicate: string;
  head: AccountMemoryItem;
  /** Newest first. Empty when this fact has never been corrected. */
  superseded: AccountMemoryItem[];
}

/** Parse a substrate timestamp as UTC.
 *
 * The routes serialise `datetime` values that were normalised to naive UTC
 * before storage, so they come back as "2026-09-20T10:00:00" with no offset.
 * ECMAScript reads an offset-less date-TIME form as LOCAL time, which would
 * shift every rendered timestamp by the viewer's zone and, worse, reorder
 * versions near a DST boundary. Appending "Z" when no offset is present is the
 * whole fix; a value that already carries one is left alone.
 */
export function parseSubstrateTimestamp(value: string): Date | null {
  if (!value) return null;
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const parsed = Date.parse(hasOffset ? value : `${value}Z`);
  return Number.isNaN(parsed) ? null : new Date(parsed);
}

function validFromMillis(item: AccountMemoryItem): number {
  return parseSubstrateTimestamp(item.valid_from)?.getTime() ?? 0;
}

/** Collapse a flat row list into one group per (subject, predicate).
 *
 * The head is the row the substrate still considers current (`valid_to` null);
 * every other row for the same key is an earlier version and is KEPT, newest
 * first, rather than dropped. Groups come back newest-head first so a fact the
 * owner just corrected sits at the top, with `key` breaking ties so the order
 * is total and a re-render never reshuffles equal rows.
 *
 * Rows are deduplicated by `edge_id`: a locally retained superseded row and the
 * same row arriving from a future history-aware GET must not render twice.
 */
export function foldMemoryVersions(items: readonly AccountMemoryItem[]): MemoryVersionGroup[] {
  const byEdge = new Map<string, AccountMemoryItem>();
  for (const item of items) {
    // Last write wins: a row re-read from the server supersedes the local copy.
    byEdge.set(item.edge_id, item);
  }

  const grouped = new Map<string, AccountMemoryItem[]>();
  for (const item of byEdge.values()) {
    const key = memoryKey(item);
    const bucket = grouped.get(key);
    if (bucket) bucket.push(item);
    else grouped.set(key, [item]);
  }

  const groups: MemoryVersionGroup[] = [];
  for (const [key, rows] of grouped) {
    const ordered = [...rows].sort((a, b) => {
      const delta = validFromMillis(b) - validFromMillis(a);
      return delta !== 0 ? delta : a.edge_id.localeCompare(b.edge_id);
    });
    // Prefer an open interval; fall back to the newest row so a key whose head
    // was closed by a writer we cannot see still renders something.
    const head = ordered.find((row) => row.valid_to === null) ?? ordered[0];
    groups.push({
      key,
      subject: head.subject,
      predicate: head.predicate,
      head,
      superseded: ordered.filter((row) => row.edge_id !== head.edge_id),
    });
  }

  groups.sort((a, b) => {
    const delta = validFromMillis(b.head) - validFromMillis(a.head);
    return delta !== 0 ? delta : a.key.localeCompare(b.key);
  });
  return groups;
}

/** Stamp the row a correction just closed with the closure the substrate made.
 *
 * `write_memory_item` sets the prior edge's `valid_until` to the replacement's
 * `valid_from` and its `superseded_by` to the replacement's `edge_id`. This
 * reproduces exactly that, so the retained row carries the same interval the
 * graph does rather than a guess. Returns the row unchanged when it is not in
 * fact the one that was replaced.
 */
export function supersededLocally(
  previousHead: AccountMemoryItem,
  replacement: AccountMemoryItem,
): AccountMemoryItem {
  if (memoryKey(previousHead) !== memoryKey(replacement)) return previousHead;
  if (previousHead.edge_id === replacement.edge_id) return previousHead;
  return {
    ...previousHead,
    valid_to: replacement.valid_from,
    superseded_by: replacement.edge_id,
  };
}

/** Render provenance as stable, readable `key=value` pairs.
 *
 * Sorted so the same provenance always reads the same way, and JSON-encoded for
 * non-strings so a nested object is shown rather than "[object Object]". This
 * is the string the panel puts on screen: provenance is the reason a fact is
 * allowed to exist here, so it is never collapsed away behind a toggle.
 */
export function formatProvenance(provenance: Record<string, unknown>): string {
  const entries = Object.entries(provenance ?? {});
  if (entries.length === 0) return "no provenance recorded";
  return entries
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

/** Build the POST body for a correction to an existing fact.
 *
 * Provenance names this panel as the source and points at the memory being
 * corrected, which is what makes the new row traceable back to a human edit.
 * Server-owned `authority_*` keys are stripped rather than sent, because the
 * route rejects the whole write when it sees one.
 */
export function buildCorrection(
  head: AccountMemoryItem,
  nextObject: string,
  options: { now?: Date; note?: string } = {},
): AccountMemoryWrite {
  const provenance: Record<string, unknown> = {
    source: "account_memory_panel",
    corrects_memory_id: head.memory_id,
    corrects_edge_id: head.edge_id,
  };
  if (options.note && options.note.trim()) provenance.note = options.note.trim();
  for (const key of Object.keys(provenance)) {
    if (key.toLowerCase().startsWith(SERVER_OWNED_PROVENANCE_PREFIX)) delete provenance[key];
  }
  return {
    subject: head.subject,
    predicate: head.predicate,
    object: nextObject.trim(),
    provenance,
    valid_from: (options.now ?? new Date()).toISOString(),
  };
}
