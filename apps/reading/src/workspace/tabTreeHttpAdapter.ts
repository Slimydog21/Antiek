/**
 * tabTreeHttpAdapter.ts — the model's TabTreeAdapter over lane B's routes
 * (THREAD-CONTRACT §1.6; wire module src/lib/api/projectTabs.ts, LB-2).
 *
 * The wire module holds no state and does no retry or rebase; this adapter
 * maps between the model's snapshot and the wire (tabTreeWire.ts) and keeps
 * the one piece of state the rev 8.8 restore rule needs. The store owns the
 * retry and rebase loop (tabTreeStore.ts), the same one the in-memory
 * stand-in drives, so swapping adapters changes no caller.
 *
 *  - `load`: GET, `retired[]` becomes the model's history.
 *  - `save`: PUT `{tree, active, expected_version}`; answers `saved` with the
 *    SERVER's snapshot (version, filled-in numbers and retired rows come from
 *    it), `conflict` for both 409 reasons, or `invalid` for a 422 (a lane-A
 *    bug the store logs). Transport failures throw, as the wire module does.
 *  - `allocate`: POST …/allocate {tab_id}; idempotent per tab_id server-side.
 *  - `retired`: GET …/retired?before=, for history older than the 200 the
 *    GET carries.
 *
 * rev 8.8: a restore PUTs the retired node back unchanged, `pruned_at`
 * included, and this adapter never strips it there. It also never sends
 * `pruned_at` on a tab it is not restoring: a tab the server's last answer
 * holds open, or one it holds no unrestored retirement for, has the field
 * dropped and the lane-A bug logged (the server would refuse the whole PUT
 * with `422 tab_tree_invalid`).
 */
import {
  allocateTab,
  getRetired,
  getTabs,
  putTabs,
  type Mothership,
  type PutTabsRequest,
  type TabsSnapshot,
} from "../lib/api/projectTabs";
import {
  fromSnapshot,
  toSnapshot,
  type ClosedTab,
  type SaveResult,
  type TabNode,
  type TabTree,
  type TabTreeAdapter,
  type TabTreeSnapshot,
} from "./tabTree";
import { fromWire, historyFromRetired, toWire } from "./tabTreeWire";

export interface HttpTabTreeAdapterOptions {
  /** The title the surface holds for a node now (null = keep the node's). */
  titleOf?: (node: TabNode) => string | null;
}

/** What the server last told us about one row, for the rev 8.8 rule. */
interface RowMemory {
  open: Set<string>;
  retired: Set<string>;
}

const LOG_PREFIX = "[antiek/tabs]";

export function createHttpTabTreeAdapter(opts: HttpTabTreeAdapterOptions = {}): TabTreeAdapter {
  const memory = new Map<string, RowMemory>();
  const rowKey = (projectId: string, mothership: Mothership) => `${projectId}\u0000${mothership}`;

  function remember(projectId: string, mothership: Mothership, snapshot: TabsSnapshot): void {
    const row: RowMemory = { open: new Set(Object.keys(snapshot.tree.nodes)), retired: new Set() };
    const older = memory.get(rowKey(projectId, mothership))?.retired ?? new Set<string>();
    // Rows fetched from older pages stay known until the tab reopens.
    for (const id of older) if (!row.open.has(id)) row.retired.add(id);
    for (const entry of snapshot.retired) if (!row.open.has(entry.node.tab_id)) row.retired.add(entry.node.tab_id);
    memory.set(rowKey(projectId, mothership), row);
  }

  /** The server's snapshot in the model's terms. The close ids of retirements
   *  the client made are carried over from the tree it sent, so an undo
   *  token taken before the write still names its close. */
  function adopt(snapshot: TabsSnapshot, mothership: Mothership, sent: TabTree | null): TabTreeSnapshot {
    const tree = fromWire(snapshot, mothership);
    if (!sent) return toSnapshot(tree);
    const history: Record<string, ClosedTab> = {};
    for (const id of Object.keys(tree.history)) {
      history[id] = Object.hasOwn(sent.history, id) ? { ...tree.history[id], close_id: sent.history[id].close_id } : tree.history[id];
    }
    return toSnapshot({ ...tree, history });
  }

  /** rev 8.8: keep `pruned_at` only on a tab being restored. */
  function guardPrunedAt(body: PutTabsRequest, row: RowMemory | undefined): void {
    if (!row) return; // nothing known yet: send the tree as the model holds it
    for (const id of Object.keys(body.tree.nodes)) {
      const node = body.tree.nodes[id];
      if (node.pruned_at == null) continue;
      if (row.open.has(id) || !row.retired.has(id)) {
        // eslint-disable-next-line no-console
        console.error(`${LOG_PREFIX} pruned_at on ${id}, which is not being restored (a lane-A bug); not sent`);
        delete node.pruned_at;
      }
    }
  }

  return {
    async load(projectId, mothership, signal) {
      const snapshot = await getTabs(projectId, mothership, signal);
      signal?.throwIfAborted();
      remember(projectId, mothership, snapshot);
      return adopt(snapshot, mothership, null);
    },

    async save(projectId, mothership, snapshot, signal): Promise<SaveResult> {
      const parsed = fromSnapshot(snapshot);
      if (!parsed.ok) {
        return { status: "invalid", reason: "tab_tree_invalid", tab_id: null, detail: `not sent: ${parsed.error.message}` };
      }
      const sent = parsed.tree;
      const body = toWire(sent, { titleOf: opts.titleOf });
      guardPrunedAt(body, memory.get(rowKey(projectId, mothership)));
      const result = await putTabs(projectId, mothership, body, signal);
      signal?.throwIfAborted();
      if (result.status === "saved") {
        remember(projectId, mothership, result.snapshot);
        return { status: "saved", snapshot: adopt(result.snapshot, mothership, sent) };
      }
      if (result.status === "conflict") {
        const { conflict } = result;
        remember(projectId, mothership, conflict.current);
        const current = adopt(conflict.current, mothership, sent);
        if (conflict.reason === "number_conflict") {
          return { status: "conflict", reason: "number_conflict", tab_id: conflict.tab_id, detail: conflict.detail, current };
        }
        return { status: "conflict", reason: "version_stale", current };
      }
      return { status: "invalid", ...result.invalid };
    },

    async allocate(projectId, mothership, tabId, signal) {
      return allocateTab(projectId, mothership, tabId, signal);
    },

    async retired(projectId, mothership, before, signal) {
      const page = await getRetired(projectId, mothership, before === null ? {} : { before }, signal);
      signal?.throwIfAborted();
      const row = memory.get(rowKey(projectId, mothership));
      const history = historyFromRetired(page.retired, {});
      const entries: ClosedTab[] = page.retired
        .map((r) => history[r.node.tab_id])
        .filter((e, i, all): e is ClosedTab => e !== undefined && all.indexOf(e) === i);
      if (row) for (const e of entries) if (!row.open.has(e.node.tab_id)) row.retired.add(e.node.tab_id);
      return { entries, next_before: page.next_before };
    },
  };
}
