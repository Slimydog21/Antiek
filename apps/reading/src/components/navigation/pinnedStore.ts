import { create } from "zustand";

/**
 * Tiny store of the operator's pinned project-tree items.
 *
 * S4 keeps this purely in-memory — pinning survives a navigation but not a
 * page reload. S9 lands localStorage persistence (key
 * `antiek.workspace.global.pinned`).
 *
 * A "pin" is an opaque string id: `investigation:inv-abc-123`,
 * `document:doc-pdf-…`, `notebook:nb-…`. Membership-only; no ordering
 * (the ProjectTree renders pinned items above Recent above All).
 */
type PinnedState = {
  pinned: Set<string>;
  pin: (id: string) => void;
  unpin: (id: string) => void;
  toggle: (id: string) => void;
  isPinned: (id: string) => boolean;
  clear: () => void;
};

export const usePinned = create<PinnedState>((set, get) => ({
  pinned: new Set(),

  pin: (id) =>
    set((s) => {
      if (s.pinned.has(id)) return s;
      const next = new Set(s.pinned);
      next.add(id);
      return { pinned: next };
    }),

  unpin: (id) =>
    set((s) => {
      if (!s.pinned.has(id)) return s;
      const next = new Set(s.pinned);
      next.delete(id);
      return { pinned: next };
    }),

  toggle: (id) => {
    const has = get().pinned.has(id);
    if (has) get().unpin(id);
    else get().pin(id);
  },

  isPinned: (id) => get().pinned.has(id),

  clear: () => set({ pinned: new Set() }),
}));
