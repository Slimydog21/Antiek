import { useEffect, useRef } from "react";
import { useLocation, useParams } from "react-router-dom";

import {
  applyOver,
  clearWsFromUrl,
  readScope,
  readWsFromUrl,
} from "./persistence";
import {
  disablePersistence,
  enablePersistence,
  setPersistScope,
  useWorkspace,
} from "./WorkspaceStore";
import { EMPTY_SNAPSHOT } from "./panel.types";

/**
 * Hydrate the workspace on every route + investigation change.
 *
 * Layering order (later wins on the slice it owns):
 *   1. EMPTY_SNAPSHOT
 *   2. global scope        (antiek.workspace.global)
 *   3. route scope         (antiek.workspace.route.<route-key>)
 *   4. investigation scope (antiek.workspace.inv.<id>)   if route has :investigationId
 *   5. URL ?ws=… param     (one-shot; cleared from the URL after applying)
 *
 * Writes happen on the OUTGOING scope so that switching routes carries
 * the operator's most recent layout for that route forward.
 *
 * Mount once at AppShell level; it owns the cross-route hydration cycle.
 */
function routeKey(pathname: string): string {
  // Collapse common dynamic params so all "/inv/<x>" routes share one
  // route-scoped layout, but the per-investigation scope can still
  // override specific ids.
  return pathname
    .replace(/\/inv\/[^/]+/, "/inv/:id")
    .replace(/\/wrestle\/[^/]+/, "/wrestle/:id")
    .replace(/\/notebook\/[^/]+/, "/notebook/:id")
    .replace(/\/backtest\/[^/]+/, "/backtest/:id")
    .replace(/\/outcomes\/[^/]+/, "/outcomes/:id")
    .replace(/\/replay\/[^/]+/, "/replay/:id")
    .replace(/\/interview\/[^/]+/, "/interview/:id")
    .replace(/\/skill-rules\/[^/]+/, "/skill-rules/:id")
    .replace(/\/create\/[^/]+/, "/create/:id");
}

export function useWorkspaceHydration() {
  const location = useLocation();
  const params = useParams<{ investigationId?: string }>();
  const investigationId = params.investigationId ?? null;
  const route = routeKey(location.pathname);
  const lastScope = useRef<string>("");

  useEffect(() => {
    // Disable persistence writes during hydration so we don't write
    // the partially-applied state to localStorage.
    disablePersistence();

    // S5 acceptance: pinned panels survive cross-route navigation.
    // Capture pinned panels from the prior scope BEFORE we overwrite.
    // Their descriptors carry forward into the new scope's snapshot
    // (with mode/zIndex preserved); the persistence subscriber writes
    // them back into the new scope on next tick.
    const priorState = useWorkspace.getState();
    const pinnedCarry = Object.values(priorState.panels).filter(
      (p) => p.pinned,
    );

    let next = { ...EMPTY_SNAPSHOT };

    // 1. global
    const global = readScope({ kind: "global" });
    if (global) next = applyOver(next, global);

    // 2. route
    const routeSnap = readScope({ kind: "route", route });
    if (routeSnap) next = applyOver(next, routeSnap);

    // 3. investigation (if applicable)
    if (investigationId) {
      const invSnap = readScope({ kind: "investigation", id: investigationId });
      if (invSnap) next = applyOver(next, invSnap);
    }

    // 4. URL one-shot
    const urlSnap = readWsFromUrl();
    if (urlSnap) {
      next = applyOver(next, urlSnap);
      clearWsFromUrl();
    }

    // 5. Pinned-carry: any pinned panel from the prior scope that
    // isn't already in `next.panels` rides along into the new scope.
    // Pinned panels with the same id in the new scope keep the new
    // scope's descriptor (operator's most recent positioning wins).
    for (const p of pinnedCarry) {
      if (!next.panels[p.id]) {
        next.panels[p.id] = p;
        if (p.mode === "docked-left") {
          if (!next.dockLeftIds.includes(p.id)) {
            next.dockLeftIds = [...next.dockLeftIds, p.id];
          }
        } else if (p.mode === "docked-right") {
          if (!next.dockRightIds.includes(p.id)) {
            next.dockRightIds = [...next.dockRightIds, p.id];
          }
        } else if (p.mode === "docked-bottom") {
          if (!next.dockBottomIds.includes(p.id)) {
            next.dockBottomIds = [...next.dockBottomIds, p.id];
          }
        } else if (p.mode === "floating") {
          if (!next.floatingIds.includes(p.id)) {
            next.floatingIds = [...next.floatingIds, p.id];
          }
          next.zCounter = Math.max(next.zCounter, p.zIndex);
        }
      }
    }

    // Apply everything in one set. Zoom is a transient focus mode — a
    // route/investigation change always exits it (never persisted).
    useWorkspace.setState({ ...next, zoomedPanelId: null });

    // Target the writes for THIS route + investigation
    setPersistScope(
      investigationId
        ? { kind: "investigation", id: investigationId }
        : { kind: "route", route },
    );

    const scopeKey = investigationId ? `inv:${investigationId}` : `route:${route}`;
    lastScope.current = scopeKey;

    enablePersistence();
  }, [route, investigationId]);
}
