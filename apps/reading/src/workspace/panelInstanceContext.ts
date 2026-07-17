import { createContext, useContext } from "react";

const PanelInstanceContext = createContext<string | null>(null);
const PanelMainViewHandoffContext = createContext<((path: string) => void) | null>(null);

/** Exact legacy workspace-panel host id, or null outside PanelLayoutPanel. */
export function usePanelInstanceId(): string | null {
  return useContext(PanelInstanceContext);
}

/** Popout-owned handoff, when navigation must target and clean up the main tab. */
export function usePanelMainViewHandoff(): ((path: string) => void) | null {
  return useContext(PanelMainViewHandoffContext);
}

export const PanelInstanceProvider = PanelInstanceContext.Provider;
export const PanelMainViewHandoffProvider = PanelMainViewHandoffContext.Provider;
