import { create } from "zustand";

import type { Workflow } from "./workflowTaxonomy";

/**
 * activeWorkflow — which of the four workflows the shell is currently in.
 *
 * Functional rationale (SPR-03): the rail, content tree, and scene chrome all
 * need one answer to "which work are we doing?" The rail sets it on click; the
 * route derives it on navigation/refresh (see AppShell). Zones 2/3 read it.
 * It is a property of what the user is looking at, not a separate navigation
 * concept — so it is always recoverable from the URL.
 */
export type ActiveWorkflow = Exclude<Workflow, "shared">;

interface ActiveWorkflowStore {
  /** The workflow whose tree + scene are shown. Defaults to the home workflow. */
  active: ActiveWorkflow;
  set: (w: ActiveWorkflow) => void;
}

export const useActiveWorkflow = create<ActiveWorkflowStore>()((set) => ({
  active: "research",
  set: (w) => set({ active: w }),
}));
