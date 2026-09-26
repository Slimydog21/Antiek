/**
 * writeOutlineStore.ts — the Write outline pane's active block tab (C5).
 *
 * The pane owns its DATA (the deliverable's blocks, fetched per section);
 * this store holds only the tab interaction state — which block tab is
 * active and the flat order the prefix ,/. keys cycle through — so the
 * companion-cycling keys get one muscle memory ("right-pane tab cycling")
 * across the companion (research/reading) and the outline (writing).
 * Visibility mirrors the companion's rule: the keys act only when the pane
 * is on screen.
 */
import { create } from "zustand";

/** The docked-preset mount: the outline pane is this right-dock panel. */
export const WRITE_OUTLINE_PANEL_ID = "write-outline:main";

/** Is the outline pane on screen? Inset preset: visible whenever the route
 *  is writing-mothership (the mode switch mounts it). Docked preset: the
 *  "WriteOutline" panel is open. */
export function writeOutlineVisible(layoutPreset: string, panelOpen: boolean): boolean {
  return layoutPreset === "omarchy-inset" || panelOpen;
}

interface WriteOutlineState {
  /** The flat block order the keys cycle (section order, then block_index). */
  blockIds: string[];
  activeBlockId: string | null;
  setBlocks: (blockIds: string[]) => void;
  setActiveBlock: (id: string | null) => void;
  cycle: (direction: 1 | -1) => void;
  reset: () => void;
}

export const useWriteOutline = create<WriteOutlineState>()((set) => ({
  blockIds: [],
  activeBlockId: null,

  setBlocks: (blockIds) =>
    set((s) => ({
      blockIds,
      activeBlockId:
        s.activeBlockId && blockIds.includes(s.activeBlockId)
          ? s.activeBlockId
          : (blockIds[0] ?? null),
    })),

  setActiveBlock: (id) => set({ activeBlockId: id }),

  cycle: (direction) =>
    set((s) => {
      if (s.blockIds.length === 0) return s;
      const cur = s.activeBlockId ? s.blockIds.indexOf(s.activeBlockId) : -1;
      const next = (cur + direction + s.blockIds.length) % s.blockIds.length;
      return { activeBlockId: s.blockIds[next] };
    }),

  reset: () => set({ blockIds: [], activeBlockId: null }),
}));
