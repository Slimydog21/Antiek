import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation, useParams } from "react-router-dom";

import { useAuth } from "../lib/auth";
import { retireLegacyWorkspaceSnapshots } from "./persistence";
import { EMPTY_SNAPSHOT } from "./panel.types";
import type { PanelDescriptor, WorkspaceSnapshot } from "./panel.types";
import { useWorkspace } from "./WorkspaceStore";

function carryPinnedPanels(panels: PanelDescriptor[]): WorkspaceSnapshot {
  const next: WorkspaceSnapshot = { ...EMPTY_SNAPSHOT, panels: {} };
  for (const panel of panels) {
    next.panels[panel.id] = panel;
    if (panel.mode === "docked-left") next.dockLeftIds.push(panel.id);
    else if (panel.mode === "docked-right") next.dockRightIds.push(panel.id);
    else if (panel.mode === "docked-bottom") next.dockBottomIds.push(panel.id);
    else if (panel.mode === "floating") {
      next.floatingIds.push(panel.id);
      next.zCounter = Math.max(next.zCounter, panel.zIndex);
    }
  }
  return next;
}

/**
 * Retire legacy external state before effects can open route starters, then
 * reset panels on navigation while carrying only same-session pinned panels.
 */
export function useWorkspaceHydration(): void {
  const location = useLocation();
  const params = useParams<{ investigationId?: string }>();
  const { sessionGeneration } = useAuth();
  const previous = useRef<{ route: string; generation: number } | null>(null);
  const route = `${location.pathname}\u0000${params.investigationId ?? ""}`;

  // The boot entry point performs the pre-mount purge. This catches later SPA
  // navigations carrying `ws` without introducing a side effect during render.
  useEffect(retireLegacyWorkspaceSnapshots, [route]);

  useLayoutEffect(() => {
    const prior = previous.current;
    const accountChanged = prior !== null && prior.generation !== sessionGeneration;
    const pinned = prior === null || accountChanged
      ? []
      : Object.values(useWorkspace.getState().panels).filter((panel) => panel.pinned);
    useWorkspace.setState(carryPinnedPanels(pinned));
    previous.current = { route, generation: sessionGeneration };
  }, [route, sessionGeneration]);
}
