/**
 * blockSources.ts — outline-block source-document assignments (C5).
 *
 * HONEST BRIDGE, stated up front: write_routes has NO block-source mutation
 * endpoint today (verified 2026-09-24: the only source_document_id in
 * write_routes is a /blocks/search FILTER, :353-359; there is no
 * deliverables PATCH at all). The assignment record therefore lives behind
 * a persistence CONTRACT, never a pretend-write:
 *
 *   TODO(lane B / write_routes): write-through to
 *   `deliverables.metadata` (the column exists) under a `block_sources`
 *   key via a PATCH endpoint. The BlockSourcesBackend interface below IS
 *   the contract — the HTTP backend swaps in through
 *   `setBlockSourcesBackend` and no caller changes. Until then the
 *   in-memory backend is the session-scoped stand-in (the tab adapter's
 *   honesty stance), and the UI labels assignments as session state.
 *
 * An assignment is operator STRUCTURE over the block (which source
 * documents ground it), refs only — document ids + the title the drag
 * carried, never document content.
 */
import { create } from "zustand";

export interface BlockSourceAssignment {
  document_id: string;
  /** The title the drag carried (null when unknown — the id is the honest
   *  label then, never a fabricated name). */
  document_title: string | null;
  assigned_at: string;
}

/** deliverable_id → outline_block_id → assignments, in assign order. */
export type BlockSourcesRecord = Record<string, BlockSourceAssignment[]>;

export interface BlockSourcesBackend {
  load: (deliverableId: string) => Promise<BlockSourcesRecord>;
  save: (deliverableId: string, record: BlockSourcesRecord) => Promise<void>;
}

/** The session-scoped stand-in (the §1.6 stance: an honest in-memory
 *  adapter until the write path lands). */
export function createInMemoryBlockSourcesBackend(): BlockSourcesBackend {
  const rows = new Map<string, BlockSourcesRecord>();
  return {
    async load(deliverableId) {
      return rows.get(deliverableId) ?? {};
    },
    async save(deliverableId, record) {
      rows.set(deliverableId, JSON.parse(JSON.stringify(record)) as BlockSourcesRecord);
    },
  };
}

interface BlockSourcesState {
  records: Record<string, BlockSourcesRecord>;
  backend: BlockSourcesBackend;
  setBlockSourcesBackend: (backend: BlockSourcesBackend) => void;
  ensureDeliverable: (deliverableId: string) => Promise<void>;
  /** Assign a source document to an outline block. Idempotent per
   *  (block, document) — re-dropping focuses the record, never duplicates. */
  assign: (deliverableId: string, outlineBlockId: string, source: { document_id: string; document_title: string | null }) => void;
  /** Remove one assignment (the operator's undo of a mis-drop). */
  unassign: (deliverableId: string, outlineBlockId: string, documentId: string) => void;
  /** Test seam. */
  reset: () => void;
}

export const useBlockSources = create<BlockSourcesState>()((set, get) => {
  function persist(deliverableId: string) {
    const record = get().records[deliverableId] ?? {};
    void get().backend.save(deliverableId, record);
  }

  return {
    records: {},
    backend: createInMemoryBlockSourcesBackend(),

    setBlockSourcesBackend: (backend) => set({ backend, records: {} }),

    ensureDeliverable: async (deliverableId) => {
      if (get().records[deliverableId]) return;
      const record = await get().backend.load(deliverableId);
      set((s) => ({ records: { ...s.records, [deliverableId]: record } }));
    },

    assign: (deliverableId, outlineBlockId, source) => {
      if (!source.document_id.trim()) return; // no identity, no assignment
      set((s) => {
        const forDeliverable = { ...(s.records[deliverableId] ?? {}) };
        const existing = forDeliverable[outlineBlockId] ?? [];
        if (existing.some((a) => a.document_id === source.document_id)) return s;
        forDeliverable[outlineBlockId] = [
          ...existing,
          {
            document_id: source.document_id,
            document_title: source.document_title,
            assigned_at: new Date().toISOString(),
          },
        ];
        return { records: { ...s.records, [deliverableId]: forDeliverable } };
      });
      persist(deliverableId);
    },

    unassign: (deliverableId, outlineBlockId, documentId) => {
      set((s) => {
        const forDeliverable = { ...(s.records[deliverableId] ?? {}) };
        const existing = forDeliverable[outlineBlockId] ?? [];
        const next = existing.filter((a) => a.document_id !== documentId);
        if (next.length === existing.length) return s;
        if (next.length === 0) delete forDeliverable[outlineBlockId];
        else forDeliverable[outlineBlockId] = next;
        return { records: { ...s.records, [deliverableId]: forDeliverable } };
      });
      persist(deliverableId);
    },

    reset: () => set({ records: {}, backend: createInMemoryBlockSourcesBackend() }),
  };
});
